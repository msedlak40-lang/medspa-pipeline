import os
from datetime import timedelta

import pandas as pd

from config import OUTPUT_DIR
from transforms.normalizers import normalize_card_type


def match_gravity_payments(emr_df, gravity_df, date_tolerance_days=3):
    """
    Match Gravity payments directly to EMR **card payment lines**.

    EMR card payment lines:
      - Service/Product blank
      - Amount != 0
      - Payment Type NOT in:
            Client Bank, Alle Rewards, Aspire Awards,
            Reward Points, Clover Gift Card, Cash

    Priority:
      1) Same amount
      2) Same day preferred
      3) Otherwise +/-3 days
      4) Card type tie-breaker (vs/mc/dc/ax)
      5) Ambiguous -> unmatched

    Refunds exported separately.
    """
    gravity_all = gravity_df.copy()

    payments = gravity_all[~gravity_all["is_refund"] & (gravity_all["amount"] > 0)].copy()
    refunds = gravity_all[gravity_all["is_refund"] | (gravity_all["amount"] <= 0)].copy()
    refunds.to_csv(os.path.join(OUTPUT_DIR, "Gravity_Refunds.csv"), index=False)

    emr = emr_df.copy()
    emr["amount"] = pd.to_numeric(emr["amount"], errors="coerce").fillna(0)
    emr["payment_type"] = emr["payment_type"].astype(str)
    emr["visit_date"] = pd.to_datetime(emr["visit_date"])

    service_col = emr["service_text"]
    service_mask = service_col.notna() & (service_col.astype(str).str.strip() != "")
    non_service_lines = emr[~service_mask].copy()

    THIRD_PARTY_TYPES = {
        "client bank",
        "alle rewards",
        "aspire awards",
        "reward points",
        "clover gift card",
        "cash",
    }

    non_service_lines["payment_type_norm"] = non_service_lines["payment_type"].str.strip().str.lower()

    card_lines = non_service_lines[
        (~non_service_lines["payment_type_norm"].isin(THIRD_PARTY_TYPES))
        & (non_service_lines["amount"] != 0)
    ].copy()

    if card_lines.empty:
        payments.to_csv(os.path.join(OUTPUT_DIR, "Unmatched_Gravity_Payments.csv"), index=False)
        return pd.DataFrame(columns=list(payments.columns) + ["Customer", "ApplyToRefNumber", "TxnDate"]), payments

    card_lines["card_payment"] = card_lines["amount"].abs().round(2)
    card_lines["card_type_key"] = card_lines["payment_type_norm"].apply(normalize_card_type)

    card_details = card_lines[
        ["invoice_number", "visit_date", "Customer", "card_payment", "card_type_key"]
    ].copy()

    matched_rows = []
    unmatched_rows = []

    for _, g in payments.iterrows():
        g_amt = round(float(g["amount"]), 2)
        g_date = g["settlement_date"]
        g_card_key = normalize_card_type(g["card_type"])

        candidates = card_details[card_details["card_payment"] == g_amt].copy()
        if candidates.empty:
            unmatched_rows.append(g)
            continue

        candidates["date_diff"] = (candidates["visit_date"] - g_date).abs()

        chosen = None

        same_day = candidates[candidates["date_diff"] == pd.Timedelta(days=0)]
        if len(same_day) == 1:
            chosen = same_day.iloc[0]
        elif len(same_day) > 1:
            ct_match = same_day[same_day["card_type_key"].fillna("") == g_card_key]
            if len(ct_match) == 1:
                chosen = ct_match.iloc[0]

        if chosen is None:
            in_window = candidates[candidates["date_diff"] <= timedelta(days=date_tolerance_days)]
            if len(in_window) == 1:
                chosen = in_window.iloc[0]
            elif len(in_window) > 1:
                ct_match = in_window[in_window["card_type_key"].fillna("") == g_card_key]
                if len(ct_match) == 1:
                    chosen = ct_match.iloc[0]

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
