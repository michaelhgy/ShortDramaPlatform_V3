"""Editable query links for software-owned collectors; never stores financial data."""
from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import re
import secrets
from urllib.parse import urlsplit, parse_qs
from urllib.request import Request, build_opener, HTTPCookieProcessor, HTTPRedirectHandler
from http.cookiejar import CookieJar
from server import revenue_collectors as collectors

ACTIVE = ContextVar("revenue_query_configuration", default=None)
DEFAULT_HUASHENG = "https://scnrzu35lckk.feishu.cn/share/base/query/shrcnCXYADPz9wc4apC1pZ6Fvvb"


def initialize(conn):
    # Append-only configuration history. Collector implementation and bindings remain unchanged.
    conn.execute("""CREATE TABLE IF NOT EXISTS v3_revenue_query_revisions (
        collector_id TEXT NOT NULL, revision INTEGER NOT NULL, config_json TEXT NOT NULL,
        saved_at TEXT NOT NULL, PRIMARY KEY(collector_id,revision))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS v3_revenue_query_tests (
        token TEXT PRIMARY KEY, collector_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
        base_revision INTEGER NOT NULL, result_json TEXT NOT NULL, tested_at TEXT NOT NULL,
        expires_at TEXT NOT NULL, used INTEGER NOT NULL DEFAULT 0)""")


def now():
    return datetime.now(timezone.utc)


def default_config(collector_id):
    spec = collectors.definition(collector_id)
    if not spec:
        raise ValueError("采集器不存在；这里只能管理软件已适配的采集器")
    config = {"source_url": spec.get("source_url", DEFAULT_HUASHENG if collector_id == "huasheng" else ""),
            "enabled": True, "source_period": "" if spec["date_precision"] == "day" else spec.get("cumulative_period", "unknown"), "baseline_periods": []}
    if collector_id in collectors.ZISHI_TYPES:
        config.update(daily_url=spec["daily_url"], previous_month_url=spec["previous_month_url"])
    if collector_id == "pingyue":
        from server.pingyue_collector import DEFAULT_CODE
        config["extract_code"] = DEFAULT_CODE
    return config


def current(conn, collector_id):
    fallback = default_config(collector_id)
    row = conn.execute("SELECT revision,config_json,saved_at FROM v3_revenue_query_revisions WHERE collector_id=? ORDER BY revision DESC LIMIT 1", (collector_id,)).fetchone()
    return {**(json.loads(row[1]) if row else fallback), "revision": row[0] if row else 0,
            "saved_at": row[2] if row else ""}


