import pandas as pd
import numpy as np
import os
import time
import json
import dotenv
import ast
import re
from pathlib import Path
from dataclasses import dataclass, field
from sqlalchemy.sql import text
from datetime import datetime, timedelta
from typing import Dict, List, Union, Optional
from sqlalchemy import create_engine, Engine, inspect

from smolagents import (
    ToolCallingAgent,
    OpenAIServerModel,
    tool,
)
from db_config import DatabaseConfig

# =========================================================
# DATABASE SETUP
# =========================================================

db_engine = DatabaseConfig.get_engine()
BASE_DIR = Path(__file__).resolve().parent

# =========================================================
# CATALOG DATA
# =========================================================

paper_supplies = [
    {"item_name": "A4 paper",                         "category": "paper",        "unit_price": 0.05},
    {"item_name": "Letter-sized paper",              "category": "paper",        "unit_price": 0.06},
    {"item_name": "Cardstock",                       "category": "paper",        "unit_price": 0.15},
    {"item_name": "Colored paper",                   "category": "paper",        "unit_price": 0.10},
    {"item_name": "Glossy paper",                    "category": "paper",        "unit_price": 0.20},
    {"item_name": "Matte paper",                     "category": "paper",        "unit_price": 0.18},
    {"item_name": "Recycled paper",                  "category": "paper",        "unit_price": 0.08},
    {"item_name": "Eco-friendly paper",              "category": "paper",        "unit_price": 0.12},
    {"item_name": "Poster paper",                    "category": "paper",        "unit_price": 0.25},
    {"item_name": "Banner paper",                    "category": "paper",        "unit_price": 0.30},
    {"item_name": "Kraft paper",                     "category": "paper",        "unit_price": 0.10},
    {"item_name": "Construction paper",              "category": "paper",        "unit_price": 0.07},
    {"item_name": "Wrapping paper",                  "category": "paper",        "unit_price": 0.15},
    {"item_name": "Glitter paper",                   "category": "paper",        "unit_price": 0.22},
    {"item_name": "Decorative paper",                "category": "paper",        "unit_price": 0.18},
    {"item_name": "Letterhead paper",                "category": "paper",        "unit_price": 0.12},
    {"item_name": "Legal-size paper",                "category": "paper",        "unit_price": 0.08},
    {"item_name": "Crepe paper",                     "category": "paper",        "unit_price": 0.05},
    {"item_name": "Photo paper",                     "category": "paper",        "unit_price": 0.25},
    {"item_name": "Uncoated paper",                  "category": "paper",        "unit_price": 0.06},
    {"item_name": "Butcher paper",                   "category": "paper",        "unit_price": 0.10},
    {"item_name": "Heavyweight paper",               "category": "paper",        "unit_price": 0.20},
    {"item_name": "Standard copy paper",             "category": "paper",        "unit_price": 0.04},
    {"item_name": "Bright-colored paper",            "category": "paper",        "unit_price": 0.12},
    {"item_name": "Patterned paper",                 "category": "paper",        "unit_price": 0.15},

    {"item_name": "Paper plates",                    "category": "product",      "unit_price": 0.10},
    {"item_name": "Paper cups",                      "category": "product",      "unit_price": 0.08},
    {"item_name": "Paper napkins",                   "category": "product",      "unit_price": 0.02},
    {"item_name": "Disposable cups",                 "category": "product",      "unit_price": 0.10},
    {"item_name": "Table covers",                    "category": "product",      "unit_price": 1.50},
    {"item_name": "Envelopes",                       "category": "product",      "unit_price": 0.05},
    {"item_name": "Sticky notes",                    "category": "product",      "unit_price": 0.03},
    {"item_name": "Notepads",                        "category": "product",      "unit_price": 2.00},
    {"item_name": "Invitation cards",                "category": "product",      "unit_price": 0.50},
    {"item_name": "Flyers",                          "category": "product",      "unit_price": 0.15},
    {"item_name": "Party streamers",                 "category": "product",      "unit_price": 0.05},
    {"item_name": "Decorative adhesive tape (washi tape)", "category": "product", "unit_price": 0.20},
    {"item_name": "Paper party bags",                "category": "product",      "unit_price": 0.25},
    {"item_name": "Name tags with lanyards",         "category": "product",      "unit_price": 0.75},
    {"item_name": "Presentation folders",            "category": "product",      "unit_price": 0.50},

    {"item_name": "Large poster paper (24x36 inches)", "category": "large_format", "unit_price": 1.00},
    {"item_name": "Rolls of banner paper (36-inch width)", "category": "large_format", "unit_price": 2.50},

    {"item_name": "100 lb cover stock",              "category": "specialty",    "unit_price": 0.50},
    {"item_name": "80 lb text paper",                "category": "specialty",    "unit_price": 0.40},
    {"item_name": "250 gsm cardstock",               "category": "specialty",    "unit_price": 0.30},
    {"item_name": "220 gsm poster paper",            "category": "specialty",    "unit_price": 0.35},
]

# =========================================================
# STARTER HELPER FUNCTIONS
# =========================================================

