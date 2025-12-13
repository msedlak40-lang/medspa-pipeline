# main.py - MedSpa pipeline with tips + strict matching

import os
from datetime import timedelta

import pandas as pd

# ---------- PATHS & CONFIG ----------

INPUT_DIR = "input"
OUTPUT_DIR = "output"

EMR_FILE = os.path.join(INPUT_DIR, "emr_transactions.xlsx")
GRAVITY_FILE = os.path.join(INPUT_DIR, "gravity_payments.csv")
COA_FILE = os.path.join(INPUT_DIR, "COA_Quickbooks_matched.xlsx")
CUSTOMER_MASTER_FILE = os.path.join(INPUT_DIR, "customer_master.xlsx")
EMR_TIPS_BASE = os.path.join(INPUT_DIR, "emr_tips")  # .xlsx or .csv

SERVICE_SHEET = "emr_service_items"
PAYMENT_SHEET = "emr_payment_types"

MERCHANT_CLEARING_ACCOUNT = "1030 Merchant Clearing"


# ---------- UTILITIES ----------

def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def normalize_card_type(value: str) -> str:
    """
    Normalize EMR and Gravity card types to:
      'vs' (Visa), 'mc' (MasterCard), 'dc' (Discover), 'ax' (Amex)
    """
    if value is None:
        return ""
    v = str(value).strip().lower()
    mapping = {
        "visa": "vs", "vs": "vs", "v": "vs",
        "mastercard": "mc", "master card": "mc", "mc": "mc",
        "discover": "dc", "disc": "dc", "dc": "dc",
        "amex": "ax", "american express": "ax", "ax": "ax",
    }
    return mapping.get(v, v)


# ---------- LOADERS ----------

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

    df["service_amount"] = df["price"] * df["quantity"]

    return df


