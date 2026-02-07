"""
Pipeline processing tab — upload files, run pipeline, download results.
"""
import os
import io
import sys

import streamlit as st
import pandas as pd

from config import (
    INPUT_DIR, OUTPUT_DIR,
    EMR_FILE, GRAVITY_FILE, COA_FILE, CUSTOMER_MASTER_FILE, EMR_TIPS_BASE,
)


# --- helpers -----------------------------------------------------------------

_INPUT_FILES = [
    ("EMR Transactions", EMR_FILE, "xlsx", True),
    ("Gravity Payments", GRAVITY_FILE, "csv", True),
    ("COA Mappings", COA_FILE, "xlsx", True),
    ("Customer Master", CUSTOMER_MASTER_FILE, "xlsx", True),
    ("EMR Tips", EMR_TIPS_BASE + ".xlsx", "xlsx", False),
]


def _file_exists(path):
    """Check for the file, also try .csv variant for tips."""
    if os.path.isfile(path):
        return True
    base, ext = os.path.splitext(path)
    if ext == ".xlsx" and os.path.isfile(base + ".csv"):
        return True
    return False


def _save_upload(uploaded, dest_path):
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "wb") as f:
        f.write(uploaded.getbuffer())


def _categorize_output(fname):
    fl = fname.lower()
    if any(k in fl for k in ("invoice_import", "receive_payments", "vendor_receivable", "journalentries")):
        return "QuickBooks Imports"
    if any(k in fl for k in ("unmatched", "unmapped", "duplicate")):
        return "Exceptions"
    return "Reference"


# --- main render -------------------------------------------------------------

def render_pipeline_tab():
    # ---- 1. File status -----------------------------------------------------
    st.header("Input Files")

    cols = st.columns(len(_INPUT_FILES))
    for col, (label, path, _, required) in zip(cols, _INPUT_FILES):
        exists = _file_exists(path)
        icon = "\u2705" if exists else ("\u274c" if required else "\u2796")
        col.metric(label, icon)

    # ---- 2. Upload ----------------------------------------------------------
    st.header("Upload New Files")

    up_cols = st.columns(2)
    upload_specs = [
        ("EMR Transactions (.xlsx)", ["xlsx"], EMR_FILE),
        ("Gravity Payments (.csv)", ["csv"], GRAVITY_FILE),
        ("COA Mappings (.xlsx)", ["xlsx"], COA_FILE),
        ("Customer Master (.xlsx)", ["xlsx"], CUSTOMER_MASTER_FILE),
    ]

    for i, (label, types, dest) in enumerate(upload_specs):
        with up_cols[i % 2]:
            uploaded = st.file_uploader(label, type=types, key=f"upload_{i}")
            if uploaded is not None:
                _save_upload(uploaded, dest)
                st.success(f"Saved {os.path.basename(dest)}")

    # Tips uploader (optional)
    tips_up = st.file_uploader("EMR Tips (.xlsx or .csv)", type=["xlsx", "csv"], key="upload_tips")
    if tips_up is not None:
        ext = os.path.splitext(tips_up.name)[1]
        _save_upload(tips_up, EMR_TIPS_BASE + ext)
        st.success(f"Saved emr_tips{ext}")

    # ---- 3. Run pipeline ----------------------------------------------------
    st.header("Process")

    col1, col2 = st.columns([1, 3])
    with col1:
        run_button = st.button("\U0001f680 Run Pipeline", type="primary", use_container_width=True)

    if run_button:
        with st.spinner("Processing..."):
            try:
                from main import run_pipeline

                old_stdout = sys.stdout
                sys.stdout = buffer = io.StringIO()

                run_pipeline()

                output = buffer.getvalue()
                sys.stdout = old_stdout

                st.success("\u2705 Pipeline completed successfully!")
                with st.expander("Processing Log", expanded=False):
                    st.code(output)
            except Exception as e:
                sys.stdout = sys.__stdout__
                st.error(f"\u274c Pipeline failed: {e}")
                import traceback
                st.code(traceback.format_exc())

    # ---- 4. Download outputs ------------------------------------------------
    st.header("Download Results")

    if not os.path.isdir(OUTPUT_DIR):
        st.info("No output files yet. Run the pipeline first.")
    else:
        output_files = sorted(
            f for f in os.listdir(OUTPUT_DIR)
            if os.path.isfile(os.path.join(OUTPUT_DIR, f)) and f != ".gitkeep"
        )
        if not output_files:
            st.info("No output files yet. Run the pipeline first.")
        else:
            categories = {}
            for fname in output_files:
                cat = _categorize_output(fname)
                categories.setdefault(cat, []).append(fname)

            for cat in ["QuickBooks Imports", "Exceptions", "Reference"]:
                files = categories.get(cat, [])
                if not files:
                    continue
                st.subheader(cat)
                dl_cols = st.columns(min(len(files), 3))
                for i, fname in enumerate(files):
                    fpath = os.path.join(OUTPUT_DIR, fname)
                    size_kb = os.path.getsize(fpath) / 1024
                    with dl_cols[i % len(dl_cols)]:
                        with open(fpath, "rb") as fh:
                            st.download_button(
                                f"{fname} ({size_kb:.1f} KB)",
                                data=fh.read(),
                                file_name=fname,
                                key=f"dl_{fname}",
                            )

    # ---- 5. Run history -----------------------------------------------------
    st.header("Processing History")

    try:
        from db.connection import get_connection
        conn = get_connection()
        history = pd.read_sql_query(
            """SELECT run_id, run_timestamp, run_status,
                      emr_rows, gravity_rows, invoices_exported,
                      payments_exported, cash_exported, jes_exported
               FROM pipeline_runs ORDER BY run_timestamp DESC LIMIT 10""",
            conn,
        )
        conn.close()
        if history.empty:
            st.info("No pipeline runs recorded yet.")
        else:
            st.dataframe(history, use_container_width=True, hide_index=True)
    except Exception:
        st.info("No pipeline runs recorded yet.")
