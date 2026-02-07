import os

import pandas as pd

from config import OUTPUT_DIR


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
