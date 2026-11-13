"""Software-owned revenue collector definitions and ID-based catalog bindings.

Only bindings and validated link settings live in SQLite. Collector code and
capabilities are never created from user-entered links or theater names.
"""
import sqlite3

# The registry is the single source of truth for collector capabilities.
# Parsers stay independent so a new theater does not change the run engine.
REVENUE_ADAPTERS = {
    "青柠剧场": {
        "adapter_key": "qingning", "name": "青柠端原生",
        "source_url": "https://vd.xingvan.com/duangg.html", "query_mode": "html_post",
        "date_precision": "day", "supports_detail": True,
        "status": "ready", "notes": "按日查询；当前只保存账号日收益，保留明细解析与校验能力",
    },
    "顶好剧场": {
        "adapter_key": "dinghao", "name": "顶好端原生",
        "source_url": "https://zyusdk.banxiawl.com/IncomeInquiry?videoChannel=1&nativeChannel=1",
        "query_mode": "json_post",
        "date_precision": "day", "supports_detail": False,
        "empty_result_is_boundary": True,
        "status": "ready", "notes": "按日返回账号收益总额；原站查询成功且返回0.00表示无收益记录，首次连续7天无记录停止",
    },
    "青柠绿泡泡": {
        "adapter_key": "qingning_lpp", "name": "青柠绿泡泡",
        "aliases": ["青柠", "青柠剧场", "青柠绿泡泡", "青柠绿泡泡剧场"],
        "source_url": "https://vd.xingvan.com/lpp.html", "query_mode": "form_json_post",
        "date_precision": "day", "supports_detail": False,
        "empty_result_is_boundary": True,
        "status": "ready", "runtime_verified": True,
        "notes": "按日查询结算收益；剧目汇总只用于对账，不保存视频明细。已用提供的账号核验有收益及正常空数据",
    },
    "触摸剧场": {
        "adapter_key": "touch", "name": "触摸端原生/IAA",
        "aliases": ["触摸", "触摸剧场", "触摸端", "触摸端原生", "触摸端原生/IAA", "触摸IAA"],
        "source_url": "https://c3andggd.yichafen.com/qz/167SsX4Q2t",
        "query_mode": "public_page",
        "date_precision": "cumulative_unknown", "supports_detail": False,
        "supports_month_query": False, "cumulative_period": "unknown",
        "status": "ready", "notes": "仅实现当前累计查询，月份归属未确认；增量记入采集日，暂不能补查历史月份",
    },
    "平阅剧场": {
        "adapter_key": "pingyue", "name": "平阅端原生",
        "aliases": ["平阅", "平阅剧场", "平阅端", "平阅端原生"],
        "source_url": "http://yt.szmr.com/#/revenue/query/ac3HDs5JiB9rIXEz",
        "query_mode": "human_verified_session", "requires_extract_code": True,
        "empty_result_is_boundary": True,
        "date_precision": "day", "supports_detail": False,
        "status": "ready", "runtime_verified": False,
        "notes": "按日查询挂载收益；人工填写原站验证码后复用查询会话。同步中或缺少日明细不记零；完整真实查询待人工验证。",
    },
    "古言剧场": {
        "adapter_key": "guyan_native", "name": "古言端原生",
        "aliases": ["古言", "古言剧场", "古言端", "古言端原生", "古言星途", "古言星途剧场"],
        "source_url": "https://scnrzu35lckk.feishu.cn/share/base/query/shrcnmW22x9VpoIX5qKMILzfFne",
        "query_mode": "feishu_guest_form", "date_precision": "cumulative_unknown",
        "supports_detail": False, "supports_month_query": False, "cumulative_period": "2026-11",
        "status": "ready", "runtime_verified": True,
        "notes": "当前链接返回区间汇总；首次记采集日，后续只记累计增量，不均摊。工作日12点左右更新，节假日不更新；换月请在查单管理核对新期间，不支持指定日期或自动补查三个月。",
    },
    "花生剧场": {
        "adapter_key": "huasheng", "query_mode": "feishu_form",
        "date_precision": "cumulative_unknown", "supports_detail": False,
        "supports_month_query": False, "cumulative_period": "unknown",
        "status": "ready", "notes": "仅实现当前累计查询，月份归属未确认；增量记入采集日，暂不能补查历史月份",
    },
}


