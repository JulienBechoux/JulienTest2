# Freight Cost Dashboard

This application consolidates freight cost information from three different sources:

- **Manual accruals**
- **SAP ERP**
- **SAP TM (with TM FO and TM FB)**

It produces a unified dataset with:

- **Carrier**
- **Type of goods**
- **Date**
- **Origin**
- **Destination**
- **Value**
- **Currency**
- **Source System**

and provides an interactive dashboard to slice and dice freight spend.

---

## 1. Features

- **Data consolidation**
  - Merges cost data from Manual Accruals, SAP ERP, and SAP TM.
  - Uses mapping tables (carriers, shipping points, plants, customers) to enrich ERP data.
  - Uses TM FO / TM FB to enrich SAP TM data with dates, origins, and destinations.

- **Standardized output**
  - Common schema across all sources:
    - `Source System`
    - `Carrier`
    - `Type of goods`
    - `Date`
    - `Origin`
    - `Destination`
    - `Value`
    - `Currency`

- **Interactive dashboard**
  - Filter by:
    - Date range
    - Carrier
    - Type of goods
    - Origin
    - Destination
    - Source system
  - Visuals:
    - Total freight cost KPI
    - Cost over time
    - Top carriers by cost
    - Top lanes (Origin → Destination) by cost
    - Detailed table of all filtered records

---

## 2. Installation

### 2.1. Prerequisites

- Python 3.9+ recommended
- Ability to install Python packages (e.g. via `pip`)

### 2.2. Setup

```bash
# Create and activate a virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate  # on Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
