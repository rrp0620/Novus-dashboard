import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timedelta

# --- 1. SETUP ---
st.set_page_config(page_title="Novus Dashboard", page_icon="🗝️", layout="wide") # Layout="wide" for better table view

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
        # Added &expand=customer to get Email and City/State
        url = (f"https://api.bookeo.com/v2/bookings"
               f"?apiKey={API_KEY}"
               f"&secretKey={SECRET_KEY}"
               f"&startTime={start_str}"
               f"&endTime={end_str}"
               f"&itemsPerPage=100"
               f"&expand=customer") 
        
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

with st.spinner('Compiling data...'):
    bookings = get_bookeo_data()
    expenses = get_expenses()

# --- 5. DATA EXTRACTION & SORTING ---
table_data = []
total_rev = 0.0

for b in bookings:
    # 1. PRICE
    gross = b.get('price', {}).get('totalGross', {})
    val = float(gross.get('amount', 0))
    total_rev += val
    
    # 2. PARTICIPANTS (Sum up the list)
    # Data looks like: participants -> numbers -> [{number: 2}, {number: 1}]
    part_list = b.get('participants', {}).get('numbers', [])
    count = sum([p.get('number', 0) for p in part_list])

    # 3. CUSTOMER DETAILS (From the 'customer' expansion)
    cust = b.get('customer', {})
    # If expansion fails, fallback to basic fields
    email = cust.get('emailAddress', 'N/A')
    
    address = cust.get('streetAddress', {})
    city = address.get('city', '')
    state = address.get('state', '')
    location = f"{city}, {state}".strip(", ")
    
    if not location: location = "N/A"

    # 4. DATES (Cleanup formatting)
    created_raw = b.get('creationTime', '')[:10] # YYYY-MM-DD
    event_raw = b.get('startTime', '')[:10]      # YYYY-MM-DD

    table_data.append({
        "Booking Created": created_raw,
        "Event Date": event_raw,
        "Customer Name": b.get('title', 'Unknown'),
        "Email": email,
        "Participants": count,
        "Amount": val, # Keep as number for sorting, format later
        "Location": location
    })

# Convert to DataFrame
df = pd.DataFrame(table_data)

# SORTING: Sort by 'Event Date' (Newest first)
if not df.empty:
    df['Event Date'] = pd.to_datetime(df['Event Date'])
    df = df.sort_values(by='Event Date', ascending=False)
    # Convert back to string for clean display
    df['Event Date'] = df['Event Date'].dt.strftime('%Y-%m-%d')
    
    # FORMATTING THE DOLLAR SIGN
    df['Amount'] = df['Amount'].apply(lambda x: f"${x:,.2f}")

# --- 6. DISPLAY ---
total_exp = expenses['Amount'].sum() if not expenses.empty else 0
c1, c2, c3 = st.columns(3)
c1.metric("Revenue", f"${total_rev:,.0f}")
c2.metric("Expenses", f"${total_exp:,.0f}")
c3.metric("Profit", f"${total_rev - total_exp:,.0f}")

st.divider()

if not df.empty:
    st.subheader("Recent Bookings")
    st.dataframe(
        df, 
        hide_index=True,
        column_order=("Event Date", "Booking Created", "Customer Name", "Email", "Participants", "Amount", "Location")
    )
else:
    st.info("No bookings found in the last 14 days.")

st.link_button("➕ Manage Expenses", EDIT_LINK)
