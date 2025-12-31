import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timedelta

# --- 1. SETUP ---
st.set_page_config(page_title="Novus Dashboard", page_icon="🗝️")

# Retrieve Keys
try:
    API_KEY = st.secrets["API_KEY"]
    SECRET_KEY = st.secrets["SECRET_KEY"]
except:
    st.error("❌ Secrets missing.")
    st.stop()

# --- 2. CONFIG ---
SHEET_ID = "YOUR_GOOGLE_SHEET_ID_HERE" # <--- Ensure this is correct!
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv"

# --- 3. FAST DATA ENGINE ---
@st.cache_data(ttl=1800) # Cache for 30 mins
def get_bookeo_data():
    # Look back 14 days instead of 30 for speed
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=14)
    
    start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")

    all_bookings = []
    page_token = ""
    
    # We will only pull up to 3 pages (300 bookings) to keep it fast
    for _ in range(3): 
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
                    break
                time.sleep(1) # Small pause
            else:
                break
        except:
            break

    return all_bookings

def get_expenses():
    try:
        df = pd.read_csv(SHEET_URL)
        if 'Amount' in df.columns:
            df['Amount'] = pd.to_numeric(df['Amount'].astype(str).str.replace(r'[$,]', '', regex=True), errors='coerce').fillna(0)
        return df
    except:
        return pd.DataFrame(columns=["Date", "Category", "Amount"])

# --- 4. DASHBOARD ---
st.title("🗝️ Novus Performance")
st.caption("Last 14 Days")

with st.spinner('Loading Data...'):
    bookings = get_bookeo_data()
    expenses = get_expenses()

# Calculate
total_rev = sum([float(b.get('finalPrice', {}).get('amount', 0)) for b in bookings])
total_exp = expenses['Amount'].sum() if not expenses.empty else 0

# Visuals
c1, c2 = st.columns(2)
c1.metric("Revenue (14d)", f"${total_rev:,.0f}")
c2.metric("Profit", f"${total_rev - total_exp:,.0f}")

st.divider()
if not expenses.empty:
    st.subheader("Expenses")
    st.bar_chart(expenses.groupby("Category")["Amount"].sum())

with st.expander("Recent Booking List"):
    st.write(pd.DataFrame([{"Date": b.get('startTime')[:10], "Amt": b.get('finalPrice', {}).get('amount')} for b in bookings]))
