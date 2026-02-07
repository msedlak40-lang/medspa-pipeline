import os

import pandas as pd

from config import OUTPUT_DIR


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

    unmapped = merged[merged["matched_item"].isna() & merged["service_text"].notna()][["service_text"]].drop_duplicates()
    unmapped = unmapped.rename(columns={"service_text": "unmapped_service_text"})
    unmapped.to_csv(os.path.join(OUTPUT_DIR, "Unmapped_Services.csv"), index=False)

    return merged, unmapped
