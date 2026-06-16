import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

# -----------------------------
# Helpers
# -----------------------------

@st.cache_data
def load_excel(file, sheet_name=0):
    return pd.read_excel(file, sheet_name=sheet_name)

def clean_carrier_manual_accruals(series: pd.Series) -> pd.Series:
    # "Carrier Description = Carrier. Please remove text as of / and what is after"
    return series.astype(str).str.split("/").str[0].str.strip()

def map_type_of_goods_from_product_hierarchy(series: pd.Series) -> pd.Series:
    # "Whatever starts with 1 or 4 = FG, the rest = NFG."
    s = series.astype(str).str.strip()
    return np.where(s.str.startswith(("1", "4")), "FG", "NFG")

def safe_parse_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce")

# -----------------------------
# Load & transform sources
# -----------------------------

def transform_manual_accruals(df: pd.DataFrame) -> pd.DataFrame:
    # Column mapping from user:
    # Carrier Description = Carrier (cleaned)
    # PBU = Type of goods
    # Planned Arrival Date-Last Stop = Date
    # Source Location Description = Origin
    # Destination Location Descripti = Destination
    # Net Amt in Doc Crcy = Value (Costs)
    # Currency = Currency
    df = df.copy()

    df["Carrier"] = clean_carrier_manual_accruals(df["Carrier Description"])
    df["Type of goods"] = df["PBU"]
    df["Date"] = safe_parse_date(df["Planned Arrival Date-Last Stop"])
    df["Origin"] = df["Source Location Description"]
    df["Destination"] = df["Destination Location Descripti"]
    df["Value"] = pd.to_numeric(df["Net Amt in Doc Crcy"], errors="coerce")
    df["Currency"] = df["Currency"]

    df["Source System"] = "Manual accruals"

    return df[[
        "Date", "Carrier", "Type of goods", "Origin",
        "Destination", "Value", "Currency", "Source System"
    ]]

def build_carrier_lookup(erp_carrier_df: pd.DataFrame) -> dict:
    # ERP Carrier Name: Supplier / Name 1
    # We assume SAP ERP ServcAgent matches "Supplier" code
    return dict(zip(erp_carrier_df["Supplier"].astype(str), erp_carrier_df["Name 1"].astype(str)))

def build_shipping_point_lookup(shp_df: pd.DataFrame) -> dict:
    # ERP Shipping Point: ShPt / Description
    return dict(zip(shp_df["ShPt"].astype(str), shp_df["Description"].astype(str)))

def build_plants_lookup(plants_df: pd.DataFrame) -> dict:
    # ERP Plants: Plnt / Name 1
    return dict(zip(plants_df["Plnt"].astype(str), plants_df["Name 1"].astype(str)))

def build_customers_lookup(customers_df: pd.DataFrame) -> dict:
    # ERP Customers: Ship-To / Name 1
    # (file content not visible here, but we follow user’s rule)
    return dict(zip(customers_df.iloc[:, 0].astype(str), customers_df.iloc[:, 1].astype(str)))

def transform_sap_erp(
    df: pd.DataFrame,
    carrier_lookup: dict,
    shipping_point_lookup: dict,
    plants_lookup: dict,
    customers_lookup: dict | None = None,
) -> pd.DataFrame:
    # Column mapping from user:
    # ServcAgent = Carrier (map via ERP Carrier Name)
    # Product Hierarchy = Type of goods (1/4 => FG, else NFG)
    # Deliv.Date = Date
    # ShPt = Origin (map via ERP Shipping Point; if empty => "Import")
    # Ship-To = Destination (map via ERP Customers; if empty => Plnt mapped via ERP Plants)
    # Loc.curr.amount = Value (Costs)
    # Local Curr. = Currency
    df = df.copy()

    # Carrier
    df["ServcAgent_str"] = df["ServcAgent"].astype(str)
    df["Carrier"] = df["ServcAgent_str"].map(carrier_lookup).fillna(df["ServcAgent_str"])

    # Type of goods
    df["Type of goods"] = map_type_of_goods_from_product_hierarchy(df["Product Hierarchy"])

    # Date
    df["Date"] = safe_parse_date(df["Deliv.Date"])

    # Origin
    shpt_str = df["ShPt"].astype(str)
    df["Origin"] = np.where(
        df["ShPt"].isna() | (shpt_str == "") | (shpt_str == "nan"),
        "Import",
        shpt_str.map(shipping_point_lookup).fillna(shpt_str),
    )

    # Destination
    ship_to_str = df["Ship-To"].astype(str)
    plnt_str = df["Plnt"].astype(str)

    dest_from_ship_to = None
    if customers_lookup is not None:
        dest_from_ship_to = ship_to_str.map(customers_lookup)

    dest_from_plnt = plnt_str.map(plants_lookup).fillna(plnt_str)

    df["Destination"] = np.where(
        df["Ship-To"].notna() & (ship_to_str != "") & (ship_to_str != "nan") & (dest_from_ship_to.notna() if dest_from_ship_to is not None else False),
        dest_from_ship_to,
        dest_from_plnt,
    )

    # Value & Currency
    df["Value"] = pd.to_numeric(df["Loc.curr.amount"], errors="coerce")
    df["Currency"] = df["Local Curr."]

    df["Source System"] = "SAP ERP"

    return df[[
        "Date", "Carrier", "Type of goods", "Origin",
        "Destination", "Value", "Currency", "Source System"
    ]]

