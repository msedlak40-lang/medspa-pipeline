"""
Fuzzy matching between QB item names and EMR product names.
Uses rapidfuzz for fast string similarity.
"""

import pandas as pd
from rapidfuzz import fuzz

from db.connection import get_connection


def _normalize_name(name):
    """Strip QB hierarchy prefix (e.g. 'Injectables:Botox...' -> 'Botox...')."""
    s = str(name).strip()
    if ":" in s:
        s = s.split(":")[-1].strip()
    return s.lower()


def match_inventory_items(qb_items_df, emr_items_df, threshold=85):
    """
    For each QB item, find best EMR match by name using fuzzy matching.

    Returns (matched_df, unmatched_df).
      matched_df columns: qb_item_name, emr_product_name, confidence, match_status
      unmatched_df: QB items with no match above any reasonable score
    """
    qb = qb_items_df.copy()
    emr = emr_items_df.copy()

    emr_names = emr["emr_product_name"].dropna().unique().tolist()
    emr_names_lower = [str(n).strip().lower() for n in emr_names]

    matched_rows = []
    unmatched_rows = []

    for _, qb_row in qb.iterrows():
        qb_name = str(qb_row["qb_item_name"])
        qb_norm = _normalize_name(qb_name)

        best_score = 0
        best_emr_name = None

        for emr_name, emr_lower in zip(emr_names, emr_names_lower):
            # Use token_sort_ratio for robustness against word order differences
            score = fuzz.token_sort_ratio(qb_norm, emr_lower)
            if score > best_score:
                best_score = score
                best_emr_name = emr_name

        if best_emr_name is not None and best_score >= 50:
            status = "auto" if best_score >= threshold else "pending"
            matched_rows.append({
                "qb_item_name": qb_name,
                "emr_product_name": best_emr_name,
                "confidence": round(best_score, 1),
                "match_status": status,
            })
        else:
            unmatched_rows.append({
                "qb_item_name": qb_name,
                "best_emr_candidate": best_emr_name,
                "best_score": round(best_score, 1) if best_score > 0 else 0,
            })

    matched_df = pd.DataFrame(matched_rows)
    unmatched_df = pd.DataFrame(unmatched_rows)

    return matched_df, unmatched_df


def store_item_mappings(df, conn=None):
    """
    Store match results in item_mapping table. Returns count stored.
    """
    if df.empty:
        return 0

    close_conn = conn is None
    if conn is None:
        conn = get_connection()

    count = 0
    for _, row in df.iterrows():
        conn.execute(
            """INSERT INTO item_mapping
               (qb_item_name, emr_product_name, match_confidence, match_status)
               VALUES (?, ?, ?, ?)""",
            (str(row["qb_item_name"]),
             str(row.get("emr_product_name", "")),
             float(row.get("confidence", 0)),
             str(row.get("match_status", "pending"))),
        )
        count += 1

    conn.commit()
    if close_conn:
        conn.close()
    return count


def get_pending_mappings(conn=None):
    """
    Query item_mapping where match_status = 'pending'.
    Returns DataFrame for UI review queue.
    """
    close_conn = conn is None
    if conn is None:
        conn = get_connection()

    df = pd.read_sql_query(
        "SELECT * FROM item_mapping WHERE match_status = 'pending' ORDER BY match_confidence DESC",
        conn,
    )

    if close_conn:
        conn.close()
    return df


def confirm_mapping(conn, qb_item_name, emr_product_name):
    """
    Update match_status to 'confirmed' and link names in inventory_items.
    """
    conn.execute(
        """UPDATE item_mapping
           SET match_status = 'confirmed', matched_at = CURRENT_TIMESTAMP
           WHERE qb_item_name = ? AND emr_product_name = ?""",
        (qb_item_name, emr_product_name),
    )

    # Also link the two names in inventory_items:
    # If a QB row exists, update it with the EMR name
    existing = conn.execute(
        "SELECT item_id FROM inventory_items WHERE qb_item_name = ?",
        (qb_item_name,),
    ).fetchone()

    if existing:
        conn.execute(
            """UPDATE inventory_items
               SET emr_product_name = ?, updated_at = CURRENT_TIMESTAMP
               WHERE qb_item_name = ?""",
            (emr_product_name, qb_item_name),
        )
        # If a separate EMR-only row exists, merge its data and remove it
        emr_row = conn.execute(
            "SELECT item_id, sku, category, selling_price FROM inventory_items WHERE emr_product_name = ? AND qb_item_name IS NULL",
            (emr_product_name,),
        ).fetchone()
        if emr_row:
            conn.execute(
                """UPDATE inventory_items
                   SET sku = COALESCE(sku, ?), category = COALESCE(category, ?),
                       selling_price = COALESCE(selling_price, ?),
                       updated_at = CURRENT_TIMESTAMP
                   WHERE item_id = ?""",
                (emr_row[1], emr_row[2], emr_row[3], existing[0]),
            )
            conn.execute("DELETE FROM inventory_items WHERE item_id = ?", (emr_row[0],))
    else:
        # No QB row, update the EMR row with the QB name
        conn.execute(
            """UPDATE inventory_items
               SET qb_item_name = ?, updated_at = CURRENT_TIMESTAMP
               WHERE emr_product_name = ?""",
            (qb_item_name, emr_product_name),
        )

    conn.commit()
    return True


def reject_mapping(conn, qb_item_name):
    """
    Update match_status to 'rejected' for the given QB item.
    """
    conn.execute(
        """UPDATE item_mapping
           SET match_status = 'rejected', matched_at = CURRENT_TIMESTAMP
           WHERE qb_item_name = ?""",
        (qb_item_name,),
    )
    conn.commit()
    return True