def generate_sample_inventory(paper_supplies: list, coverage: float = 0.4, seed: int = 137) -> pd.DataFrame:
    np.random.seed(seed)
    num_items = int(len(paper_supplies) * coverage)

    selected_indices = np.random.choice(
        range(len(paper_supplies)),
        size=num_items,
        replace=False
    )

    selected_items = [paper_supplies[i] for i in selected_indices]

    inventory = []
    for item in selected_items:
        inventory.append({
            "item_name": item["item_name"],
            "category": item["category"],
            "unit_price": item["unit_price"],
            "current_stock": np.random.randint(200, 800),
            "min_stock_level": np.random.randint(50, 150)
        })

    return pd.DataFrame(inventory)


def init_database(db_engine: Engine = db_engine, seed: int = 137) -> Engine:
    """
    Initialize database with sample data.
    
    WARNING: This function is for LOCAL DEVELOPMENT/TESTING ONLY.
    It drops existing tables and recreates them with sample data.
    
    In production (PostgreSQL), database schema should be managed
    separately using migrations or cloud-specific tools.
    
    Args:
        db_engine: SQLAlchemy engine
        seed: Random seed for reproducibility
        
    Returns:
        SQLAlchemy engine
    """
    # Guard: Only allow in local SQLite mode
    if not DatabaseConfig.is_local():
        print("WARNING: init_database() skipped - using PostgreSQL in production mode")
        print("Database schema should be initialized separately in production")
        return db_engine
    
    print("Initializing SQLite database with sample data (LOCAL DEVELOPMENT MODE)")
    try:
        with db_engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS transactions"))
            conn.execute(text(
                """
                CREATE TABLE transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_name TEXT,
                    transaction_type TEXT,
                    units INTEGER,
                    price REAL,
                    transaction_date TEXT
                )
                """
            ))

        initial_date = datetime(2025, 1, 1).isoformat()

        # Historical customer requests
        quote_requests_df = pd.read_csv("quote_requests.csv")
        quote_requests_df["id"] = range(1, len(quote_requests_df) + 1)
        quote_requests_df.to_sql("quote_requests", db_engine, if_exists="replace", index=False)

        # Historical quotes
        quotes_df = pd.read_csv("quotes.csv")
        quotes_df["request_id"] = range(1, len(quotes_df) + 1)
        quotes_df["order_date"] = initial_date

        if "request_metadata" in quotes_df.columns:
            quotes_df["request_metadata"] = quotes_df["request_metadata"].apply(
                lambda x: ast.literal_eval(x) if isinstance(x, str) else x
            )
            quotes_df["job_type"] = quotes_df["request_metadata"].apply(lambda x: x.get("job_type", ""))
            quotes_df["order_size"] = quotes_df["request_metadata"].apply(lambda x: x.get("order_size", ""))
            quotes_df["event_type"] = quotes_df["request_metadata"].apply(lambda x: x.get("event_type", ""))

        quotes_df = quotes_df[[
            "request_id",
            "total_amount",
            "quote_explanation",
            "order_date",
            "job_type",
            "order_size",
            "event_type"
        ]]
        quotes_df.to_sql("quotes", db_engine, if_exists="replace", index=False)

        inventory_df = generate_sample_inventory(paper_supplies, seed=seed)

        initial_transactions = []
        initial_transactions.append({
            "item_name": None,
            "transaction_type": "sales",
            "units": None,
            "price": 50000.0,
            "transaction_date": initial_date,
        })

        for _, item in inventory_df.iterrows():
            initial_transactions.append({
                "item_name": item["item_name"],
                "transaction_type": "stock_orders",
                "units": int(item["current_stock"]),
                "price": float(item["current_stock"] * item["unit_price"]),
                "transaction_date": initial_date,
            })

        pd.DataFrame(initial_transactions).to_sql("transactions", db_engine, if_exists="append", index=False)
        inventory_df.to_sql("inventory", db_engine, if_exists="replace", index=False)

        return db_engine

    except Exception as e:
        print(f"Error initializing database: {e}")
        raise


