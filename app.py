import streamlit as st
import pandas as pd
import numpy as np

# -----------------------------
# Helpers
# -----------------------------

def safe_parse_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce")


def clean_carrier_manual(carrier: pd.Series) -> pd.Series:
    # Remove " as of ..." and everything after
    return carrier.astype(str).str.split(" as of", n=1).str[0].str.strip()


def load_excel(file, sheet_name=None):
    if file is None:
        return None
    return pd.read_excel(file, sheet_name=sheet_name)


# -----------------------------
# Transformations
# -----------------------------

def transform_manual_accruals(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    # Mapping
    out["Carrier"] = clean_carrier_manual(out["Carrier Description"])
    out["Type of goods"] = out["PBU"]
    out["Date"] = safe_parse_date(out["Planned Arrival Date-Last Stop"])
    out["Origin"] = out["Source Location Description"]
    out["Destination"] = out["Destination Location Descripti"]
    out["Value"] = pd.to_numeric(out["Net Amt in Doc Crcy"], errors="coerce")
    out["Currency"] = out["Currency"]
    out["Source System"] = "Manual accruals"

    return out[[
        "Date", "Carrier", "Type of goods", "Origin",
        "Destination", "Value", "Currency", "Source System"
    ]]


def map_product_hierarchy_to_type(h: pd.Series) -> pd.Series:
    h = h.astype(str).str.strip()
    # Starts with 1 or 4 => FG, else NFG
    return np.where(h.str.startswith(("1", "4")), "FG", "NFG")


def transform_sap_erp(
    erp_df: pd.DataFrame,
    carrier_name_df: pd.DataFrame,
    shipping_point_df: pd.DataFrame,
    customers_df: pd.DataFrame,
    plants_df: pd.DataFrame,
) -> pd.DataFrame:
    df = erp_df.copy()

    # Carrier: ServcAgent -> ERP Carrier Name.Name 1
    carrier_map = carrier_name_df.set_index("ServcAgent")["Name 1"]
    df["Carrier"] = df["ServcAgent"].map(carrier_map)

    # Type of goods: Product Hierarchy
    df["Type of goods"] = map_product_hierarchy_to_type(df["Product Hierarchy"])

    # Date
    df["Date"] = safe_parse_date(df["Deliv.Date"])

    # Origin: ShPt -> ERP Shipping Point.Description, if empty => "Import"
    shp_map = shipping_point_df.set_index("ShPt")["Description"]
    df["Origin"] = df["ShPt"].map(shp_map)
    df.loc[df["ShPt"].isna() | (df["ShPt"] == ""), "Origin"] = "Import"

    # Destination:
    # If Ship-To not empty: Ship-To -> ERP Customers.Name 1
    # Else: Plnt -> ERP Plants.Name 1
    cust_map = customers_df.set_index("Ship-To")["Name 1"]
    plant_map = plants_df.set_index("Plnt")["Name 1"]

    df["Destination"] = df["Ship-To"].map(cust_map)
    mask_empty_shipto = df["Ship-To"].isna() | (df["Ship-To"] == "")
    df.loc[mask_empty_shipto, "Destination"] = df.loc[mask_empty_shipto, "Plnt"].map(plant_map)

    # Value & Currency
    df["Value"] = pd.to_numeric(df["Loc.curr.amount"], errors="coerce")
    df["Currency"] = df["Local Curr."]

    df["Source System"] = "SAP ERP"

    return df[[
        "Date", "Carrier", "Type of goods", "Origin",
        "Destination", "Value", "Currency", "Source System"
    ]]


def transform_sap_tm(tm_df: pd.DataFrame, fo_df: pd.DataFrame, fb_df: pd.DataFrame) -> pd.DataFrame:
    """
    Rules:
    - Use Freight Document in SAP TM as reference.
    - Freight Document starting with '69' => look up in TM FB.
    - Freight Document starting with '68' => look up in TM FO.
    - Carrier comes from FO/FB 'Carrier' column (NOT from TM 'Invoicing Party').
    - FB:
        Date = Expected Arrival Date
        Origin = Source Location Description
        Destination = Destination Location Descripti
    - FO:
        Date = Actual Delivered Date
        If empty => Planned Arrival Date-Last Stop
        Origin = Source Location Description
        Destination = Destination Location Descripti
    """

    tm = tm_df.copy()
    tm["Freight Document"] = tm["Freight Document"].astype(str)

    # ----------------- FO reference -----------------
    fo = fo_df.copy()
    if "Document" in fo.columns:
        fo["Document"] = fo["Document"].astype(str)
    else:
        fo["Document"] = fo["Freight Document"].astype(str) if "Freight Document" in fo.columns else ""

    # Date logic for FO
    fo["Date"] = pd.NaT
    if "Actual Delivered Date" in fo.columns:
        fo["Date"] = safe_parse_date(fo["Actual Delivered Date"])

    if "Planned Arrival Date-Last Stop" in fo.columns:
        planned = safe_parse_date(fo["Planned Arrival Date-Last Stop"])
        fo["Date"] = fo["Date"].fillna(planned)

    fo["Origin"] = fo.get("Source Location Description")
    fo["Destination"] = fo.get("Destination Location Descripti")

    # Carrier from FO file
    if "Carrier" in fo.columns:
        fo["Carrier_ref"] = fo["Carrier"]
    else:
        fo["Carrier_ref"] = np.nan

    fo_ref_cols = ["Document", "Date", "Origin", "Destination", "Carrier_ref"]
    fo_ref = fo[fo_ref_cols].drop_duplicates(subset=["Document"])

    # ----------------- FB reference -----------------
    fb = fb_df.copy()
    if "Document" in fb.columns:
        fb["Document"] = fb["Document"].astype(str)
    else:
        fb["Document"] = fb["Freight Document"].astype(str) if "Freight Document" in fb.columns else ""

    fb["Date"] = pd.NaT
    if "Expected Arrival Date" in fb.columns:
        fb["Date"] = safe_parse_date(fb["Expected Arrival Date"])

    fb["Origin"] = fb.get("Source Location Description")
    fb["Destination"] = fb.get("Destination Location Descripti")

    # Carrier from FB file
    if "Carrier" in fb.columns:
        fb["Carrier_ref"] = fb["Carrier"]
    else:
        fb["Carrier_ref"] = np.nan

    fb_ref_cols = ["Document", "Date", "Origin", "Destination", "Carrier_ref"]
    fb_ref = fb[fb_ref_cols].drop_duplicates(subset=["Document"])

    # ----------------- Merge logic by prefix -----------------
    # Freight Document starting with 69 -> FB
    # Freight Document starting with 68 -> FO
    tm["FD_prefix"] = tm["Freight Document"].str[:2]

    tm_fb = tm[tm["FD_prefix"] == "69"].merge(
        fb_ref,
        left_on="Freight Document",
        right_on="Document",
        how="left",
        suffixes=("", "_fb"),
    )

    tm_fo = tm[tm["FD_prefix"] == "68"].merge(
        fo_ref,
        left_on="Freight Document",
        right_on="Document",
        how="left",
        suffixes=("", "_fo"),
    )

    # Combine back
    tm_merged = pd.concat([tm_fb, tm_fo], ignore_index=True)

    # Final fields
    tm_merged["Date"] = tm_merged["Date"]
    tm_merged["Origin"] = tm_merged["Origin"]
    tm_merged["Destination"] = tm_merged["Destination"]

    # Carrier must come from FO/FB Carrier_ref
    tm_merged["Carrier"] = tm_merged["Carrier_ref"]

    tm_merged["Value"] = pd.to_numeric(tm_merged["Net Amt in Doc Crcy"], errors="coerce")
    tm_merged["Currency"] = tm_merged["Currency"]
    tm_merged["Type of goods"] = "Unknown"
    tm_merged["Source System"] = "SAP TM"

    return tm_merged[[
        "Date", "Carrier", "Type of goods", "Origin",
        "Destination", "Value", "Currency", "Source System"
    ]]


# -----------------------------
# Streamlit UI
# -----------------------------

st.set_page_config(page_title="Freight Cost Dashboard", layout="wide")

st.title("📦 Freight Cost Dashboard")

st.markdown(
    "Upload the three cost sources and reference master data to see consolidated freight costs, "
    "filter by period, and slice & dice by carrier, type of goods, origin, and destination."
)

with st.sidebar:
    st.header("📁 Upload files")

    st.subheader("Manual accruals")
    file_manual = st.file_uploader("Manual accruals file", type=["xlsx", "xls"], key="manual")

    st.subheader("SAP ERP")
    file_erp = st.file_uploader("SAP ERP file", type=["xlsx", "xls"], key="erp")
    file_erp_carrier = st.file_uploader("ERP Carrier Name file", type=["xlsx", "xls"], key="erp_carrier")
    file_erp_shpt = st.file_uploader("ERP Shipping Point file", type=["xlsx", "xls"], key="erp_shpt")
    file_erp_customers = st.file_uploader("ERP Customers file", type=["xlsx", "xls"], key="erp_customers")
    file_erp_plants = st.file_uploader("ERP Plants file", type=["xlsx", "xls"], key="erp_plants")

    st.subheader("SAP TM")
    file_tm = st.file_uploader("SAP TM file", type=["xlsx", "xls"], key="tm")
    file_tm_fo = st.file_uploader("TM FO file", type=["xlsx", "xls"], key="tm_fo")
    file_tm_fb = st.file_uploader("TM FB file", type=["xlsx", "xls"], key="tm_fb")

    st.markdown("---")
    st.subheader("Date filter")
    date_from = st.date_input("From", value=None)
    date_to = st.date_input("To", value=None)


def main():
    # Load all dataframes
    df_manual = load_excel(file_manual)
    df_erp = load_excel(file_erp)
    df_erp_carrier = load_excel(file_erp_carrier)
    df_erp_shpt = load_excel(file_erp_shpt)
    df_erp_customers = load_excel(file_erp_customers)
    df_erp_plants = load_excel(file_erp_plants)

    df_tm = load_excel(file_tm)
    df_fo = load_excel(file_tm_fo)
    df_fb = load_excel(file_tm_fb)

    transformed_frames = []

    # Manual accruals
    if df_manual is not None:
        try:
            df_manual_t = transform_manual_accruals(df_manual)
            transformed_frames.append(df_manual_t)
        except Exception as e:
            st.error(f"Error transforming Manual accruals: {e}")

    # SAP ERP
    if all(x is not None for x in [df_erp, df_erp_carrier, df_erp_shpt, df_erp_customers, df_erp_plants]):
        try:
            df_erp_t = transform_sap_erp(
                df_erp,
                df_erp_carrier,
                df_erp_shpt,
                df_erp_customers,
                df_erp_plants,
            )
            transformed_frames.append(df_erp_t)
        except Exception as e:
            st.error(f"Error transforming SAP ERP: {e}")
    elif df_erp is not None:
        st.warning("SAP ERP file uploaded but one or more reference master files are missing.")

    # SAP TM
    if all(x is not None for x in [df_tm, df_fo, df_fb]):
        try:
            df_tm_t = transform_sap_tm(df_tm, df_fo, df_fb)
            transformed_frames.append(df_tm_t)
        except Exception as e:
            st.error(f"Error transforming SAP TM: {e}")
    elif df_tm is not None:
        st.warning("SAP TM file uploaded but TM FO and/or TM FB files are missing.")

    if not transformed_frames:
        st.info("Upload the required files in the sidebar to see the dashboard.")
        return

    df_all = pd.concat(transformed_frames, ignore_index=True)

    # Apply date filter
    if "Date" in df_all.columns:
        df_all["Date"] = pd.to_datetime(df_all["Date"], errors="coerce")
        if date_from is not None:
            df_all = df_all[df_all["Date"] >= pd.to_datetime(date_from)]
        if date_to is not None:
            df_all = df_all[df_all["Date"] <= pd.to_datetime(date_to)]

    st.subheader("Consolidated freight costs")

    st.dataframe(df_all)

    # KPIs
    total_cost = df_all["Value"].sum(skipna=True)
    total_shipments = len(df_all)
    unique_carriers = df_all["Carrier"].nunique(dropna=True)

    col1, col2, col3 = st.columns(3)
    col1.metric("Total cost", f"{total_cost:,.2f}")
    col2.metric("Number of shipments", f"{total_shipments}")
    col3.metric("Number of carriers", f"{unique_carriers}")

    # Slice & dice
    st.markdown("### Slice & dice")

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        carrier_filter = st.multiselect(
            "Carrier",
            options=sorted(df_all["Carrier"].dropna().unique()),
            default=None,
        )
    with col_f2:
        type_filter = st.multiselect(
            "Type of goods",
            options=sorted(df_all["Type of goods"].dropna().unique()),
            default=None,
        )
    with col_f3:
        origin_filter = st.multiselect(
            "Origin",
            options=sorted(df_all["Origin"].dropna().unique()),
            default=None,
        )

    dest_filter = st.multiselect(
        "Destination",
        options=sorted(df_all["Destination"].dropna().unique()),
        default=None,
    )

    df_filtered = df_all.copy()
    if carrier_filter:
        df_filtered = df_filtered[df_filtered["Carrier"].isin(carrier_filter)]
    if type_filter:
        df_filtered = df_filtered[df_filtered["Type of goods"].isin(type_filter)]
    if origin_filter:
        df_filtered = df_filtered[df_filtered["Origin"].isin(origin_filter)]
    if dest_filter:
        df_filtered = df_filtered[df_filtered["Destination"].isin(dest_filter)]

    st.subheader("Filtered data")
    st.dataframe(df_filtered)

    # Charts
    st.markdown("### Cost by carrier")
    if not df_filtered.empty:
        cost_by_carrier = df_filtered.groupby("Carrier", dropna=False)["Value"].sum().reset_index()
        cost_by_carrier = cost_by_carrier.sort_values("Value", ascending=False)
        st.bar_chart(cost_by_carrier.set_index("Carrier"))

        st.markdown("### Cost by type of goods")
        cost_by_type = df_filtered.groupby("Type of goods", dropna=False)["Value"].sum().reset_index()
        cost_by_type = cost_by_type.sort_values("Value", ascending=False)
        st.bar_chart(cost_by_type.set_index("Type of goods"))

        st.markdown("### Cost over time")
        cost_over_time = df_filtered.copy()
        cost_over_time = cost_over_time.dropna(subset=["Date"])
        if not cost_over_time.empty:
            cost_over_time = cost_over_time.groupby("Date")["Value"].sum().reset_index()
            cost_over_time = cost_over_time.sort_values("Date")
            st.line_chart(cost_over_time.set_index("Date"))
        else:
            st.info("No valid dates available to plot cost over time.")
    else:
        st.info("No data after applying filters.")


if __name__ == "__main__":
    main()
