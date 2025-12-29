import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# --- 1. SETUP & PAGE CONFIG ---
st.set_page_config(page_title="Novus Dashboard", page_icon="🗝️", layout="centered")

# Retrieve keys from Streamlit Secrets
try:
    API_KEY = st.secrets["API_KEY"]
    SECRET_KEY = st.secrets["SECRET_KEY"]
except FileNotFoundError:
    st.error("❌ Secrets missing! Go to App Settings > Secrets to add them.")
    st.stop()

# --- 2. CONNECT TO GOOGLE SHEETS (EXPENSES) ---
# ⚠️ REPLACE THIS ID WITH YOUR OWN GOOGLE SHEET ID ⚠️
SHEET_ID = "1x_YOUR_ACTUAL_SHEET_ID_GOES_HERE_x1" 
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv"
EDIT_LINK = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"

# --- 3. DATA FUNCTIONS ---

@st.cache_data(ttl=600)  # Refreshes data every 10 minutes
def get_bookeo_data():
    """Fetches the last 100 bookings from Bookeo"""
    url = f"https://api.bookeo.com/v2/bookings?apiKey={API_KEY}&secretKey={SECRET_KEY}&itemsPerPage=100"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.json().get('data', [])
        else:
            return []
    except:
        return []

def get_expenses():
    """Fetches expenses from your Google Sheet"""
    try:
        # We try to read the sheet. If it's empty or fails, return an empty table.
        df = pd.read_csv(SHEET_URL)
        # Clean up currency symbols if you typed them in the sheet manually
        if 'Amount' in df.columns:
            df['Amount'] = df['Amount'].replace('[\$,]', '', regex=True).astype(float)
        return df
    except:
        # Returns an empty dataframe if the sheet is new/blank
        return pd.DataFrame(columns=["Date", "Category", "Amount", "Notes"])

# --- 4. DASHBOARD LOGIC ---

st.title("🗝️ Novus Performance")

# A. Load Data
with st.spinner('Syncing with Bookeo & Google...'):
    bookings = get_bookeo_data()
    expenses = get_expenses()

# B. Calculate Revenue (Bookeo)
total_revenue = 0.0
if bookings:
    # Extracts the price from the complex Bookeo format
    total_revenue = sum([float(b.get('finalPrice', {}).get('amount', 0)) for b in bookings])

# C. Calculate Expenses (Google Sheet)
total_expenses = 0.0
if not expenses.empty and 'Amount' in expenses.columns:
    total_expenses = expenses['Amount'].sum()

# D. Calculate Profit
net_profit = total_revenue - total_expenses

# --- 5. VISUALS ---

# Top Metrics
col1, col2, col3 = st.columns(3)
col1.metric("Revenue", f"${total_revenue:,.0f}")
col2.metric("Expenses", f"${total_expenses:,.0f}")
col3.metric("Net Profit", f"${net_profit:,.0f}", delta_color="normal")

st.divider()

# Expense Section
st.subheader("💸 Expense Tracking")
if expenses.empty:
    st.info("No expenses found. Click 'Add Expenses' to start your sheet!")
else:
    # Bar Chart of Spending
    st.bar_chart(expenses.groupby("Category")["Amount"].sum())

# Action Button: Open Google Sheet to Edit
st.link_button("➕ Add/Edit Expenses (Opens Google Sheets)", EDIT_LINK)

# Recent Bookings Section
st.divider()
with st.expander("See Recent Bookings"):
    if bookings:
        simple_data = []
        for b in bookings:
            simple_data.append({
                "Date": b.get('startTime', '')[:10],
                "Name": b.get('customer', {}).get('firstName', 'Unknown'),
                "Price": f"${b.get('finalPrice', {}).get('amount', '0')}"
            })
        st.table(pd.DataFrame(simple_data))
    else:
        st.write("No recent bookings found.")
