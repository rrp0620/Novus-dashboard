import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# --- 1. SETTINGS & CONNECTIONS ---
st.set_page_config(page_title="Novus Dashboard", page_icon="🗝️", layout="centered")

# Pulling the keys you just saved in Streamlit Secrets
API_KEY = st.secrets["API_KEY"]
SECRET_KEY = st.secrets["SECRET_KEY"]

# --- 2. THE DATA ENGINE ---
@st.cache_data(ttl=600)  # Refreshes every 10 minutes
def get_bookeo_data():
    """Fetches bookings from Bookeo API"""
    url = f"https://api.bookeo.com/v2/bookings?apiKey={API_KEY}&secretKey={SECRET_KEY}&itemsPerPage=100"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.json().get('data', [])
        else:
            st.error(f"Bookeo Error: {response.status_code}. Check your Secrets!")
            return []
    except Exception as e:
        st.error(f"Connection Error: {e}")
        return []

# --- 3. THE DASHBOARD LOGIC ---
st.title("🗝️ Novus Performance")

data = get_bookeo_data()

if not data:
    st.warning("No booking data found. If you just opened, this is normal!")
    total_revenue = 0.0
else:
    # Bookeo stores price as {'amount': '150.00', 'currency': 'USD'}
    # This line extracts just the number so we can add it up
    prices = [float(b.get('finalPrice', {}).get('amount', 0)) for b in data]
    total_revenue = sum(prices)

# --- 4. EXPENSE TRACKING (Manual Input) ---
# For now, we use a simple 'Memory' list. 
# Once you add the Google Sheet later, this is where it will live.
st.divider()
st.subheader("Financial Overview")

# Display Metrics
col1, col2 = st.columns(2)
col1.metric("Revenue (Last 100 Bookings)", f"${total_revenue:,.2f}")
col2.metric("Target", "$5,000", delta=f"{total_revenue - 5000:,.2f}")

# --- 5. THE EXPENSE FORM ---
st.divider()
with st.expander("📝 Add Expense (Rent, Utilities, etc.)"):
    with st.form("expense_form", clear_on_submit=True):
        date = st.date_input("Date Paid", datetime.now())
        category = st.selectbox("Category", ["Rent", "Labor", "Electric", "Gas", "Water", "Insurance", "Marketing"])
        amount = st.number_input("Amount ($)", min_value=0.0, step=10.0)
        submitted = st.form_submit_button("Log Expense")
        
        if submitted:
            st.success(f"Logged ${amount} for {category}. (Note: Connect Google Sheets to save this permanently!)")

# --- 6. DATA TABLE ---
if data:
    with st.expander("View Recent Bookings"):
        # Show a clean table of the latest bookings
        simple_data = []
        for b in data:
            simple_data.append({
                "Date": b.get('startTime', '')[:10],
                "Customer": b.get('customer', {}).get('firstName', 'N/A'),
                "Price": f"${b.get('finalPrice', {}).get('amount', '0')}"
            })
        st.table(pd.DataFrame(simple_data))
