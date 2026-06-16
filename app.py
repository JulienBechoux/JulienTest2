import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

st.set_page_config(layout="wide", page_title="Executive Supply Chain Dashboard")

# =====================================================
# HEADER
# =====================================================
st.title("📊 Executive Supply Chain Dashboard")

st.markdown("""
Upload your SAP datasets and analyze cost drivers, carriers, and performance.
""")

# =====================================================
# UPLOAD
# =====================================================
st.sidebar.header("Upload Files")

accruals_file = st.sidebar.file_uploader("Manual Accruals", type=["xlsx"])
tm_file = st.sidebar.file_uploader("SAP TM", type=["xlsx"])
erp_file = st.sidebar.file_uploader("SAP ERP", type=["xlsx"])

# =====================================================
# HELPERS
# =====================================================
@st.cache_data
def load_excel(file):
    return pd.read_excel(file, engine="openpyxl")

def safe_rename(df):
    """Map all cost/currency columns to unified names."""
    col_map = {
        # Manual Accruals + SAP TM
        "Net Amt in Doc Crcy": "Cost",
        "Net amt in doc crcy": "Cost",

        # SAP ERP
        "Loc.curr.amount": "Cost",
        "Loc curr amount": "Cost",

        # Currency fields
        "Local Curr.": "Currency",
        "Local Curr": "Currency",
        "Currency": "Currency",

        # Date fields
        "Deliv.Date": "Date",
        "Actual Delivered Date": "Date",

        # Route fields
        "Source location": "Source",
        "Destination location": "Destination",
        "Source Location Description": "Source",
        "Destination Location Descripti": "Destination",

        # Carrier fields
        "Carrier": "Carrier",
        "Carrier Description": "Carrier",

        # Delivery type
        "DlvTy": "DlvTy",
    }
    rename_map = {k: v for k, v in col_map.items() if k in df.columns}
    return df.rename(columns=rename_map)

def parse_euro_number(series):
    """Convert European number formats to float."""
    if series is None:
        return pd.Series(dtype=float)
    s = series.astype(str).fillna("").str.strip()
    s = s.str.replace(r"[^\d\-,\.]", "", regex=True)

    def _convert(val):
        if val is None:
            return np.nan
        v = str(val).strip()
        if v == "" or v.lower() == "nan":
            return np.nan
        if v.count(".") > 0 and v.count(",") > 0:
            if v.rfind(",") > v.rfind("."):
                v = v.replace(".", "").replace(",", ".")
            else:
                v = v.replace(",", "")
        else:
            if v.count(",") == 1 and v.count(".") == 0:
                v = v.replace(",", ".")
            else:
                v = v.replace(",", "")
        try:
            return float(v)
        except Exception:
            return np.nan

    return series.apply(_convert)

# =====================================================
# LOAD FILES
# =====================================================
accruals = load_excel(accruals_file) if accruals_file else None
tm = load_excel(tm_file) if tm_file else None
erp = load_excel(erp_file) if erp_file else None

if accruals is None:
    st.warning("Upload Manual Accruals file to start.")
    st.stop()

# =====================================================
# CLEANING
# =====================================================
def clean_accruals(df):
    df = safe_rename(df)

    if "Cost" in df.columns:
        df["Cost"] = parse_euro_number(df["Cost"])

    if "Currency" not in df.columns:
        df["Currency"] = None

    if "Carrier" not in df.columns:
        df["Carrier"] = None

    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce", dayfirst=True)

    if "Source" not in df.columns:
        df["Source"] = None
    if "Destination" not in df.columns:
        df["Destination"] = None

    df["SourceSystem"] = "Accruals"
    return df

def clean_tm(df):
    if df is None:
        return None

    df = safe_rename(df)

    if "Cost" in df.columns:
        df["Cost"] = parse_euro_number(df["Cost"])
    else:
        df["Cost"] = np.nan

    if "Currency" not in df.columns:
        df["Currency"] = None

    if "Carrier" not in df.columns:
        df["Carrier"] = None

    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce", dayfirst=True)

    if "Source" not in df.columns:
        df["Source"] = None
    if "Destination" not in df.columns:
        df["Destination"] = None

    df["SourceSystem"] = "TM"
    return df

