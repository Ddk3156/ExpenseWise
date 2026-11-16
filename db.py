"""Database layer: connects to MongoDB, creates collections, validators and indexes."""
import os
from datetime import datetime

from dotenv import load_dotenv
from pymongo import ASCENDING, DESCENDING, MongoClient

load_dotenv()

_db = None  # one shared connection for the whole app

DEFAULT_EXPENSE = ["Food", "Rent", "Transportation", "Shopping", "Utilities",
                   "Healthcare", "Education", "Entertainment", "Travel", "Other"]
DEFAULT_INCOME = ["Salary", "Freelancing", "Scholarship", "Business", "Other"]

# JSON-Schema validators: MongoDB itself rejects bad documents.
VALIDATORS = {
    "transactions": {"$jsonSchema": {
        "bsonType": "object",
        "required": ["type", "amount", "category", "date"],
        "properties": {
            "type": {"enum": ["income", "expense"]},
            "amount": {"bsonType": ["double", "int", "long"], "minimum": 0.01},
            "category": {"bsonType": "string"},
            "description": {"bsonType": "string"},
            "date": {"bsonType": "date"},
        }}},
    "categories": {"$jsonSchema": {
        "bsonType": "object",
        "required": ["name", "type"],
        "properties": {"name": {"bsonType": "string"}, "type": {"enum": ["income", "expense"]}}}},
    "goals": {"$jsonSchema": {
        "bsonType": "object",
        "required": ["name"],
        "properties": {"name": {"bsonType": "string"}, "target": {"bsonType": ["double", "int", "long", "null"]}}}},
    "gullak_entries": {"$jsonSchema": {
        "bsonType": "object",
        "required": ["goal_id", "kind", "amount"],
        "properties": {"goal_id": {"bsonType": "objectId"}, "kind": {"enum": ["deposit", "withdraw"]},
                       "amount": {"bsonType": ["double", "int", "long"], "minimum": 0.01}}}},
    "budgets": {"$jsonSchema": {
        "bsonType": "object",
        "required": ["month", "category", "amount"],
        "properties": {"month": {"bsonType": "string"}, "category": {"bsonType": "string"},
                       "amount": {"bsonType": ["double", "int", "long"], "minimum": 0.01}}}},
}


def get_db():
    """Return the database, connecting and preparing it on first use."""
    global _db
    if _db is None:
        uri = os.getenv("MONGO_URI", "").strip()
        if not uri:
            raise RuntimeError("MONGO_URI is not set. Copy .env.example to .env and fill it in.")
        client = MongoClient(uri, serverSelectionTimeoutMS=8000)
        client.admin.command("ping")  # fails fast with a clear error if unreachable
        _db = client[os.getenv("DATABASE_NAME", "expense_tracker")]
        setup(_db)
    return _db


def setup(db):
    """Create collections (with validators), indexes and default categories. Safe to re-run."""
    existing = db.list_collection_names()
    for name, validator in VALIDATORS.items():
        if name not in existing:
            try:
                db.create_collection(name, validator=validator)
            except Exception:
                pass  # validators are a bonus; the app still works without them

    db.transactions.create_index([("date", DESCENDING)])
    db.transactions.create_index([("category", ASCENDING), ("date", DESCENDING)])
    db.categories.create_index([("type", ASCENDING), ("name", ASCENDING)], unique=True)
    db.budgets.create_index([("month", ASCENDING), ("category", ASCENDING)], unique=True)
    db.goals.create_index([("name", ASCENDING)], unique=True)
    db.gullak_entries.create_index([("goal_id", ASCENDING), ("date", DESCENDING)])

    if db.categories.count_documents({}) == 0:
        now = datetime.utcnow()
        docs = [{"name": n, "type": "expense", "is_default": True, "created_at": now} for n in DEFAULT_EXPENSE]
        docs += [{"name": n, "type": "income", "is_default": True, "created_at": now} for n in DEFAULT_INCOME]
        db.categories.insert_many(docs)