def ensure_database_ready(db_engine: Engine = db_engine, seed: int = 137) -> Engine:
    """
    Ensure required tables exist without destructive resets.

    This is intended for cloud/production startup where tables might not yet exist.
    If tables are present, it leaves existing data untouched.
    """
    required_tables = {"transactions", "quote_requests", "quotes", "inventory"}
    inspector = inspect(db_engine)
    existing_tables = set(inspector.get_table_names())

    def _looks_like_text(sql_type: str) -> bool:
        t = sql_type.lower()
        return "text" in t or "char" in t or "string" in t

    def _looks_like_int(sql_type: str) -> bool:
        t = sql_type.lower()
        return "int" in t

    def _looks_like_float(sql_type: str) -> bool:
        t = sql_type.lower()
        return any(x in t for x in ["double", "real", "numeric", "decimal", "float"])

    def _transactions_schema_valid() -> bool:
        if "transactions" not in existing_tables:
            return False

        cols = {c["name"]: str(c["type"]) for c in inspector.get_columns("transactions")}
        required_cols = {"id", "item_name", "transaction_type", "units", "price", "transaction_date"}
        if not required_cols.issubset(set(cols.keys())):
            return False

        return (
            _looks_like_int(cols["id"]) and
            _looks_like_text(cols["item_name"]) and
            _looks_like_text(cols["transaction_type"]) and
            _looks_like_int(cols["units"]) and
            _looks_like_float(cols["price"]) and
            _looks_like_text(cols["transaction_date"])
        )

    if "transactions" in existing_tables and not _transactions_schema_valid():
        print("Detected invalid transactions schema. Rebuilding transactions table with correct types.")
        with db_engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS transactions"))
        existing_tables.remove("transactions")

    missing_tables = required_tables - existing_tables

    if not missing_tables:
        return db_engine

    print(f"Bootstrapping missing tables: {sorted(missing_tables)}")
    initial_date = datetime(2025, 1, 1).isoformat()
    inventory_df = None

    if "quote_requests" in missing_tables:
        quote_requests_df = pd.read_csv(BASE_DIR / "quote_requests.csv")
        quote_requests_df["id"] = range(1, len(quote_requests_df) + 1)
        quote_requests_df.to_sql("quote_requests", db_engine, if_exists="replace", index=False)

    if "quotes" in missing_tables:
        quotes_df = pd.read_csv(BASE_DIR / "quotes.csv")
        quotes_df["request_id"] = range(1, len(quotes_df) + 1)
        quotes_df["order_date"] = initial_date

        if "request_metadata" in quotes_df.columns:
            quotes_df["request_metadata"] = quotes_df["request_metadata"].apply(
                lambda x: ast.literal_eval(x) if isinstance(x, str) else x
            )
            quotes_df["job_type"] = quotes_df["request_metadata"].apply(lambda x: x.get("job_type", ""))
            quotes_df["order_size"] = quotes_df["request_metadata"].apply(lambda x: x.get("order_size", ""))
            quotes_df["event_type"] = quotes_df["request_metadata"].apply(lambda x: x.get("event_type", ""))

        quotes_df = quotes_df[[
            "request_id",
            "total_amount",
            "quote_explanation",
            "order_date",
            "job_type",
            "order_size",
            "event_type",
        ]]
        quotes_df.to_sql("quotes", db_engine, if_exists="replace", index=False)

    if "inventory" in missing_tables:
        inventory_df = generate_sample_inventory(paper_supplies, seed=seed)
        inventory_df.to_sql("inventory", db_engine, if_exists="replace", index=False)

    if "transactions" in missing_tables:
        with db_engine.begin() as conn:
            if DatabaseConfig.is_local():
                conn.execute(text(
                    """
                    CREATE TABLE IF NOT EXISTS transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        item_name TEXT,
                        transaction_type TEXT,
                        units INTEGER,
                        price REAL,
                        transaction_date TEXT
                    )
                    """
                ))
            else:
                conn.execute(text(
                    """
                    CREATE TABLE IF NOT EXISTS transactions (
                        id BIGSERIAL PRIMARY KEY,
                        item_name TEXT,
                        transaction_type TEXT,
                        units INTEGER,
                        price DOUBLE PRECISION,
                        transaction_date TEXT
                    )
                    """
                ))

        if inventory_df is None:
            inventory_df = pd.read_sql("SELECT item_name, unit_price, current_stock FROM inventory", db_engine)

        initial_transactions = [{
            "item_name": None,
            "transaction_type": "sales",
            "units": None,
            "price": 50000.0,
            "transaction_date": initial_date,
        }]

        for _, item in inventory_df.iterrows():
            initial_transactions.append({
                "item_name": item["item_name"],
                "transaction_type": "stock_orders",
                "units": int(item["current_stock"]),
                "price": float(item["current_stock"] * item["unit_price"]),
                "transaction_date": initial_date,
            })

        pd.DataFrame(initial_transactions).to_sql("transactions", db_engine, if_exists="append", index=False)

        if not DatabaseConfig.is_local():
            with db_engine.begin() as conn:
                conn.execute(text(
                    "SELECT setval(pg_get_serial_sequence('transactions','id'), COALESCE((SELECT MAX(id) FROM transactions), 1), true)"
                ))

    return db_engine


def create_transaction(
    item_name: str,
    transaction_type: str,
    quantity: int,
    price: float,
    date: Union[str, datetime],
) -> int:
    try:
        date_str = date.isoformat() if isinstance(date, datetime) else date

        if transaction_type not in {"stock_orders", "sales"}:
            raise ValueError("Transaction type must be 'stock_orders' or 'sales'")

        next_id_df = pd.read_sql(text("SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM transactions"), db_engine)
        next_id = int(next_id_df.iloc[0]["next_id"])

        transaction = pd.DataFrame([{
            "id": next_id,
            "item_name": item_name,
            "transaction_type": transaction_type,
            "units": quantity,
            "price": price,
            "transaction_date": date_str,
        }])

        transaction.to_sql("transactions", db_engine, if_exists="append", index=False)

        return next_id

    except Exception as e:
        print(f"Error creating transaction: {e}")
        raise


