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
SHEET_ID = "1f79HfLYphC8X3JHjLNxleia6weOJQr-YMbisLk69Pj4" 
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv"
EDIT_LINK = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"

# --- 3. DATA ENGINE ---
@st.cache_data(ttl=600)
def get_bookeo_data():
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=14)
    start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")

    all_bookings = []
    page_token = ""
    
    for _ in range(5): 
        # We don't need 'expand' anymore since we found the data in the standard view!
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

# --- 5. FIXED PARSING LOGIC ---
total_rev = 0.0
list_for_table = []

for b in bookings:
    # 1. GET PRICE (Fixed based on your data)
    # Your data format: price -> totalGross -> amount
    price_data = b.get('price', {})
    gross = price_data.get('totalGross', {})
    
    val_str = gross.get('amount', '0') # This grabs "30"
    val = float(val_str)
        
    total_rev += val
    
    # 2. GET NAME (Fixed based on your data)
    # Your data format: "title": "Courtney Ash"
    customer_name = b.get('title', 'Unknown')
    
    list_for_table.append({
        "Date": b.get('startTime', '')[:10],
        "Customer": customer_name,
        "Amt": val
    })

total_exp = expenses['Amount'].sum() if not expenses.empty else 0

# Visuals
c1, c2, c3 = st.columns(3)
c1.metric("Revenue", f"${total_rev:,.0f}")
c2.metric("Expenses", f"${total_exp:,.0f}")
c3.metric("Profit", f"${total_rev - total_exp:,.0f}")

st.divider()

if bookings:
    st.subheader("Recent Bookings")
    st.dataframe(pd.DataFrame(list_for_table))
else:
    st.write("No bookings found.")

st.link_button("➕ Add Expenses", EDIT_LINK)
