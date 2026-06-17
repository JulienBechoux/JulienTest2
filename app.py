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

def clean_carrier_manual(series):
    return series.astype(str).str.split("/").str[0].str.strip()

def map_type_of_goods(ph):
    ph = ph.astype(str).str.strip()
    return np.where(ph.str.startswith(("1", "4")), "FG", "NFG")

def safe_date(series):
    return pd.to_datetime(series, errors="coerce")

# -----------------------------
# Manual Accruals
# -----------------------------

def transform_manual(df):
    df = df.copy()

    df["Carrier"] = clean_carrier_manual(df["Carrier Description"])
    df["Type of goods"] = df["PBU"]
    df["Date"] = safe_date(df["Planned Arrival Date-Last Stop"])
    df["Origin"] = df["Source Location Description"]
    df["Destination"] = df["Destination Location Descripti"]
    df["Value"] = pd.to_numeric(df["Net Amt in Doc Crcy"], errors="coerce")
    df["Currency"] = df["Currency"]
    df["Source System"] = "Manual accruals"

    return df[[
        "Date", "Carrier", "Type of goods", "Origin",
        "Destination", "Value", "Currency", "Source System"
    ]]

# -----------------------------
# ERP Lookups
# -----------------------------

def lookup_carrier(df):
    return dict(zip(df["Supplier"].astype(str), df["Name 1"].astype(str)))

def lookup_plants(df):
    return dict(zip(df["Plnt"].astype(str), df["Name 1"].astype(str)))

def lookup_shipping(df):
    return dict(zip(df["ShPt"].astype(str), df["Description"].astype(str)))

def lookup_customers(df):
    return dict(zip(df.iloc[:, 0].astype(str), df.iloc[:, 1].astype(str)))

# -----------------------------
# SAP ERP
# -----------------------------

def transform_erp(df, carrier_lu, ship_lu, plant_lu, cust_lu=None):
    df = df.copy()

    df["ServcAgent_str"] = df["ServcAgent"].astype(str)
    df["Carrier"] = df["ServcAgent_str"].map(carrier_lu).fillna(df["ServcAgent_str"])

    df["Type of goods"] = map_type_of_goods(df["Product Hierarchy"])
    df["Date"] = safe_date(df["Deliv.Date"])

    shpt = df["ShPt"].astype(str)
    df["Origin"] = np.where(
        df["ShPt"].isna() | (shpt == "") | (shpt == "nan"),
        "Import",
        shpt.map(ship_lu).fillna(shpt)
    )

    ship_to = df["Ship-To"].astype(str)
    plnt = df["Plnt"].astype(str)

    dest_from_ship = ship_to.map(cust_lu) if cust_lu else None
    dest_from_plnt = plnt.map(plant_lu).fillna(plnt)

    df["Destination"] = np.where(
        df["Ship-To"].notna() & (ship_to != "") & (ship_to != "nan") &
        (dest_from_ship.notna() if cust_lu else False),
        dest_from_ship,
        dest_from_plnt
    )

    df["Value"] = pd.to_numeric(df["Loc.curr.amount"], errors="coerce")
    df["Currency"] = df["Local Curr."]
    df["Source System"] = "SAP ERP"

    return df[[
        "Date", "Carrier", "Type of goods", "Origin",
        "Destination", "Value", "Currency", "Source System"
    ]]

# -----------------------------
# SAP TM (Corrected Logic)
# -----------------------------

def transform_tm(tm_df, fo_df, fb_df):
    tm = tm_df.copy()

    tm["Carrier"] = tm["Invoicing Party"]
    tm["Value"] = pd.to_numeric(tm["Net Amt in Doc Crcy"], errors="coerce")
    tm["Currency"] = tm["Currency"]
    tm["Freight Document"] = tm["Freight Document"].astype(str)

    # --- FO ---
    fo = fo_df.copy()
    fo["Document"] = fo["Document"].astype(str)
    fo["Date"] = pd.NaT

    if "Actual Delivered Date" in fo.columns:
        fo["Date"] = safe_date(fo["Actual Delivered Date"])

    if "Planned Arrival Date-Last Stop" in fo.columns:
        planned = safe_date(fo["Planned Arrival Date-Last Stop"])
        fo["Date"] = fo["Date"].fillna(planned)

    fo["Origin"] = fo.get("Source Location Description")
    fo["Destination"] = fo.get("Destination Location Descripti")

    # --- FB ---
    fb = fb_df.copy()
    fb["Document"] = fb["Document"].astype(str)
    fb["Date"] = pd.NaT

    if "Expected Arrival Date" in fb.columns:
        fb["Date"] = safe_date(fb["Expected Arrival Date"])

    fb["Origin"] = fb.get("Source Location Description")
    fb["Destination"]
