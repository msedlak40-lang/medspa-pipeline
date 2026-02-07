import os

import pandas as pd

from config import EMR_FILE, EMR_TIPS_BASE


def load_emr():
    """
    Expect emr_transactions.xlsx to have columns:
      Date, Invoice #, CID, Client Name, Service/Product, SKU, Staff,
      QTY, Price, Discounts, Tax, Total Due, Amount, Payment Type
    """
    df = pd.read_excel(EMR_FILE)

    rename_map = {
        "Date": "visit_date",
        "Invoice #": "invoice_number",
        "CID": "patient_id",
        "Client Name": "patient_name",
        "Service/Product": "service_text",
        "SKU": "sku",
        "Staff": "staff",
        "QTY": "quantity",
        "Price": "price",
        "Discounts": "discounts",
        "Tax": "tax",
        "Total Due": "total_due",
        "Amount": "amount",
        "Payment Type": "payment_type",
    }
    df = df.rename(columns=rename_map)

    # Types / cleaning
    df["visit_date"] = pd.to_datetime(df["visit_date"])
    df["invoice_number"] = df["invoice_number"].astype(str).str.strip()
    df["patient_id"] = df["patient_id"].astype(str)
    df["patient_name"] = df["patient_name"].astype(str)

    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(1)
    df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0)
    df["total_due"] = pd.to_numeric(df["total_due"], errors="coerce").fillna(0)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    df["discounts"] = pd.to_numeric(df["discounts"], errors="coerce").fillna(0)

    df["service_amount"] = df["price"] * df["quantity"]

    return df


def load_emr_tips():
    """
    Load optional emr_tips file from input/emr_tips.xlsx or input/emr_tips.csv.

    IMPORTANT: Real headers are on the SECOND row (row index 1), so we read with header=1.

    Returns DataFrame: invoice_number, tip_total_invoice
    """
    tips_df = None
    for ext, reader in [(".xlsx", pd.read_excel), (".csv", pd.read_csv)]:
        path = EMR_TIPS_BASE + ext
        if os.path.exists(path):
            tips_df = reader(path, header=1)  # second row as header
            break

    if tips_df is None:
        print("No emr_tips file found; skipping tips integration.")
        return pd.DataFrame(columns=["invoice_number", "tip_total_invoice"])

    tips_df.columns = [str(c).strip() for c in tips_df.columns]

    norm_map = {
        c: str(c).strip().lower().replace(" ", "").replace("_", "")
        for c in tips_df.columns
    }

    invoice_candidates = [c for c, n in norm_map.items() if "invoice" in n]
    tip_candidates = [c for c, n in norm_map.items() if "tip" in n]

    if not invoice_candidates or not tip_candidates:
        print(
            "emr_tips file missing an identifiable Invoice or Tip column; "
            f"columns seen: {list(tips_df.columns)}. Skipping tips integration."
        )
        return pd.DataFrame(columns=["invoice_number", "tip_total_invoice"])

    invoice_col = invoice_candidates[0]
    tip_col = tip_candidates[0]

    tips_df = tips_df.rename(columns={invoice_col: "invoice_number", tip_col: "tip_amount"})
    tips_df["invoice_number"] = tips_df["invoice_number"].astype(str).str.strip()
    tips_df["tip_amount"] = pd.to_numeric(tips_df["tip_amount"], errors="coerce").fillna(0)

    tips = tips_df.groupby("invoice_number", as_index=False)["tip_amount"].sum()
    tips = tips.rename(columns={"tip_amount": "tip_total_invoice"})

    print(f"Tips loaded for {len(tips)} invoices.")
    return tips