def get_all_inventory(as_of_date: str) -> Dict[str, int]:
    query = """
        SELECT
            item_name,
            SUM(CASE
                WHEN transaction_type = 'stock_orders' THEN units
                WHEN transaction_type = 'sales' THEN -units
                ELSE 0
            END) as stock
        FROM transactions
        WHERE item_name IS NOT NULL
        AND transaction_date <= :as_of_date
        GROUP BY item_name
        HAVING stock > 0
    """

    result = pd.read_sql(text(query), db_engine, params={"as_of_date": as_of_date})
    return dict(zip(result["item_name"], result["stock"]))


def get_stock_level(item_name: str, as_of_date: Union[str, datetime]) -> pd.DataFrame:
    if isinstance(as_of_date, datetime):
        as_of_date = as_of_date.isoformat()

    stock_query = """
        SELECT
            item_name,
            COALESCE(SUM(CASE
                WHEN transaction_type = 'stock_orders' THEN units
                WHEN transaction_type = 'sales' THEN -units
                ELSE 0
            END), 0) AS current_stock
        FROM transactions
        WHERE item_name = :item_name
        AND transaction_date <= :as_of_date
        GROUP BY item_name
    """

    return pd.read_sql(
        text(stock_query),
        db_engine,
        params={"item_name": item_name, "as_of_date": as_of_date},
    )


def get_supplier_delivery_date(input_date_str: str, quantity: int) -> str:
    print(f"FUNC (get_supplier_delivery_date): Calculating for qty {quantity} from date string '{input_date_str}'")

    try:
        input_date_dt = datetime.fromisoformat(input_date_str.split("T")[0])
    except (ValueError, TypeError):
        print(f"WARN (get_supplier_delivery_date): Invalid date format '{input_date_str}', using today as base.")
        input_date_dt = datetime.now()

    if quantity <= 10:
        days = 0
    elif quantity <= 100:
        days = 1
    elif quantity <= 1000:
        days = 4
    else:
        days = 7

    delivery_date_dt = input_date_dt + timedelta(days=days)
    return delivery_date_dt.strftime("%Y-%m-%d")


def get_cash_balance(as_of_date: Union[str, datetime]) -> float:
    try:
        if isinstance(as_of_date, datetime):
            as_of_date = as_of_date.isoformat()

        transactions = pd.read_sql(
            text("SELECT * FROM transactions WHERE transaction_date <= :as_of_date"),
            db_engine,
            params={"as_of_date": as_of_date},
        )

        if not transactions.empty:
            total_sales = transactions.loc[transactions["transaction_type"] == "sales", "price"].sum()
            total_purchases = transactions.loc[transactions["transaction_type"] == "stock_orders", "price"].sum()
            return float(total_sales - total_purchases)

        return 0.0

    except Exception as e:
        print(f"Error getting cash balance: {e}")
        return 0.0


def generate_financial_report(as_of_date: Union[str, datetime]) -> Dict:
    if isinstance(as_of_date, datetime):
        as_of_date = as_of_date.isoformat()

    cash = get_cash_balance(as_of_date)

    inventory_df = pd.read_sql("SELECT * FROM inventory", db_engine)
    inventory_value = 0.0
    inventory_summary = []

    for _, item in inventory_df.iterrows():
        stock_info = get_stock_level(item["item_name"], as_of_date)
        stock = int(stock_info["current_stock"].iloc[0])
        item_value = stock * item["unit_price"]
        inventory_value += item_value

        inventory_summary.append({
            "item_name": item["item_name"],
            "stock": stock,
            "unit_price": item["unit_price"],
            "value": item_value,
        })

    top_sales_query = """
        SELECT item_name, SUM(units) as total_units, SUM(price) as total_revenue
        FROM transactions
        WHERE transaction_type = 'sales' AND transaction_date <= :date
        GROUP BY item_name
        ORDER BY total_revenue DESC
        LIMIT 5
    """
    top_sales = pd.read_sql(text(top_sales_query), db_engine, params={"date": as_of_date})
    top_selling_products = top_sales.to_dict(orient="records")

    return {
        "as_of_date": as_of_date,
        "cash_balance": cash,
        "inventory_value": inventory_value,
        "total_assets": cash + inventory_value,
        "inventory_summary": inventory_summary,
        "top_selling_products": top_selling_products,
    }


def search_quote_history(search_terms: List[str], limit: int = 5) -> List[Dict]:
    conditions = []
    params = {}

    for i, term in enumerate(search_terms):
        param_name = f"term_{i}"
        conditions.append(
            f"(LOWER(qr.response) LIKE :{param_name} OR "
            f"LOWER(q.quote_explanation) LIKE :{param_name})"
        )
        params[param_name] = f"%{term.lower()}%"

    where_clause = " OR ".join(conditions) if conditions else "1=1"

    query = f"""
        SELECT
            qr.response AS original_request,
            q.total_amount,
            q.quote_explanation,
            q.job_type,
            q.order_size,
            q.event_type,
            q.order_date
        FROM quotes q
        JOIN quote_requests qr ON q.request_id = qr.id
        WHERE {where_clause}
        ORDER BY q.order_date DESC
        LIMIT {limit}
    """

    with db_engine.connect() as conn:
        result = conn.execute(text(query), params)
        return [dict(row._mapping) for row in result]

