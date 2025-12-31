import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timedelta

# --- 1. SETUP ---
st.set_page_config(page_title="Novus Dashboard", page_icon="🗝️", layout="centered")

# Retrieve Keys
try:
    API_KEY = st.secrets["API_KEY"]
    SECRET_KEY = st.secrets["SECRET_KEY"]
except:
    st.error("❌ Secrets missing. Check Streamlit settings.")
    st.stop()

# --- 2. GOOGLE SHEET CONFIG ---
# PASTE YOUR ID HERE:
SHEET_ID = "YOUR_GOOGLE_SHEET_ID_HERE" 

SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv"
EDIT_LINK = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"

# --- 3. THE DATA ENGINE ---
@st.cache_data(ttl=3600) # Remembers data for 1 hour to avoid 429 errors
def get_bookeo_data():
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=30)
    
    start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")

    all_bookings = []
    has_more_pages = True
    page_token = ""

    while has_more_pages:
        url = (f"https://api.bookeo.com/v2/bookings"
               f"?apiKey={API_KEY}"
               f"&secretKey={SECRET_KEY}"
               f"&startTime={start_str}"
               f"&endTime={end_str}"
               f"&itemsPerPage=100")
        
        if page_token:
            url += f"&pageNavigationToken={page_token}"

        try:
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                bookings = data.get('data', [])
                all_bookings.extend(bookings)
                
                page_token = data.get('info', {}).get('pageNavigationToken')
                if not page_token:
                    has_more_pages = False
                else:
                    # GENTLE PAUSE: Prevents Error 429
                    time.sleep(1.5) 
            elif response.status_code == 429:
                st.warning("⚠️ Bookeo is busy. Waiting 20 seconds to try again...")
                time.sleep(20)
            else:
                has_more_pages = False
        except:
            has_more_pages = False

    return all_bookings

def get_expenses():
    try:
        df = pd.read_csv(SHEET_URL)
        if 'Amount' in df.columns:
            df['Amount'] = df['Amount'].astype(str).str.replace(r'[$,]', '', regex=True)
            df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0.0)
        return df
    except:
        return pd.DataFrame(columns=["Date", "Category", "Amount"])

# --- 4. DASHBOARD DISPLAY ---
st.title("🗝️ Novus Performance")
st.caption("30-Day View")

with st.spinner('Updating from Bookeo...'):
    bookings = get_bookeo_data()
    expenses = get_expenses()

# CALCULATIONS
total_revenue = sum([float(b.get('finalPrice', {}).get('amount', 0)) for b in bookings])
total_expenses = expenses['Amount'].sum() if not expenses.empty else 0
net_profit = total_revenue - total_expenses

# METRICS
col1, col2, col3 = st.columns(3)
col1.metric("Revenue", f"${total_revenue:,.0f}")
col2.metric("Expenses", f"${total_expenses:,.0f}")
col3.metric("Profit", f"${net_profit:,.0f}")

st.divider()

# MANAGE EXPENSES
st.link_button("➕ Open Google Sheets to Add Expenses", EDIT_LINK)

# RECENT LIST
with st.expander(f"Recent Games ({len(bookings)})"):
    if bookings:
        df_list = []
        for b in bookings:
            df_list.append({
                "Date": b.get('startTime', '')[:10],
                "Price": float(b.get('finalPrice', {}).get('amount', 0))
            })
        st.dataframe(pd.DataFrame(df_list))
