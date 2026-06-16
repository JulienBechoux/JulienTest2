Overview
Freight Costs Dashboard is a lightweight interactive web application that simulates and visualizes freight spend across three data sources: Manual accruals, SAP ERP, and SAP TM. The app provides year-over-year comparisons, monthly time series, breakdowns by source, mode share, and a detailed transaction table with filtering and download capability.

The app ships with simulated data for the last 24 months so you can explore the dashboard immediately. You can also upload up to three real files (CSV or Excel) to replace the simulated data. The app will attempt to normalize common column names.

Features
Simulated dataset covering the last 24 months for three sources.

Filters for year, source, transport mode, region, and carrier.

KPIs: total spend, average monthly spend, top carrier.

Time series: monthly spend with year comparison.

Breakdowns: spend by source and mode share pie chart.

Detailed table with download button for filtered data.

Upload support: accept CSV/XLSX files and attempt to map common column names to the expected schema.

Automated insights panel that highlights YoY change, top region, and top mode.

Expected data schema (for uploads)
When uploading your own files, the app expects the following columns (case-insensitive, common variants are mapped automatically):

date — date of the transaction (e.g., 2026-03-01, 03/01/2026, shipment_date)

source — which file/system the record comes from (e.g., SAP ERP, Manual accruals)

mode — transport mode (e.g., Air, Ocean, Road, Rail)

carrier — carrier or vendor name

region — region or zone (e.g., EMEA, AMER, APAC)

amount — numeric freight cost amount

If your file uses different column names, the app will try to map common synonyms. If mapping fails, the app will notify you in the sidebar.
