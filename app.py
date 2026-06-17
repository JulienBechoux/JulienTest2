# app.py
import io
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st


# ------------- Helpers -------------------------------------------------


def _clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.replace("\n", " ", regex=False)
        .str.replace("\r", " ", regex=False)
    )
    return df


def _parse_date(series, dayfirst=True):
    return pd.to_datetime(series, errors="coerce", dayfirst=dayfirst)


def _strip_after_slash(text: str) -> str:
    if pd.isna(text):
        return text
    return str(text).split(" /")[0]


# ------------- Transformations ----------------------------------------


def transform_manual_accruals(df: pd.DataFrame) -> pd.DataFrame:
    df = _clean_column_names(df)

    # Column names as seen in the sample
    col_doc = "Document"
    col_value = "Net Amt in Doc Crcy"
    col_curr = "Currency"
    col_carrier_desc = "Carrier Description"
    col_pbu = "PBU"
    col_date = "Planned Arrival Date-Last Stop"
    col_origin = "Source Location Description"
    col_dest = "Destination Location Descripti"

    # Basic safety
    for c in [
        col_doc,
        col_value,
        col_curr,
        col_carrier_desc,
        col_pbu,
        col_date,
        col_origin,
        col_dest,
    ]:
        if c not in df.columns:
            st.warning(f"[Manual accruals] Expected column '{c}' not found.")
    # Carrier
    df["Carrier"] = df[col_carrier_desc].apply(_strip_after_slash)

    # Type of goods
    df["Type of goods"] = df[col_pbu].fillna("Unknown")

    # Date
    df["Date"] = _parse_date(df[col_date])

    # Origin / Destination
    df["Origin"] = df[col_origin]
    df["Destination"] = df[col_dest]

    # Value / Currency
    df["Value"] = pd.to_numeric(df[col_value], errors="coerce")
    df["Currency"] = df[col_curr]

    df["Source System"] = "Manual Accruals"

    return df[
        [
            "Source System",
            "Carrier",
            "Type of goods",
            "Date",
            "Origin",
            "Destination",
            "Value",
            "Currency",
        ]
    ].dropna(subset=["Date", "Carrier", "Origin", "Destination", "Value"])


def transform_sap_erp(
    df_erp: pd.DataFrame,
    df_carrier: pd.DataFrame,
    df_shippt: pd.DataFrame,
    df_plants: pd.DataFrame,
    df_customers: pd.DataFrame,
) -> pd.DataFrame:
    df_erp = _clean_column_names(df_erp)
    df_carrier = _clean_column_names(df_carrier)
    df_shippt = _clean_column_names(df_shippt)
    df_plants = _clean_column_names(df_plants)
    df_customers = _clean_column_names(df_customers)

    # Expected columns (SAP ERP)
    col_servcagent = "ServcAgent"
    col_prod_hier = "Product Hierarchy"
    col_date = "Deliv.Date"
    col_shpt = "ShPt"
    col_shipto = "Ship-To"
    col_plnt = "Plnt"
    col_value = "Loc.curr.amount"
    col_curr = "Local Curr."

    for c in [
        col_servcagent,
        col_prod_hier,
        col_date,
        col_shpt,
        col_shipto,
        col_plnt,
        col_value,
        col_curr,
    ]:
        if c not in df_erp.columns:
            st.warning(f"[SAP ERP] Expected column '{c}' not found.")

    # Carrier mapping
    # ERP Carrier Name: first column is supplier number, second is Name 1
    carrier_key = df_carrier.columns[0]
    carrier_name = df_carrier.columns[1]
    carrier_map = df_carrier.set_index(carrier_key)[carrier_name]

    df_erp["Carrier"] = df_erp[col_servcagent].map(carrier_map).fillna(
        df_erp[col_servcagent].astype(str)
    )

    # Type of goods from Product Hierarchy
    def classify_type(ph):
        ph = str(ph) if not pd.isna(ph) else ""
        if ph.startswith("1") or ph.startswith("4"):
            return "FG"
        return "NFG"

    df_erp["Type of goods"] = df_erp[col_prod_hier].apply(classify_type)

    # Date
    df_erp["Date"] = _parse_date(df_erp[col_date])

    # Origin from Shipping Point
    shippt_key = "ShPt"
    shippt_desc = "Description"
    if shippt_key not in df_shippt.columns or shippt_desc not in df_shippt.columns:
        st.warning("[ERP Shipping Point] Expected columns not found.")
        shippt_map = {}
    else:
        shippt_map = df_shippt.set_index(shippt_key)[shippt_desc]

    df_erp["Origin"] = df_erp[col_shpt].map(shippt_map)
    df_erp.loc[df_erp[col_shpt].isna() | (df_erp[col_shpt] == ""), "Origin"] = "Import"

    # Destination mapping
    cust_key = df_customers.columns[0] if len(df_customers.columns) > 1 else None
    cust_name = df_customers.columns[1] if len(df_customers.columns) > 1 else None
    if cust_key and cust_name:
        cust_map = df_customers.set_index(cust_key)[cust_name]
    else:
        cust_map = {}

    plant_key = "Plnt"
    plant_name = "Name 1"
    if plant_key not in df_plants.columns or plant_name not in df_plants.columns:
        st.warning("[ERP Plants] Expected columns not found.")
        plant_map = {}
    else:
        plant_map = df_plants.set_index(plant_key)[plant_name]

    df_erp["Destination"] = df_erp[col_shipto].map(cust_map)

    # If Ship-To empty, use Plant
    mask_empty_shipto = df_erp[col_shipto].isna() | (df_erp[col_shipto] == "")
    df_erp.loc[mask_empty_shipto, "Destination"] = df_erp.loc[
        mask_empty_shipto, col_plnt
    ].map(plant_map)

    # Value / Currency
    df_erp["Value"] = pd.to_numeric(df_erp[col_value], errors="coerce")
    df_erp["Currency"] = df_erp[col_curr]

    df_erp["Source System"] = "SAP ERP"

    return df_erp[
        [
            "Source System",
            "Carrier",
            "Type of goods",
            "Date",
            "Origin",
            "Destination",
            "Value",
            "Currency",
        ]
    ].dropna(subset=["Date", "Carrier", "Origin", "Destination", "Value"])


