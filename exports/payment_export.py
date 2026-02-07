import pandas as pd

from config import MERCHANT_CLEARING_ACCOUNT


def build_receive_payments(matched_df):
    """
    Returns Receive Payments df for Gravity matches (does not write; run_pipeline writes after ledger filtering).
    """
    if matched_df.empty:
        return pd.DataFrame(
            columns=[
                "Customer", "TxnDate", "RefNumber", "Amount",
                "PaymentMethod", "DepositToAccount", "ApplyToRefNumber",
            ]
        )

    df = matched_df.copy()
    df["TxnDate"] = pd.to_datetime(df["TxnDate"]).dt.strftime("%Y-%m-%d")
    df["RefNumber"] = df["transaction_id"]
    df["Amount"] = df["amount"]
    df["PaymentMethod"] = df["card_type"]
    df["DepositToAccount"] = MERCHANT_CLEARING_ACCOUNT

    receive_df = df[
        ["Customer", "TxnDate", "RefNumber", "Amount",
         "PaymentMethod", "DepositToAccount", "ApplyToRefNumber"]
    ].copy()

    return receive_df


def build_cash_receive_payments(emr_df):
    """
    Build a separate Receive Payments file for CASH only.
    For partial payments (cash + card on same invoice), only cash goes here.
    """
    df = emr_df.copy()
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    df["payment_type"] = df["payment_type"].astype(str)
    df["visit_date"] = pd.to_datetime(df["visit_date"])

    service_col = df["service_text"]
    service_mask = service_col.notna() & (service_col.astype(str).str.strip() != "")
    non_service_lines = df[~service_mask].copy()

    non_service_lines["payment_type_norm"] = non_service_lines["payment_type"].str.strip().str.lower()

    cash_lines = non_service_lines[
        (non_service_lines["payment_type_norm"] == "cash") &
        (non_service_lines["amount"] != 0)
    ].copy()

    if cash_lines.empty:
        return pd.DataFrame(
            columns=[
                "Customer", "TxnDate", "RefNumber", "Amount",
                "PaymentMethod", "DepositToAccount", "ApplyToRefNumber",
            ]
        )

    cash_receive_df = pd.DataFrame()
    cash_receive_df["Customer"] = cash_lines["Customer"]
    cash_receive_df["TxnDate"] = cash_lines["visit_date"].dt.strftime("%Y-%m-%d")
    cash_receive_df["RefNumber"] = "CASH-" + cash_lines["invoice_number"].astype(str)
    cash_receive_df["Amount"] = cash_lines["amount"].abs()
    cash_receive_df["PaymentMethod"] = "Cash"
    cash_receive_df["DepositToAccount"] = MERCHANT_CLEARING_ACCOUNT
    cash_receive_df["ApplyToRefNumber"] = cash_lines["invoice_number"]

    return cash_receive_df