def transform_sap_tm(
    tm_df: pd.DataFrame,
    fo_df: pd.DataFrame,
    fb_df: pd.DataFrame,
) -> pd.DataFrame:
    # SAP TM file:
    # Invoicing Party = Carrier
    # Net Amt in Doc Crcy = Value (Costs)
    # Currency = Currency
    # Freight Document as reference to get:
    #   Actual Delivered Date = Date (if empty, Planned Arrival Date-Last Stop)
    #   Source Location Description = Origin
    #   Destination Location Descripti = Destination
    #
    # We assume:
    #   tm_df has column "Freight Document"
    #   fo_df/fb_df have column "Document" (as in TM FB sample)
    #   and the date/origin/destination columns as named by user.
    tm = tm_df.copy()
    tm["Carrier"] = tm["Invoicing Party"]
    tm["Value"] = pd.to_numeric(tm["Net Amt in Doc Crcy"], errors="coerce")
    tm["Currency"] = tm["Currency"]

    # Build FO/FB reference
    fo = fo_df.copy()
    fb = fb_df.copy()

    for ref_df in (fo, fb):
        if "Document" not in ref_df.columns:
            continue
        # Date
        if "Actual Delivered Date" in ref_df.columns:
            ref_df["Date"] = safe_parse_date(ref_df["Actual Delivered Date"])
        else:
            ref_df["Date"] = pd.NaT

        if "Planned Arrival Date-Last Stop" in ref_df.columns:
            planned = safe_parse_date(ref_df["Planned Arrival Date-Last Stop"])
            ref_df["Date"] = ref_df["Date"].fillna(planned)

        # Origin / Destination
        ref_df["Origin"] = ref_df.get("Source Location Description")
        ref_df["Destination"] = ref_df.get("Destination Location Descripti")

    # Concatenate FO & FB reference data
    ref_cols = ["Document", "Date", "Origin", "Destination"]
    ref_all = pd.concat(
        [df[ref_cols] for df in (fo, fb) if all(c in df.columns for c in ref_cols)],
        ignore_index=True,
    ).drop_duplicates(subset=["Document"])

    # Join TM with FO/FB
    tm["Freight Document"] = tm["Freight Document"].astype(str)
    ref_all["Document"] = ref_all["Document"].astype(str)

    tm = tm.merge(
        ref_all,
        left_on="Freight Document",
        right_on="Document",
        how="left",
        suffixes=("", "_ref"),
    )

    tm["Date"] = tm["Date"]
    tm["Origin"] = tm["Origin"]
    tm["Destination"] = tm["Destination"]

    tm["Type of goods"] = "Unknown"  # not provided for TM

    tm["Source System"] = "SAP TM"

    return tm[[
        "Date", "Carrier", "Type of goods", "Origin",
        "Destination", "Value", "Currency", "Source System"
    ]]

# -----------------------------
# Dashboard
# -----------------------------

def build_dashboard(df: pd.DataFrame):
    st.sidebar.header("Filters")

    min_date = df["Date"].min()
    max_date = df["Date"].max()

    date_range = st.sidebar.date_input(
        "Date range",
        value=(min_date.date() if pd.notna(min_date) else datetime.today().date(),
               max_date.date() if pd.notna(max_date) else datetime.today().date()),
    )

    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
        mask = (df["Date"].dt.date >= start_date) & (df["Date"].dt.date <= end_date)
        df = df[mask]

    carriers = sorted(df["Carrier"].dropna().unique().tolist())
    selected_carriers = st.sidebar.multiselect("Carrier", carriers, default=carriers)

    if selected_carriers:
        df = df[df["Carrier"].isin(selected_carriers)]

    types = sorted(df["Type of goods"].dropna().unique().tolist())
    selected_types = st.sidebar.multiselect("Type of goods", types, default=types)
    if selected_types:
        df = df[df["Type of goods"].isin(selected_types)]

    origins = sorted(df["Origin"].dropna().unique().tolist())
    selected_origins = st.sidebar.multiselect("Origin", origins)
    if selected_origins:
        df = df[df["Origin"].isin(selected_origins)]

    destinations = sorted(df["Destination"].dropna().unique().tolist())
    selected_destinations = st.sidebar.multiselect("Destination", destinations)
    if selected_destinations:
        df = df[df["Destination"].isin(selected_destinations)]

    currencies = sorted(df["Currency"].dropna().unique().tolist())
    selected_currency = st.sidebar.selectbox("Currency (no conversion)", ["All"] + currencies)
    if selected_currency != "All":
        df = df[df["Currency"] == selected_currency]

    st.subheader("Key figures")

    total_cost = df["Value"].sum()
    st.metric("Total freight cost", f"{total_cost:,.2f} {selected_currency if selected_currency != 'All' else ''}")

    st.write("### Costs by carrier")
    cost_by_carrier = (
        df.groupby("Carrier", as_index=False)["Value"]
        .sum()
        .sort_values("Value", ascending=False)
    )
    st.bar_chart(cost_by_carrier.set_index("Carrier"))

    st.write("### Costs by type of goods")
    cost_by_type = df.groupby("Type of goods", as_index=False)["Value"].sum()
    st.bar_chart(cost_by_type.set_index("Type of goods"))

    st.write("### Costs over time")
    cost_over_time = (
        df.groupby("Date", as_index=False)["Value"]
        .sum()
        .sort_values("Date")
    )
    st.line_chart(cost_over_time.set_index("Date"))

    st.write("### Top origin–destination lanes")
    lanes = (
        df.assign(Lane=df["Origin"].astype(str) + " → " + df["Destination"].astype(str))
        .groupby("Lane", as_index=False)["Value"]
        .sum()
        .sort_values("Value", ascending=False)
        .head(20)
    )
    st.bar_chart(lanes.set_index("Lane"))

    st.write("### Raw data")
    st.dataframe(df.sort_values("Date", ascending=False))


