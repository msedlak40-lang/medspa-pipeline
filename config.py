import os

# ---------- PATHS ----------

INPUT_DIR = "input"
OUTPUT_DIR = "output"

STATE_DIR = "state"
LEDGER_FILE = os.path.join(STATE_DIR, "posted_ledger.csv")

EMR_FILE = os.path.join(INPUT_DIR, "emr_transactions.xlsx")
GRAVITY_FILE = os.path.join(INPUT_DIR, "gravity_payments.csv")
COA_FILE = os.path.join(INPUT_DIR, "COA_Quickbooks_matched.xlsx")
CUSTOMER_MASTER_FILE = os.path.join(INPUT_DIR, "customer_master.xlsx")
EMR_TIPS_BASE = os.path.join(INPUT_DIR, "emr_tips")  # .xlsx or .csv

SERVICE_SHEET = "emr_service_items"
PAYMENT_SHEET = "emr_payment_types"

# ---------- ACCOUNTS ----------

MERCHANT_CLEARING_ACCOUNT = "1030 Merchant Clearing"

# ---------- INVENTORY ----------

ITEM_COST_FILE = os.path.join(INPUT_DIR, "item_cost.xlsx")
EMR_INVENTORY_FILE = os.path.join(INPUT_DIR, "skinfix_inventory.xlsx")

# ---------- DATABASE ----------

DB_FILE = os.path.join(STATE_DIR, "pipeline.db")
