# Viva notes – questions you will probably get

## How a request flows (say this in your own words)
"The browser asks Flask for a URL. The route in `app.py` reads the form or query string, validates it, talks to MongoDB through PyMongo, and hands the result to a Jinja template that produces HTML. The summaries are MongoDB aggregation pipelines in `analytics.py`."

## Quick tour of files (60 seconds)
* `db.py` – connects, creates validators + indexes + default categories (runs once at startup)
* `app.py` – one function per page/action (CRUD, categories, budgets, report)
* `analytics.py` – every report, each a `$match → $group → $sort` pipeline
* `templates/` – the pages; `static/style.css` – looks only
* `seed.py` – sample data; `mongo_queries.js` – same operations in the Mongo shell

## Questions and short answers
1. **Why MongoDB for this?** Transactions are self-contained documents; the schema can evolve (e.g. add tags) without migrations; the aggregation framework does the grouping/summing inside the database.
2. **What is a document / collection?** A JSON-like record / a group of documents (like a row / a table).
3. **Explain your three collections.** transactions (money events), categories (allowed labels), budgets (limit per category per month).
4. **Why store the category name in the transaction instead of an ObjectId reference?** Reports group by category with no join; categories rarely change; the app blocks deleting a category in use so data stays consistent. Trade-off: renaming a category would need updating transactions.
5. **What does `$match` / `$group` / `$sort` / `$limit` do?** Filter documents / combine by a key and compute `$sum` etc. / order / keep first N.
6. **Walk through "top spending categories".** Match expenses in the month → group by category summing amount → sort descending; the first result is the highest.
7. **How do you get a month's data?** Range query `date >= 1st of month` and `< 1st of next month` – index-friendly and works for any month length.
8. **What is an index and which ones did you add?** A sorted lookup structure that avoids scanning every document; date, (category,date), and two unique indexes.
9. **How do you prevent duplicate categories/budgets?** Unique compound indexes; the app catches `DuplicateKeyError`.
10. **What is an upsert?** Update if a matching document exists, otherwise insert. Used when saving budgets.
11. **What is `$set`?** Updates only the listed fields instead of replacing the whole document.
12. **What is `$jsonSchema` validation?** Rules stored in MongoDB that reject invalid documents even if the app is bypassed.
13. **How does the over-budget alert work?** After saving an expense, `budget_status` compares spending against that month's category and overall budget; if spent > budget a warning is flashed.
14. **Why store amounts as double? Any risk?** Fine for 2-decimal personal amounts since we round; Decimal128 is the exact-money choice for production.
15. **Security?** Input validated server-side; regex search is escaped (`re.escape`); secrets live in `.env` (git-ignored); delete uses POST. Missing: login and CSRF tokens (listed as future scope).
16. **How would you add multiple users?** Add a `users` collection and a `user_id` field to every document; filter every query by it.
17. **How would you scale it?** Indexes already match the queries; could shard on user_id; pre-aggregate monthly totals if data grew very large.
18. **What would you improve?** Charts, recurring transactions, CSV export, Decimal128, login.

## Practice before the viva
1. Open Compass/mongosh, run queries 5, 6, 7 from `mongo_queries.js`, and compare numbers with the Report page.
2. Add a transaction in the UI → find it in Compass → edit it → watch `updated_at` change.
3. Exceed a budget on purpose to show the alert.
4. Be able to say honestly who wrote what: the project was built by you alone.
