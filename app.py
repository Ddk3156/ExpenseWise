"""ExpenseWise - Personal Expense & Budget Management System.  Run:  python app.py"""
import os
import re
from datetime import date, datetime

from bson import ObjectId
from bson.errors import InvalidId
from flask import Flask, abort, flash, redirect, render_template, request, url_for
from pymongo.errors import DuplicateKeyError

import analytics
import gullak
from db import get_db

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-only-change-me")
app.register_blueprint(gullak.bp) 

# ---------------- helpers ----------------
@app.template_filter("inr")
def inr(value):
    """Format a number as Indian rupees, e.g. 1234567.5 -> ₹12,34,567.50"""
    v = float(value or 0)
    sign, v = ("-" if v < 0 else ""), abs(v)
    whole, dec = f"{v:.2f}".split(".")
    if len(whole) > 3:
        whole = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", whole[:-3]) + "," + whole[-3:]
    return f"{sign}₹{whole}" + ("" if dec == "00" else f".{dec}")

CAT_COLORS = {"Food": "#f59e0b", "Rent": "#6366f1", "Transportation": "#0ea5e9", "Shopping": "#ec4899",
              "Utilities": "#14b8a6", "Healthcare": "#ef4444", "Education": "#8b5cf6", "Entertainment": "#f97316",
              "Travel": "#10b981", "Other": "#64748b", "Salary": "#16a34a", "Freelancing": "#06b6d4",
              "Scholarship": "#84cc16", "Business": "#eab308"}
EXTRA_COLORS = ["#d946ef", "#0891b2", "#ca8a04", "#e11d48", "#7c3aed", "#059669", "#ea580c", "#2563eb"]


@app.template_filter("cat_color")
def cat_color(name):
    """Every category always gets the same colour (fixed for defaults, hashed for custom ones)."""
    return CAT_COLORS.get(name) or EXTRA_COLORS[sum(map(ord, name or "")) % len(EXTRA_COLORS)]


app.jinja_env.globals["shift_month"] = analytics.add_months   # used by the month arrows

def current_month():
    """Month from ?month=YYYY-MM (or the form), defaulting to this month."""
    m = request.values.get("month") or date.today().strftime("%Y-%m")
    return m if re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", m) else date.today().strftime("%Y-%m")


def to_oid(value):
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        abort(404)


@app.context_processor
def inject_globals():
    return {"month_label": analytics.month_label, "nav_month": request.values.get("month", "")}


def parse_transaction(form):
    """Validate form input and return a transaction document. Raises ValueError with a friendly message."""
    db = get_db()
    try:
        ttype, category = form.get("category", "").split(":", 1)
    except ValueError:
        raise ValueError("Please choose a category")
    if not db.categories.find_one({"type": ttype, "name": category}):
        raise ValueError("That category does not exist")
    try:
        amount = round(float(form.get("amount", "")), 2)
    except ValueError:
        raise ValueError("Amount must be a number")
    if not 0 < amount <= 1_000_000_000:
        raise ValueError("Amount must be greater than 0")
    try:
        when = datetime.strptime(form.get("date", ""), "%Y-%m-%d")
    except ValueError:
        raise ValueError("Please enter a valid date")
    description = form.get("description", "").strip()
    if len(description) > 200:
        raise ValueError("Description is too long (max 200 characters)")
    return {"type": ttype, "amount": amount, "category": category, "description": description, "date": when}


def render_tx_form(title, f, tx_id=None):
    cats = list(get_db().categories.find().sort([("type", 1), ("name", 1)]))
    return render_template("transaction_form.html", title=title, f=f, categories=cats, tx_id=tx_id)


# ---------------- dashboard ----------------
@app.get("/")
def dashboard():
    db, month = get_db(), current_month()
    budgets = analytics.budget_status(db, month)
    overall = next((b for b in budgets if b["category"] == analytics.OVERALL), None)
    return render_template(
        "dashboard.html", month=month,
        totals=analytics.totals(db, month), balance=analytics.totals(db)["savings"],
        remaining=overall["remaining"] if overall else None,
        categories=analytics.category_spend(db, month), budgets=budgets[:6],
        recent=list(db.transactions.find().sort("date", -1).limit(5)),
        trend=analytics.trend(db, month, 6))


# ---------------- transactions (CRUD) ----------------
@app.get("/transactions")
def transactions():
    db, month = get_db(), current_month()
    all_months = request.args.get("all") == "1"
    query = {}
    if not all_months:
        start, end = analytics.month_range(month)
        query["date"] = {"$gte": start, "$lt": end}
    if request.args.get("type") in ("income", "expense"):
        query["type"] = request.args["type"]
    if request.args.get("category"):
        query["category"] = request.args["category"]
    q = request.args.get("q", "").strip()
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [{"description": rx}, {"category": rx}]
    rows = list(db.transactions.find(query).sort("date", -1).limit(300))
    income = sum(r["amount"] for r in rows if r["type"] == "income")
    expense = sum(r["amount"] for r in rows if r["type"] == "expense")
    names = sorted(db.categories.distinct("name"))
    return render_template("transactions.html", rows=rows, month=month, all_months=all_months,
                           names=names, income=income, expense=expense, args=request.args)