def clean_erp(df):
    if df is None:
        return None

    df = safe_rename(df)

    # Cost
    if "Cost" in df.columns:
        df["Cost"] = parse_euro_number(df["Cost"])
    else:
        df["Cost"] = np.nan

    # Currency
    if "Currency" not in df.columns:
        df["Currency"] = None

    # Carrier
    if "Carrier" not in df.columns:
        df["Carrier"] = None

    # Date
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce", dayfirst=True)
    else:
        df["Date"] = None

    # Route logic
    if "Source" not in df.columns:
        df["Source"] = None
    if "Destination" not in df.columns:
        df["Destination"] = None

    # Apply DlvTy rules
    if "DlvTy" in df.columns:
        df["DlvTy"] = df["DlvTy"].astype(str).str.strip()

        # ZZEL → Import
        df.loc[df["DlvTy"] == "ZZEL", "Route"] = "Import"

        # ZZLR, ZZPR, ZZRO → swap source/destination
        swap_mask = df["DlvTy"].isin(["ZZLR", "ZZPR", "ZZRO"])
        df.loc[swap_mask, ["Source", "Destination"]] = df.loc[
            swap_mask, ["Destination", "Source"]
        ].values

    # Build route if not Import
    df["Route"] = df["Route"].fillna(df["Source"].astype(str) + " → " + df["Destination"].astype(str))

    df["SourceSystem"] = "ERP"
    return df

# =====================================================
# UNIFY DATASETS
# =====================================================
accruals = clean_accruals(accruals)
tm = clean_tm(tm)
erp = clean_erp(erp)

frames = [accruals]
if tm is not None:
    frames.append(tm)
if erp is not None:
    frames.append(erp)

df = pd.concat(frames, ignore_index=True, sort=False)

# =====================================================
# FILTERS
# =====================================================
st.sidebar.header("Filters")

# Date filter
if "Date" in df.columns:
    min_d = df["Date"].min()
    max_d = df["Date"].max()
    date_range = st.sidebar.date_input("Date Range", [min_d, max_d])

    df = df[
        (df["Date"] >= pd.to_datetime(date_range[0])) &
        (df["Date"] <= pd.to_datetime(date_range[1]))
    ]

# Carrier filter
if "Carrier" in df.columns:
    carriers = df["Carrier"].dropna().unique()
    selected_carriers = st.sidebar.multiselect("Carrier", carriers, default=carriers)
    df = df[df["Carrier"].isin(selected_carriers)]

# =====================================================
# KPIs
# =====================================================
total_cost = df["Cost"].sum()
shipments = len(df)
avg_cost = df["Cost"].mean()

col1, col2, col3 = st.columns(3)
col1.metric("Total Cost", f"€{total_cost:,.0f}")
col2.metric("Shipments", f"{shipments:,}")
col3.metric("Avg Cost", f"€{avg_cost:,.0f}")

# =====================================================
# COST DRIVERS
# =====================================================
st.subheader("💸 Cost Drivers")

if "Carrier" in df.columns:
    carrier_df = df.groupby("Carrier")["Cost"].sum().sort_values(ascending=False).head(15)
    fig = px.bar(carrier_df, orientation="h")
    st.plotly_chart(fig, use_container_width=True)

# =====================================================
# ROUTES
# =====================================================
if "Route" in df.columns:
    st.subheader("🌍 Top Routes")
    route_df = df.groupby("Route")["Cost"].sum().sort_values(ascending=False).head(15)
    fig = px.bar(route_df, orientation="h")
    st.plotly_chart(fig, use_container_width=True)

# =====================================================
# TREND
# =====================================================
if "Date" in df.columns:
    st.subheader("📈 Cost Trend")
    trend = df.groupby(pd.Grouper(key="Date", freq="W"))["Cost"].sum()
    fig = px.line(trend)
    st.plotly_chart(fig, use_container_width=True)

# =====================================================
# DATA TABLE
# =====================================================
st.subheader("🔍 Data")
st.dataframe(df, use_container_width=True)
