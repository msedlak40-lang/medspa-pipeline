import pandas as pd


def build_invoice_import(emr_df):
    """
    Returns invoice import dataframe (does not write to disk; run_pipeline writes after ledger filtering).
    """
    df = emr_df.copy()
    df = df[~df["matched_item"].isna()].copy()

    # Only include actual service lines (service text not blank)
    service_mask = df["service_text"].notna() & (df["service_text"].astype(str).str.strip() != "")
    df = df[service_mask].copy()

    df["TxnDate"] = df["visit_date"].dt.strftime("%Y-%m-%d")
    df["RefNumber"] = df["invoice_number"]
    df["Item"] = df["matched_item"]
    df["Qty"] = df["quantity"].replace(0, 1)
    df["Rate"] = df["service_amount"] / df["Qty"]
    df["Amount"] = df["service_amount"]
    df["TaxCode"] = df["taxcode"]
    df["Memo"] = df["service_text"]

    invoice_df = df[
        ["Customer", "TxnDate", "RefNumber", "Item", "Qty", "Rate", "Amount", "TaxCode", "Memo"]
    ].copy()

    return invoice_df