def load_emr_tips():
    """
    Load optional emr_tips file from input/emr_tips.xlsx or input/emr_tips.csv.

    Real headers are on the SECOND row (row index 1).
    We detect invoice/tip columns by name fragments, not exact strings.

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


def load_gravity():
    """
    Expect gravity_payments.csv columns incl:
      Date/Time, Approval, Sale Amount, Total, Card Type, etc.
    """
    df = pd.read_csv(GRAVITY_FILE)

    rename_map = {
        "Date/Time": "settlement_datetime",
        "Approval": "transaction_id",
        "Type": "type",
        "Card": "card",
        "Name": "name",
        "Sale Amount": "sale_amount",
        "Tip": "tip",
        "Total": "amount",
        "Cashier": "cashier",
        "Source": "source",
        "Card Type": "card_type",
    }
    for old, new in rename_map.items():
        if old in df.columns:
            df = df.rename(columns={old: new})

    required = ["settlement_datetime", "amount", "card_type", "transaction_id", "sale_amount"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Gravity file missing required columns: {missing}")

    df["settlement_datetime"] = pd.to_datetime(df["settlement_datetime"])
    df["settlement_date"] = df["settlement_datetime"].dt.normalize()

    df["sale_amount"] = pd.to_numeric(df["sale_amount"], errors="coerce").fillna(0)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    df["tip"] = pd.to_numeric(df.get("tip", 0), errors="coerce").fillna(0)

    df["is_refund"] = df["sale_amount"] < 0

    return df[
        ["settlement_date", "amount", "card_type", "transaction_id", "is_refund",
         "sale_amount", "tip", "type", "card", "name", "cashier", "source"]
    ].copy()


def load_coa_mappings():
    service_map = pd.read_excel(COA_FILE, sheet_name=SERVICE_SHEET)
    payment_map = pd.read_excel(COA_FILE, sheet_name=PAYMENT_SHEET)

    service_map.columns = [c.strip().lower().replace(" ", "_") for c in service_map.columns]
    payment_map.columns = [c.strip().lower().replace(" ", "_") for c in payment_map.columns]

    return service_map, payment_map


# ---------- CUSTOMER MASTER ----------

def load_customer_master():
    if not os.path.exists(CUSTOMER_MASTER_FILE):
        return pd.DataFrame(columns=["patient_id", "patient_name"])

    df = pd.read_excel(CUSTOMER_MASTER_FILE)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    rename_map = {}
    if "patientid" in df.columns:
        rename_map["patientid"] = "patient_id"
    if "patientname" in df.columns:
        rename_map["patientname"] = "patient_name"
    df = df.rename(columns=rename_map)

    for col in ["patient_id", "patient_name"]:
        if col not in df.columns:
            df[col] = None

    df["patient_id"] = df["patient_id"].astype(str)
    df["patient_name"] = df["patient_name"].astype(str)

    return df[["patient_id", "patient_name"]]


def save_customer_master(master_df):
    master_df.to_excel(CUSTOMER_MASTER_FILE, index=False)


def apply_customer_logic(emr_df, master_df):
    emr = emr_df.copy()
    emr["patient_id"] = emr["patient_id"].astype(str)
    emr["patient_name"] = emr["patient_name"].astype(str)

    master = master_df.copy()
    master["patient_id"] = master["patient_id"].astype(str)
    master["patient_name"] = master["patient_name"].astype(str)

    merged = emr.merge(
        master.rename(columns={"patient_name": "master_patient_name"}),
        on="patient_id",
        how="left"
    )

    conflict_mask = (
        merged["master_patient_name"].notna() &
        (merged["patient_name"].str.strip() != merged["master_patient_name"].str.strip())
    )
    conflicts = merged[conflict_mask][
        ["patient_id", "patient_name", "master_patient_name"]
    ].drop_duplicates()

    if not conflicts.empty:
        conflict_path = os.path.join(OUTPUT_DIR, "Duplicate_ID_Different_Name.csv")
        conflicts.to_csv(conflict_path, index=False)
        print(f"⚠️ Name conflicts found. See {conflict_path}")
    else:
        print("✅ No patient ID/name conflicts found.")

    existing_ids = set(master["patient_id"])
    new_rows = emr[~emr["patient_id"].isin(existing_ids)][
        ["patient_id", "patient_name"]
    ].drop_duplicates()

    if not new_rows.empty:
        master = pd.concat([master, new_rows], ignore_index=True)

    emr["Customer"] = emr["patient_name"]
    return emr, master


# ---------- SERVICE & PAYMENT MAPPING ----------

def map_services(emr_df, service_map):
    sm = service_map.copy()
    if "emr_service_text" not in sm.columns:
        raise ValueError("Service mapping sheet must contain 'emr_service_text' column.")
    if "matched_item" not in sm.columns or "taxcode" not in sm.columns:
        raise ValueError("Service mapping sheet must contain 'matched_item' and 'taxcode' columns.")

    sm["emr_service_text_norm"] = sm["emr_service_text"].astype(str).str.strip().str.lower()

    df = emr_df.copy()
    df["service_text_norm"] = df["service_text"].astype(str).str.strip().str.lower()

    merged = df.merge(
        sm[["emr_service_text_norm", "matched_item", "taxcode"]],
        left_on="service_text_norm",
        right_on="emr_service_text_norm",
        how="left",
    )

    unmapped = merged[merged["matched_item"].isna()][["service_text"]].drop_duplicates()
    unmapped = unmapped.rename(columns={"service_text": "unmapped_service_text"})
    unmapped.to_csv(os.path.join(OUTPUT_DIR, "Unmapped_Services.csv"), index=False)

    return merged, unmapped


def map_payments(emr_df, payment_map):
    pm = payment_map.copy()
    if "payment_type" not in pm.columns or "mapped_to_account" not in pm.columns:
        raise ValueError("Payment mapping sheet must contain 'payment_type' and 'mapped_to_account' columns.")

    pm["payment_type_norm"] = pm["payment_type"].astype(str).str.strip().str.lower()

    df = emr_df.copy()
    df["payment_type_norm"] = df["payment_type"].astype(str).str.strip().str.lower()

    merged = df.merge(
        pm[["payment_type_norm", "mapped_to_account"]],
        on="payment_type_norm",
        how="left",
    )

    unmapped = merged[merged["mapped_to_account"].isna()][["payment_type"]].drop_duplicates()
    unmapped = unmapped.rename(columns={"payment_type": "unmapped_payment_type"})
    unmapped.to_csv(os.path.join(OUTPUT_DIR, "Unmapped_Payments.csv"), index=False)

    return merged, unmapped


# ---------- INVOICE CREATION ----------

def build_invoice_import(emr_df):
    df = emr_df.copy()
    df = df[~df["matched_item"].isna()].copy()

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

    invoice_df.to_csv(os.path.join(OUTPUT_DIR, "Invoice_Import_ItemBased.csv"), index=False)
    return invoice_df


# ---------- GRAVITY MATCHING ----------

def match_gravity_payments(emr_df, gravity_df, date_tolerance_days=3):
    """
    STRICT, SIMPLE MATCHING:

    We match Gravity payments directly to EMR **card payment lines**, not to
    invoice-level "expected patient payment" math.

    EMR card payment lines:
      - Service/Product is blank
      - Amount != 0
      - Payment Type NOT in:
            Client Bank, Alle Rewards, Aspire Awards,
            Reward Points, Clover Gift Card, Cash

    For each Gravity payment:
      1) Find EMR card lines where card_payment == gravity.amount
      2) Among those, prefer:
           a) Same-day matches first
           b) Within same-day, card type (VS/MC/DC/AX) as tie-breaker
      3) If still ambiguous, allow ±date_tolerance_days window, same logic
      4) If still ambiguous or no candidates -> Unmatched_Gravity_Payments

    Refunds (negative Sale Amount or non-positive Total) are exported separately.
    """

    gravity_all = gravity_df.copy()

    # Split payments vs refunds
    payments = gravity_all[~gravity_all["is_refund"] & (gravity_all["amount"] > 0)].copy()
    refunds = gravity_all[gravity_all["is_refund"] | (gravity_all["amount"] <= 0)].copy()
    refunds.to_csv(os.path.join(OUTPUT_DIR, "Gravity_Refunds.csv"), index=False)

    # Prep EMR
    emr = emr_df.copy()
    emr["amount"] = pd.to_numeric(emr["amount"], errors="coerce").fillna(0)
    emr["payment_type"] = emr["payment_type"].astype(str)
    emr["visit_date"] = pd.to_datetime(emr["visit_date"])

    # Identify service vs non-service lines
    service_col = emr["service_text"]
    service_mask = service_col.notna() & (service_col.astype(str).str.strip() != "")
    non_service_lines = emr[~service_mask].copy()

    # Third-party types we do NOT match to Gravity (they reduce what card pays)
    THIRD_PARTY_TYPES = {
        "client bank",
        "alle rewards",
        "aspire awards",
        "reward points",
        "clover gift card",
        "cash",
    }

    non_service_lines["payment_type_norm"] = (
        non_service_lines["payment_type"].str.strip().str.lower()
    )

    # Card payment lines are non-service, non-third-party, non-zero amount
    card_lines = non_service_lines[
        (~non_service_lines["payment_type_norm"].isin(THIRD_PARTY_TYPES))
        & (non_service_lines["amount"] != 0)
    ].copy()

    # If there are no card lines at all, everything will end up unmatched
    if card_lines.empty:
        payments.to_csv(os.path.join(OUTPUT_DIR, "Unmatched_Gravity_Payments.csv"), index=False)
        return pd.DataFrame(columns=list(payments.columns) + ["Customer", "ApplyToRefNumber", "TxnDate"]), payments

    # Prep card line info
    card_lines["card_payment"] = card_lines["amount"].abs().round(2)
    card_lines["card_type_key"] = card_lines["payment_type_norm"].apply(normalize_card_type)

    card_details = card_lines[[
        "invoice_number",
        "visit_date",
        "Customer",
        "card_payment",
        "card_type_key",
    ]].copy()

    matched_rows = []
    unmatched_rows = []

    for _, g in payments.iterrows():
        g_amt = round(float(g["amount"]), 2)
        g_date = g["settlement_date"]
        g_card_key = normalize_card_type(g["card_type"])

        # 1) amount filter
        candidates = card_details[card_details["card_payment"] == g_amt].copy()
        if candidates.empty:
            unmatched_rows.append(g)
            continue

        # 2) compute date difference
        candidates["date_diff"] = (candidates["visit_date"] - g_date).abs()

        chosen = None

        # --- Stage 1: same-day matches ---
        same_day = candidates[candidates["date_diff"] == pd.Timedelta(days=0)]

        if len(same_day) == 1:
            chosen = same_day.iloc[0]
        elif len(same_day) > 1:
            # Try card type tie-breaker
            ct_match = same_day[same_day["card_type_key"].fillna("") == g_card_key]
            if len(ct_match) == 1:
                chosen = ct_match.iloc[0]
            # If still multiple, we will not pick; we'll try window next.

        # --- Stage 2: ±date_tolerance_days window ---
        if chosen is None:
            in_window = candidates[candidates["date_diff"] <= timedelta(days=date_tolerance_days)]

            if len(in_window) == 1:
                chosen = in_window.iloc[0]
            elif len(in_window) > 1:
                ct_match = in_window[in_window["card_type_key"].fillna("") == g_card_key]
                if len(ct_match) == 1:
                    chosen = ct_match.iloc[0]
                # If still >1, we leave it unmatched as ambiguous.

        if chosen is not None:
            row = g.copy()
            row["Customer"] = chosen["Customer"]
            row["ApplyToRefNumber"] = chosen["invoice_number"]
            row["TxnDate"] = g_date
            matched_rows.append(row)
        else:
            unmatched_rows.append(g)

    matched_df = pd.DataFrame(matched_rows)
    unmatched_df = pd.DataFrame(unmatched_rows)
    unmatched_df.to_csv(os.path.join(OUTPUT_DIR, "Unmatched_Gravity_Payments.csv"), index=False)

    return matched_df, unmatched_df


def build_receive_payments(matched_df):
    if matched_df.empty:
        receive_df = pd.DataFrame(
            columns=[
                "Customer", "TxnDate", "RefNumber", "Amount",
                "PaymentMethod", "DepositToAccount", "ApplyToRefNumber",
            ]
        )
    else:
        df = matched_df.copy()
        df["TxnDate"] = df["TxnDate"].dt.strftime("%Y-%m-%d")
        df["RefNumber"] = df["transaction_id"]
        df["Amount"] = df["amount"]
        df["PaymentMethod"] = df["card_type"]
        df["DepositToAccount"] = MERCHANT_CLEARING_ACCOUNT
        receive_df = df[
            ["Customer", "TxnDate", "RefNumber", "Amount",
             "PaymentMethod", "DepositToAccount", "ApplyToRefNumber"]
        ].copy()

    receive_df.to_csv(os.path.join(OUTPUT_DIR, "Receive_Payments_From_Gravity.csv"), index=False)
    return receive_df

def build_cash_receive_payments(emr_df):
    """
    Build a separate Receive Payments file for **cash** payments only.

    Rules:
      - Use EMR NON-service lines (Service/Product blank)
      - payment_type == 'Cash' (case-insensitive)
      - amount != 0
      - For partial payments (cash + card on same invoice), only the cash
        portion goes here; the card portion is already handled via Gravity.

    Output columns (same structure as Gravity receive file):
      Customer | TxnDate | RefNumber | Amount | PaymentMethod | DepositToAccount | ApplyToRefNumber
    """
    df = emr_df.copy()

    # Ensure types
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    df["payment_type"] = df["payment_type"].astype(str)
    df["visit_date"] = pd.to_datetime(df["visit_date"])

    # Identify service vs non-service lines
    service_col = df["service_text"]
    service_mask = service_col.notna() & (service_col.astype(str).str.strip() != "")
    non_service_lines = df[~service_mask].copy()

    # Normalize payment type for filtering
    non_service_lines["payment_type_norm"] = (
        non_service_lines["payment_type"].str.strip().str.lower()
    )

    # Cash payment lines: non-service, payment_type == 'cash', non-zero amount
    cash_lines = non_service_lines[
        (non_service_lines["payment_type_norm"] == "cash") &
        (non_service_lines["amount"] != 0)
    ].copy()

    if cash_lines.empty:
        cash_receive_df = pd.DataFrame(
            columns=[
                "Customer", "TxnDate", "RefNumber", "Amount",
                "PaymentMethod", "DepositToAccount", "ApplyToRefNumber",
            ]
        )
    else:
        cash_receive_df = pd.DataFrame()
        cash_receive_df["Customer"] = cash_lines["Customer"]
        cash_receive_df["TxnDate"] = cash_lines["visit_date"].dt.strftime("%Y-%m-%d")
        # Make a reference that won't collide with card transaction IDs
        cash_receive_df["RefNumber"] = "CASH-" + cash_lines["invoice_number"].astype(str)
        cash_receive_df["Amount"] = cash_lines["amount"].abs()
        cash_receive_df["PaymentMethod"] = "Cash"
        cash_receive_df["DepositToAccount"] = MERCHANT_CLEARING_ACCOUNT
        cash_receive_df["ApplyToRefNumber"] = cash_lines["invoice_number"]

    path = os.path.join(OUTPUT_DIR, "Receive_Payments_Cash.csv")
    cash_receive_df.to_csv(path, index=False)
    return cash_receive_df


# ---------- VENDOR RECEIVABLE JEs ----------

def build_vendor_receivable_jes(emr_df):
    df = emr_df.copy()
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)

    vr = df[df["mapped_to_account"].astype(str).str.contains("Vendor Receivable", na=False)].copy()
    vr = vr[vr["amount"] != 0]

    if vr.empty:
        je_df = pd.DataFrame(columns=[
            "Date", "RefNumber", "Account", "Debit", "Credit", "Name", "Memo"
        ])
        je_df.to_csv(os.path.join(OUTPUT_DIR, "Vendor_Receivable_JournalEntries.csv"), index=False)
        return je_df

    jes = []
    for _, row in vr.iterrows():
        amount = float(row["amount"])
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
    je_df.to_csv(os.path.join(OUTPUT_DIR, "Vendor_Receivable_JournalEntries.csv"), index=False)
    return je_df


# ---------- MAIN PIPELINE ----------

def run_pipeline():
    ensure_output_dir()
    print("Loading files...")

    emr = load_emr()
    tips = load_emr_tips()

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

    print("Checking EMR customers (duplicate IDs with different names)...")
    emr, customer_master = apply_customer_logic(emr, customer_master)
    save_customer_master(customer_master)

    print("Mapping services...")
    emr, _ = map_services(emr, service_map)

    print("Mapping payments...")
    emr, _ = map_payments(emr, payment_map)

    print("Building Invoice_Import_ItemBased.csv...")
    build_invoice_import(emr)

    print("Matching Gravity payments...")
    matched_gravity, _ = match_gravity_payments(emr, gravity)

    print("Building Receive_Payments_From_Gravity.csv...")
    build_receive_payments(matched_gravity)

    print("Building Receive_Payments_Cash.csv...")
    build_cash_receive_payments(emr)

    print("Building Vendor_Receivable_JournalEntries.csv...")
    build_vendor_receivable_jes(emr)

    print("✅ Done. Check the 'output' folder for results.")


if __name__ == "__main__":
    import traceback
    try:
        run_pipeline()
    except Exception as e:
        print("❌ ERROR:", e)
        traceback.print_exc()