# One source has four independent business channels. Bind by stable ID, never
# infer a request type from the user-created theater name.
KUJIANG_TYPES = {
    "kujiang_iaa": ("酷匠-IAA", ["酷匠IAA", "酷匠-IAA"]),
    "kujiang_self": ("酷匠-自营", ["酷匠自营", "酷匠-自营"]),
    "kujiang_lpp": ("酷匠-绿泡泡", ["酷匠绿泡泡", "酷匠-绿泡泡"]),
    "kujiang_native": ("酷匠-端+漫剧", ["酷匠端", "酷匠端原生", "酷匠端+漫剧", "酷匠-端+漫剧"]),
}
for _id, (_name, _aliases) in KUJIANG_TYPES.items():
    REVENUE_ADAPTERS[_name] = {
        "adapter_key": _id, "name": _name, "query_theater": _name,
        "aliases": ["酷匠", "酷匠剧场", *_aliases],
        "source_url": "http://api.data.djff.asia/query/find.html",
        "query_mode": "kujiang_json", "date_precision": "day", "supports_detail": False,
        "empty_result_is_boundary": True, "status": "ready",
        "runtime_verified": _id == "kujiang_native",
        "notes": "按来源记录日期查询账号收益，四种业务独立选择；来源提示部分日期可能为区间收益，不拆分、不均摊。首次连续7天正常无记录停止，成功不重复。",
    }


# Zishi has four business channels; day/month links belong to one collector.
ZISHI_TYPES = {
    "zishi_expert": ("子诗达人", "https://q7w8vltyes.feishu.cn/share/base/query/shrcnFOgvAl5rNR2Ucu9kvHFnDS", "https://q7w8vltyes.feishu.cn/share/base/query/shrcnlZGA3JKjEFLcD4rQIQeied"),
    "zishi_agency": ("子诗机构", "https://c3andggd.yichafen.com/qz/136FWXsWot", "https://c3andggd.yichafen.com/qz/154I6XsWbt"),
    # Actual source headings are the reverse of the supplied link captions.
    "zishi_expert_iaa": ("子诗达人IAA", "https://s6w549ed.yichafen.com/qz/M1r0syY2Et", "https://s6w549ed.yichafen.com/qz/D6t2LyY2at"),
    "zishi_lpp": ("子诗绿泡泡", "https://q7w8vltyes.feishu.cn/share/base/query/shrcnt3OcOlkPtUqs46COXv0cnb", ""),
}
for _id, (_name, _url, _daily_url) in ZISHI_TYPES.items():
    REVENUE_ADAPTERS[_name] = {
        "adapter_key": _id, "name": _name, "aliases": ["子诗", "子诗剧场", _name, _name + "剧场"],
        "source_url": _url, "daily_url": _daily_url,
        "previous_month_url": "https://c3andggd.yichafen.com/qz/137dhyLFbt" if _id == "zishi_agency" else "",
        "query_mode": "zishi_month_day_check", "date_precision": "cumulative_unknown",
        "cumulative_period": "auto", "supports_detail": False, "supports_month_query": False,
        "status": "ready", "runtime_verified": _id == "zishi_agency",
        "notes": "按结果字段识别月份和实际日期；月累计增量归采集日，昨日仅交叉核对、不重复相加。来源延迟显示实际日期；无匹配或校验失败保留待重试；仅补已有专用链接的历史月份。" + ("IAA原链接表的昨日/本月标注与页面标题相反，已按页面实际含义配置。" if _id == "zishi_expert_iaa" else ""),
    }


