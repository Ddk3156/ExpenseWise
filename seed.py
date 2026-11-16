"""Fill the database with ~4 months of realistic sample data for demos/screenshots.
   python seed.py           -> adds sample data only if there are no transactions yet
   python seed.py --reset   -> wipes transactions and budgets first, then adds sample data
"""
import random
import sys
from datetime import date, datetime

import analytics
from db import get_db

random.seed(42)  # same data every run

# (day of month, type, category, description, typical amount)
RECURRING = [
    (1, "income", "Salary", "Monthly salary", 60000), (2, "expense", "Rent", "House rent", 15000),
    (4, "expense", "Utilities", "Electricity bill", 1800), (5, "expense", "Utilities", "Internet & mobile", 999),
    (3, "expense", "Food", "Grocery shopping", 2600), (9, "expense", "Food", "Restaurant dinner", 1200),
    (15, "expense", "Food", "Weekend takeout", 900), (22, "expense", "Food", "Groceries", 2400),
    (6, "expense", "Transportation", "Metro / auto pass", 1200), (18, "expense", "Transportation", "Fuel", 1500),
    (8, "expense", "Shopping", "Clothing", 3200), (21, "expense", "Shopping", "Home essentials", 1800),
    (11, "expense", "Education", "Online course", 2500), (14, "expense", "Healthcare", "Pharmacy", 800),
    (7, "expense", "Entertainment", "Movies & streaming", 700), (24, "expense", "Entertainment", "Concert / games", 1200),
    (12, "income", "Freelancing", "Freelance project", 12000), (27, "expense", "Other", "Miscellaneous", 600),
]
BUDGETS = {"Overall": 50000, "Food": 7000, "Shopping": 5000, "Transportation": 3000,
           "Entertainment": 2000, "Utilities": 3000, "Rent": 15000, "Education": 3000, "Healthcare": 1500}


def main():
    db = get_db()
    if "--reset" in sys.argv:
        db.transactions.delete_many({})
        db.budgets.delete_many({})
    elif db.transactions.count_documents({}):
        print("Transactions already exist. Use --reset to replace them.")
        return
    today, cur = date.today(), date.today().strftime("%Y-%m")
    txs, budgets = [], []
    for back in range(3, -1, -1):  # 3 months ago ... this month
        month = analytics.add_months(cur, -back)
        y, m = map(int, month.split("-"))
        for day, ttype, cat, desc, base in RECURRING:
            if back == 0 and day > today.day:
                continue  # no future-dated transactions in the current month
            amount = base if desc in ("Monthly salary", "House rent", "Internet & mobile") \
                else round(base * random.uniform(0.7, 1.4) / 10) * 10
            txs.append({"type": ttype, "amount": float(amount), "category": cat, "description": desc,
                        "date": datetime(y, m, day), "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()})
        for cat, amt in BUDGETS.items():
            budgets.append({"month": month, "category": cat, "amount": float(amt), "created_at": datetime.utcnow()})
    db.transactions.insert_many(txs)
    db.budgets.insert_many(budgets)
    print(f"Inserted {len(txs)} transactions and {len(budgets)} budgets.")


if __name__ == "__main__":
    main()
