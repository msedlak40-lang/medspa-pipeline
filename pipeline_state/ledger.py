import os

import pandas as pd

from config import LEDGER_FILE
from utils.file_utils import ensure_state_dir


def load_posted_ledger() -> set:
    """
    Returns a set of posted keys already exported/imported.
    Ledger is stored locally at state/posted_ledger.csv and is NOT committed to git.
    """
    ensure_state_dir()
    if not os.path.exists(LEDGER_FILE):
        return set()

    try:
        df = pd.read_csv(LEDGER_FILE, dtype=str)
    except Exception:
        return set()

    if "posted_key" not in df.columns:
        return set()

    return set(df["posted_key"].dropna().astype(str))


def append_to_posted_ledger(keys, run_id: str):
    """
    Append posted keys to ledger. Assumes "exported = imported" per your workflow.
    """
    ensure_state_dir()
    keys = [k for k in keys if isinstance(k, str) and k.strip()]

    if not keys:
        return

    df_new = pd.DataFrame({
        "posted_key": keys,
        "run_id": run_id,
        "posted_utc": pd.Timestamp.utcnow().isoformat()
    })

    if os.path.exists(LEDGER_FILE):
        df_new.to_csv(LEDGER_FILE, mode="a", header=False, index=False)
    else:
        df_new.to_csv(LEDGER_FILE, index=False)


def filter_invoices_by_ledger(invoice_df: pd.DataFrame, posted_keys: set):
    df = invoice_df.copy()
    df["__posted_key"] = "INV|" + df["RefNumber"].astype(str)
    keep = ~df["__posted_key"].isin(posted_keys)
    return df[keep].drop(columns=["__posted_key"]), df[~keep].drop(columns=["__posted_key"])


def filter_card_payments_by_ledger(receive_df: pd.DataFrame, posted_keys: set):
    df = receive_df.copy()
    # RefNumber for card payments = Gravity transaction_id (Approval)
    df["__posted_key"] = "CC|" + df["RefNumber"].astype(str)
    keep = ~df["__posted_key"].isin(posted_keys)
    return df[keep].drop(columns=["__posted_key"]), df[~keep].drop(columns=["__posted_key"])


def filter_cash_payments_by_ledger(cash_df: pd.DataFrame, posted_keys: set):
    df = cash_df.copy()
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0)
    amt_str = df["Amount"].round(2).map(lambda x: f"{x:.2f}")
    df["__posted_key"] = "CASH|" + df["ApplyToRefNumber"].astype(str) + "|" + amt_str
    keep = ~df["__posted_key"].isin(posted_keys)
    return df[keep].drop(columns=["__posted_key"]), df[~keep].drop(columns=["__posted_key"])


def filter_vendor_jes_by_ledger(je_df: pd.DataFrame, posted_keys: set):
    """
    Vendor JE file has multiple lines per journal entry. We create a deterministic key per line.
    """
    df = je_df.copy().reset_index(drop=True)
    df["__posted_key"] = "VR|" + df["RefNumber"].astype(str) + "|" + df.index.astype(str)
    keep = ~df["__posted_key"].isin(posted_keys)
    return df[keep].drop(columns=["__posted_key"]), df[~keep].drop(columns=["__posted_key"])