def transform_sap_tm(df_tm: pd.DataFrame, df_fo: pd.DataFrame, df_fb: pd.DataFrame):
    df_tm = _clean_column_names(df_tm)
    df_fo = _clean_column_names(df_fo)
    df_fb = _clean_column_names(df_fb)

    # Expected columns
    col_fd = "Freight Document"
    col_invoicing = "Invoicing Party"
    col_value = "Net Amt in Doc Crcy"
    col_curr = "Currency"

    for c in [col_fd, col_invoicing, col_value, col_curr]:
        if c not in df_tm.columns:
            st.warning(f"[SAP TM] Expected column '{c}' not found.")

    # FO / FB expected columns
    col_doc_fo = "Freight Document"
    col_doc_fb = "Freight Document"
    col_act_deliv = "Actual Delivered Date"
    col_plan_arr = "Planned Arrival Date-Last Stop"
    col_exp_arr = "Expected Arrival Date"
    col_origin = "Source Location Description"
    col_dest = "Destination Location Descripti"

    for c in [col_doc_fo, col_act_deliv, col_plan_arr, col_origin, col_dest]:
        if c not in df_fo.columns:
            st.warning(f"[TM FO] Expected column '{c}' not found.")

    for c in [col_doc_fb, col_exp_arr, col_origin, col_dest]:
        if c not in df_fb.columns:
            st.warning(f"[TM FB] Expected column '{c}' not found.")

    df_tm["FD_str"] = df_tm[col_fd].astype(str)

    # 68... -> FO
    tm_68 = df_tm[df_tm["FD_str"].str.startswith("68")].copy()
    tm_69 = df_tm[df_tm["FD_str"].str.startswith("69")].copy()

    # Merge with FO
    df_fo_ren = df_fo.rename(columns={col_doc_fo: col_fd})
    merged_68 = tm_68.merge(df_fo_ren, on=col_fd, how="left", suffixes=("", "_FO"))

    # Date: Actual Delivered Date if not empty, else Planned Arrival Date-Last Stop
    merged_68["Date"] = _parse_date(merged_68[col_act_deliv])
    mask_empty_date = merged_68["Date"].isna()
    merged_68.loc[mask_empty_date, "Date"] = _parse_date(
        merged_68.loc[mask_empty_date, col_plan_arr]
    )

    merged_68["Origin"] = merged_68[col_origin]
    merged_68["Destination"] = merged_68[col_dest]

    # Merge with FB
    df_fb_ren = df_fb.rename(columns={col_doc_fb: col_fd})
    merged_69 = tm_69.merge(df_fb_ren, on=col_fd, how="left", suffixes=("", "_FB"))

    merged_69["Date"] = _parse_date(merged_69[col_exp_arr])
    merged_69["Origin"] = merged_69[col_origin]
    merged_69["Destination"] = merged_69[col_dest]

    df_all = pd.concat([merged_68, merged_69], ignore_index=True)

    df_all["Carrier"] = df_all[col_invoicing]
    df_all["Type of goods"] = "Unknown"  # not available in TM

    df_all["Value"] = pd.to_numeric(df_all[col_value], errors="coerce")
    df_all["Currency"] = df_all[col_curr]

    df_all["Source System"] = "SAP TM"

    return df_all[
        [
            "Source System",
            "Carrier",
            "Type of goods",
            "Date",
            "Origin",
            "Destination",
            "Value",
            "Currency",
        ]
    ].dropna(subset=["Date", "Carrier", "Origin", "Destination", "Value"])


