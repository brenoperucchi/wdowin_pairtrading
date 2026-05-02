# Getting Started

Follow these instructions to quickly boot the WIN×WDO Pair Trading system on your local machine.

## 1. Prerequisites

- **Windows OS** (MetaTrader 5 API requires Windows).
- **MetaTrader 5** running and logged into your B3 Broker account.
- **Python 3.10+**
- **Node.js 18+**

## 2. Install Backend Dependencies

Open a terminal in the root directory of the project:

```bash
pip install fastapi uvicorn MetaTrader5 numpy pandas statsmodels
```

## 3. Install Frontend Dependencies

Open a second terminal, navigate to the dashboard directory, and install:

```bash
cd regime-dashboard
npm install
```

## 4. Launching the System

You have two options to run the system: **Production (PM2)** or **Development (Manual)**.

### Option A: Using the Startup Script (Recommended)

Run the provided `.bat` file to automatically start both the backend and frontend:

```bash
.\regime-dashboard\start.bat
```
*(This will launch the Python API on port 8080 and the React App on port 5174).*

### Option B: Manual Start

**Terminal 1 (Backend):**
```bash
python server.py
# Or using uvicorn directly:
uvicorn server:app --host 0.0.0.0 --port 8080 --reload
```

**Terminal 2 (Frontend):**
```bash
cd regime-dashboard
npm run dev
```

## 5. Access the Dashboard

Open your web browser and navigate to:
`http://localhost:5174`

You should immediately see the live Z-Score and NWE charts. If you see a "Simulated" banner, it means the Python backend cannot connect to your MetaTrader 5 terminal. Check the `server.py` MT5 path configuration.