# =========================================================
# MULTI-AGENT SYSTEM STARTS HERE
# =========================================================

dotenv.load_dotenv(dotenv_path=".env")
openai_api_key = os.getenv("OPENAI_API_KEY")

model = OpenAIServerModel(
    model_id="gpt-4o-mini",
    api_base="https://api.openai.com/v1",
    api_key=openai_api_key,
)

CATALOG_DF = pd.DataFrame(paper_supplies)

# =========================================================
# PARSING HELPERS
# =========================================================

@dataclass
class ParsedItem:
    requested_name: str
    canonical_name: Optional[str]
    quantity: int
    unit_label: str = "units"


@dataclass
class ParsedRequest:
    raw_text: str
    request_date: str
    delivery_date: Optional[str]
    items: List[ParsedItem] = field(default_factory=list)


CATALOG_NAMES = [item["item_name"] for item in paper_supplies]


def normalize_text(s: str) -> str:
    s = s.lower().strip()
    s = s.replace("\n", " ")
    s = re.sub(r"\s+", " ", s)
    return s


def extract_request_date(request_text: str) -> str:
    match = re.search(r"Date of request:\s*(\d{4}-\d{2}-\d{2})", request_text)
    if match:
        return match.group(1)
    return datetime.now().strftime("%Y-%m-%d")


def extract_delivery_date(request_text: str) -> Optional[str]:
    match = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}",
        request_text,
        flags=re.IGNORECASE
    )
    if match:
        try:
            dt = datetime.strptime(match.group(0), "%B %d, %Y")
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return None
    return None


def get_unit_price(item_name: str) -> Optional[float]:
    match = CATALOG_DF[CATALOG_DF["item_name"] == item_name]
    if match.empty:
        return None
    return float(match.iloc[0]["unit_price"])


def compute_discount(total_units: int, subtotal: float) -> float:
    if total_units >= 3000:
        return round(subtotal * 0.12, 2)
    if total_units >= 1000:
        return round(subtotal * 0.08, 2)
    if total_units >= 500:
        return round(subtotal * 0.05, 2)
    return 0.0

# =========================================================
# TOOLS
# =========================================================

@tool
def inventory_snapshot_tool(as_of_date: str) -> Dict[str, int]:
    """Return all inventory quantities available as of a given ISO date.

    Args:
        as_of_date: ISO format date string to check inventory as of.
    """
    return get_all_inventory(as_of_date)


@tool
def stock_check_tool(item_name: str, as_of_date: str) -> Dict[str, Union[str, int]]:
    """Return current stock for a single item as of a given ISO date.

    Args:
        item_name: Name of the item to check stock for.
        as_of_date: ISO format date string to check stock as of.
    """
    df = get_stock_level(item_name, as_of_date)
    if df.empty:
        return {"item_name": item_name, "current_stock": 0}
    return {
        "item_name": item_name,
        "current_stock": int(df.iloc[0]["current_stock"])
    }


@tool
def supplier_eta_tool(input_date_str: str, quantity: int) -> str:
    """Return estimated supplier delivery date for a replenishment order.

    Args:
        input_date_str: ISO format date string for when the order is placed.
        quantity: Number of units to order.
    """
    return get_supplier_delivery_date(input_date_str, quantity)


@tool
def cash_balance_tool(as_of_date: str) -> float:
    """Return cash balance as of a given ISO date.

    Args:
        as_of_date: ISO format date string to check balance as of.
    """
    return get_cash_balance(as_of_date)


@tool
def financial_report_tool(as_of_date: str) -> Dict:
    """Return a financial report as of a given ISO date.

    Args:
        as_of_date: ISO format date string to generate report as of.
    """
    return generate_financial_report(as_of_date)


@tool
def quote_history_tool(search_terms: List[str], limit: int = 5) -> List[Dict]:
    """Search past quote history using keywords from a request.

    Args:
        search_terms: List of keywords to search for in quote history.
        limit: Maximum number of results to return.
    """
    return search_quote_history(search_terms, limit)


@tool
def create_sale_tool(item_name: str, quantity: int, price: float, date: str) -> int:
    """Create a sales transaction in the database.

    Args:
        item_name: Name of the item being sold.
        quantity: Number of units sold.
        price: Price per unit.
        date: ISO format date of the transaction.
    """
    return create_transaction(
        item_name=item_name,
        transaction_type="sales",
        quantity=quantity,
        price=price,
        date=date,
    )


@tool
def create_stock_order_tool(item_name: str, quantity: int, price: float, date: str) -> int:
    """Create a stock order transaction in the database.

    Args:
        item_name: Name of the item being ordered.
        quantity: Number of units to order.
        price: Price per unit.
        date: ISO format date of the transaction.
    """
    return create_transaction(
        item_name=item_name,
        transaction_type="stock_orders",
        quantity=quantity,
        price=price,
        date=date,
    )