# ------------- Dashboard ----------------------------------------------


def build_dashboard(df_all: pd.DataFrame):
    st.sidebar.header("Filters")

    min_date = df_all["Date"].min()
    max_date = df_all["Date"].max()

    date_range = st.sidebar.date_input(
        "Date range",
        value=(min_date.date() if pd.notna(min_date) else datetime.today().date(),
               max_date.date() if pd.notna(max_date) else datetime.today().date()),
    )

    if isinstance(date_range, tuple):
        start_date, end_date = date_range
    else:
        start_date, end_date = date_range, date_range

    mask_date = (df_all["Date"].dt.date >= start_date) & (
        df_all["Date"].dt.date <= end_date
    )

    carriers = sorted(df_all["Carrier"].dropna().unique())
    carrier_sel = st.sidebar.multiselect("Carrier", carriers, default=carriers)

    types = sorted(df_all["Type of goods"].dropna().unique())
    type_sel = st.sidebar.multiselect("Type of goods", types, default=types)

    origins = sorted(df_all["Origin"].dropna().unique())
    origin_sel = st.sidebar.multiselect("Origin", origins, default=origins)

    dests = sorted(df_all["Destination"].dropna().unique())
    dest_sel = st.sidebar.multiselect("Destination", dests, default=dests)

    systems = sorted(df_all["Source System"].dropna().unique())
    system_sel = st.sidebar.multiselect("Source system", systems, default=systems)

    df_f = df_all[
        mask_date
        & df_all["Carrier"].isin(carrier_sel)
        & df_all["Type of goods"].isin(type_sel)
        & df_all["Origin"].isin(origin_sel)
        & df_all["Destination"].isin(dest_sel)
        & df_all["Source System"].isin(system_sel)
    ].copy()

    st.markdown("## Freight cost overview")

    if df_f.empty:
        st.info("No data for the selected filters.")
        return

    # KPI
    total_cost = df_f["Value"].sum()
    st.metric("Total freight cost (all currencies)", f"{total_cost:,.2f}")

    # Cost over time
    df_time = (
        df_f.groupby(df_f["Date"].dt.date)["Value"].sum().reset_index(name="Total Cost")
    )
    fig_time = px.line(df_time, x="Date", y="Total Cost", title="Cost over time")
    st.plotly_chart(fig_time, use_container_width=True)

    # Cost by carrier
    df_carrier = (
        df_f.groupby("Carrier")["Value"].sum().reset_index(name="Total Cost")
    ).sort_values("Total Cost", ascending=False)
    fig_carrier = px.bar(
        df_carrier.head(20),
        x="Carrier",
        y="Total Cost",
        title="Top carriers by cost",
    )
    fig_carrier.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig_carrier, use_container_width=True)

    # Cost by lane (Origin–Destination)
    df_lane = (
        df_f.groupby(["Origin", "Destination"])["Value"]
        .sum()
        .reset_index(name="Total Cost")
        .sort_values("Total Cost", ascending=False)
    )
    df_lane["Lane"] = df_lane["Origin"] + " → " + df_lane["Destination"]
    fig_lane = px.bar(
        df_lane.head(20),
        x="Lane",
        y="Total Cost",
        title="Top lanes by cost",
    )
    fig_lane.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig_lane, use_container_width=True)

    # Raw data
    st.markdown("## Detailed records")
    st.dataframe(df_f.sort_values("Date", ascending=False))


