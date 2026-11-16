"""Gullak - savings boxes. Put part of your available money aside for a goal (trip, phone, car...).
Two collections:  goals {name, icon, target}   and   gullak_entries {goal_id, kind, amount, ...}
A box's balance is never stored; it is calculated from its entries with an aggregation pipeline."""
from datetime import date, datetime

from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from pymongo.errors import DuplicateKeyError

import analytics
from db import get_db

bp = Blueprint("gullak", __name__, url_prefix="/gullak")
ICONS = ["🐷", "🏖️", "📱", "🚗", "🏠", "💻", "🎓", "💍", "📈", "🎁"]


def _oid(value):
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        abort(404)


def _number(raw, label):
    try:
        return float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number")


# ---------- calculations (used by the page AND the dashboard) ----------
def balances(db):
    """Saved amount per box.  PIPELINE: $group by goal; deposits add, withdrawals subtract."""
    rows = db.gullak_entries.aggregate([
        {"$group": {"_id": "$goal_id", "saved": {"$sum": {"$cond": [
            {"$eq": ["$kind", "deposit"]}, "$amount", {"$multiply": ["$amount", -1]}]}}}}])
    return {r["_id"]: round(r["saved"], 2) for r in rows}


def summary(db):
    """locked = money inside boxes;  available = all-time savings minus locked."""
    locked = round(sum(balances(db).values()), 2)
    return {"locked": locked, "available": round(analytics.totals(db)["savings"] - locked, 2)}


# ---------- pages ----------
@bp.get("/")
def index():
    db = get_db()
    bal = balances(db)
    s = summary(db)
    boxes = []
    for g in db.goals.find().sort("created_at", 1):
        saved, target = bal.get(g["_id"], 0.0), g.get("target")
        boxes.append({**g, "saved": saved, "target": target,
                      "pct": round(saved / target * 100, 1) if target else None,
                      "reached": bool(target) and saved >= target,
                      "history": list(db.gullak_entries.find({"goal_id": g["_id"]}).sort("date", -1).limit(4))})
    cats = [c["name"] for c in db.categories.find({"type": "expense"}).sort("name", 1)]
    return render_template("gullak.html", boxes=boxes, icons=ICONS, expense_cats=cats, **s)


@bp.post("/")
def create():
    name, icon = request.form.get("name", "").strip(), request.form.get("icon", "🐷")
    try:
        if not name or len(name) > 40:
            raise ValueError("Give the box a name (max 40 characters)")
        target = None
        if request.form.get("target", "").strip():
            target = round(_number(request.form["target"], "Target"), 2)
            if not 0 < target <= 1_000_000_000:
                raise ValueError("Target must be greater than 0")
        get_db().goals.insert_one({"name": name, "icon": icon if icon in ICONS else "🐷",
                                   "target": target, "created_at": datetime.utcnow()})
        flash(f"Box '{name}' created.", "success")
    except ValueError as e:
        flash(str(e), "error")
    except DuplicateKeyError:  # unique index on goals.name
        flash("You already have a box with that name.", "error")
    return redirect(url_for("gullak.index"))


@bp.post("/<gid>/deposit")
def deposit(gid):
    db = get_db()
    goal = db.goals.find_one({"_id": _oid(gid)}) or abort(404)
    available = summary(db)["available"]
    pct_raw, amt_raw = request.form.get("percent", "").strip(), request.form.get("amount", "").strip()
    try:
        pct = None
        if pct_raw and amt_raw:
            raise ValueError("Enter either a percentage or an amount, not both")
        if pct_raw:
            pct = _number(pct_raw, "Percentage")
            if not 0 < pct <= 100:
                raise ValueError("Percentage must be between 0 and 100")
            amount = round(available * pct / 100, 2)   # percent of what is available RIGHT NOW
        elif amt_raw:
            amount = round(_number(amt_raw, "Amount"), 2)
        else:
            raise ValueError("Enter a percentage or an amount")
        if amount <= 0:
            raise ValueError("There is nothing available to move right now")
        if amount > available + 0.005:
            raise ValueError(f"Only {available:.2f} is available to move")
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("gullak.index"))
    db.gullak_entries.insert_one({"goal_id": goal["_id"], "kind": "deposit", "amount": amount,
                                  "percent": pct, "date": datetime.utcnow()})
    flash(f"₹{amount:,.2f} moved into '{goal['name']}'.", "success")
    return redirect(url_for("gullak.index"))


@bp.post("/<gid>/empty")
def empty(gid):
    """Empty a box. mode=spend -> records a real expense;  mode=return -> money goes back to the balance."""
    db = get_db()
    goal = db.goals.find_one({"_id": _oid(gid)}) or abort(404)
    saved, mode = balances(db).get(goal["_id"], 0.0), request.form.get("mode")
    if saved <= 0:
        flash("This box is already empty.", "error")
        return redirect(url_for("gullak.index"))
    now = datetime.utcnow()
    if mode == "spend":
        category = request.form.get("category", "Other")
        if not db.categories.find_one({"type": "expense", "name": category}):
            flash("Choose a valid expense category.", "error")
            return redirect(url_for("gullak.index"))
        when = datetime.combine(date.today(), datetime.min.time())
        db.transactions.insert_one({"type": "expense", "amount": saved, "category": category,
                                    "description": f"Gullak: {goal['name']}", "date": when,
                                    "created_at": now, "updated_at": now})
        flash(f"₹{saved:,.2f} spent on '{goal['name']}' and recorded as a {category} expense.", "success")
        for msg in analytics.budget_alerts(db, category, when):
            flash(msg, "warning")
    elif mode == "return":
        flash(f"₹{saved:,.2f} returned to your available balance.", "success")
    else:
        abort(400)
    db.gullak_entries.insert_one({"goal_id": goal["_id"], "kind": "withdraw", "amount": saved,
                                  "mode": mode, "date": now})
    return redirect(url_for("gullak.index"))


@bp.post("/<gid>/delete")
def delete(gid):
    db = get_db()
    goal = db.goals.find_one({"_id": _oid(gid)}) or abort(404)
    if balances(db).get(goal["_id"], 0.0) > 0:
        flash("Empty the box first (spend it or return it), then delete.", "error")
    else:
        db.gullak_entries.delete_many({"goal_id": goal["_id"]})
        db.goals.delete_one({"_id": goal["_id"]})
        flash(f"Box '{goal['name']}' deleted.", "success")
    return redirect(url_for("gullak.index"))
