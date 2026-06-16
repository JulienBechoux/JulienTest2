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
    # Read full sheet (first sheet by default)
    df = pd.read_excel(file, engine="openpyxl")

    # Keep only useful columns if present
    keep_candidates = [
        "Material", "Matl Group", "Net value",
        "Loc.curr.amount", "Local Curr.", "Loc curr amount", "Local Curr"
    ]
    keep_cols = [c for c in df.columns if c in keep_candidates]
    if keep_cols:
        df = df[keep_cols].copy()

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
    """
    Map common source column names to canonical names used in the app.
    - For SAP TM and Manual accruals: map 'Net Amt in Doc Crcy' -> 'Cost'
    - For SAP ERP: map 'Loc.curr.amount' -> 'NetValue' and 'Local Curr.' -> 'Currency'
    - Also map other common variants.
    """
    col_map = {
        # TM / accruals
        "Net Amt in Doc Crcy": "Cost",
        "Net Amt in Doc Crcy ": "Cost",
        "Net amt in doc crcy": "Cost",
        "Net value": "NetValue",
        # ERP specific
        "Loc.curr.amount": "NetValue",
        "Loc.curr.amount ": "NetValue",
        "Loc curr amount": "NetValue",
        "Loc.curr.amount.": "NetValue",
        "Local Curr.": "Currency",
        "Local Curr": "Currency",
        "Local Curr. ": "Currency",
        "Local Curr .": "Currency",
        # Generic
        "Net value ": "NetValue",
    }
    # Only rename columns that exist
    rename_map = {k: v for k, v in col_map.items() if k in df.columns}
    return df.rename(columns=rename_map)

@st.cache_data
def parse_euro_number(series):
    """
    Convert numbers that may use '.' as thousand separator and ',' as decimal separator
    into float. Also handles plain numeric strings.
    """
    if series is None:
        return series
    s = series.astype(str).fillna("").str.strip()
    # Remove currency symbols and spaces
    s = s.str.replace(r"[^\d\-,\.]", "", regex=True)
    # Heuristic conversions:
    # If there are both '.' and ',' and '.' appears before ',' -> '.' thousands, ',' decimal
    def _convert(val):
        if val is None or val == "" or val.lower() == "nan":
            return np.nan
        v = str(val)
        # remove leading/trailing whitespace
        v = v.strip()
        # if both separators present
        if v.count(".") > 0 and v.count(",") > 0:
            # assume dot thousands, comma decimal if last comma is after last dot
            if v.rfind(",") > v.rfind("."):
                v = v.replace(".", "").replace(",", ".")
            else:
                v = v.replace(",", "")
        else:
            # only commas -> treat comma as decimal
            if v.count(",") == 1 and v.count(".") == 0:
                v = v.replace(",", ".")
            else:
                # remove any thousands separators (commas)
                v = v.replace(",", "")
        try:
            return float(v)
        except Exception:
            return np.nan
    return series.apply(_convert)

