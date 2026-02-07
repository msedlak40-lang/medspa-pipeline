from db.connection import get_connection

SCHEMA_SQL = """
-- Pipeline run tracking
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id          TEXT PRIMARY KEY,
    run_timestamp   TEXT NOT NULL,
    run_status      TEXT NOT NULL DEFAULT 'started',
    emr_rows        INTEGER,
    gravity_rows    INTEGER,
    invoices_exported   INTEGER,
    payments_exported   INTEGER,
    cash_exported       INTEGER,
    jes_exported        INTEGER
);

-- Raw EMR transactions per run
CREATE TABLE IF NOT EXISTS emr_transactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL,
    visit_date      TEXT,
    invoice_number  TEXT,
    patient_id      TEXT,
    patient_name    TEXT,
    service_text    TEXT,
    sku             TEXT,
    staff           TEXT,
    quantity        REAL,
    price           REAL,
    discounts       REAL,
    tax             REAL,
    total_due       REAL,
    amount          REAL,
    payment_type    TEXT,
    service_amount  REAL,
    FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id)
);

-- EMR tips per run
CREATE TABLE IF NOT EXISTS emr_tips (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL,
    invoice_number  TEXT,
    tip_total_invoice REAL,
    FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id)
);

-- Gravity payments per run
CREATE TABLE IF NOT EXISTS gravity_payments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL,
    settlement_date TEXT,
    amount          REAL,
    card_type       TEXT,
    transaction_id  TEXT,
    is_refund       INTEGER,
    sale_amount     REAL,
    tip             REAL,
    type            TEXT,
    card            TEXT,
    name            TEXT,
    cashier         TEXT,
    source          TEXT,
    FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id)
);

-- Customer master (persistent across runs)
CREATE TABLE IF NOT EXISTS customer_master (
    patient_id      TEXT PRIMARY KEY,
    patient_name    TEXT NOT NULL,
    first_seen      TEXT,
    last_seen       TEXT
);

-- Customer name change audit trail
CREATE TABLE IF NOT EXISTS customer_name_changes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id      TEXT NOT NULL,
    old_name        TEXT,
    new_name        TEXT,
    detected_at     TEXT NOT NULL,
    resolution_status TEXT DEFAULT 'unresolved'
);

-- Service mappings (loaded from COA)
CREATE TABLE IF NOT EXISTS service_mappings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    emr_service_text TEXT NOT NULL,
    matched_item    TEXT,
    taxcode         TEXT,
    is_active       INTEGER DEFAULT 1
);

-- Payment mappings (loaded from COA)
CREATE TABLE IF NOT EXISTS payment_mappings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_type    TEXT NOT NULL,
    mapped_to_account TEXT,
    is_active       INTEGER DEFAULT 1
);

-- Payment match results per run
CREATE TABLE IF NOT EXISTS payment_matches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL,
    gravity_transaction_id TEXT,
    emr_invoice     TEXT,
    match_type      TEXT,
    confidence      TEXT,
    date_diff_days  INTEGER,
    FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id)
);

-- Unmatched Gravity payments per run
CREATE TABLE IF NOT EXISTS unmatched_gravity_payments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL,
    gravity_transaction_id TEXT,
    amount          REAL,
    reason_code     TEXT,
    FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id)
);

-- Unmapped services per run
CREATE TABLE IF NOT EXISTS unmapped_services (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL,
    service_text    TEXT,
    occurrence_count INTEGER DEFAULT 1
);

-- Unmapped payments per run
CREATE TABLE IF NOT EXISTS unmapped_payments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL,
    payment_type    TEXT,
    occurrence_count INTEGER DEFAULT 1
);

-- Export history per run
CREATE TABLE IF NOT EXISTS export_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL,
    file_name       TEXT NOT NULL,
    record_count    INTEGER,
    exported_at     TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id)
);

-- Master inventory items (merged from QB + EMR)
CREATE TABLE IF NOT EXISTS inventory_items (
    item_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    qb_item_name    TEXT,
    emr_product_name TEXT,
    sku             TEXT,
    category        TEXT,
    unit_cost       REAL DEFAULT 0,
    selling_price   REAL DEFAULT 0,
    cogs_account    TEXT,
    is_active       INTEGER DEFAULT 1,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- QB to EMR item mapping (for fuzzy match results)
CREATE TABLE IF NOT EXISTS item_mapping (
    mapping_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    qb_item_name    TEXT NOT NULL,
    emr_product_name TEXT,
    match_confidence REAL,
    match_status    TEXT CHECK(match_status IN ('auto', 'confirmed', 'rejected', 'pending')),
    matched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Point-in-time inventory snapshots
CREATE TABLE IF NOT EXISTS inventory_snapshots (
    snapshot_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id         INTEGER,
    as_of_date      DATE NOT NULL,
    quantity_on_hand REAL,
    unit_cost       REAL,
    source          TEXT CHECK(source IN ('initial_load', 'count', 'derived')),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES inventory_items(item_id)
);

-- Inventory movements (purchases, usage, adjustments)
CREATE TABLE IF NOT EXISTS inventory_transactions (
    txn_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id         INTEGER,
    run_id          TEXT,
    txn_date        DATE NOT NULL,
    txn_type        TEXT CHECK(txn_type IN ('purchase', 'usage', 'adjustment')),
    quantity        REAL,
    unit_cost       REAL,
    source          TEXT,
    reference_id    TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES inventory_items(item_id)
);

-- Links services to inventory products used
CREATE TABLE IF NOT EXISTS service_product_mapping (
    mapping_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    service_item    TEXT NOT NULL,
    item_id         INTEGER,
    quantity_per_service REAL DEFAULT 1,
    is_active       INTEGER DEFAULT 1,
    FOREIGN KEY (item_id) REFERENCES inventory_items(item_id)
);
"""


def init_database():
    conn = get_connection()
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()