def normalize(collector_id, payload, old=None):
    default = default_config(collector_id)
    if not isinstance(payload, dict) or not isinstance(payload.get("source_url"), str) or type(payload.get("enabled")) is not bool:
        raise ValueError("请填写查单链接和启用状态")
    url = payload["source_url"].strip()
    parts, known = urlsplit(url), urlsplit(default["source_url"])
    pingyue = collector_id == "pingyue"
    kujiang = collector_id in collectors.KUJIANG_TYPES
    zishi = collector_id in collectors.ZISHI_TYPES
    if (len(url) > 1500 or re.search(r"[\s\\\x00-\x1f]", url) or parts.scheme not in (("http", "https") if kujiang else (("http",) if pingyue else ("https",))) or
            parts.hostname != known.hostname or parts.port not in ((None, 80 if parts.scheme == "http" else 443) if (pingyue or kujiang) else (None, 443)) or
            parts.username is not None or parts.password is not None or (parts.fragment and not pingyue)):
        raise ValueError("只支持该采集器已适配来源的查单链接；更换网站需要重新适配，不能填写本机或其他网站地址")
    path = parts.path
    valid_path = {
        "pingyue": path in ("", "/") and not parts.query and bool(re.fullmatch(r"/revenue/query/[A-Za-z0-9_-]+", parts.fragment)),
        "touch": bool(re.fullmatch(r"/qz/[A-Za-z0-9]+/?", path)),
        "huasheng": bool(re.fullmatch(r"/share/base/query/shrcn[A-Za-z0-9]+", path)),
        "guyan_native": bool(re.fullmatch(r"/share/base/query/shrcn[A-Za-z0-9]+", path)) and not parts.query,
        "dinghao": path == "/IncomeInquiry" and parse_qs(parts.query).get("nativeChannel") == ["1"] and parse_qs(parts.query).get("videoChannel") == ["1"],
        "qingning_lpp": path == "/lpp.html",
        "qingning": bool(re.fullmatch(r"/[A-Za-z0-9_-]+\.html", path)) and path != "/lpp.html",
    }.get(collector_id, bool(re.fullmatch(r"/query/[A-Za-z0-9_-]+\.html", path)) if kujiang else False)
    if zishi:
        from server.zishi_collector import validate_source
        validate_source(url, known.hostname)
        valid_path = True
    if not valid_path:
        raise ValueError("链接不符合该采集器的已适配页面类型，请核对剧场及业务渠道")
    period = payload.get("source_period", default["source_period"])
    if not isinstance(period, str):
        raise ValueError("收益期间格式不正确")
    if zishi:
        if period != "auto":
            raise ValueError("子诗月份由实际结果自动识别，无需手填")
    elif default["source_period"] == "":
        if period != "":
            raise ValueError("按日采集器不需要设置累计期间")
    elif period != "unknown":
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period):
            raise ValueError("累计期间请填写 YYYY-MM，不能确认时保留 unknown")
        date.fromisoformat(period + "-01")
    old = old or default
    relation = payload.get("period_relation", "same")
    if relation not in ("same", "new"):
        raise ValueError("请选择是否属于同一收益期间")
    baselines = list(old.get("baseline_periods", []))
    if period and relation == "new":
        if period == "unknown" or period == old["source_period"]:
            raise ValueError("切换新期间需要填写与当前不同的具体月份")
        baselines = []
    elif period != old["source_period"]:
        if old["source_period"] != "unknown" or period == "unknown":
            raise ValueError("不同月份必须选择新的收益期间，不能复用旧月份累计基线")
        baselines = list(dict.fromkeys([old["source_period"], *baselines]))
    config = {"source_url": url, "enabled": payload["enabled"], "source_period": period, "baseline_periods": baselines}
    if zishi:
        from server.zishi_collector import validate_source
        for key in ("daily_url", "previous_month_url"):
            value = payload.get(key, old.get(key, default.get(key, "")))
            if not isinstance(value, str):
                raise ValueError("子诗查单链接格式不正确")
            value = value.strip()
            if key == "daily_url" and bool(default[key]) != bool(value):
                raise ValueError("该子诗业务必须保留对应的昨日查单链接")
            if key == "previous_month_url" and value and collector_id != "zishi_agency":
                raise ValueError("该业务尚未适配专用上月链接，不能混用机构来源")
            if value:
                if len(value) > 1500 or re.search(r"[\s\\\x00-\x1f]", value):
                    raise ValueError("子诗查单链接格式不正确")
                validate_source(value, known.hostname)
            config[key] = value
        links = [config[k] for k in ("source_url", "daily_url", "previous_month_url") if config[k]]
        if len(links) != len(set(links)):
            raise ValueError("月累计、昨日和上月不能填写同一链接")
    if pingyue:
        code = payload.get("extract_code", old.get("extract_code", ""))
        if not isinstance(code, str) or not re.fullmatch(r"[0-9]{6}", code.strip()):
            raise ValueError("平阅提取码需填写 6 位数字")
        config["extract_code"] = code.strip()
    return config


