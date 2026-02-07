import pandas as pd

from db.connection import get_connection


# ---------- PIPELINE RUNS ----------

def create_run(run_id: str):
    conn = get_connection()
    conn.execute(
        "INSERT INTO pipeline_runs (run_id, run_timestamp, run_status) VALUES (?, ?, ?)",
        (run_id, pd.Timestamp.utcnow().isoformat(), "started"),
    )
    conn.commit()
    conn.close()


def update_run_status(run_id: str, status: str, **stats):
    conn = get_connection()
    set_clauses = ["run_status = ?"]
    params = [status]
    for col in ("emr_rows", "gravity_rows", "invoices_exported",
                "payments_exported", "cash_exported", "jes_exported"):
        if col in stats:
            set_clauses.append(f"{col} = ?")
            params.append(stats[col])
    params.append(run_id)
    conn.execute(
        f"UPDATE pipeline_runs SET {', '.join(set_clauses)} WHERE run_id = ?",
        params,
    )
    conn.commit()
    conn.close()


# ---------- EMR TRANSACTIONS ----------

def store_emr_transactions(run_id: str, emr_df: pd.DataFrame):
    conn = get_connection()
    cols = [
        "visit_date", "invoice_number", "patient_id", "patient_name",
        "service_text", "sku", "staff", "quantity", "price", "discounts",
        "tax", "total_due", "amount", "payment_type", "service_amount",
    ]
    df = emr_df.copy()
    df["run_id"] = run_id
    if "visit_date" in df.columns:
        df["visit_date"] = df["visit_date"].astype(str)
    for col in cols:
        if col not in df.columns:
            df[col] = None
    df[["run_id"] + cols].to_sql("emr_transactions", conn, if_exists="append", index=False)
    conn.close()


# ---------- EMR TIPS ----------

def store_emr_tips(run_id: str, tips_df: pd.DataFrame):
    if tips_df.empty:
        return
    conn = get_connection()
    df = tips_df.copy()
    df["run_id"] = run_id
    df[["run_id", "invoice_number", "tip_total_invoice"]].to_sql(
        "emr_tips", conn, if_exists="append", index=False
    )
    conn.close()


# ---------- GRAVITY PAYMENTS ----------

def store_gravity_payments(run_id: str, gravity_df: pd.DataFrame):
    conn = get_connection()
    df = gravity_df.copy()
    df["run_id"] = run_id
    if "settlement_date" in df.columns:
        df["settlement_date"] = df["settlement_date"].astype(str)
    df["is_refund"] = df["is_refund"].astype(int)
    cols = [
        "run_id", "settlement_date", "amount", "card_type", "transaction_id",
        "is_refund", "sale_amount", "tip", "type", "card", "name", "cashier", "source",
    ]
    for col in cols:
        if col not in df.columns:
            df[col] = None
    df[cols].to_sql("gravity_payments", conn, if_exists="append", index=False)
    conn.close()


# ---------- CUSTOMER MASTER ----------

def upsert_customer_master(master_df: pd.DataFrame):
    conn = get_connection()
    now = pd.Timestamp.utcnow().isoformat()
    for _, row in master_df.iterrows():
        conn.execute(
            """INSERT INTO customer_master (patient_id, patient_name, first_seen, last_seen)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(patient_id) DO UPDATE SET
                   patient_name = excluded.patient_name,
                   last_seen = excluded.last_seen""",
            (str(row["patient_id"]), str(row["patient_name"]), now, now),
        )
    conn.commit()
    conn.close()


def store_name_conflicts(conflicts_df: pd.DataFrame):
    if conflicts_df.empty:
        return
    conn = get_connection()
    now = pd.Timestamp.utcnow().isoformat()
    for _, row in conflicts_df.iterrows():
        conn.execute(
            """INSERT INTO customer_name_changes
               (patient_id, old_name, new_name, detected_at)
               VALUES (?, ?, ?, ?)""",
            (str(row["patient_id"]), str(row.get("master_patient_name", "")),
             str(row["patient_name"]), now),
        )
    conn.commit()
    conn.close()


# ---------- MAPPINGS ----------

def store_service_mappings(service_map_df: pd.DataFrame):
    conn = get_connection()
    conn.execute("DELETE FROM service_mappings")
    for _, row in service_map_df.iterrows():
        conn.execute(
            "INSERT INTO service_mappings (emr_service_text, matched_item, taxcode) VALUES (?, ?, ?)",
            (str(row.get("emr_service_text", "")),
             str(row.get("matched_item", "")),
             str(row.get("taxcode", ""))),
        )
    conn.commit()
    conn.close()


def store_payment_mappings(payment_map_df: pd.DataFrame):
    conn = get_connection()
    conn.execute("DELETE FROM payment_mappings")
    for _, row in payment_map_df.iterrows():
        conn.execute(
            "INSERT INTO payment_mappings (payment_type, mapped_to_account) VALUES (?, ?)",
            (str(row.get("payment_type", "")),
             str(row.get("mapped_to_account", ""))),
        )
    conn.commit()
    conn.close()


# ---------- MATCH RESULTS ----------

