"""All reporting logic. Each function is ONE MongoDB aggregation pipeline (plus tiny Python glue)."""
import calendar
from datetime import date, datetime

OVERALL = "Overall"  # category name used for the overall monthly budget


# ---------- small date helpers ----------
def month_range(month):
    """'2026-11' -> (datetime(2026,11,1), datetime(2026,12,1)). Used as [start, end) in queries."""
    y, m = map(int, month.split("-"))
    return datetime(y, m, 1), datetime(y + (m == 12), m % 12 + 1, 1)


def add_months(month, delta):
    y, m = map(int, month.split("-"))
    t = y * 12 + m - 1 + delta
    return f"{t // 12}-{t % 12 + 1:02d}"


def month_label(month):
    y, m = map(int, month.split("-"))
    return f"{calendar.month_name[m]} {y}"


# ---------- aggregation pipelines ----------
def totals(db, month=None):
    """Income, expense, savings and count. PIPELINE: $match (month) -> $group by type."""
    match = {}
    if month:
        start, end = month_range(month)
        match = {"date": {"$gte": start, "$lt": end}}
    rows = db.transactions.aggregate([
        {"$match": match},
        {"$group": {"_id": "$type", "total": {"$sum": "$amount"}, "count": {"$sum": 1}}},
    ])
    out = {"income": 0.0, "expense": 0.0, "count": 0}
    for r in rows:
        out[r["_id"]] = round(r["total"], 2)
        out["count"] += r["count"]
    out["savings"] = round(out["income"] - out["expense"], 2)
    return out


def category_spend(db, month, ttype="expense"):
    """Spending per category, biggest first.
    PIPELINE: $match (month + type) -> $group by category -> $sort desc."""
    start, end = month_range(month)
    rows = db.transactions.aggregate([
        {"$match": {"type": ttype, "date": {"$gte": start, "$lt": end}}},
        {"$group": {"_id": "$category", "total": {"$sum": "$amount"}, "count": {"$sum": 1}}},
        {"$sort": {"total": -1}},
    ])
    items = [{"category": r["_id"], "total": round(r["total"], 2), "count": r["count"]} for r in rows]
    grand = sum(i["total"] for i in items) or 1
    for i in items:
        i["share"] = round(i["total"] / grand * 100, 1)
    return items


def trend(db, month, n=6):
    """Income vs expense for the last n months.
    PIPELINE: $match (date range) -> $group by (year-month string, type) using $dateToString."""
    months = [add_months(month, -i) for i in range(n - 1, -1, -1)]
    start, end = month_range(months[0])[0], month_range(month)[1]
    rows = db.transactions.aggregate([
        {"$match": {"date": {"$gte": start, "$lt": end}}},
        {"$group": {"_id": {"m": {"$dateToString": {"format": "%Y-%m", "date": "$date"}}, "t": "$type"},
                    "total": {"$sum": "$amount"}}},
    ])
    look = {(r["_id"]["m"], r["_id"]["t"]): r["total"] for r in rows}
    result = []
    for m in months:
        inc, exp = round(look.get((m, "income"), 0), 2), round(look.get((m, "expense"), 0), 2)
        result.append({"month": m, "label": month_label(m), "income": inc, "expense": exp,
                       "savings": round(inc - exp, 2)})
    return result


def budget_status(db, month):
    """Budget vs actual for every budget set in that month (Python merges the two results)."""
    spend = {c["category"]: c["total"] for c in category_spend(db, month)}
    total_expense = sum(spend.values())
    items = []
    for b in db.budgets.find({"month": month}):
        spent = total_expense if b["category"] == OVERALL else spend.get(b["category"], 0)
        pct = round(spent / b["amount"] * 100, 1)
        items.append({"id": str(b["_id"]), "category": b["category"], "budget": b["amount"],
                      "spent": round(spent, 2), "remaining": round(b["amount"] - spent, 2), "pct": pct,
                      "status": "over" if spent > b["amount"] else ("warn" if pct >= 80 else "ok")})
    items.sort(key=lambda x: (x["category"] != OVERALL, -x["pct"]))  # Overall first, then most used
    return items


def budget_alerts(db, category, when):
    """After saving an expense: messages for any budget (category or overall) now exceeded."""
    msgs = []
    for b in budget_status(db, when.strftime("%Y-%m")):
        if b["category"] in (category, OVERALL) and b["status"] == "over":
            name = "overall monthly budget" if b["category"] == OVERALL else f"{b['category']} budget"
            msgs.append(f"Over your {name}: spent {b['spent']:.2f} of {b['budget']:.2f}")
    return msgs


def monthly_report(db, month):
    """Everything on the Report page."""
    t = totals(db, month)
    prev_month = add_months(month, -1)
    prev = totals(db, prev_month)
    spend = category_spend(db, month)
    change = round((t["expense"] - prev["expense"]) / prev["expense"] * 100, 1) if prev["expense"] else None
    start, end = month_range(month)
    biggest = db.transactions.find({"type": "expense", "date": {"$gte": start, "$lt": end}}) \
        .sort("amount", -1).limit(1)
    biggest = next(iter(biggest), None)
    y, m = map(int, month.split("-"))
    today = date.today()
    days = today.day if (today.year, today.month) == (y, m) else calendar.monthrange(y, m)[1]
    return {
        "month": month, "label": month_label(month), "totals": t, "previous": prev,
        "previous_label": month_label(prev_month), "expense_change_pct": change,
        "savings_rate": round(t["savings"] / t["income"] * 100, 1) if t["income"] else None,
        "avg_daily_spend": round(t["expense"] / days, 2) if days else 0,
        "category_spend": spend, "top3": spend[:3], "highest": spend[0] if spend else None,
        "income_by_category": category_spend(db, month, "income"),
        "biggest_expense": biggest, "trend": trend(db, month, 6),
    }
