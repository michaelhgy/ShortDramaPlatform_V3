"""Pingyue's public query protocol, with human unlock and an in-process page session.

The website stores the unlocked extraction code in sessionStorage. This client keeps
that state and the cookie jar together; it NEVER queries before a successful unlock.
No browser dependency, CAPTCHA solver, financial writes or import endpoints here.
"""
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import base64
import json
import re
import secrets
import threading
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPCookieProcessor
from http.cookiejar import CookieJar
from server.revenue_query_settings import NoRedirect

ORIGIN = 'http://yt.szmr.com'
DEFAULT_URL = ORIGIN + '/#/revenue/query/ac3HDs5JiB9rIXEz'
DEFAULT_CODE = '987357'
REGISTRY_LOCK = threading.RLock()
SESSIONS = {}
MAX_SESSIONS = 64


class VerificationRequired(Exception):
    def __init__(self, challenge_id):
        self.challenge_id = challenge_id
        super().__init__('平阅等待人工填写验证码，验证后继续采集')


@dataclass
class QuerySession:
    source_url: str
    extract_code: str = field(repr=False)
    lock: object = field(default_factory=threading.RLock, repr=False)
    opener: object = field(default_factory=lambda: build_opener(HTTPCookieProcessor(CookieJar()), NoRedirect()), repr=False)
    verified: bool = False
    resolved: bool = False
    challenge_id: str = ''
    captcha_id: str = ''
    image: str = ''
    state: str = ''
    error: str = ''
    touched: float = field(default_factory=time.monotonic)

    @property
    def token(self):
        match = re.fullmatch(r'/revenue/query/([A-Za-z0-9_-]+)', urlsplit(self.source_url).fragment)
        if not match:
            raise ValueError('平阅查单链接格式不正确')
        return match[1]

    def request(self, endpoint, params=None, *, post=False, image=False):
        # Fixed origin and endpoint allow-list; never follow redirects carrying IDs/codes.
        if endpoint not in ('resolve', 'unlock', 'query', 'captcha'):
            raise ValueError('不支持的平阅查询操作')
        path = '/api/common/captcha' if image else '/api/RevenueQuery/' + endpoint
        url = ORIGIN + path
        body = json.dumps(params).encode() if post else None
        if not post:
            url += '?' + urlencode(params or {})
        request = Request(url, data=body, headers={
            'User-Agent': 'Mozilla/5.0 ShortDramaOpsV3', 'Referer': self.source_url,
            'Content-Type': 'application/json', 'Accept': 'image/*' if image else 'application/json',
        })
        try:
            with self.opener.open(request, timeout=30) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ValueError('平阅响应过大，请核对查单来源')
                if image:
                    kind = response.headers.get_content_type()
                    if kind not in ('image/png', 'image/jpeg', 'image/gif', 'image/webp'):
                        raise ValueError('平阅未返回有效的验证码图片，请刷新重试')
                    return 'data:' + kind + ';base64,' + base64.b64encode(raw).decode()
                value = json.loads(raw.decode('utf-8'))
                if not isinstance(value, dict) or 'code' not in value:
                    raise ValueError('平阅返回结构已变化，需要重新适配')
                return value
        except (OSError, json.JSONDecodeError, UnicodeError) as exc:
            # Do not echo URLs containing account IDs, extraction codes or captcha answers.
            raise ValueError('平阅请求未完成，请检查网络后重试') from None

    def resolve(self):
        if self.resolved:
            return
        response = self.request('resolve', {'token': self.token})
        if response.get('code') != 1:
            raise ValueError('平阅查单链接无效或已失效，请在查单管理中核对')
        self.resolved = True

    def refresh(self):
        self.captcha_id = secrets.token_hex(16)
        self.image = ''
        self.image = self.request('captcha', {'id': self.captcha_id, 'server': 1, '_': int(time.time()*1000)}, image=True)

    def challenge(self):
        self.verified = False
        if self.state != 'pending':
            self.challenge_id = secrets.token_urlsafe(24)
            self.state, self.error = 'pending', ''
        if not self.image:
            self.refresh()
        raise VerificationRequired(self.challenge_id)

    def query(self, channel, day):
        with self.lock:
            self.touched = time.monotonic()
            self.resolve()
            if not self.verified:
                self.challenge()
            result = self.request('query', {'token': self.token, 'extract_code': self.extract_code,
                'video_account_id': channel, 'start_date': day, 'end_date': day})
            if result.get('code') != 1:
                message = str(result.get('msg') or '')
                if re.search('验证码|captcha|提取码|验证失效|请先验证|未解锁', message, re.I):
                    self.state, self.image, self.error = '', '', ''
                    self.challenge()
                raise ValueError('平阅查询未成功，请稍后重试或在原网页核对')
            return parse_day(result.get('data'), day)

    def public(self):
        return {'id': self.challenge_id, 'collector_id': 'pingyue', 'collector_name': '平阅端原生',
                'source_url': self.source_url, 'state': self.state, 'image': self.image,
                'generation': self.captcha_id, 'message': self.error}


