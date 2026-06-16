# Freight Cost Analytics App

This app consolidates freight cost information from three different sources:

- **Manual accruals**
- **SAP ERP**
- **SAP TM** (with TM FO and TM FB as reference)

It applies the business rules you described to harmonize the data into a single model and
provides an interactive dashboard to analyze **actual freight costs spent in a period**,
with rich filtering to slice and dice by carrier, type of goods, origin, destination, and currency.

---

## 1. Features

- **Multi‑source consolidation**
  - Manual accruals
  - SAP ERP (with lookups to ERP Carrier Name, ERP Plants, ERP Shipping Point, ERP Customers)
  - SAP TM (with TM FO and TM FB for date/origin/destination)

- **Unified data model**
  - `Date`
  - `Carrier`
  - `Type of goods`
  - `Origin`
  - `Destination`
  - `Value` (freight cost)
  - `Currency`
  - `Source System` (Manual accruals / SAP ERP / SAP TM)

- **Interactive dashboard**
  - Date range filter
  - Carrier filter
  - Type of goods filter
  - Origin / Destination filters
  - Currency filter (no FX conversion, just selection)
  - KPIs and charts:
    - Total freight cost
    - Costs by carrier
    - Costs by type of goods
    - Costs over time
    - Top origin–destination lanes
    - Raw data table

---

## 2. Installation

### 2.1. Prerequisites

- Python 3.10+ recommended
- `pip` installed

### 2.2. Setup

```bash
# Create and activate a virtual environment (optional but recommended)
python -m venv .venv
source .venv/bin/activate  # on Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
