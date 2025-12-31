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

# GOOGLE SHEET CONFIG (Replace with your actual Sheet ID below)
# Example ID: 1BxiM_9_random_letters_7s
SHEET_ID = "1f79HfLYphC8X3JHjLNxleia6weOJQr-YMbisLk69Pj4" 

SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv"
EDIT_LINK = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"

# --- 2. THE DATA ENGINE ---
@st.cache_data(ttl=600)
def get_bookeo_data():
    # 1. Look back 30 days
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=30)
    
    # 2. Format dates for Bookeo
    start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")

    all_bookings = []
    has_more_pages = True
    page_token = ""

    # 3. Pagination Loop (Collects ALL data, not just the first 100)
    while has_more_pages:
        url = (f"https://api.bookeo.com/v2/bookings"
               f"?apiKey={API_KEY}"
               f"&secretKey={SECRET_KEY}"
               f"&startTime={start_str}"
               f"&endTime={end_str}"
               f"&itemsPerPage=100") # Fixed: Changed 300 to 100
        
        if page_token:
            url += f"&pageNavigationToken={page_token}"

        try:
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                bookings = data.get('data', [])
                all_bookings.extend(bookings)
                
                # Check if there is another page of data
                info = data.get('info', {})
                page_token = info.get('pageNavigationToken')
                
                if not page_token:
                    has_more_pages = False
            else:
                st.error(f"⚠️ Bookeo Error {response.status_code}: {response.text}")
                has_more_pages = False
        except Exception as e:
            st.error(f"⚠️ Connection Failed: {e}")
            has_more_pages = False

    return all_bookings

def get_expenses():
    try:
        df = pd.read_csv(SHEET_URL)
        # Clean currency symbols
        if 'Amount' in df.columns:
            # Force conversion to string first to avoid errors, then replace
            df['Amount'] = df['Amount'].astype(str).str.replace(r'[$,]', '', regex=True)
            df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0.0)
        return df
    except:
        return pd.DataFrame(columns=["Date", "Category", "Amount"])

# --- 3. DASHBOARD DISPLAY ---
st.title("🗝️ Novus Performance")
st.caption("Data: Last 30 Days")

with st.spinner('Syncing with Bookeo...'):
    bookings = get_bookeo_data()
    expenses = get_expenses()

# CALCULATIONS
total_revenue = 0.0
if bookings:
    for b in bookings:
        price_info = b.get('finalPrice', {})
        # Only count if amount exists
        if price_info:
            total_revenue += float(price_info.get('amount', 0))

total_expenses = expenses['Amount'].sum() if not expenses.empty and 'Amount' in expenses.columns else 0
net_profit = total_revenue - total_expenses

# METRICS
col1, col2, col3 = st.columns(3)
col1.metric("Revenue", f"${total_revenue:,.0f}")
col2.metric("Expenses", f"${total_expenses:,.0f}")
col3.metric("Profit", f"${net_profit:,.0f}", delta_color="normal")

st.divider()

# TABLE & LINK
st.link_button("➕ Add Expenses (Google Sheets)", EDIT_LINK)

with st.expander(f"View Bookings ({len(bookings)} found)"):
    if bookings:
        simple_data = []
        for b in bookings:
            simple_data.append({
                "Date": b.get('startTime', '')[:10],
                "Customer": b.get('customer', {}).get('firstName', 'Unknown'),
                "Price": f"${b.get('finalPrice', {}).get('amount', '0')}"
            })
        st.dataframe(pd.DataFrame(simple_data))
