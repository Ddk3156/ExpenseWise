# ExpenseWise – Personal Expense & Budget Management System

Python (Flask) + **MongoDB** (PyMongo). Server-rendered HTML pages (Jinja2), no JavaScript framework.
Amounts are in INR (₹).

## 1. Prerequisites
* Python 3.9+  (check: `python --version`)
* A MongoDB database – either **MongoDB Atlas (free, cloud)** or local MongoDB Community Server

## 2. Get a MongoDB connection string (Atlas, ~5 min)
1. Sign in at https://cloud.mongodb.com → create a free **M0** cluster.
2. **Database Access** → Add New Database User → username + password (note them; avoid `@ : /` in the password).
3. **Network Access** → Add IP Address → "Add current IP" (or `0.0.0.0/0` for a college demo).
4. **Clusters → Connect → Drivers** → copy the string, e.g.
   `mongodb+srv://myuser:mypassword@cluster0.xxxxx.mongodb.net/`
   (Local MongoDB instead? Use `mongodb://localhost:27017`.)

## 3. Install and run
```bash
cd expense_tracker
python -m venv venv
venv\Scripts\activate            # Windows        (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env           # Windows        (Mac/Linux: cp .env.example .env)
```
Open `.env` and set `MONGO_URI`, `DATABASE_NAME`, `SECRET_KEY`. Then:
```bash
python seed.py                   # optional: 4 months of sample data for demo/screenshots
python app.py                    # open http://127.0.0.1:5000
```
On first start the app creates the collections, validators, indexes and default categories itself.
`python seed.py --reset` wipes transactions/budgets and re-inserts the sample data.

## 4. Troubleshooting
| Symptom | Fix |
|---|---|
| `MONGO_URI is not set` | `.env` missing – copy `.env.example` to `.env` and fill it |
| `ServerSelectionTimeoutError` / timeout | Atlas → Network Access → add your current IP; check internet/VPN |
| `Authentication failed` | Wrong user/password in the URI; special characters must be URL-encoded |
| `ModuleNotFoundError` | Activate the venv and run `pip install -r requirements.txt` |
| Port 5000 busy | Change `port=5000` at the bottom of `app.py` |

## 5. Project structure
```
app.py         routes (what each URL does) – Flask
db.py          MongoDB connection, validators, indexes, default categories
analytics.py   all summary/report logic = MongoDB aggregation pipelines
seed.py        sample data loader
templates/     HTML pages (Jinja2);  static/style.css  styling
mongo_queries.js   the same operations as raw mongosh queries (for the viva)
tests/smoke_test.py  automated check of every page/action (uses mongomock)
docs/          REPORT.md (project report) and VIVA_NOTES.md
```

## 6. Pages
Dashboard · Transactions (add / edit / delete / filter / search) · Categories (default + custom) ·
Budgets (overall + per category, per month) · Report (monthly summary, top categories, comparison)



