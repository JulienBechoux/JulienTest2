# =====================================================
# AUTO‑CLEAN EDGE METADATA INJECTION
# =====================================================
import os, sys

def _clean_edge_injection():
    """
    Removes any Edge browser metadata accidentally injected into this file.
    Prevents crashes like InvalidIndexError during concat.
    """
    bad_markers = [
        "edge_all_open_tabs",
        "User's Edge browser tabs metadata",
        "pageTitle",
        "pageUrl",
        "tabId",
        "isCurrent"
    ]

    try:
        with open(__file__, "r", encoding="utf-8") as f:
            lines = f.readlines()

        cleaned = []
        skipping = False

        for line in lines:
            if any(marker in line for marker in bad_markers):
                skipping = True
                continue

            if skipping:
                if line.strip().endswith("]") or line.strip().endswith("}"):
                    skipping = False
                continue

            cleaned.append(line)

        if len(cleaned) != len(lines):
            with open(__file__, "w", encoding="utf-8") as f:
                f.writelines(cleaned)
            print("⚠️ Edge metadata removed from app.py")

    except Exception:
        pass

_clean_edge_injection()

# =====================================================
# REAL APPLICATION STARTS HERE
# =====================================================

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import base64

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
    """Map all cost/currency/date/route columns to unified names safely."""

    rename_map = {}

    # Cost fields
    for col in df.columns:
        if col.strip().lower() in [
            "net amt in doc crcy",
            "net amt in doc crcy ",
            "net amt",
            "loc.curr.amount",
            "loc curr amount",
        ]:
            rename_map[col] = "Cost"

    # Currency fields
    for col in df.columns:
        if col.strip().lower() in ["local curr.", "local curr", "currency"]:
            rename_map[col] = "Currency"

    # Date fields
    for col in df.columns:
        if col.strip().lower() in ["deliv.date", "actual delivered date"]:
            rename_map[col] = "Date"

    # Carrier fields
    for col in df.columns:
        if col.strip().lower() in ["carrier", "carrier description"]:
            rename_map[col] = "Carrier"

    # Delivery type
    for col in df.columns:
        if col.strip().lower() == "dlvty":
            rename_map[col] = "DlvTy"

    # Route fields — only FIRST becomes Source/Destination
    source_candidates = [c for c in df.columns if "source" in c.lower()]
    dest_candidates = [c for c in df.columns if "dest" in c.lower()]

    if source_candidates:
        rename_map[source_candidates[0]] = "Source"
        for i, col in enumerate(source_candidates[1:], start=2):
            rename_map[col] = f"Source_{i}"

    if dest_candidates:
        rename_map[dest_candidates[0]] = "Destination"
        for i, col in enumerate(dest_candidates[1:], start=2):
            rename_map[col] = f"Destination_{i}"

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
# CLEANING FUNCTIONS
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

# FORCE UNIQUE COLUMN NAMES BEFORE CONCAT
for f in frames:
    f.columns = pd.io.parsers.ParserBase({'names': f.columns})._maybe_dedup_names(f.columns)

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

# =====================================================
# DOWNLOAD SAFE VERSION OF APP.PY
# =====================================================
with open(__file__, "r", encoding="utf-8") as f:
    app_code = f.read()

st.sidebar.download_button(
    label="⬇️ Download app.py (safe)",
    data=app_code,
    file_name="app.py",
    mime="text/plain"
)