# =========================================================
# AGENTS
# =========================================================

@tool
def get_catalog_items() -> str:
    """Return the full catalog of available paper supply items with names and unit prices.
    """
    return json.dumps(
        [{"item_name": item["item_name"], "unit_price": item["unit_price"]} for item in paper_supplies],
        indent=2
    )


class ParsingAgent(ToolCallingAgent):
    """Agent that uses LLM to parse customer requests into structured orders."""

    def __init__(self, model):
        super().__init__(
            tools=[get_catalog_items],
            model=model,
            name="request_parser",
            description=(
                "Parses natural language customer requests to extract ordered items, "
                "quantities, and match them to exact catalog item names."
            ),
        )

    def parse_request(self, request_text: str) -> ParsedRequest:
        request_date = extract_request_date(request_text)
        delivery_date = extract_delivery_date(request_text)

        catalog_str = json.dumps(CATALOG_NAMES)
        prompt = (
            "You are a precise order parser for a paper supply company.\n"
            f"Available catalog items: {catalog_str}\n\n"
            "Parse the customer request below and extract ALL ordered items.\n"
            "For each item determine:\n"
            "1. The quantity (integer)\n"
            "2. The EXACT matching catalog item name from the list above\n"
            "3. What the customer called it (raw name)\n\n"
            "Rules:\n"
            "- Each unique item must appear only ONCE (no duplicates)\n"
            "- If the same product is mentioned multiple times, sum the quantities\n"
            "- Match to the closest catalog name (e.g. 'standard printer paper' -> 'A4 paper')\n"
            "- If a size like 24x36 is specified, prefer the matching sized item\n"
            "- Only include items that can be matched to the catalog\n\n"
            "Return ONLY a valid JSON array, no explanation:\n"
            '[{"item": "exact catalog name", "quantity": 123, "raw_name": "customer term"}]\n\n'
            f"Customer request:\n{request_text}"
        )

        result = self.run(prompt)

        # Handle RunResult: may be a list of dicts directly or a string
        if isinstance(result, list):
            parsed_json = result
        else:
            result_str = str(result)
            parsed_json = []
            # Try JSON first, then Python literal eval for single-quoted dicts
            for parser in (json.loads, ast.literal_eval):
                try:
                    parsed_json = parser(result_str)
                    break
                except (json.JSONDecodeError, ValueError, SyntaxError):
                    continue
            if not parsed_json:
                match = re.search(r'\[.*\]', result_str, re.DOTALL)
                if match:
                    for parser in (json.loads, ast.literal_eval):
                        try:
                            parsed_json = parser(match.group())
                            break
                        except (json.JSONDecodeError, ValueError, SyntaxError):
                            continue

        seen_canonical = {}
        for entry in parsed_json:
            canonical = entry.get("item", "")
            qty = int(entry.get("quantity", 0))
            raw = entry.get("raw_name", canonical)

            if canonical not in CATALOG_DF["item_name"].values:
                continue
            if canonical in seen_canonical:
                seen_canonical[canonical].quantity += qty
                continue

            seen_canonical[canonical] = ParsedItem(
                requested_name=raw,
                canonical_name=canonical,
                quantity=qty,
            )

        items = list(seen_canonical.values())
        print("LLM parsed items:", [
            {"name": i.canonical_name, "qty": i.quantity} for i in items
        ])

        return ParsedRequest(
            raw_text=request_text,
            request_date=request_date,
            delivery_date=delivery_date,
            items=items,
        )


class InventoryAgent(ToolCallingAgent):
    """Agent responsible for managing paper inventory."""

    def __init__(self, model):
        super().__init__(
            tools=[
                inventory_snapshot_tool,
                stock_check_tool,
                supplier_eta_tool,
                cash_balance_tool,
                financial_report_tool,
            ],
            model=model,
            name="inventory_manager",
            description="Agent responsible for tracking stock, shortages, reorder feasibility, and delivery timing."
        )

    def assess_request(self, parsed: ParsedRequest) -> Dict:
        assessment = {
            "supported_items": [],
            "unsupported_items": [],
            "in_stock_items": [],
            "reorder_items": [],
            "blocked_items": [],
            "can_fulfill": True,
            "reason": [],
        }

        cash = cash_balance_tool(parsed.request_date)

        for item in parsed.items:
            if not item.canonical_name:
                assessment["unsupported_items"].append({
                    "requested_name": item.requested_name,
                    "quantity": item.quantity,
                    "reason": "Item could not be matched to catalog"
                })
                assessment["can_fulfill"] = False
                assessment["reason"].append(f"Unsupported item: {item.requested_name}")
                continue

            unit_price = get_unit_price(item.canonical_name)
            stock_info = stock_check_tool(item.canonical_name, parsed.request_date)
            stock = int(stock_info["current_stock"])

            if stock >= item.quantity:
                assessment["supported_items"].append(item)
                assessment["in_stock_items"].append({
                    "item_name": item.canonical_name,
                    "quantity": item.quantity,
                    "stock_available": stock,
                    "unit_price": unit_price,
                })
                continue

            shortage = item.quantity - stock
            eta = supplier_eta_tool(parsed.request_date, shortage)
            reorder_cost = shortage * unit_price if unit_price is not None else float("inf")

            can_reorder = (
                parsed.delivery_date is not None and
                eta <= parsed.delivery_date and
                cash >= reorder_cost
            )

            if can_reorder:
                assessment["supported_items"].append(item)
                assessment["reorder_items"].append({
                    "item_name": item.canonical_name,
                    "requested_qty": item.quantity,
                    "stock_available": stock,
                    "shortage": shortage,
                    "eta": eta,
                    "unit_price": unit_price,
                    "reorder_cost": reorder_cost,
                })
            else:
                reasons = []
                if parsed.delivery_date is None:
                    reasons.append("missing delivery date")
                elif eta > parsed.delivery_date:
                    reasons.append(f"supplier ETA {eta} misses requested delivery date {parsed.delivery_date}")
                if cash < reorder_cost:
                    reasons.append("insufficient cash for replenishment")

                assessment["blocked_items"].append({
                    "item_name": item.canonical_name,
                    "requested_qty": item.quantity,
                    "stock_available": stock,
                    "shortage": shortage,
                    "eta": eta,
                    "reorder_cost": reorder_cost,
                    "reason": "; ".join(reasons) if reasons else "cannot replenish in time",
                })
                assessment["can_fulfill"] = False
                assessment["reason"].append(f"{item.canonical_name}: {assessment['blocked_items'][-1]['reason']}")

        return assessment


