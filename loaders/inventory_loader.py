"""
Inventory data loaders for QB costs and EMR inventory.
"""

import pandas as pd

from config import ITEM_COST_FILE, EMR_INVENTORY_FILE
from db.connection import get_connection


def load_qb_item_costs(filepath=None):
    """
    Read item_cost.xlsx (QuickBooks export).

    Columns used: Type, Item, Cost, COGS Account, Active Status
    Filters to Inventory Part / Inventory Assembly, Active only.
    """
    path = filepath or ITEM_COST_FILE
    df = pd.read_excel(path)

    # Filter to inventory types only (skip Service, Discount, etc.)
    inventory_types = {"Inventory Part", "Inventory Assembly"}
    df = df[df["Type"].isin(inventory_types)].copy()

    # Filter to active items
    df = df[df["Active Status"] == "Active"].copy()

    # Rename columns
    df = df.rename(columns={
        "Item": "qb_item_name",
        "Cost": "unit_cost",
        "COGS Account": "cogs_account",
    })

    # Clean cost
    df["unit_cost"] = pd.to_numeric(df["unit_cost"], errors="coerce").fillna(0)

    # Keep only needed columns
    cols = ["qb_item_name", "unit_cost", "cogs_account"]
    for col in cols:
        if col not in df.columns:
            df[col] = None

    return df[cols].reset_index(drop=True)


def load_emr_inventory(filepath=None):
    """
    Read skinfix_inventory.xlsx (EMR export).

    Columns: Product Name, SKU, QTY, Price, Product Type, Status
    Filters to Active items. Cleans Price column (removes '$').
    """
    path = filepath or EMR_INVENTORY_FILE
    df = pd.read_excel(path)

    # Filter to active items
    if "Status" in df.columns:
        df = df[df["Status"] == "Active"].copy()

    # Rename columns
    df = df.rename(columns={
        "Product Name": "emr_product_name",
        "QTY": "quantity",
        "Price": "selling_price",
        "Product Type": "category",
    })

    # Clean price - remove '$' and commas, convert to float
    df["selling_price"] = (
        df["selling_price"]
        .astype(str)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.strip()
    )
    df["selling_price"] = pd.to_numeric(df["selling_price"], errors="coerce").fillna(0)

    # Clean quantity
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0)

    # Clean SKU
    if "SKU" in df.columns:
        df["sku"] = df["SKU"].astype(str).str.strip()
    else:
        df["sku"] = ""

    cols = ["emr_product_name", "sku", "quantity", "selling_price", "category"]
    for col in cols:
        if col not in df.columns:
            df[col] = None

    return df[cols].reset_index(drop=True)


def store_qb_items_to_db(df, conn=None):
    """
    Insert/update inventory_items table from QB data.
    Match on qb_item_name. Returns count of rows upserted.
    """
    close_conn = conn is None
    if conn is None:
        conn = get_connection()

    count = 0
    for _, row in df.iterrows():
        name = str(row["qb_item_name"])
        conn.execute(
            """INSERT INTO inventory_items (qb_item_name, unit_cost, cogs_account)
               VALUES (?, ?, ?)
               ON CONFLICT(item_id) DO NOTHING""",
            (name, float(row.get("unit_cost", 0)),
             str(row.get("cogs_account", "") or "")),
        )
        # Use upsert logic: check if exists, then insert or update
        existing = conn.execute(
            "SELECT item_id FROM inventory_items WHERE qb_item_name = ?",
            (name,),
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE inventory_items
                   SET unit_cost = ?, cogs_account = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE qb_item_name = ?""",
                (float(row.get("unit_cost", 0)),
                 str(row.get("cogs_account", "") or ""),
                 name),
            )
        else:
            conn.execute(
                """INSERT INTO inventory_items
                   (qb_item_name, unit_cost, cogs_account)
                   VALUES (?, ?, ?)""",
                (name, float(row.get("unit_cost", 0)),
                 str(row.get("cogs_account", "") or "")),
            )
        count += 1

    conn.commit()
    if close_conn:
        conn.close()
    return count


def store_emr_inventory_to_db(df, conn=None):
    """
    Insert/update inventory_items table from EMR data.
    Match on emr_product_name. Returns count of rows upserted.
    """
    close_conn = conn is None
    if conn is None:
        conn = get_connection()

    count = 0
    for _, row in df.iterrows():
        name = str(row["emr_product_name"])
        existing = conn.execute(
            "SELECT item_id FROM inventory_items WHERE emr_product_name = ?",
            (name,),
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE inventory_items
                   SET sku = ?, category = ?, selling_price = ?,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE emr_product_name = ?""",
                (str(row.get("sku", "") or ""),
                 str(row.get("category", "") or ""),
                 float(row.get("selling_price", 0)),
                 name),
            )
        else:
            conn.execute(
                """INSERT INTO inventory_items
                   (emr_product_name, sku, category, selling_price)
                   VALUES (?, ?, ?, ?)""",
                (name,
                 str(row.get("sku", "") or ""),
                 str(row.get("category", "") or ""),
                 float(row.get("selling_price", 0))),
            )
        count += 1

    conn.commit()
    if close_conn:
        conn.close()
    return count


def create_inventory_snapshot(conn=None, as_of_date=None, source="initial_load"):
    """
    For each inventory_item, create a snapshot record.
    Pull quantity from latest EMR load, unit_cost from latest QB load.
    Returns count of snapshots created.
    """
    close_conn = conn is None
    if conn is None:
        conn = get_connection()

    if as_of_date is None:
        as_of_date = pd.Timestamp.now().strftime("%Y-%m-%d")

    rows = conn.execute(
        "SELECT item_id, unit_cost FROM inventory_items WHERE is_active = 1"
    ).fetchall()

    count = 0
    for row in rows:
        item_id = row[0]
        unit_cost = row[1] or 0

        # Get quantity from EMR inventory (stored via emr_product_name link)
        qty_row = conn.execute(
            """SELECT ii.selling_price
               FROM inventory_items ii
               WHERE ii.item_id = ?""",
            (item_id,),
        ).fetchone()

        # For initial load, use a placeholder quantity of 0
        # (real quantity comes from EMR inventory load, linked separately)
        conn.execute(
            """INSERT INTO inventory_snapshots
               (item_id, as_of_date, quantity_on_hand, unit_cost, source)
               VALUES (?, ?, ?, ?, ?)""",
            (item_id, as_of_date, 0, unit_cost, source),
        )
        count += 1

    conn.commit()
    if close_conn:
        conn.close()
    return count


if __name__ == "__main__":
    qb_df = load_qb_item_costs()
    print(f"Loaded {len(qb_df)} QB items with costs")

    emr_df = load_emr_inventory()
    print(f"Loaded {len(emr_df)} EMR inventory items")

    # Test matching
    from matching.inventory_matcher import match_inventory_items
    matched, unmatched = match_inventory_items(qb_df, emr_df)
    print(f"Auto-matched: {len(matched[matched['match_status'] == 'auto'])}")
    print(f"Pending review: {len(matched[matched['match_status'] == 'pending'])}")
    print(f"No match found: {len(unmatched)}")