# =====================================================
# PREPARE DATA (CACHED)
# =====================================================
@st.cache_data
def prepare_data(accruals, tm, erp):

    # --- Manual accruals ---
    accruals = safe_rename(accruals)

    # Parse dates once for any column that looks like a date
    for col in accruals.columns:
        if "Date" in col or "date" in col.lower():
            try:
                accruals[col] = pd.to_datetime(accruals[col], errors="coerce", dayfirst=True)
            except Exception:
                accruals[col] = pd.to_datetime(accruals[col], errors="coerce")

    # Ensure Cost column exists for accruals (map Net Amt in Doc Crcy -> Cost)
    if "Cost" in accruals.columns:
        accruals["Cost"] = parse_euro_number(accruals["Cost"])
    else:
        # try other likely columns
        possible_amounts = [c for c in accruals.columns if "amt" in c.lower() or "amount" in c.lower() or "net" in c.lower()]
        if possible_amounts:
            accruals["Cost"] = parse_euro_number(accruals[possible_amounts[0]])
        else:
            accruals["Cost"] = 0.0

    # --- TM processing ---
    if tm is not None:
        tm = safe_rename(tm)

        # TM: 'Net Amt in Doc Crcy' should map to 'Cost' via safe_rename
        if "Cost" in tm.columns:
            tm["Cost"] = parse_euro_number(tm["Cost"])
        else:
            # fallback: try to find a numeric-like column
            possible_amounts = [c for c in tm.columns if "amt" in c.lower() or "amount" in c.lower() or "net" in c.lower()]
            if possible_amounts:
                tm["Cost"] = parse_euro_number(tm[possible_amounts[0]])
            else:
                tm["Cost"] = np.nan

        # TM currency column is typically 'Currency' (per your note)
        if "Currency" in tm.columns:
            tm["Currency"] = tm["Currency"].astype(str).str.strip()
        else:
            # try common variants
            possible_curr = [c for c in tm.columns if "curr" in c.lower() or "currency" in c.lower()]
            if possible_curr:
                tm["Currency"] = tm[possible_curr[0]].astype(str).str.strip()
            else:
                tm["Currency"] = None

        # Gross Weight -> numeric
        if "Gross Weight" in tm.columns:
            tm["Gross Weight"] = parse_euro_number(tm["Gross Weight"])

        # Cost per kg
        if "Cost" in tm.columns and "Gross Weight" in tm.columns:
            tm["Cost_per_kg"] = tm["Cost"] / tm["Gross Weight"].replace(0, np.nan)
        else:
            tm["Cost_per_kg"] = np.nan

    # --- ERP processing ---
    if erp is not None:
        erp = safe_rename(erp)

        # ERP: Loc.curr.amount -> NetValue (per your note)
        if "NetValue" in erp.columns:
            erp["NetValue"] = parse_euro_number(erp["NetValue"])
        else:
            # fallback: try to find a numeric-like column
            possible_amounts = [c for c in erp.columns if "loc" in c.lower() and "amt" in c.lower() or "amount" in c.lower() or "net" in c.lower()]
            if possible_amounts:
                erp["NetValue"] = parse_euro_number(erp[possible_amounts[0]])
            else:
                erp["NetValue"] = np.nan

        # ERP currency column: Local Curr. -> Currency
        if "Currency" in erp.columns:
            erp["Currency"] = erp["Currency"].astype(str).str.strip()
        else:
            possible_curr = [c for c in erp.columns if "curr" in c.lower() or "currency" in c.lower()]
            if possible_curr:
                erp["Currency"] = erp[possible_curr[0]].astype(str).str.strip()
            else:
                erp["Currency"] = None

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
# prefer parsed 'Actual Delivered Date' if present, else original column
date_col = None
if "Actual Delivered Date" in accruals.columns:
    date_col = "Actual Delivered Date"
else:
    # try to find any date-like column
    date_candidates = [c for c in accruals.columns if "date" in c.lower()]
    if date_candidates:
        date_col = date_candidates[0]

if date_col:
    try:
        accruals[date_col] = pd.to_datetime(accruals[date_col], errors="coerce", dayfirst=True)
    except Exception:
        accruals[date_col] = pd.to_datetime(accruals[date_col], errors="coerce")
    date_range = st.sidebar.date_input(
        "Date Range",
        [accruals[date_col].min(), accruals[date_col].max()]
    )

df = accruals.copy()

if status_filter and "Execution Status" in df.columns:
    df = df[df["Execution Status"].isin(status_filter)]

if date_range and date_col in df.columns:
    df = df[
        (df[date_col] >= pd.to_datetime(date_range[0])) &
        (df[date_col] <= pd.to_datetime(date_range[1]))
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

    # Use the date_col if present
    if date_col in df.columns:
        time = df.groupby(pd.Grouper(key=date_col, freq="W"))["Cost"].sum()
        results["time"] = time

    if "Carrier Description" in df.columns:
        total_cost = df.groupby("Carrier Description")["Cost"].sum()
        if not total_cost.empty:
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

avg_cost_per_kg = tm["Cost_per_kg"].mean() if tm is not None and "Cost_per_kg" in tm.columns else 0

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

    df["Route"] = df["Source Location Description"].astype(str) + " → " + df["Destination Location Descripti"].astype(str)
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