class QuotingAgent(ToolCallingAgent):
    """Agent responsible for providing quotes to customer quoting requests."""

    def __init__(self, model):
        super().__init__(
            tools=[
                quote_history_tool,
                stock_check_tool,
                cash_balance_tool,
                financial_report_tool,
            ],
            model=model,
            name="quote_processor",
            description="Agent responsible for generating transparent, customer-facing quotes using pricing and quote history."
        )

    def generate_quote(self, parsed: ParsedRequest, inventory_assessment: Dict) -> Dict:
        searchable_terms = []
        for item in parsed.items:
            searchable_terms.extend(normalize_text(item.requested_name).split()[:3])

        history = quote_history_tool(searchable_terms[:5], limit=3)

        line_items = []
        subtotal = 0.0
        total_units = 0

        for item in inventory_assessment["supported_items"]:
            unit_price = get_unit_price(item.canonical_name)
            if unit_price is None:
                continue

            line_total = round(item.quantity * unit_price, 2)
            subtotal += line_total
            total_units += item.quantity

            line_items.append({
                "requested_name": item.requested_name,
                "item_name": item.canonical_name,
                "quantity": item.quantity,
                "unit_price": unit_price,
                "line_total": line_total,
            })

        discount = compute_discount(total_units, subtotal)
        total = round(subtotal - discount, 2)

        explanation_parts = []
        if line_items:
            explanation_parts.append(
                f"The quote uses current catalog pricing for {len(line_items)} matched item(s)."
            )
        if discount > 0:
            explanation_parts.append(
                f"A bulk discount of ${discount:.2f} was applied based on the order size."
            )
        if history:
            explanation_parts.append(
                f"Similar historical quotes were reviewed for consistency."
            )

        return {
            "line_items": line_items,
            "subtotal": round(subtotal, 2),
            "discount": discount,
            "total": total,
            "historical_matches": history,
            "quote_explanation": " ".join(explanation_parts) if explanation_parts else "Standard quote generated."
        }


class OrderingAgent(ToolCallingAgent):
    """Agent responsible for processing customer orders."""

    def __init__(self, model):
        super().__init__(
            tools=[
                create_sale_tool,
                create_stock_order_tool,
                stock_check_tool,
            ],
            model=model,
            name="order_processor",
            description="Agent responsible for committing stock replenishment and sales transactions."
        )

    def finalize_order(self, parsed: ParsedRequest, inventory_assessment: Dict, quote: Dict) -> Dict:
        executed_transactions = []

        for item in inventory_assessment["reorder_items"]:
            stock_order_id = create_stock_order_tool(
                item_name=item["item_name"],
                quantity=int(item["shortage"]),
                price=round(item["shortage"] * item["unit_price"], 2),
                date=parsed.request_date,
            )
            executed_transactions.append({
                "type": "stock_order",
                "id": stock_order_id,
                "item_name": item["item_name"],
                "quantity": int(item["shortage"]),
            })

        discount_ratio = 0.0
        if quote["subtotal"] > 0:
            discount_ratio = quote["discount"] / quote["subtotal"]

        for line in quote["line_items"]:
            undiscounted = line["line_total"]
            discounted_line_total = round(undiscounted * (1 - discount_ratio), 2)

            sale_id = create_sale_tool(
                item_name=line["item_name"],
                quantity=int(line["quantity"]),
                price=discounted_line_total,
                date=parsed.request_date,
            )
            executed_transactions.append({
                "type": "sale",
                "id": sale_id,
                "item_name": line["item_name"],
                "quantity": int(line["quantity"]),
            })

        return {
            "status": "fulfilled",
            "transactions": executed_transactions
        }


