"""Smoke test: exercises every page and action using an in-memory fake MongoDB (mongomock).
   pip install mongomock   then   python tests/smoke_test.py
   (The real app always uses real MongoDB; this just lets you check the logic without a server.)"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mongomock
import db as database

database._db = mongomock.MongoClient().expense_test
database.setup(database._db)
import seed, app as appmod

seed.main()
c = appmod.app.test_client()
D = database._db
ok = lambda cond, msg: print(("PASS " if cond else "FAIL ") + msg) or (cond or sys.exit(1))

for url in ["/", "/transactions", "/transactions?all=1&type=expense&q=food", "/categories", "/budgets", "/report",
            "/transactions/new", "/?month=2025-01", "/report?month=2025-01", "/?month=garbage"]:
    r = c.get(url); ok(r.status_code == 200, f"GET {url} -> {r.status_code}")

ok(c.get("/transactions/zzz/edit").status_code == 404, "bad id -> 404")

# CREATE (+ budget alert)
r = c.post("/transactions/new", data={"category": "expense:Food", "amount": "99999", "description": "Test feast",
           "date": date_str if (date_str := __import__("datetime").date.today().isoformat()) else ""}, follow_redirects=True)
ok(b"Transaction added" in r.data and b"Over your Food budget" in r.data, "create + over-budget alert")
tx = D.transactions.find_one({"description": "Test feast"})
ok(tx and isinstance(tx["amount"], float), "stored with float amount")

# VALIDATION
for bad in [{"category": "expense:Food", "amount": "-5", "date": "2026-01-01"},
            {"category": "expense:Nope", "amount": "5", "date": "2026-01-01"},
            {"category": "expense:Food", "amount": "abc", "date": "2026-01-01"},
            {"category": "expense:Food", "amount": "5", "date": "31-31-2026"}]:
    r = c.post("/transactions/new", data=bad); ok(b"flash error" in r.data, f"rejects {bad['amount']}/{bad['category']}")

# UPDATE
r = c.post(f"/transactions/{tx['_id']}/edit", data={"category": "expense:Shopping", "amount": "123.456",
           "description": "Edited", "date": "2026-03-05"}, follow_redirects=True)
t2 = D.transactions.find_one({"_id": tx["_id"]})
ok(t2["category"] == "Shopping" and t2["amount"] == 123.46 and t2["description"] == "Edited", "update works")
ok(c.get(f"/transactions/{tx['_id']}/edit").status_code == 200, "edit page loads")

# DELETE
c.post(f"/transactions/{tx['_id']}/delete"); ok(D.transactions.find_one({"_id": tx["_id"]}) is None, "delete works")

# CATEGORIES
c.post("/categories", data={"name": "Pets", "type": "expense"})
ok(D.categories.find_one({"name": "Pets"}) is not None, "add category")
r = c.post("/categories", data={"name": "Pets", "type": "expense"}, follow_redirects=True)
ok(b"already exists" in r.data, "duplicate category rejected (unique index)")
pets = D.categories.find_one({"name": "Pets"})
c.post(f"/categories/{pets['_id']}/delete"); ok(D.categories.find_one({"name": "Pets"}) is None, "delete unused custom category")
food = D.categories.find_one({"name": "Food", "type": "expense"})
r = c.post(f"/categories/{food['_id']}/delete", follow_redirects=True); ok(b"Default categories" in r.data, "default category protected")

# BUDGETS (upsert)
c.post("/budgets", data={"month": "2026-02", "category": "Food", "amount": "1000"})
c.post("/budgets", data={"month": "2026-02", "category": "Food", "amount": "2000"})
ok(D.budgets.count_documents({"month": "2026-02", "category": "Food"}) == 1 and
   D.budgets.find_one({"month": "2026-02", "category": "Food"})["amount"] == 2000, "budget upsert (no duplicates)")
b = D.budgets.find_one({"month": "2026-02", "category": "Food"})
c.post(f"/budgets/{b['_id']}/delete"); ok(D.budgets.find_one({"_id": b["_id"]}) is None, "delete budget")

# ANALYTICS correctness against a manual calculation
import analytics
from datetime import date
m = date.today().strftime("%Y-%m")
rep = analytics.monthly_report(D, m)
s, e = analytics.month_range(m)
manual = sum(t["amount"] for t in D.transactions.find({"type": "expense", "date": {"$gte": s, "$lt": e}}))
ok(abs(rep["totals"]["expense"] - manual) < 0.01, f"report expense total matches manual sum ({manual})")
ok(rep["highest"]["category"] == rep["category_spend"][0]["category"], "highest category = first of sorted list")
ok(abs(sum(x["share"] for x in rep["category_spend"]) - 100) < 0.5, "category shares add to ~100%")
ok(len(rep["trend"]) == 6, "trend has 6 months")
print("\nALL TESTS PASSED")