def store_payment_matches(run_id: str, matched_df: pd.DataFrame):
    if matched_df.empty:
        return
    conn = get_connection()
    for _, row in matched_df.iterrows():
        conn.execute(
            """INSERT INTO payment_matches
               (run_id, gravity_transaction_id, emr_invoice, match_type, confidence)
               VALUES (?, ?, ?, ?, ?)""",
            (run_id, str(row.get("transaction_id", "")),
             str(row.get("ApplyToRefNumber", "")), "amount+date", "matched"),
        )
    conn.commit()
    conn.close()


def store_unmatched_gravity(run_id: str, unmatched_df: pd.DataFrame):
    if unmatched_df.empty:
        return
    conn = get_connection()
    for _, row in unmatched_df.iterrows():
        conn.execute(
            """INSERT INTO unmatched_gravity_payments
               (run_id, gravity_transaction_id, amount, reason_code)
               VALUES (?, ?, ?, ?)""",
            (run_id, str(row.get("transaction_id", "")),
             float(row.get("amount", 0)), "no_match"),
        )
    conn.commit()
    conn.close()


# ---------- UNMAPPED ----------

def store_unmapped_services(run_id: str, unmapped_df: pd.DataFrame):
    if unmapped_df.empty:
        return
    conn = get_connection()
    for _, row in unmapped_df.iterrows():
        conn.execute(
            "INSERT INTO unmapped_services (run_id, service_text) VALUES (?, ?)",
            (run_id, str(row.get("unmapped_service_text", row.get("service_text", "")))),
        )
    conn.commit()
    conn.close()


def store_unmapped_payments(run_id: str, unmapped_df: pd.DataFrame):
    if unmapped_df.empty:
        return
    conn = get_connection()
    for _, row in unmapped_df.iterrows():
        conn.execute(
            "INSERT INTO unmapped_payments (run_id, payment_type) VALUES (?, ?)",
            (run_id, str(row.get("unmapped_payment_type", row.get("payment_type", "")))),
        )
    conn.commit()
    conn.close()


# ---------- INVENTORY ----------

def insert_inventory_item(conn, item_data):
    """Insert a new inventory item. Returns item_id."""
    cur = conn.execute(
        """INSERT INTO inventory_items
           (qb_item_name, emr_product_name, sku, category,
            unit_cost, selling_price, cogs_account)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (item_data.get("qb_item_name"),
         item_data.get("emr_product_name"),
         item_data.get("sku"),
         item_data.get("category"),
         item_data.get("unit_cost", 0),
         item_data.get("selling_price", 0),
         item_data.get("cogs_account")),
    )
    conn.commit()
    return cur.lastrowid


def update_inventory_item(conn, item_id, item_data):
    """Update an existing inventory item. Returns True on success."""
    set_parts = []
    params = []
    for col in ("qb_item_name", "emr_product_name", "sku", "category",
                "unit_cost", "selling_price", "cogs_account", "is_active"):
        if col in item_data:
            set_parts.append(f"{col} = ?")
            params.append(item_data[col])
    if not set_parts:
        return False
    set_parts.append("updated_at = CURRENT_TIMESTAMP")
    params.append(item_id)
    conn.execute(
        f"UPDATE inventory_items SET {', '.join(set_parts)} WHERE item_id = ?",
        params,
    )
    conn.commit()
    return True


def get_inventory_item_by_qb_name(conn, qb_item_name):
    """Look up an inventory item by QB name. Returns dict or None."""
    row = conn.execute(
        "SELECT * FROM inventory_items WHERE qb_item_name = ?",
        (qb_item_name,),
    ).fetchone()
    return dict(row) if row else None


def get_inventory_item_by_emr_name(conn, emr_product_name):
    """Look up an inventory item by EMR name. Returns dict or None."""
    row = conn.execute(
        "SELECT * FROM inventory_items WHERE emr_product_name = ?",
        (emr_product_name,),
    ).fetchone()
    return dict(row) if row else None


def insert_inventory_snapshot(conn, snapshot_data):
    """Insert an inventory snapshot record. Returns snapshot_id."""
    cur = conn.execute(
        """INSERT INTO inventory_snapshots
           (item_id, as_of_date, quantity_on_hand, unit_cost, source)
           VALUES (?, ?, ?, ?, ?)""",
        (snapshot_data["item_id"],
         snapshot_data["as_of_date"],
         snapshot_data.get("quantity_on_hand", 0),
         snapshot_data.get("unit_cost", 0),
         snapshot_data.get("source", "initial_load")),
    )
    conn.commit()
    return cur.lastrowid


def insert_inventory_transaction(conn, txn_data):
    """Insert an inventory transaction record. Returns txn_id."""
    cur = conn.execute(
        """INSERT INTO inventory_transactions
           (item_id, run_id, txn_date, txn_type, quantity, unit_cost, source, reference_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (txn_data["item_id"],
         txn_data.get("run_id"),
         txn_data["txn_date"],
         txn_data["txn_type"],
         txn_data.get("quantity", 0),
         txn_data.get("unit_cost", 0),
         txn_data.get("source"),
         txn_data.get("reference_id")),
    )
    conn.commit()
    return cur.lastrowid


# ---------- EXPORT HISTORY ----------

def record_export(run_id: str, file_name: str, record_count: int):
    conn = get_connection()
    conn.execute(
        """INSERT INTO export_history (run_id, file_name, record_count, exported_at)
           VALUES (?, ?, ?, ?)""",
        (run_id, file_name, record_count, pd.Timestamp.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
