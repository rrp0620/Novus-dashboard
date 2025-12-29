import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# --- 1. SETUP ---
st.set_page_config(page_title="Novus Dashboard", page_icon="🗝️", layout="centered")

# Retrieve Keys
try:
    API_KEY = st.secrets["API_KEY"]
    SECRET_KEY = st.secrets["SECRET_KEY"]
except:
    st.error("❌ Secrets missing. Please check your Streamlit settings.")
    st.stop()

# GOOGLE SHEET CONFIG (Replace with your ID)
SHEET_ID = "YOUR_GOOGLE_SHEET_ID_HERE"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv"
EDIT_LINK = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"

# --- 2. THE TIME MACHINE (FETCH DATA) ---
@st.cache_data(ttl=600)
def get_bookeo_data():
    # 1. Calculate dates: Look back 30 days from today
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=30)
    
    # 2. Format dates for Bookeo (ISO 8601 format)
    # Bookeo requires: YYYY-MM-DDTHH:mm:ssZ
    start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 3. Build the URL
    url = (f"https://api.bookeo.com/v2/bookings"
           f"?apiKey={API_KEY}"
           f"&secretKey={SECRET_KEY}"
           f"&startTime={start_str}"
           f"&endTime={end_str}"
           f"&itemsPerPage=300") # Max limit per call

    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.json().get('data', [])
        else:
            # If it fails, we show the EXACT error message on screen
            st.error(f"⚠️ Connection Error {response.status_code}: {response.text}")
            return []
    except Exception as e:
        st.error(f"⚠️ System Error: {e}")
        return []

def get_expenses():
    try:
        df = pd.read_csv(SHEET_URL)
        if 'Amount' in df.columns:
            df['Amount'] = df['Amount'].replace('[\$,]', '', regex=True).astype(float)
        return df
    except:
        return pd.DataFrame(columns=["Date", "Category", "Amount"])

# --- 3. DASHBOARD DISPLAY ---
st.title("🗝️ Novus Performance")
st.caption("Showing data for the last 30 days")

with st.spinner('Syncing data...'):
    bookings = get_bookeo_data()
    expenses = get_expenses()

# CALCULATIONS
total_revenue = 0.0
if bookings:
    for b in bookings:
        # Check if price exists and is not cancelled
        price_info = b.get('finalPrice', {})
        if price_info:
            total_revenue += float(price_info.get('amount', 0))

total_expenses = expenses['Amount'].sum() if not expenses.empty and 'Amount' in expenses.columns else 0
net_profit = total_revenue - total_expenses

# METRICS
col1, col2, col3 = st.columns(3)
col1.metric("Revenue (30d)", f"${total_revenue:,.0f}")
col2.metric("Expenses", f"${total_expenses:,.0f}")
col3.metric("Net Profit", f"${net_profit:,.0f}")

st.divider()

# RAW DATA CHECK (For Debugging)
with st.expander("🔍 Debug: View Raw Booking Data"):
    if bookings:
        st.write(f"Found {len(bookings)} bookings in the last 30 days.")
        st.dataframe(pd.DataFrame(bookings))
    else:
        st.warning("No bookings found in this date range (or connection failed).")

st.link_button("➕ Manage Expenses", EDIT_LINK)
