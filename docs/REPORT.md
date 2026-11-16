# Personal Expense and Budget Management System (ExpenseWise)

**Name:** ______  **Roll No:** ______  **Course:** ______  **Guide:** ______

## 1. Problem statement
Develop a MongoDB application to manage personal financial transactions, income, expenses, spending categories and monthly budgets. Users should be able to record transactions, update expense details, categorize spending and monitor their financial activity, generate monthly expenditure summaries and identify major spending categories.

## 2. Objectives
1. Record income and expense transactions (Create).
2. View, search and filter transactions (Read), edit their details (Update) and remove them (Delete).
3. Organise spending into default and user-defined categories.
4. Set monthly budgets (overall and per category) and compare them with actual spending.
5. Generate a monthly expenditure summary and identify the major spending categories.

## 3. Technology stack
| Layer | Technology | Why |
|---|---|---|
| Database | MongoDB (Atlas) | Flexible documents, powerful aggregation framework |
| Driver | PyMongo | Official Python driver |
| Backend | Python + Flask | Small and readable; routes map directly to features |
| Frontend | Jinja2 HTML templates + CSS | Server-rendered, no JavaScript framework to maintain |

## 4. System architecture
Browser → Flask routes (`app.py`) → analytics / database helpers (`analytics.py`, `db.py`) → MongoDB.
Each page request is handled by one route; the route queries MongoDB, then passes the result to a template that renders HTML.

## 5. Database design
Database: `expense_tracker`, three collections.

**transactions**
| Field | Type | Notes |
|---|---|---|
| _id | ObjectId | auto |
| type | string | "income" or "expense" |
| amount | double | > 0, rounded to 2 decimals |
| category | string | name of the category |
| description | string | optional, max 200 chars |
| date | date | when it happened |
| created_at, updated_at | date | audit fields |

**categories** `{ name, type, is_default, created_at }` – 10 default expense and 5 default income categories; users can add their own.

**budgets** `{ month: "YYYY-MM", category, amount, created_at, updated_at }` – `category = "Overall"` stores the whole-month limit.

**Design decisions**
* *Category stored by name inside each transaction* (denormalised) so reports need no join; the app prevents deleting a category that is still used.
* *Dates stored as real BSON dates* so MongoDB can range-query and group them (`$gte`/`$lt`, `$dateToString`).
* *Amounts stored as doubles rounded to 2 decimals.* Simple and adequate for a personal tracker; `Decimal128` would be the production choice.

**Schema validation** – a `$jsonSchema` validator on each collection makes MongoDB itself reject, e.g., a transaction whose type is not income/expense or whose amount is ≤ 0.

**Indexes**
| Collection | Index | Purpose |
|---|---|---|
| transactions | `{date: -1}` | month filtering and "recent" lists |
| transactions | `{category: 1, date: -1}` | category filtering |
| categories | `{type: 1, name: 1}` **unique** | no duplicate categories |
| budgets | `{month: 1, category: 1}` **unique** | one budget per category per month |

## 6. Features and how they map to the problem statement
| Requirement | Implementation |
|---|---|
| Record transactions | `/transactions/new` → `insert_one` |
| Update expense details | `/transactions/<id>/edit` → `update_one` with `$set` |
| Categorize spending | Categories page; each transaction carries a category |
| Monitor financial activity | Dashboard (balance, monthly income/expense, budget usage, recent items, 6-month table); transaction list with filters and search |
| Monthly budgets | `/budgets`; saved with an **upsert** (update if it exists, else insert) |
| Monthly expenditure summary | `/report` |
| Identify major spending categories | Top-3 list and the "highest spending category" card |
| Extra | Over-budget alerts when an expense is saved; savings rate; average daily spend; biggest expense; month-over-month change |

## 7. Aggregation pipelines (core of the report)
**Monthly summary** (`analytics.totals`)
```js
[{ $match: { date: { $gte: start, $lt: end } } },
 { $group: { _id: "$type", total: { $sum: "$amount" }, count: { $sum: 1 } } }]
```
**Major spending categories** (`analytics.category_spend`)
```js
[{ $match: { type: "expense", date: { $gte: start, $lt: end } } },
 { $group: { _id: "$category", total: { $sum: "$amount" }, count: { $sum: 1 } } },
 { $sort: { total: -1 } }]            // first item = highest category; first 3 = top 3
```
**Six-month trend** (`analytics.trend`)
```js
[{ $match: { date: { $gte: firstMonth, $lt: endOfThisMonth } } },
 { $group: { _id: { m: { $dateToString: { format: "%Y-%m", date: "$date" } }, t: "$type" },
             total: { $sum: "$amount" } } }]
```
**Budget vs actual** – the budgets are read with `find({month})`, merged with `category_spend`; an equivalent single-query `$lookup` version is in `mongo_queries.js`.

_Insert screenshots of each pipeline's output (from Compass/mongosh) here._

## 8. Validation and error handling
Amount must be a number > 0; the date must be valid; the category must exist; descriptions ≤ 200 characters; duplicate categories are rejected by the unique index; default or in-use categories cannot be deleted; invalid ids return 404; a missing or wrong `MONGO_URI` produces a clear message.

## 9. Testing
`tests/smoke_test.py` runs 30 automated checks: every page loads, create/update/delete work, invalid input is rejected, duplicates are blocked, budget upsert does not duplicate, and report totals equal an independent manual sum. _Add manual test-case table / screenshots here._

## 10. Screenshots
_Dashboard · Add transaction · Transactions list · Categories · Budgets · Report · MongoDB Compass collections_

## 11. Limitations and future scope
* Single user, no login (future: register/login with hashed passwords and a `user_id` on every document).
* No CSRF protection (future: Flask-WTF).
* Amounts are doubles (future: `Decimal128`).
* Future: recurring transactions, CSV export, charts, multi-currency, mobile app.

## 12. Conclusion
The system covers the full lifecycle of personal finance records in MongoDB – recording, updating, categorising, budgeting and reporting – and uses the aggregation framework to answer "how much did I spend this month and where did it go".