def parse_day(data, day):
    if not isinstance(data, dict) or not isinstance(data.get('list'), list) or not isinstance(data.get('summary'), dict):
        raise ValueError('平阅未返回完整的日收益结构，未入账')
    if data.get('syncing'):
        return 'pending', None, '来源正在同步收益，稍后再查'
    rows = data['list']
    if not rows:
        # The source does not prove that no row means a final zero. Do not invent one
        # or let seven missing rows falsely finish the first history scan.
        if data.get('syncing') is False and str(data['summary'].get('total_revenue')) in ('0', '0.00', '0.0'):
            return 'no_data', None, '平阅正常返回：该日无收益记录'
        return 'pending', None, '该日未返回收益明细，待来源更新或确认'
    if len(rows) != 1 or not isinstance(rows[0], dict) or rows[0].get('stat_date') != day:
        raise ValueError('平阅返回日期不匹配或有重复日数据，未入账')
    def money(value):
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValueError('平阅收益金额缺失或格式错误，未入账') from None
        if not amount.is_finite() or amount < 0 or amount != amount.quantize(Decimal('.01')):
            raise ValueError('平阅收益金额无效，未入账')
        return amount
    amount = money(rows[0].get('ad_revenue'))
    total = money(data['summary'].get('total_revenue'))
    if amount != total:
        raise ValueError('平阅当日明细与当日汇总不一致，未入账，请在原网页核对')
    return 'success', amount, ''


def get_session(config):
    url, code = config['source_url'], config.get('extract_code', DEFAULT_CODE)
    # Token or code changes create a different session; never reuse another link's unlock.
    parts = urlsplit(url)
    if parts.hostname != 'yt.szmr.com' or parts.port not in (None, 80) or parts.scheme != 'http' or parts.username or parts.password:
        raise ValueError('平阅查单来源不正确')
    key = (url, code)
    with REGISTRY_LOCK:
        if key not in SESSIONS:
            if len(SESSIONS) >= MAX_SESSIONS:
                idle = [(s.touched, k) for k, s in SESSIONS.items() if s.state != 'pending']
                if not idle:
                    raise ValueError('平阅会话过多，请先完成或稍后处理现有验证')
                del SESSIONS[min(idle)[1]]
            SESSIONS[key] = QuerySession(url, code)
        return SESSIONS[key]


def fetch_day(channel, day, config):
    return get_session(config).query(channel, day)


def find(challenge_id):
    with REGISTRY_LOCK:
        return next((s for s in SESSIONS.values() if s.challenge_id == challenge_id), None)


def challenge_state(challenge_id):
    session = find(challenge_id)
    # No waiting on the network lock; queue stop and UI polling must stay responsive.
    return session.state if session else 'expired'


def defer_waiting(challenge_id):
    session = find(challenge_id)
    if session and session.state == 'pending':
        with session.lock:
            if session.state == 'pending':
                session.state = 'deferred'


def supersede(old, new):
    if (old['source_url'], old.get('extract_code')) == (new['source_url'], new.get('extract_code')) and new['enabled']:
        return
    with REGISTRY_LOCK:
        session = SESSIONS.get((old['source_url'], old.get('extract_code')))
    if session:
        with session.lock:
            session.verified, session.state = False, 'superseded'
            session.image = ''


def handle(handler, method, path, payload):
    if not path.startswith('/api/v3/revenue-verification'):
        return False
    from http import HTTPStatus
    try:
        if path == '/api/v3/revenue-verification' and method == 'GET':
            with REGISTRY_LOCK:
                result = {'items': [s.public() for s in SESSIONS.values() if s.state == 'pending']}
        elif method == 'GET' and (match := re.fullmatch(r'/api/v3/revenue-verification/([A-Za-z0-9_-]+)', path)):
            session = find(match[1])
            result = {'state': session.state if session else 'expired'}
        else:
            match = re.fullmatch(r'/api/v3/revenue-verification/([A-Za-z0-9_-]+)/(submit|refresh|defer)', path)
            session = find(match[1]) if match else None
            if method != 'POST' or not session:
                handler._json(HTTPStatus.NOT_FOUND, {'error': '验证会话已失效，请重新试查或继续采集'})
                return True
            with session.lock:
                session.touched = time.monotonic()
                if session.state != 'pending':
                    raise ValueError('当前验证已处理，请刷新后重试')
                action = match[2]
                if action == 'defer':
                    session.state = 'deferred'
                    result = {'verified': False, 'deferred': True}
                elif action == 'refresh':
                    session.refresh()
                    result = session.public()
                else:
                    payload = payload or {}
                    answer = str(payload.get('answer', '')).strip()
                    if not re.fullmatch(r'[A-Za-z0-9]{1,12}', answer):
                        raise ValueError('请看图填写验证码')
                    if payload.get('generation') != session.captcha_id:
                        raise ValueError('验证码图片已刷新，请按当前图片重新填写')
                    response = session.request('unlock', {'token': session.token, 'extract_code': session.extract_code,
                        'captcha_id': session.captcha_id, 'captcha': answer}, post=True)
                    if response.get('code') == 1:
                        session.verified, session.state = True, 'ready'
                        session.image, session.error = '', ''
                        result = {'verified': True}
                    else:
                        session.error = '验证未通过，请重新填写；也请在采集器详情核对提取码'
                        session.refresh()
                        result = {**session.public(), 'verified': False}
        handler._json(HTTPStatus.OK, result)
    except (ValueError, OSError) as exc:
        handler._json(HTTPStatus.BAD_REQUEST, {'error': str(exc)})
    return True
