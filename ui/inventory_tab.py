"""
Inventory setup tab — load inventory data, review and confirm item matches.
"""
import os

import streamlit as st
import pandas as pd

from config import ITEM_COST_FILE, EMR_INVENTORY_FILE


def render_inventory_tab():
    st.header("Inventory Management")

    # ---- 1. Load source data ------------------------------------------------
    st.subheader("1. Load Source Data")

    col1, col2 = st.columns(2)

    # --- QB items ---
    with col1:
        st.markdown("**QuickBooks Item Costs**")
        qb_exists = os.path.isfile(ITEM_COST_FILE)
        st.caption(f"File: {'found' if qb_exists else 'missing'} \u2014 {ITEM_COST_FILE}")

        qb_up = st.file_uploader("Upload item_cost.xlsx", type=["xlsx"], key="inv_qb")
        if qb_up is not None:
            os.makedirs(os.path.dirname(ITEM_COST_FILE), exist_ok=True)
            with open(ITEM_COST_FILE, "wb") as f:
                f.write(qb_up.getbuffer())
            st.success("Saved item_cost.xlsx")
            qb_exists = True

        if qb_exists and st.button("Load QB Items", key="load_qb"):
            with st.spinner("Loading QB items..."):
                from loaders.inventory_loader import load_qb_item_costs, store_qb_items_to_db
                from db.connection import get_connection
                from db.schema import init_database

                init_database()
                qb_df = load_qb_item_costs()
                conn = get_connection()
                count = store_qb_items_to_db(qb_df, conn)
                conn.close()
                st.success(f"\u2705 Loaded {count} QB items")

    # --- EMR inventory ---
    with col2:
        st.markdown("**EMR Inventory (SkinFix)**")
        emr_exists = os.path.isfile(EMR_INVENTORY_FILE)
        st.caption(f"File: {'found' if emr_exists else 'missing'} \u2014 {EMR_INVENTORY_FILE}")

        emr_up = st.file_uploader("Upload skinfix_inventory.xlsx", type=["xlsx"], key="inv_emr")
        if emr_up is not None:
            os.makedirs(os.path.dirname(EMR_INVENTORY_FILE), exist_ok=True)
            with open(EMR_INVENTORY_FILE, "wb") as f:
                f.write(emr_up.getbuffer())
            st.success("Saved skinfix_inventory.xlsx")
            emr_exists = True

        if emr_exists and st.button("Load EMR Inventory", key="load_emr_inv"):
            with st.spinner("Loading EMR inventory..."):
                from loaders.inventory_loader import load_emr_inventory, store_emr_inventory_to_db
                from db.connection import get_connection
                from db.schema import init_database

                init_database()
                emr_df = load_emr_inventory()
                conn = get_connection()
                count = store_emr_inventory_to_db(emr_df, conn)
                conn.close()
                st.success(f"\u2705 Loaded {count} EMR inventory items")

    st.divider()

    # ---- 2. Run matching ----------------------------------------------------
    st.subheader("2. Match Items")

    if st.button("\U0001f504 Run Fuzzy Matching", key="run_match"):
        with st.spinner("Matching items..."):
            from loaders.inventory_loader import load_qb_item_costs, load_emr_inventory
            from matching.inventory_matcher import match_inventory_items, store_item_mappings
            from db.connection import get_connection
            from db.schema import init_database

            init_database()
            qb_df = load_qb_item_costs()
            emr_df = load_emr_inventory()
            matched_df, unmatched_df = match_inventory_items(qb_df, emr_df)

            conn = get_connection()
            stored = store_item_mappings(matched_df, conn)
            conn.close()

            auto_count = len(matched_df[matched_df["match_status"] == "auto"]) if not matched_df.empty else 0
            pending_count = len(matched_df[matched_df["match_status"] == "pending"]) if not matched_df.empty else 0

            st.success(
                f"\u2705 Matching complete: {auto_count} auto-matched, "
                f"{pending_count} pending review, {len(unmatched_df)} unmatched"
            )

            if not unmatched_df.empty:
                with st.expander("Unmatched QB Items"):
                    st.dataframe(unmatched_df, use_container_width=True, hide_index=True)

    st.divider()

    # ---- 3. Review pending matches ------------------------------------------
    st.subheader("3. Review Pending Matches")

    try:
        from matching.inventory_matcher import get_pending_mappings, confirm_mapping, reject_mapping
        from db.connection import get_connection

        conn = get_connection()
        pending_df = get_pending_mappings(conn)
    except Exception:
        pending_df = pd.DataFrame()
        conn = None

    if pending_df.empty:
        st.info("No pending matches to review.")
    else:
        st.write(f"**{len(pending_df)} items need review:**")

        # Build an editable table approach: iterate rows with confirm/reject
        for idx, row in pending_df.iterrows():
            with st.container():
                c1, c2, c3, c4 = st.columns([3, 3, 1, 2])
                with c1:
                    st.write(f"**QB:** {row['qb_item_name']}")
                with c2:
                    st.write(f"**EMR:** {row['emr_product_name'] or 'No match'}")
                with c3:
                    conf = row.get("match_confidence", 0) or 0
                    st.write(f"{conf:.0f}%")
                with c4:
                    bc1, bc2 = st.columns(2)
                    with bc1:
                        if st.button("\u2713 Confirm", key=f"confirm_{row['qb_item_name']}_{idx}"):
                            confirm_mapping(conn, row["qb_item_name"], row["emr_product_name"])
                            st.rerun()
                    with bc2:
                        if st.button("\u2717 Reject", key=f"reject_{row['qb_item_name']}_{idx}"):
                            reject_mapping(conn, row["qb_item_name"])
                            st.rerun()
                st.divider()

    if conn is not None:
        conn.close()

    # ---- 4. Inventory snapshot ----------------------------------------------
    st.subheader("4. Create Inventory Snapshot")

    snapshot_date = st.date_input("As-of Date", key="snap_date")
    if st.button("\U0001f4f8 Create Snapshot", key="create_snap"):
        with st.spinner("Creating snapshot..."):
            from loaders.inventory_loader import create_inventory_snapshot
            from db.connection import get_connection
            from db.schema import init_database

            init_database()
            conn = get_connection()
            count = create_inventory_snapshot(conn, str(snapshot_date), source="initial_load")
            conn.close()
            st.success(f"\u2705 Created snapshot for {count} items as of {snapshot_date}")

    st.divider()

    # ---- 5. Inventory summary -----------------------------------------------
    st.subheader("Current Inventory Status")

    try:
        from db.connection import get_connection

        conn = get_connection()
        inv_df = pd.read_sql_query(
            """SELECT
                   ii.item_id,
                   COALESCE(ii.qb_item_name, '') AS qb_name,
                   COALESCE(ii.emr_product_name, '') AS emr_name,
                   ii.category,
                   ii.unit_cost,
                   ii.selling_price,
                   ii.is_active
               FROM inventory_items ii
               WHERE ii.is_active = 1
               ORDER BY ii.qb_item_name""",
            conn,
        )
        conn.close()

        if inv_df.empty:
            st.info("No inventory items loaded yet.")
        else:
            st.write(f"**{len(inv_df)} active items**")
            st.dataframe(inv_df, use_container_width=True, hide_index=True)
    except Exception:
        st.info("No inventory data available. Load source data first.")