# ------------- Streamlit UI -------------------------------------------


def main():
    st.set_page_config(page_title="Freight Cost Dashboard", layout="wide")
    st.title("Freight Cost Dashboard")

    st.markdown(
        """
This app consolidates freight cost information from **Manual Accruals**, **SAP ERP**, and **SAP TM**
into a single view so you can slice and dice by carrier, type of goods, date, origin, and destination.
"""
    )

    st.markdown("### 1. Upload mapping files")
    col1, col2, col3 = st.columns(3)

    with col1:
        file_carrier = st.file_uploader(
            "ERP Carrier Name (XLSX)", type=["xlsx"], key="carrier"
        )
        file_shippt = st.file_uploader(
            "ERP Shipping Point (XLSX)", type=["xlsx"], key="shippt"
        )
    with col2:
        file_plants = st.file_uploader(
            "ERP Plants (XLSX)", type=["xlsx"], key="plants"
        )
        file_customers = st.file_uploader(
            "ERP Customers (XLSX)", type=["xlsx"], key="customers"
        )
    with col3:
        st.write("Mapping files are required for SAP ERP transformation.")

    st.markdown("### 2. Upload source data files")
    col4, col5, col6 = st.columns(3)

    with col4:
        file_manual = st.file_uploader(
            "Manual accruals (XLSX)", type=["xlsx"], key="manual"
        )
        file_erp = st.file_uploader("SAP ERP (XLSX)", type=["xlsx"], key="erp")
    with col5:
        file_tm = st.file_uploader("SAP TM (XLSX)", type=["xlsx"], key="tm")
    with col6:
        file_tm_fo = st.file_uploader("TM FO (XLSX)", type=["xlsx"], key="tmfo")
        file_tm_fb = st.file_uploader("TM FB (XLSX)", type=["xlsx"], key="tmfb")

    if not any(
        [file_manual, file_erp, file_tm and file_tm_fo and file_tm_fb]
    ):
        st.info("Upload at least one data source to start.")
        return

    dfs = []

    # Manual accruals
    if file_manual is not None:
        df_manual_raw = pd.read_excel(file_manual)
        df_manual = transform_manual_accruals(df_manual_raw)
        dfs.append(df_manual)

    # SAP ERP
    if (
        file_erp is not None
        and file_carrier is not None
        and file_shippt is not None
        and file_plants is not None
        and file_customers is not None
    ):
        df_erp_raw = pd.read_excel(file_erp)
        df_carrier = pd.read_excel(file_carrier)
        df_shippt = pd.read_excel(file_shippt)
        df_plants = pd.read_excel(file_plants)
        df_customers = pd.read_excel(file_customers)

        df_erp = transform_sap_erp(
            df_erp_raw, df_carrier, df_shippt, df_plants, df_customers
        )
        dfs.append(df_erp)
    elif file_erp is not None:
        st.warning(
            "SAP ERP file uploaded but one or more mapping files are missing. "
            "SAP ERP data will not be included."
        )

    # SAP TM
    if file_tm is not None and file_tm_fo is not None and file_tm_fb is not None:
        df_tm_raw = pd.read_excel(file_tm)
        df_tm_fo = pd.read_excel(file_tm_fo)
        df_tm_fb = pd.read_excel(file_tm_fb)

        df_tm = transform_sap_tm(df_tm_raw, df_tm_fo, df_tm_fb)
        dfs.append(df_tm)
    elif file_tm is not None:
        st.warning(
            "SAP TM file uploaded but TM FO and/or TM FB are missing. "
            "SAP TM data will not be included."
        )

    if not dfs:
        st.error("No valid dataset could be built. Please check your uploads.")
        return

    df_all = pd.concat(dfs, ignore_index=True)
    df_all = df_all.dropna(subset=["Date"])

    build_dashboard(df_all)


if __name__ == "__main__":
    main()
