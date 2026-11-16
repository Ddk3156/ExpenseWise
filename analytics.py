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
    
# ---------- timeline + projection (Analytics page) ----------
def _linear_forecast(values, steps):
    """Least-squares straight line through `values`, extended `steps` points ahead (never below 0)."""
    n = len(values)
    if n == 0:
        return [0.0] * steps
    if n == 1:
        return [round(values[0], 2)] * steps
    mx, my = (n - 1) / 2, sum(values) / n
    slope = sum((x - mx) * (y - my) for x, y in enumerate(values)) / sum((x - mx) ** 2 for x in range(n))
    return [round(max(0.0, my + slope * (n + i - mx)), 2) for i in range(steps)]


def timeline(db, n=6, ahead=2):
    """Monthly totals per category for the last n months + a projection.
    PIPELINE: $match (date range) -> $group by (year-month, type, category).
    Completed months are 'actual'; the current month and `ahead` future months are projected."""
    month = date.today().strftime("%Y-%m")
    months = [add_months(month, -i) for i in range(n - 1, -1, -1)]
    future = [add_months(month, i) for i in range(1, ahead + 1)]
    rows = db.transactions.aggregate([
        {"$match": {"date": {"$gte": month_range(months[0])[0], "$lt": month_range(month)[1]}}},
        {"$group": {"_id": {"m": {"$dateToString": {"format": "%Y-%m", "date": "$date"}},
                            "t": "$type", "c": "$category"},
                    "total": {"$sum": "$amount"}}},
    ])
    by = {}  # (type, category or None for the total) -> {month: amount}
    for r in rows:
        m, t, c = r["_id"]["m"], r["_id"]["t"], r["_id"]["c"]
        for key in ((t, None), (t, c)):
            by.setdefault(key, {})
            by[key][m] = by[key].get(m, 0) + r["total"]

    # months before the very first transaction are "no data yet" (None), not zero - zeros would distort the trend
    has_data = {m for key in by for m in by[key]}
    first = next((i for i, m in enumerate(months[:-1]) if m in has_data), len(months) - 1)

    def make(key, name, group, default=False):
        actual = [round(by.get(key, {}).get(m, 0), 2) for m in months[first:-1]]   # completed months with data
        return {"name": name, "group": group, "default": default,
                "data": [None] * first + actual + _linear_forecast(actual, 1 + ahead)}

    cats = lambda t: sorted((k for k in by if k[0] == t and k[1]), key=lambda k: -sum(by[k].values()))
    series = [make(("expense", None), "Total expenses", "totals", True),
              make(("income", None), "Total income", "totals", True)]
    series += [make(k, k[1], "expense") for k in cats("expense")]
    series += [make(k, f"{k[1]} (income)", "income") for k in cats("income")]
    short = lambda m: f"{calendar.month_abbr[int(m[5:])]} {m[:4]}"
    return {"labels": [short(m) for m in months + future], "n_actual": n - 1, "series": series}


def pace(db):
    """Current month: spent so far and the full-month estimate at the same daily rate."""
    today = date.today()
    days = calendar.monthrange(today.year, today.month)[1]
    spent = totals(db, today.strftime("%Y-%m"))["expense"]
    return {"spent": spent, "projected": round(spent / today.day * days, 2), "day": today.day, "days": days}
