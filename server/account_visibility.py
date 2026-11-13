"""Historical reads retain every account status. Live collection uses its own eligibility rules."""


def visible_account_sql(conn, *, account_id=None, uid=None, account_name=None):
    """Compatibility predicate for historical queries; status never removes saved facts."""
    return '1=1'


def cancelled_account_keys(conn):
    columns = {row[1] for row in conn.execute('PRAGMA table_info(accounts)')}
    if 'status' not in columns:
        return set(), set(), set()
    fields = [name if name in columns else "''" for name in ('id', 'channel_id', 'nickname')]
    rows = conn.execute("SELECT " + ','.join(fields) + " FROM accounts WHERE TRIM(COALESCE(status,''))='注销'").fetchall()
    return tuple({str(row[i]) for row in rows if row[i]} for i in range(3))


def hide_cancelled_rows(conn, rows):
    """Compatibility adapter: production/task history remains queryable after 注销."""
    return list(rows)
