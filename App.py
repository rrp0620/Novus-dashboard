import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import os

# --- 1. SETUP & CONFIGURATION ---
st.set_page_config(page_title="Novus Dashboard", layout="wide")
st.title("🗝️ Novus Escape Room Performance")

# Replace these with your actual keys from Bookeo
API_KEY = "AJNJNEFLU4ML66339FF9J415703EJAR9166F64C9036"
SECRET_KEY = "y6Ry3shNdaAKYUtGkYRnf8OLbhU2ad2td"
EXPENSE_FILE = "expenses.csv"

# --- 2. DATA LOADING (BOOKEO API) ---
def get_bookeo_data():
    # This fetches bookings from the last 30 days
    url = f"https://api.bookeo.com/v2/bookings?apiKey={API_KEY}&secretKey={SECRET_KEY}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json().get('data', [])
            return pd.DataFrame(data)
        else:
            st.error("Failed to connect to Bookeo. Check your API keys.")
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Error: {e}")
        return pd.DataFrame()

# --- 3. EXPENSE MANAGEMENT ---
if not os.path.exists(EXPENSE_FILE):
    df_empty = pd.DataFrame(columns=["Date", "Category", "Amount"])
    df_empty.to_csv(EXPENSE_FILE, index=False)

def add_expense(date, category, amount):
    new_data = pd.DataFrame([[date, category, amount]], columns=["Date", "Category", "Amount"])
    new_data.to_csv(EXPENSE_FILE, mode='a', header=False, index=False)

# --- 4. SIDEBAR - INPUT EXPENSES ---
st.sidebar.header("Add Expenses")
with st.sidebar.form("expense_form", clear_on_submit=True):
    exp_date = st.date_input("Date Paid")
    exp_cat = st.selectbox("Category", ["Rent", "Labor", "Electric", "Gas", "Water", "Insurance", "Other"])
    exp_amt = st.number_input("Amount ($)", min_value=0.0, step=10.0)
    submit = st.form_submit_button("Save Expense")
    
    if submit:
        add_expense(exp_date, exp_cat, exp_amt)
        st.sidebar.success("Expense Saved!")

# --- 5. DASHBOARD CALCULATIONS ---
bookings = get_bookeo_data()
expenses = pd.read_csv(EXPENSE_FILE)

# Calculate Totals
total_revenue = 0
if not bookings.empty:
    # This logic assumes 'finalPrice' exists in the Bookeo JSON
    total_revenue = bookings['finalPrice'].apply(lambda x: float(x.get('amount', 0))).sum()

total_expenses = expenses['Amount'].sum()
net_profit = total_revenue - total_expenses

# --- 6. VISUALS ---
col1, col2, col3 = st.columns(3)
col1.metric("Total Revenue", f"${total_revenue:,.2f}")
col2.metric("Total Expenses", f"${total_expenses:,.2f}", delta_color="inverse")
col3.metric("Net Profit", f"${net_profit:,.2f}")

st.divider()

st.subheader("Expense Breakdown")
if not expenses.empty:
    st.bar_chart(expenses.set_index("Category")["Amount"])
else:
    st.info("No expenses recorded yet. Use the sidebar to add some!")
