import os
import traceback

import pandas as pd

from config import OUTPUT_DIR
from utils.file_utils import ensure_output_dir, ensure_state_dir
from db.schema import init_database
from db.operations import (
    create_run, update_run_status,
    store_emr_transactions, store_emr_tips, store_gravity_payments,
    upsert_customer_master, store_name_conflicts,
    store_service_mappings, store_payment_mappings,
    store_payment_matches, store_unmatched_gravity,
    store_unmapped_services, store_unmapped_payments,
    record_export,
)
from loaders.emr_loader import load_emr, load_emr_tips
from loaders.gravity_loader import load_gravity
from loaders.mapping_loader import load_coa_mappings
from loaders.customer_loader import load_customer_master, save_customer_master, apply_customer_logic
from transforms.service_mapper import map_services
from transforms.payment_mapper import map_payments
from matching.gravity_matcher import match_gravity_payments
from exports.invoice_export import build_invoice_import
from exports.payment_export import build_receive_payments, build_cash_receive_payments
from exports.journal_export import build_vendor_receivable_jes
from pipeline_state.ledger import (
    load_posted_ledger, append_to_posted_ledger,
    filter_invoices_by_ledger, filter_card_payments_by_ledger,
    filter_cash_payments_by_ledger, filter_vendor_jes_by_ledger,
)


def run_pipeline():
    ensure_output_dir()
    ensure_state_dir()
    init_database()

    run_id = pd.Timestamp.utcnow().strftime("%Y%m%dT%H%M%SZ")
    create_run(run_id)
    posted_keys = load_posted_ledger()

    # --- Load ---
    print("Loading files...")
    emr = load_emr()
    tips = load_emr_tips()

    # Merge tips into EMR
    emr["invoice_number"] = emr["invoice_number"].astype(str).str.strip()
    if not tips.empty:
        tips["invoice_number"] = tips["invoice_number"].astype(str).str.strip()
        emr = emr.merge(tips, on="invoice_number", how="left")
        emr["tip_total_invoice"] = pd.to_numeric(emr["tip_total_invoice"], errors="coerce").fillna(0)
        print("Tips merged into EMR transactions.")
    else:
        emr["tip_total_invoice"] = 0.0

    gravity = load_gravity()
    service_map, payment_map = load_coa_mappings()
    customer_master = load_customer_master()

    # Store raw data in SQLite
    store_emr_transactions(run_id, emr)
    store_emr_tips(run_id, tips)
    store_gravity_payments(run_id, gravity)
    store_service_mappings(service_map)
    store_payment_mappings(payment_map)

    # --- Customer logic ---
    print("Checking EMR customers (duplicate IDs with different names)...")
    emr, customer_master, conflicts = apply_customer_logic(emr, customer_master)
    save_customer_master(customer_master)
    upsert_customer_master(customer_master)
    store_name_conflicts(conflicts)

    # --- Mapping ---
    print("Mapping services...")
    emr, unmapped_svc = map_services(emr, service_map)
    store_unmapped_services(run_id, unmapped_svc)

    print("Mapping payments...")
    emr, unmapped_pmt = map_payments(emr, payment_map)
    store_unmapped_payments(run_id, unmapped_pmt)

    # --- Build, filter, export ---
    print("Building Invoice_Import_ItemBased.csv...")
    invoice_df = build_invoice_import(emr)
    invoice_new, invoice_skipped = filter_invoices_by_ledger(invoice_df, posted_keys)
    invoice_new.to_csv(os.path.join(OUTPUT_DIR, "Invoice_Import_ItemBased.csv"), index=False)
    invoice_skipped.to_csv(os.path.join(OUTPUT_DIR, "Skipped_Invoices_AlreadyPosted.csv"), index=False)
    record_export(run_id, "Invoice_Import_ItemBased.csv", len(invoice_new))

    print("Matching Gravity payments...")
    matched_gravity, unmatched_gravity = match_gravity_payments(emr, gravity)
    store_payment_matches(run_id, matched_gravity)
    store_unmatched_gravity(run_id, unmatched_gravity)

    print("Building Receive_Payments_From_Gravity.csv...")
    receive_df = build_receive_payments(matched_gravity)
    receive_new, receive_skipped = filter_card_payments_by_ledger(receive_df, posted_keys)
    receive_new.to_csv(os.path.join(OUTPUT_DIR, "Receive_Payments_From_Gravity.csv"), index=False)
    receive_skipped.to_csv(os.path.join(OUTPUT_DIR, "Skipped_CardPayments_AlreadyPosted.csv"), index=False)
    record_export(run_id, "Receive_Payments_From_Gravity.csv", len(receive_new))

    print("Building Receive_Payments_Cash.csv...")
    cash_df = build_cash_receive_payments(emr)
    cash_new, cash_skipped = filter_cash_payments_by_ledger(cash_df, posted_keys)
    cash_new.to_csv(os.path.join(OUTPUT_DIR, "Receive_Payments_Cash.csv"), index=False)
    cash_skipped.to_csv(os.path.join(OUTPUT_DIR, "Skipped_CashPayments_AlreadyPosted.csv"), index=False)
    record_export(run_id, "Receive_Payments_Cash.csv", len(cash_new))

    print("Building Vendor_Receivable_JournalEntries.csv...")
    je_df = build_vendor_receivable_jes(emr)
    je_new, je_skipped = filter_vendor_jes_by_ledger(je_df, posted_keys)
    je_new.to_csv(os.path.join(OUTPUT_DIR, "Vendor_Receivable_JournalEntries.csv"), index=False)
    je_skipped.to_csv(os.path.join(OUTPUT_DIR, "Skipped_VendorJEs_AlreadyPosted.csv"), index=False)
    record_export(run_id, "Vendor_Receivable_JournalEntries.csv", len(je_new))

    # --- Mark exported rows as posted ---
    keys_to_post = []

    if not invoice_new.empty:
        keys_to_post += ["INV|" + x for x in invoice_new["RefNumber"].astype(str).unique().tolist()]

    if not receive_new.empty:
        keys_to_post += ["CC|" + x for x in receive_new["RefNumber"].astype(str).unique().tolist()]

    if not cash_new.empty:
        cash_amt_str = cash_new["Amount"].round(2).map(lambda x: f"{x:.2f}")
        keys_to_post += (
            "CASH|" + cash_new["ApplyToRefNumber"].astype(str) + "|" + cash_amt_str
        ).unique().tolist()

    if not je_new.empty:
        je_new_idx = je_new.reset_index(drop=True)
        keys_to_post += (
            "VR|" + je_new_idx["RefNumber"].astype(str) + "|" + je_new_idx.index.astype(str)
        ).unique().tolist()

    append_to_posted_ledger(keys_to_post, run_id=run_id)

    # --- Finalize run ---
    update_run_status(
        run_id, "completed",
        emr_rows=len(emr),
        gravity_rows=len(gravity),
        invoices_exported=len(invoice_new),
        payments_exported=len(receive_new),
        cash_exported=len(cash_new),
        jes_exported=len(je_new),
    )

    print("Done. Check the 'output' folder for results.")
    print(f"Posted ledger updated. Run ID: {run_id}")


if __name__ == "__main__":
    try:
        run_pipeline()
    except Exception as e:
        print("ERROR:", e)
        traceback.print_exc()