class Orchestrator(ToolCallingAgent):
    """Orchestrator that coordinates workflow between specialized agents."""

    def __init__(self, model):
        self.model = model

        self.parser = ParsingAgent(model)
        self.inventory_manager = InventoryAgent(model)
        self.quote_processor = QuotingAgent(model)
        self.order_processor = OrderingAgent(model)

        super().__init__(
            tools=[],
            model=model,
            name="orchestrator",
            description=(
                "Receives customer requests, delegates parsing, inventory checking, "
                "quote generation, and order finalization to worker agents."
            ),
        )

    def process_order(self, customer_request: str) -> str:
        parsed = self.parser.parse_request(customer_request)

        if not parsed.items:
            return (
                "We could not identify any orderable paper items in your request. "
                "Please resend your request with quantities and product descriptions."
            )

        inventory_assessment = self.inventory_manager.assess_request(parsed)

        if len(inventory_assessment["supported_items"]) == 0:
            unsupported = inventory_assessment["unsupported_items"] + inventory_assessment["blocked_items"]
            reasons = "; ".join(
                [f"{x.get('requested_name', x.get('item_name'))}: {x.get('reason', 'not available')}" for x in unsupported]
            )
            return (
                "We are unable to fulfill this request at this time. "
                f"Reason(s): {reasons}."
            )

        if not inventory_assessment["can_fulfill"]:
            blocked_reasons = "; ".join(
                [f"{x['item_name']}: {x['reason']}" for x in inventory_assessment["blocked_items"]]
            )
            unsupported_reasons = "; ".join(
                [f"{x['requested_name']}: {x['reason']}" for x in inventory_assessment["unsupported_items"]]
            )

            all_reasons = "; ".join([r for r in [blocked_reasons, unsupported_reasons] if r])

            return (
                "We can quote some matched items, but we cannot fully fulfill the complete request "
                f"by the requested timeline. Reason(s): {all_reasons}."
            )

        quote = self.quote_processor.generate_quote(parsed, inventory_assessment)
        order_result = self.order_processor.finalize_order(parsed, inventory_assessment, quote)

        items_summary = ", ".join(
            [f"{li['quantity']} x {li['item_name']}" for li in quote["line_items"]]
        )

        delivery_phrase = (
            f" Estimated delivery target: {parsed.delivery_date}."
            if parsed.delivery_date else ""
        )

        return (
            f"Order confirmed. Items: {items_summary}. "
            f"Quoted total: ${quote['total']:.2f} "
            f"(subtotal ${quote['subtotal']:.2f}, discount ${quote['discount']:.2f}). "
            f"{quote['quote_explanation']}{delivery_phrase}"
        )

# =========================================================
# TEST SCENARIOS
# =========================================================

def run_test_scenarios():
    print("Initializing Database...")
    init_database()

    try:
        quote_requests_sample = pd.read_csv("quote_requests_sample.csv")
        quote_requests_sample["request_date"] = pd.to_datetime(
            quote_requests_sample["request_date"], format="%m/%d/%y", errors="coerce"
        )
        quote_requests_sample.dropna(subset=["request_date"], inplace=True)
        quote_requests_sample = quote_requests_sample.sort_values("request_date")
    except Exception as e:
        print(f"FATAL: Error loading test data: {e}")
        return

    initial_date = quote_requests_sample["request_date"].min().strftime("%Y-%m-%d")
    report = generate_financial_report(initial_date)
    current_cash = report["cash_balance"]
    current_inventory = report["inventory_value"]

    orchestrator = Orchestrator(model)

    results = []
    for idx, row in quote_requests_sample.iterrows():
        request_date = row["request_date"].strftime("%Y-%m-%d")

        print(f"\n=== Request {idx+1} ===")
        print(f"Context: {row['job']} organizing {row['event']}")
        print(f"Request Date: {request_date}")
        print(f"Cash Balance: ${current_cash:.2f}")
        print(f"Inventory Value: ${current_inventory:.2f}")

        request_with_date = f"{row['request']} (Date of request: {request_date})"

        response = orchestrator.process_order(request_with_date)

        report = generate_financial_report(request_date)
        current_cash = report["cash_balance"]
        current_inventory = report["inventory_value"]

        print(f"Response: {response}")
        print(f"Updated Cash: ${current_cash:.2f}")
        print(f"Updated Inventory: ${current_inventory:.2f}")

        results.append(
            {
                "request_id": idx + 1,
                "request_date": request_date,
                "cash_balance": current_cash,
                "inventory_value": current_inventory,
                "response": response,
            }
        )

        time.sleep(1)

    final_date = quote_requests_sample["request_date"].max().strftime("%Y-%m-%d")
    final_report = generate_financial_report(final_date)
    print("\n===== FINAL FINANCIAL REPORT =====")
    print(f"Final Cash: ${final_report['cash_balance']:.2f}")
    print(f"Final Inventory: ${final_report['inventory_value']:.2f}")

    pd.DataFrame(results).to_csv("test_results.csv", index=False)
    return results


if __name__ == "__main__":
    results = run_test_scenarios()