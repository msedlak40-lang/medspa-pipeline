import os

import pandas as pd

from config import CUSTOMER_MASTER_FILE, OUTPUT_DIR


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
    """
    EMR is source of truth for ID.
    If a patient_id appears with a different name vs historical master, we flag it.
    Returns (emr_df_with_Customer, updated_master, conflicts_df).
    """
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
        print(f"Warning: Name conflicts found. See {conflict_path}")
    else:
        print("No patient ID/name conflicts found.")

    existing_ids = set(master["patient_id"])
    new_rows = emr[~emr["patient_id"].isin(existing_ids)][
        ["patient_id", "patient_name"]
    ].drop_duplicates()

    if not new_rows.empty:
        master = pd.concat([master, new_rows], ignore_index=True)

    # Use EMR name as QB Customer name (your current approach)
    emr["Customer"] = emr["patient_name"]
    return emr, master, conflicts