# -----------------------------
# Streamlit app
# -----------------------------

def main():
    st.title("Freight Cost Analytics")

    st.markdown(
        """
This app consolidates freight cost data from **Manual accruals**, **SAP ERP**, and **SAP TM**
into a single model and provides an interactive dashboard with filters to slice and dice
by date, carrier, type of goods, origin, destination, and currency.
        """
    )

    st.sidebar.header("Upload data files")

    manual_file = st.sidebar.file_uploader("Manual accruals (Excel)", type=["xlsx", "xls"])
    sap_erp_file = st.sidebar.file_uploader("SAP ERP (Excel)", type=["xlsx", "xls"])
    sap_tm_file = st.sidebar.file_uploader("SAP TM (Excel)", type=["xlsx", "xls"])

    erp_carrier_file = st.sidebar.file_uploader("ERP Carrier Name (Excel)", type=["xlsx", "xls"])
    erp_plants_file = st.sidebar.file_uploader("ERP Plants (Excel)", type=["xlsx", "xls"])
    erp_shipping_point_file = st.sidebar.file_uploader("ERP Shipping Point (Excel)", type=["xlsx", "xls"])
    erp_customers_file = st.sidebar.file_uploader("ERP Customers (Excel)", type=["xlsx", "xls"])

    tm_fo_file = st.sidebar.file_uploader("TM FO (Excel)", type=["xlsx", "xls"])
    tm_fb_file = st.sidebar.file_uploader("TM FB (Excel)", type=["xlsx", "xls"])

    data_frames = []

    # Manual accruals
    if manual_file is not None:
        df_manual = load_excel(manual_file)
        df_manual_t = transform_manual_accruals(df_manual)
        data_frames.append(df_manual_t)

    # SAP ERP
    if sap_erp_file is not None and erp_carrier_file is not None and erp_plants_file is not None and erp_shipping_point_file is not None:
        df_erp = load_excel(sap_erp_file)
        df_carrier = load_excel(erp_carrier_file)
        df_plants = load_excel(erp_plants_file)
        df_shp = load_excel(erp_shipping_point_file)

        carrier_lookup = build_carrier_lookup(df_carrier)
        plants_lookup = build_plants_lookup(df_plants)
        shipping_point_lookup = build_shipping_point_lookup(df_shp)

        customers_lookup = None
        if erp_customers_file is not None:
            df_customers = load_excel(erp_customers_file)
            customers_lookup = build_customers_lookup(df_customers)

        df_erp_t = transform_sap_erp(
            df_erp,
            carrier_lookup=carrier_lookup,
            shipping_point_lookup=shipping_point_lookup,
            plants_lookup=plants_lookup,
            customers_lookup=customers_lookup,
        )
        data_frames.append(df_erp_t)

    # SAP TM
    if sap_tm_file is not None and tm_fo_file is not None and tm_fb_file is not None:
        df_tm = load_excel(sap_tm_file)
        df_fo = load_excel(tm_fo_file)
        df_fb = load_excel(tm_fb_file)

        df_tm_t = transform_sap_tm(df_tm, df_fo, df_fb)
        data_frames.append(df_tm_t)

    if not data_frames:
        st.info("Upload at least one data source to see the dashboard.")
        return

    unified = pd.concat(data_frames, ignore_index=True)

    # Ensure Date is datetime
    unified["Date"] = safe_parse_date(unified["Date"])

    build_dashboard(unified)


if __name__ == "__main__":
    main()
