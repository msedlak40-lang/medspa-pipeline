import pandas as pd


def build_vendor_receivable_jes(emr_df):
    """
    Returns Vendor JE df (does not write; run_pipeline writes after ledger filtering).
    """
    df = emr_df.copy()
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)

    vr = df[df["mapped_to_account"].astype(str).str.contains("Vendor Receivable", na=False)].copy()
    vr = vr[vr["amount"] != 0]

    if vr.empty:
        return pd.DataFrame(columns=[
            "Date", "RefNumber", "Account", "Debit", "Credit", "Name", "Memo"
        ])

    jes = []
    for _, row in vr.iterrows():
        gross_amount = float(row["amount"])
        discount_amount = float(row.get("discounts", 0))
        amount = gross_amount - discount_amount
        date_str = row["visit_date"].strftime("%Y-%m-%d")
        customer_name = row["Customer"]
        account_vendor = row["mapped_to_account"]
        vendor_tag = account_vendor.split(":")[-1].strip().replace(" ", "")
        ref = f"VR-{row['invoice_number']}-{vendor_tag}"
        memo = f"Vendor receivable from {account_vendor}"

        jes.append({
            "Date": date_str,
            "RefNumber": ref,
            "Account": account_vendor,
            "Debit": amount,
            "Credit": "",
            "Name": "",
            "Memo": memo,
        })
        jes.append({
            "Date": date_str,
            "RefNumber": ref,
            "Account": "Accounts Receivable",
            "Debit": "",
            "Credit": amount,
            "Name": customer_name,
            "Memo": memo,
        })

    je_df = pd.DataFrame(jes)
    return je_df