def definition(collector_id):
    for theater_name, spec in REVENUE_ADAPTERS.items():
        if spec['adapter_key'] != collector_id:
            continue
        stem = theater_name.replace('剧场', '')
        return dict(spec, id=collector_id,
                    name=spec.get('name', stem + '收益采集器'),
                    runtime_verified=spec.get('runtime_verified', False),
                    aliases=spec.get('aliases', [theater_name, stem, stem + '端', stem + '端原生']))
    return None


def definitions():
    return [definition(spec['adapter_key']) for spec in REVENUE_ADAPTERS.values()]


def initialize(conn):
    from server.revenue_query_settings import initialize as initialize_query_settings
    initialize_query_settings(conn)
    conn.execute("""CREATE TABLE IF NOT EXISTS v3_theater_revenue_collector_settings (
        theater_id TEXT PRIMARY KEY REFERENCES theaters(id) ON DELETE CASCADE)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS v3_theater_revenue_collectors (
        theater_id TEXT NOT NULL REFERENCES theaters(id) ON DELETE CASCADE,
        collector_id TEXT NOT NULL,
        PRIMARY KEY(theater_id,collector_id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS v3_account_revenue_collectors (
        account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
        theater_id TEXT NOT NULL,
        collector_id TEXT NOT NULL,
        FOREIGN KEY(theater_id,collector_id)
          REFERENCES v3_theater_revenue_collectors(theater_id,collector_id) ON DELETE CASCADE)""")


def theater_ids(conn,theater_id):
    return [row[0] for row in conn.execute('SELECT collector_id FROM v3_theater_revenue_collectors WHERE theater_id=? ORDER BY collector_id',(theater_id,))]


def set_theater(conn,theater_id,values):
    if not isinstance(values,list) or any(not isinstance(v,str) or not definition(v) for v in values):
        raise ValueError('请选择软件中已有的收益采集器')
    values=list(dict.fromkeys(values))
    conn.execute("INSERT OR IGNORE INTO v3_theater_revenue_collector_settings VALUES(?)", (theater_id,))
    old=set(theater_ids(conn,theater_id))
    for collector_id in old-set(values):
        # Account selections become unconfigured; financial history stays intact.
        conn.execute('DELETE FROM v3_account_revenue_collectors WHERE theater_id=? AND collector_id=?',(theater_id,collector_id))
        conn.execute('DELETE FROM v3_theater_revenue_collectors WHERE theater_id=? AND collector_id=?',(theater_id,collector_id))
    for collector_id in values:
        conn.execute('INSERT OR IGNORE INTO v3_theater_revenue_collectors VALUES(?,?)',(theater_id,collector_id))


def account_id(conn,account_id,theater_id):
    row=conn.execute("""SELECT c.collector_id FROM v3_account_revenue_collectors c
        JOIN v3_theater_revenue_collectors t ON t.theater_id=c.theater_id AND t.collector_id=c.collector_id
        WHERE c.account_id=? AND c.theater_id=?""",(account_id,theater_id)).fetchone()
    return row[0] if row else ''


def set_account(conn,account_id,theater_id,value):
    if not isinstance(value,str):
        raise ValueError('收益采集器选择不正确')
    if value and (not definition(value) or value not in theater_ids(conn,theater_id)):
        raise ValueError('该采集器未关联到当前剧场，请先在剧场管理中配置')
    conn.execute('DELETE FROM v3_account_revenue_collectors WHERE account_id=?',(account_id,))
    if value:
        conn.execute('INSERT INTO v3_account_revenue_collectors VALUES(?,?,?)',(account_id,theater_id,value))


def theater_record(conn,item):
    confirmed = conn.execute('SELECT 1 FROM v3_theater_revenue_collector_settings WHERE theater_id=?', (item['id'],)).fetchone() is not None
    return dict(item,revenue_collector_ids=theater_ids(conn,item['id']),revenue_collectors_confirmed=confirmed)


def account_record(conn,item):
    return dict(item,revenue_collector_id=account_id(conn,item['id'],item['theater_id']))