def fingerprint(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()


def inventory(conn):
    items = []
    for spec in collectors.definitions():
        config = current(conn, spec["id"])
        revisions = [{"revision": row[0], **json.loads(row[1]), "saved_at": row[2]} for row in conn.execute(
            "SELECT revision,config_json,saved_at FROM v3_revenue_query_revisions WHERE collector_id=? ORDER BY revision DESC LIMIT 20", (spec["id"],))]
        # Include built-in revision zero so the very first change can be restored too.
        revisions.append({"revision": 0, **default_config(spec["id"]), "saved_at": ""})
        latest = conn.execute("SELECT result_json,tested_at FROM v3_revenue_query_tests WHERE collector_id=? ORDER BY tested_at DESC LIMIT 1", (spec["id"],)).fetchone()
        items.append({**spec, **config, "default_url": default_config(spec["id"])["source_url"],
                      "history": revisions, "last_test": {**json.loads(latest[0]), "tested_at": latest[1]} if latest else None})
    return {"items": items}


def effective_spec(conn, spec):
    if not spec:
        return spec
    config = current(conn, spec["id"])
    return {**spec, "_query_settings": {**config, "collector_id": spec["id"]},
            **({"cumulative_period": config["source_period"], "_baseline_periods": config.get("baseline_periods", [])} if config["source_period"] else {})}


def source_url(collector_id, fallback):
    active = ACTIVE.get()
    return active["source_url"] if active and active["collector_id"] == collector_id else fallback


def validate_request(url):
    active = ACTIVE.get()
    if not active:
        return
    parts = urlsplit(url)
    allowed = {urlsplit(active["source_url"]).hostname}
    if active["collector_id"] in collectors.ZISHI_TYPES:
        allowed.update(urlsplit(active[key]).hostname for key in ("daily_url", "previous_month_url") if active.get(key))
    if active["collector_id"] == "dinghao":
        allowed.add("zyu.wozhangwan.com")
    kujiang = active["collector_id"] in collectors.KUJIANG_TYPES
    schemes = (urlsplit(active["source_url"]).scheme,) if kujiang else ("https",)
    port = 80 if parts.scheme == "http" else 443
    if (parts.scheme not in schemes or parts.hostname not in allowed or parts.port not in (None, port)
            or parts.username is not None or parts.password is not None):
        raise ValueError("查单请求超出当前采集器允许的来源，已阻止发送账号 ID")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("查单来源发生跳转，请核对新链接并重新测试；账号 ID 未随跳转发送")


class SafeOpener:
    def __init__(self):
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()), NoRedirect())

    def open(self, request, timeout=40):
        validate_request(request.full_url if isinstance(request, Request) else request)
        return self.opener.open(request, timeout=timeout)


def preview(conn, collector_id, payload):
    from server import v2_revenue_service as service
    old = current(conn, collector_id)
    config = normalize(collector_id, payload, old)
    channel = str(payload.get("channel_id", "")).strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,100}", channel):
        raise ValueError("请输入此查单来源对应的账号 ID")
    base = current(conn, collector_id)["revision"]
    if type(payload.get("revision")) is not int or payload["revision"] != base:
        raise ValueError("配置已被其他窗口修改，请刷新后重新测试")
    today = now().astimezone(timezone(timedelta(hours=8))).date()
    day = payload.get("query_date") or (today - timedelta(days=1)).isoformat()
    day = date.fromisoformat(day).isoformat()
    if day >= today.isoformat():
        raise ValueError("按日查询最多测试到昨天")
    spec = {**collectors.definition(collector_id), "_query_settings": {**config, "enabled": True, "collector_id": collector_id}}
    status, amount, message = "failed", None, ""
    observations = []
    try:
        if collector_id in ("dinghao", "qingning_lpp") or collector_id in collectors.KUJIANG_TYPES:
            # These query pages use a separate software-adapted API. Verify the
            # candidate page as well, rather than testing a dead link via a working API.
            token = ACTIVE.set({**config, "collector_id": collector_id})
            try:
                with SafeOpener().open(Request(config["source_url"], headers={"User-Agent": "ShortDramaOpsV3/1.0"})) as response:
                    page = response.read().decode("utf-8", errors="replace")
                valid = ("orderlookupquery" in page and "spfindid" in page) if collector_id == "qingning_lpp" else ("/static/js/app." in page and "<div id=\"app\"" in page.replace("'", '"'))
                if collector_id in collectors.KUJIANG_TYPES:
                    from server.kujiang_collector import validate_page
                    valid = validate_page(page, config["source_url"])
                if not valid:
                    raise ValueError("候选网页不再符合当前专用接口的页面结构，需要重新适配")
            finally:
                ACTIVE.reset(token)
        zishi = collector_id in collectors.ZISHI_TYPES
        status, amount, message, observations = service._fetch({"channel_id": channel}, collector_id,
            today.isoformat() if zishi else day, spec, today.isoformat()[:7] if zishi else config["source_period"])
        if zishi and status == "success" and config.get("previous_month_url"):
            previous_period = service._months(today.isoformat())[1]
            previous_status, _, previous_message, previous_observations = service._fetch({"channel_id": channel}, collector_id,
                today.isoformat(), spec, previous_period)
            observations += previous_observations
            message += "；上月试查：" + previous_message
            if previous_status != "success":
                status, amount = previous_status, None
        if status == "success" and (amount is None or not Decimal(str(amount)).is_finite() or Decimal(str(amount)) < 0):
            status, amount, message = "failed", None, "来源没有返回有效的收益金额"
    except Exception as exc:
        from server.pingyue_collector import VerificationRequired
        if isinstance(exc, VerificationRequired):
            return {"status": "verification_required", "passed": False, "amount": None,
                    "query_date": day, "source_period": config["source_period"], "source_url": config["source_url"],
                    "message": str(exc), "verification_id": exc.challenge_id, "test_token": "", "revision": base}
        status, amount, message = "failed", None, str(exc)
    passed = status == "success"
    result = {"status": status, "passed": passed, "amount": str(amount) if amount is not None else None,
              "query_date": day if not config["source_period"] else "",
              "source_period": config["source_period"], "source_url": config["source_url"],
              "message": message or ("已解析收益结果；仅供预览，未写入收益或改变采集进度" if passed else "未找到可核对的收益结果，不能据此启用新链接；请换有数据的账号或日期测试"),
              "candidate_fingerprint": fingerprint(config),
              **({"source_observations": observations} if collector_id in collectors.ZISHI_TYPES else {})}
    tested_at, token = now(), secrets.token_urlsafe(32)
    # Test evidence only: no financial writes, no account binding or initial-history changes.
    with conn:
        conn.execute("INSERT INTO v3_revenue_query_tests(token,collector_id,fingerprint,base_revision,result_json,tested_at,expires_at) VALUES(?,?,?,?,?,?,?)",
                     (token, collector_id, fingerprint(config), base, json.dumps(result, ensure_ascii=False), tested_at.isoformat(), (tested_at+timedelta(minutes=30)).isoformat()))
    return {**result, "test_token": token if passed else "", "revision": base}


