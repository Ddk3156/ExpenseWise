// Run these in mongosh or MongoDB Compass (use expense_tracker)  -- same logic the app runs through PyMongo.
use expense_tracker

// 1. CREATE a transaction
db.transactions.insertOne({ type: "expense", amount: 450.0, category: "Food",
  description: "Lunch", date: new Date("2026-11-10"), created_at: new Date(), updated_at: new Date() })

// 2. UPDATE expense details
db.transactions.updateOne({ description: "Lunch" }, { $set: { amount: 520.0, category: "Entertainment", updated_at: new Date() } })

// 3. DELETE
db.transactions.deleteOne({ description: "Lunch" })

// 4. Search + filter (what the Transactions page does)
db.transactions.find({ type: "expense", date: { $gte: ISODate("2026-11-01"), $lt: ISODate("2026-12-01") },
  $or: [{ description: /food/i }, { category: /food/i }] }).sort({ date: -1 })

// 5. MONTHLY SUMMARY: income vs expense for a month
db.transactions.aggregate([
  { $match: { date: { $gte: ISODate("2026-11-01"), $lt: ISODate("2026-12-01") } } },
  { $group: { _id: "$type", total: { $sum: "$amount" }, count: { $sum: 1 } } }
])

// 6. MAJOR SPENDING CATEGORIES (top 3)
db.transactions.aggregate([
  { $match: { type: "expense", date: { $gte: ISODate("2026-11-01"), $lt: ISODate("2026-12-01") } } },
  { $group: { _id: "$category", total: { $sum: "$amount" }, count: { $sum: 1 } } },
  { $sort: { total: -1 } },
  { $limit: 3 }
])

// 7. MONTH-BY-MONTH TREND
db.transactions.aggregate([
  { $group: { _id: { month: { $dateToString: { format: "%Y-%m", date: "$date" } }, type: "$type" },
              total: { $sum: "$amount" } } },
  { $sort: { "_id.month": 1 } }
])

// 8. BUDGET vs ACTUAL in one query ($lookup joins budgets with that month's spending)
db.budgets.aggregate([
  { $match: { month: "2026-11", category: { $ne: "Overall" } } },
  { $lookup: { from: "transactions", let: { cat: "$category" },
      pipeline: [ { $match: { $expr: { $and: [ { $eq: ["$category", "$$cat"] }, { $eq: ["$type", "expense"] },
                    { $gte: ["$date", ISODate("2026-11-01")] }, { $lt: ["$date", ISODate("2026-12-01")] } ] } } },
                  { $group: { _id: null, spent: { $sum: "$amount" } } } ],
      as: "actual" } },
  { $project: { category: 1, budget: "$amount", spent: { $ifNull: [{ $first: "$actual.spent" }, 0] } } },
  { $addFields: { remaining: { $subtract: ["$budget", "$spent"] } } }
])

// 9. UPSERT a budget (update if it exists, create if not)
db.budgets.updateOne({ month: "2026-11", category: "Food" }, { $set: { amount: 7000.0 } }, { upsert: true })

// 10. Inspect indexes and the schema validator
db.transactions.getIndexes()
db.getCollectionInfos({ name: "transactions" })[0].options.validator
