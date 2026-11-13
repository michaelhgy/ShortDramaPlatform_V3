"""Safe account metric mapping shared by collection and the runtime dashboard."""
from server.operations_collection import number

def build_account_core(stats: dict) -> dict:
    total = stats.get("total") or {}
    daily = []
    for row in stats.get("daily") or []:
        if not isinstance(row, dict) or not row.get("date"):
            continue
        daily.append({
            "date": row["date"], "views": number(row.get("view")),
            "followerTotal": number(row.get("fansTotal")),
            "thumbsUp": number(row.get("favorite")),
            "shares": number(row.get("forward")),
            "followsAdded": number(row.get("fansAdd")),
            "followsNet": number(row.get("fansNet")),
            "followsReduced": number(row.get("fansReduce")),
            "hearts": number(row.get("like")),
            "comments": number(row.get("comment")),
        })
    return {"videoTotal": number(total.get("postCount")),
            "followerTotal": number(total.get("fans")),
            "sourceUpdatedAt": total.get("updateTime"), "daily": daily}