@app.route("/transactions/new", methods=["GET", "POST"])
def tx_new():
    if request.method == "POST":
        try:
            doc = parse_transaction(request.form)
        except ValueError as e:
            flash(str(e), "error")
            return render_tx_form("Add transaction", request.form)
        doc["created_at"] = doc["updated_at"] = datetime.utcnow()
        get_db().transactions.insert_one(doc)
        flash("Transaction added.", "success")
        if doc["type"] == "expense":
            for msg in analytics.budget_alerts(get_db(), doc["category"], doc["date"]):
                flash(msg, "warning")
        return redirect(url_for("transactions", month=doc["date"].strftime("%Y-%m")))
    return render_tx_form("Add transaction", {"date": date.today().isoformat(), "category": "expense:Food"})


@app.route("/transactions/<tx_id>/edit", methods=["GET", "POST"])
def tx_edit(tx_id):
    db, oid = get_db(), to_oid(tx_id)
    tx = db.transactions.find_one({"_id": oid}) or abort(404)
    if request.method == "POST":
        try:
            doc = parse_transaction(request.form)
        except ValueError as e:
            flash(str(e), "error")
            return render_tx_form("Edit transaction", request.form, tx_id)
        doc["updated_at"] = datetime.utcnow()
        db.transactions.update_one({"_id": oid}, {"$set": doc})
        flash("Transaction updated.", "success")
        if doc["type"] == "expense":
            for msg in analytics.budget_alerts(db, doc["category"], doc["date"]):
                flash(msg, "warning")
        return redirect(url_for("transactions", month=doc["date"].strftime("%Y-%m")))
    form = {"category": f"{tx['type']}:{tx['category']}", "amount": tx["amount"],
            "description": tx.get("description", ""), "date": tx["date"].strftime("%Y-%m-%d")}
    return render_tx_form("Edit transaction", form, tx_id)


@app.post("/transactions/<tx_id>/delete")
def tx_delete(tx_id):
    get_db().transactions.delete_one({"_id": to_oid(tx_id)})
    flash("Transaction deleted.", "success")
    return redirect(request.referrer or url_for("transactions"))


# ---------------- categories ----------------
@app.get("/categories")
def categories():
    cats = list(get_db().categories.find().sort("name", 1))
    return render_template("categories.html",
                           expense=[c for c in cats if c["type"] == "expense"],
                           income=[c for c in cats if c["type"] == "income"])


@app.post("/categories")
def category_add():
    name, ctype = request.form.get("name", "").strip(), request.form.get("type")
    if not name or len(name) > 50 or ctype not in ("income", "expense") or name == analytics.OVERALL:
        flash("Enter a valid category name (max 50 characters).", "error")
    else:
        try:
            get_db().categories.insert_one({"name": name, "type": ctype, "is_default": False,
                                            "created_at": datetime.utcnow()})
            flash(f"Category '{name}' added.", "success")
        except DuplicateKeyError:  # the unique index on (type, name) rejects duplicates
            flash("That category already exists.", "error")
    return redirect(url_for("categories"))


@app.post("/categories/<cat_id>/delete")
def category_delete(cat_id):
    db = get_db()
    cat = db.categories.find_one({"_id": to_oid(cat_id)}) or abort(404)
    if cat.get("is_default"):
        flash("Default categories cannot be deleted.", "error")
    elif db.transactions.count_documents({"type": cat["type"], "category": cat["name"]}):
        flash("This category is used by transactions, so it cannot be deleted.", "error")
    else:
        db.categories.delete_one({"_id": cat["_id"]})
        flash("Category deleted.", "success")
    return redirect(url_for("categories"))


# ---------------- budgets ----------------
@app.get("/budgets")
def budgets():
    db, month = get_db(), current_month()
    expense_cats = sorted(c["name"] for c in db.categories.find({"type": "expense"}))
    return render_template("budgets.html", month=month, items=analytics.budget_status(db, month),
                           expense_cats=[analytics.OVERALL] + expense_cats)


@app.post("/budgets")
def budget_set():
    month, category = current_month(), request.form.get("category", "")
    try:
        amount = round(float(request.form.get("amount", "")), 2)
        if not 0 < amount <= 1_000_000_000:
            raise ValueError
    except ValueError:
        flash("Budget amount must be greater than 0.", "error")
        return redirect(url_for("budgets", month=month))
    # upsert: update this month's budget for the category if it exists, otherwise create it
    get_db().budgets.update_one(
        {"month": month, "category": category},
        {"$set": {"amount": amount, "updated_at": datetime.utcnow()},
         "$setOnInsert": {"created_at": datetime.utcnow()}},
        upsert=True)
    flash(f"{category} budget saved for {analytics.month_label(month)}.", "success")
    return redirect(url_for("budgets", month=month))


@app.post("/budgets/<b_id>/delete")
def budget_delete(b_id):
    get_db().budgets.delete_one({"_id": to_oid(b_id)})
    flash("Budget removed.", "success")
    return redirect(url_for("budgets", month=current_month()))


# ---------------- monthly report ----------------
@app.get("/report")
def report():
    month = current_month()
    return render_template("report.html", month=month, r=analytics.monthly_report(get_db(), month))

# ---------------- analytics: timeline + projection ----------------
@app.get("/analytics")
def analytics_page():
    n = 12 if request.args.get("months") == "12" else 6
    db = get_db()
    return render_template("analytics.html", n=n, data=analytics.timeline(db, n), pace=analytics.pace(db))

@app.errorhandler(404)
def not_found(_):
    return render_template("message.html", text="Page not found."), 404


@app.errorhandler(RuntimeError)
def config_error(e):
    return render_template("message.html", text=str(e)), 500


if __name__ == "__main__":
    get_db()  # connect now so problems show up immediately in the terminal
    print("Connected to MongoDB. Open http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
