import pandas as pd

from config import COA_FILE, SERVICE_SHEET, PAYMENT_SHEET


def load_coa_mappings():
    service_map = pd.read_excel(COA_FILE, sheet_name=SERVICE_SHEET)
    payment_map = pd.read_excel(COA_FILE, sheet_name=PAYMENT_SHEET)

    service_map.columns = [c.strip().lower().replace(" ", "_") for c in service_map.columns]
    payment_map.columns = [c.strip().lower().replace(" ", "_") for c in payment_map.columns]

    return service_map, payment_map
