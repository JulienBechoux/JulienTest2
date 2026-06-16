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
# CACHED LOADERS
# =====================================================
@st.cache_data
def load_excel(file):
    return pd.read_excel(file, engine="openpyxl")

@st.cache_data
def load_erp(file):
    df = pd.read_excel(file, engine="openpyxl")

    # Keep only useful columns
    keep_cols = [c for c in df.columns if c in ["Material", "Matl Group", "Net value"]]
    df = df[keep_cols]

    # Reduce size if too large
    if len(df) > 200000:
        df = df.sample(200000, random_state=42)

    return df

# =====================================================
# LOAD DATA
# =====================================================
accruals = load_excel(accruals_file) if accruals_file else None
tm = load_excel(tm_file) if tm_file else None
erp = load_erp(erp_file) if erp_file else None

# =====================================================
# SAFETY
# =====================================================
if accruals is None:
    st.warning("Upload Manual Accruals file to start.")
    st.stop()

if tm is None:
    st.info("SAP TM not uploaded — limited transport metrics")

if erp is None:
    st.info("SAP ERP not uploaded — limited product insights")

# =====================================================
# CLEANING FUNCTIONS
# =====================================================
def safe_rename(df):
    col_map = {
        "Net Amt in Doc Crcy": "Cost",
        "Net value": "NetValue"
    }
    return df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

@st.cache_data
def parse_euro_number(series):
    return pd.to_numeric(
        series.astype(str)
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False),
        errors="coerce"
    )

# =====================================================
# PREPARE DATA (CACHED)
# =====================================================
@st.cache_data
def prepare_data(accruals, tm, erp):

    accruals = safe_rename(accruals)

    # Parse dates once
    for col in accruals.columns:
        if "Date" in col:
            accruals[col] = pd.to_datetime(accruals[col], errors="coerce")

    # TM processing
    if tm is not None:
        tm = safe_rename(tm)

        if "Gross Weight" in tm.columns:
            tm["Gross Weight"] = parse_euro_number(tm["Gross Weight"])

        if "Cost" in tm.columns and "Gross Weight" in tm.columns:
            tm["Cost_per_kg"] = tm["Cost"] / tm["Gross Weight"].replace(0, np.nan)

    # ERP rename
    if erp is not None:
        erp = safe_rename(erp)

    return accruals, tm, erp

accruals, tm, erp = prepare_data(accruals, tm, erp)

# =====================================================
# FILTERS
# =====================================================
st.sidebar.header("Filters")

status_filter = []
if "Execution Status" in accruals.columns:
    status_filter = st.sidebar.multiselect(
        "Status",
        accruals["Execution Status"].dropna().unique(),
        default=accruals["Execution Status"].dropna().unique()
    )

date_range = None
if "Actual Delivered Date" in accruals.columns:
    date_range = st.sidebar.date_input(
        "Date Range",
        [accruals["Actual Delivered Date"].min(),
         accruals["Actual Delivered Date"].max()]
    )

df = accruals.copy()

if status_filter and "Execution Status" in df.columns:
    df = df[df["Execution Status"].isin(status_filter)]

if date_range and "Actual Delivered Date" in df.columns:
    df = df[
        (df["Actual Delivered Date"] >= pd.to_datetime(date_range[0])) &
        (df["Actual Delivered Date"] <= pd.to_datetime(date_range[1]))
    ]

# =====================================================
# PRE-AGGREGATIONS (CACHED)
# =====================================================
@st.cache_data
def compute_aggregations(df):

    results = {}

    if "Carrier Description" in df.columns:
        carrier = df.groupby("Carrier Description")["Cost"].agg(["sum", "count"])
        carrier["cost_per_shipment"] = carrier["sum"] / carrier["count"]
        results["carrier"] = carrier.sort_values("sum", ascending=False).head(10)

    if "Actual Delivered Date" in df.columns:
        time = df.groupby(pd.Grouper(key="Actual Delivered Date", freq="W"))["Cost"].sum()
        results["time"] = time

    if "Carrier Description" in df.columns:
        total_cost = df.groupby("Carrier Description")["Cost"].sum()
        results["top_carrier"] = total_cost.idxmax()
        results["top_cost"] = total_cost.max()

    return results

agg = compute_aggregations(df)

# =====================================================
# KPIs
# =====================================================
total_cost = df["Cost"].sum() if "Cost" in df.columns else 0
shipments = len(df)
avg_cost = df["Cost"].mean() if "Cost" in df.columns else 0

exec_rate = 0
if "Execution Status" in df.columns:
    exec_rate = (df["Execution Status"] == "Executed").mean()

avg_cost_per_kg = tm["Cost_per_kg"].mean() if tm is not None and "Cost_per_kg" in tm else 0

col1, col2, col3, col4, col5 = st.columns(5)

col1.metric("Total Cost", f"€{total_cost:,.0f}")
col2.metric("Shipments", f"{shipments:,}")
col3.metric("Avg Cost", f"€{avg_cost:,.0f}")
col4.metric("Execution Rate", f"{exec_rate*100:.1f}%")
col5.metric("Avg €/kg", f"{avg_cost_per_kg:.2f}")

# =====================================================
# COST DRIVERS
# =====================================================
st.subheader("💸 Cost Drivers")

if "carrier" in agg:
    fig = px.bar(
        agg["carrier"],
        x=agg["carrier"].index,
        y="sum"
    )
    st.plotly_chart(fig, use_container_width=True)

# =====================================================
# NETWORK
# =====================================================
if "Source Location Description" in df.columns and "Destination Location Descripti" in df.columns:

    st.subheader("🌍 Top Routes")

    df["Route"] = df["Source Location Description"] + " → " + df["Destination Location Descripti"]
    route_df = df.groupby("Route")["Cost"].sum().sort_values(ascending=False).head(15)

    fig = px.bar(route_df, orientation="h")
    st.plotly_chart(fig, use_container_width=True)

# =====================================================
# CARRIER PERFORMANCE
# =====================================================
if "carrier" in agg:
    st.subheader("🚚 Carrier Performance")

    fig = px.scatter(
        agg["carrier"],
        x="count",
        y="cost_per_shipment",
        size="sum",
        hover_name=agg["carrier"].index
    )
    st.plotly_chart(fig, use_container_width=True)

# =====================================================
# ERP ANALYSIS
# =====================================================
if erp is not None and "NetValue" in erp.columns:

    st.subheader("📦 Product Value")

    group_col = st.selectbox("Group by", [c for c in ["Matl Group", "Material"] if c in erp.columns])

    erp_group = erp.groupby(group_col)["NetValue"].sum().nlargest(10)

    fig = px.bar(erp_group)
    st.plotly_chart(fig, use_container_width=True)

# =====================================================
# SIMULATOR
# =====================================================
if "top_cost" in agg:
    st.subheader("🧮 Cost Optimization")

    reduction = st.slider("Reduce top carrier cost (%)", 0, 30, 10)

    savings = agg["top_cost"] * reduction / 100

    st.metric("Estimated Savings", f"€{savings:,.0f}")
    st.info(f"Top carrier: {agg['top_carrier']}")

# =====================================================
# TREND
# =====================================================
if "time" in agg:
    st.subheader("📈 Cost Trend")
    fig = px.line(agg["time"])
    st.plotly_chart(fig, use_container_width=True)

# =====================================================
# DATA TABLE
# =====================================================
st.subheader("🔍 Data")
st.dataframe(df, use_container_width=True)