def save(conn, collector_id, payload):
    if not isinstance(payload, dict) or type(payload.get("revision")) is not int:
        raise ValueError("缺少配置版本，请刷新后再试")
    # Lock only the short local update, never the external network request.
    conn.execute("BEGIN IMMEDIATE")
    try:
        old = current(conn, collector_id)
        config = normalize(collector_id, payload, old)
        if old["revision"] != payload["revision"]:
            raise ValueError("配置已被其他窗口修改，请刷新后重新测试")
        same_source = all(config.get(key) == old.get(key) for key in ("source_url", "source_period", "extract_code", "daily_url", "previous_month_url"))
        needs_test = not same_source or (config["enabled"] and not old["enabled"])
        if needs_test:
            tested = conn.execute("SELECT fingerprint,base_revision,result_json,expires_at,used FROM v3_revenue_query_tests WHERE token=? AND collector_id=?", (payload.get("test_token", ""), collector_id)).fetchone()
            if (not tested or tested[0] != fingerprint(config) or tested[1] != old["revision"] or
                    not json.loads(tested[2])["passed"] or tested[3] < now().isoformat() or tested[4]):
                raise ValueError("链接、提取码或期间改变后必须先测试通过，再确认生效；旧链接未被替换")
            conn.execute("UPDATE v3_revenue_query_tests SET used=1 WHERE token=?", (payload["test_token"],))
        conn.execute("INSERT INTO v3_revenue_query_revisions VALUES(?,?,?,?)", (collector_id, old["revision"]+1, json.dumps(config, ensure_ascii=False), now().isoformat()))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    if collector_id == "pingyue":
        from server.pingyue_collector import supersede
        supersede(old, config)
    return current(conn, collector_id)


def handle(handler, method, path, payload=None):
    from server.pingyue_collector import handle as handle_verification
    if handle_verification(handler, method, path, payload):
        return True
    if not path.startswith("/api/v3/revenue-query-settings"):
        return False
    from server.v2_file_service import connection
    from http import HTTPStatus
    conn = connection()
    try:
        if path == "/api/v3/revenue-query-settings" and method == "GET":
            result = inventory(conn)
        else:
            match = re.fullmatch(r"/api/v3/revenue-query-settings/([a-z_]+)(/test)?", path)
            if not match:
                handler._json(HTTPStatus.NOT_FOUND, {"error": "查单管理接口不存在"})
                return True
            if method == "POST" and match[2] == "/test":
                result = preview(conn, match[1], payload)
            elif method == "PATCH" and not match[2]:
                result = save(conn, match[1], payload)
            else:
                handler._json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "不支持此操作"})
                return True
        handler._json(HTTPStatus.OK, result)
    except (ValueError, RuntimeError, OSError) as exc:
        handler._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
    finally:
        conn.close()
    return True
