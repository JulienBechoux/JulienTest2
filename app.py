# app.py
import re
import logging
from typing import Dict, Optional
import pandas as pd
from pandas import DataFrame

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Expected logical columns and common variants to match against Excel headers
COLUMN_VARIANTS = {
    "net_amount": ["net amt in doc crcy", "net amt", "net amount", "net_amt", "net amount in doc crcy"],
    "currency": ["currency", "curr"],
    "incoterm": ["incoterm", "inco term"],
    "carrier": ["carrier", "carrier description"],
    "source_location": ["source location description", "source location", "source"],
    "destination_location": ["destination location description", "destination location", "destination"],
    "purchasing_org": ["purchasing org.", "purchasing org", "purchasing_org"],
    "company_id": ["company id", "company_id"],
    "freight_order_type": ["freight order type", "freight order"],
    "freight_account": ["freight account", "freight_account"],
    "cost_center": ["cost center", "cost_center"],
    "actual_delivered_date": ["actual delivered date", "actual delivered", "actual_delivered_date"],
    "planned_arrival_date": ["planned arrival date-last stop", "planned arrival date", "planned arrival"],
    "execution_status": ["execution status", "status", "execution_status"],
    "net_amount_currency": ["net amt in doc crcy currency", "net amt currency"]
}

DATE_REGEX = re.compile(r"(\d{1,2}\.\d{1,2}\.\d{4}\s+\d{1,2}:\d{2}:\d{2})")

def _normalize_header(h: str) -> str:
    if pd.isna(h):
        return ""
    return re.sub(r"[^0-9a-z]+", " ", str(h).strip().lower())

def _find_column(df: DataFrame, variants: list) -> Optional[str]:
    headers = {col: _normalize_header(col) for col in df.columns}
    for col, norm in headers.items():
        for v in variants:
            if v in norm:
                return col
    # fallback: try exact match on normalized header
    for col, norm in headers.items():
        for v in variants:
            if norm == v:
                return col
    return None

def map_columns(df: DataFrame) -> Dict[str, Optional[str]]:
    """Return mapping from logical name to actual DataFrame column name (or None)."""
    mapping = {}
    for logical, variants in COLUMN_VARIANTS.items():
        mapping[logical] = _find_column(df, variants)
    return mapping

def _extract_datetime_from_string(s: str) -> Optional[pd.Timestamp]:
    if pd.isna(s):
        return None
    s = str(s).strip()
    # Try to find a dd.mm.yyyy HH:MM:SS pattern
    m = DATE_REGEX.search(s)
    if m:
        dt_str = m.group(1)
        try:
            # dayfirst True because format is dd.mm.yyyy
            return pd.to_datetime(dt_str, dayfirst=True, errors="coerce")
        except Exception:
            return None
    # fallback: try generic parse
    try:
        return pd.to_datetime(s, dayfirst=True, errors="coerce")
    except Exception:
        return None

def _to_numeric_amount(x):
    if pd.isna(x):
        return None
    s = str(x).strip()
    # Remove non-numeric except dot and comma and minus
    s = re.sub(r"[^\d\-,\.]", "", s)
    # If comma used as decimal separator and dot as thousands, handle common cases:
    if s.count(",") == 1 and s.count(".") > 1:
        # remove dots (thousands), replace comma with dot
        s = s.replace(".", "").replace(",", ".")
    elif s.count(",") > 1 and s.count(".") == 1:
        # remove commas (thousands)
        s = s.replace(",", "")
    else:
        # unify comma to dot if comma looks like decimal separator
        if s.count(",") == 1 and s.count(".") == 0:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    try:
        return float(s)
    except Exception:
        return None

def normalize_status(s: str) -> Optional[str]:
    if pd.isna(s):
        return None
    s = str(s).strip().lower()
    if "executed" in s:
        return "Executed"
    if "in execution" in s or "in execution" == s:
        return "In Execution"
    return s.title() if s else None

def load_and_clean_manual_accruals(path: str, sheet_name=0) -> DataFrame:
    """
    Load the updated 'Manual accruals.xlsx' and return a cleaned DataFrame.
    - path: path to the Excel file
    - sheet_name: sheet index or name
    """
    df = pd.read_excel(path, sheet_name=sheet_name, dtype=object)
    original_cols = list(df.columns)
    logger.info("Loaded file with columns: %s", original_cols)

    mapping = map_columns(df)
    logger.info("Column mapping detected: %s", mapping)

    # Build cleaned DataFrame with canonical column names
    cleaned = pd.DataFrame()
    # Copy mapped columns or create empty columns if missing
    for logical in COLUMN_VARIANTS.keys():
        actual = mapping.get(logical)
        if actual is not None:
            cleaned[logical] = df[actual]
        else:
            cleaned[logical] = pd.NA
            logger.warning("Missing expected column for '%s' - filled with NA", logical)

    # Parse dates
    cleaned["actual_delivered_date_parsed"] = cleaned["actual_delivered_date"].apply(_extract_datetime_from_string)
    cleaned["planned_arrival_date_parsed"] = cleaned["planned_arrival_date"].apply(_extract_datetime_from_string)

    # Convert net amount to numeric
    # Try to find the best net amount column: prefer 'net_amount' logical mapping
    cleaned["net_amount_value"] = cleaned["net_amount"].apply(_to_numeric_amount)

    # If there is a separate currency column, keep it
    cleaned["currency"] = cleaned.get("currency", pd.Series([pd.NA]*len(cleaned)))

    # Normalize execution status
    cleaned["execution_status_normalized"] = cleaned["execution_status"].apply(normalize_status)

    # Trim whitespace for text columns
    text_cols = ["carrier", "source_location", "destination_location", "purchasing_org", "company_id", "freight_order_type", "freight_account", "cost_center"]
    for c in text_cols:
        if c in cleaned.columns:
            cleaned[c] = cleaned[c].astype(str).replace("nan", pd.NA).apply(lambda x: x.strip() if pd.notna(x) else x)

    # Reorder columns to a sensible order
    final_cols = [
        "net_amount_value", "currency", "incoterm", "carrier",
        "source_location", "destination_location", "purchasing_org",
        "company_id", "freight_order_type", "freight_account", "cost_center",
        "actual_delivered_date_parsed", "planned_arrival_date_parsed",
        "execution_status_normalized"
    ]
    # Keep only those that exist
    final_cols = [c for c in final_cols if c in cleaned.columns]
    cleaned = cleaned[final_cols]

    # Final housekeeping: set dtypes
    if "net_amount_value" in cleaned.columns:
        cleaned["net_amount_value"] = pd.to_numeric(cleaned["net_amount_value"], errors="coerce")

    logger.info("Cleaning complete. Resulting columns: %s", list(cleaned.columns))
    return cleaned

# Example usage when integrating into your app:
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python app.py <path_to_manual_accruals.xlsx>")
        sys.exit(1)
    path = sys.argv[1]
    df_clean = load_and_clean_manual_accruals(path)
    print(df_clean.head(10).to_string(index=False))
