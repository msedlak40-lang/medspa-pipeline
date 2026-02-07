import pandas as pd

from config import GRAVITY_FILE


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

    # Refunds: negative sale amount
    df["is_refund"] = df["sale_amount"] < 0

    return df[
        ["settlement_date", "amount", "card_type", "transaction_id", "is_refund",
         "sale_amount", "tip", "type", "card", "name", "cashier", "source"]
    ].copy()
