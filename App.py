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
    st.error("❌ Secrets missing in Streamlit Settings.")
    st.stop()

# --- 2. CONFIG (Your Sheet ID is now included!) ---
SHEET_ID = "1f79HfLYphC8X3JHjLNxleia6weOJQr-YMbisLk69Pj4" 
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv"
EDIT_LINK = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"

# --- 3. DATA ENGINE ---
@st.cache_data(ttl=1800)
def get_bookeo_data():
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=14)
    start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")

    all_bookings = []
    page_token = ""
    
    for _ in range(5): # Up to 500 bookings
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
                if not page_token: break
                time.sleep(1)
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
st.caption("14-Day View")

with st.spinner('Syncing...'):
    bookings = get_bookeo_data()
    expenses = get_expenses()

# --- 5. PRICE CALCULATION LOGIC ---
total_rev = 0.0
list_for_table = []

for b in bookings:
    # We check multiple places for the price (Bookeo varies by account type)
    price_obj = b.get('finalPrice') or b.get('totalPrice') or b.get('price')
    
    val = 0.0
    if isinstance(price_obj, dict):
        val = float(price_obj.get('amount', 0))
    elif isinstance(price_obj, (int, float)):
        val = float(price_obj)
        
    total_rev += val
    list_for_table.append({
        "Date": b.get('startTime', '')[:10],
        "Amt": val
    })

total_exp = expenses['Amount'].sum() if not expenses.empty else 0

# Visuals
c1, c2, c3 = st.columns(3)
c1.metric("Revenue (14d)", f"${total_rev:,.0f}")
c2.metric("Expenses", f"${total_exp:,.0f}")
c3.metric("Net Profit", f"${total_rev - total_exp:,.0f}")

st.divider()
st.link_button("➕ Manage Expenses (Google Sheets)", EDIT_LINK)

if not expenses.empty:
    st.subheader("Spending by Category")
    st.bar_chart(expenses.groupby("Category")["Amount"].sum())

with st.expander("View Booking History"):
    st.dataframe(pd.DataFrame(list_for_table))
