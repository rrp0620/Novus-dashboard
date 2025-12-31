import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timedelta

# --- 1. SETUP ---
st.set_page_config(page_title="Novus Salesforce", page_icon="🗝️", layout="wide")

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

# --- 3. SIDEBAR ---
with st.sidebar:
    st.title("🔍 Filters")
    today = datetime.now()
    default_start = today - timedelta(days=30)
    
    date_range = st.date_input("Select Period", (default_start, today), format="MM/DD/YYYY")
    if len(date_range) == 2:
        start_val, end_val = date_range
    else:
        start_val, end_val = default_start, today

    st.divider()
    view_mode = st.radio("Select View:", ["💰 Revenue & Profit", "🚀 Pipeline (Future)", "📉 Cancellation Analysis"])

    date_label = f"{start_val.strftime('%b %d')} - {end_val.strftime('%b %d, %Y')}"

# --- 4. DATA ENGINE ---
@st.cache_data(ttl=600)
def fetch_bookeo(start_d, end_d):
    start_str = start_d.strftime("%Y-%m-%dT00:00:00Z")
    end_str = end_d.strftime("%Y-%m-%dT23:59:59Z")

    all_bookings = []
    page_token = ""
    
    for _ in range(15): 
        url = (f"https://api.bookeo.com/v2/bookings"
               f"?apiKey={API_KEY}"
               f"&secretKey={SECRET_KEY}"
               f"&startTime={start_str}"
               f"&endTime={end_str}"
               f"&itemsPerPage=100")
        
        if page_token: url += f"&pageNavigationToken={page_token}"

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

def fetch_expenses():
    """Robust expense fetcher that never fails on missing columns"""
    default_df = pd.DataFrame(columns=["Date", "Category", "Amount"])
    try:
        df = pd.read_csv(SHEET_URL)
        
        # 1. Normalize Header Names (Strip spaces)
        df.columns = df.columns.str.strip()
        
        # 2. Ensure 'Amount' exists
        if 'Amount' not in df.columns:
            # Check if user typed 'amount' (lowercase) by mistake
            if 'amount' in df.columns:
                df.rename(columns={'amount': 'Amount'}, inplace=True)
            else:
                return default_df # Return empty if column is totally missing

        # 3. Clean 'Amount' Data
        df['Amount'] = pd.to_numeric(df['Amount'].astype(str).str.replace(r'[$,]', '', regex=True), errors='coerce').fillna(0)
        
        # 4. Clean 'Date' Data
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
            
        return df
    except:
        return default_df

with st.spinner(f'Processing Financials for {date_label}...'):
    raw_bookings = fetch_bookeo(start_val, end_val)
    raw_expenses = fetch_expenses()

# --- 5. INTELLIGENT PROCESSING ---
data_list = []

if raw_bookings:
    for b in raw_bookings:
        price_info = b.get('price', {})
        total_gross = float(price_info.get('totalGross', {}).get('amount', 0))
        total_paid = float(price_info.get('totalPaid', {}).get('amount', 0))
        
        is_canceled = b.get('canceled', False)
        
        if is_canceled:
            status = "Cancelled"
        elif total_paid >= total_gross and total_gross > 0:
            status = "Fully Paid"
        elif total_paid > 0 and total_paid < total_gross:
            status = "Partially Paid"
        else:
            status = "Unpaid"

        created = pd.to_datetime(b.get('creationTime', '')[:10])
        event = pd.to_datetime(b.get('startTime', '')[:10])
        lead_time = (event - created).days

        room_name = b.get('productName', 'Unknown')
        part_list = b.get('participants', {}).get('numbers', [])
        count = sum([p.get('number', 0) for p in part_list])

        data_list.append({
            "Event Date": event,
            "Room": room_name,
            "Total Price": total_gross,
            "Paid Amount": total_paid,
            "Outstanding": total_gross - total_paid,
            "Status": status,
            "Participants": count,
            "Lead Days": lead_time,
            "Customer": b.get('title', 'Unknown'),
            "Day": event.strftime("%A")
        })

df = pd.DataFrame(data_list)

# --- CRITICAL FIX FOR EXPENSE FILTERING ---
# We force filtered_expenses to always have an 'Amount' column, even if empty
if not raw_expenses.empty and 'Date' in raw_expenses.columns:
    mask = (raw_expenses['Date'] >= pd.to_datetime(start_val)) & (raw_expenses['Date'] <= pd.to_datetime(end_val))
    filtered_expenses = raw_expenses.loc[mask]
else:
    # This was the line causing the error! Now fixed:
    filtered_expenses = pd.DataFrame(columns=["Date", "Category", "Amount"])

# --- 6. DASHBOARD VIEWS ---
st.title(f"{view_mode}")
st.caption(f"Range: {date_label}")

if df.empty:
    st.warning("No Bookeo data found for this period.")
    # We don't stop here, we still show expenses if available

# === VIEW 1: REVENUE (Real Money Only) ===
if view_mode == "💰 Revenue & Profit":
    active_df = df[df['Status'] != "Cancelled"] if not df.empty else df
    
    real_revenue = active_df['Paid Amount'].sum() if not active_df.empty else 0
    
    # Safe sum (will be 0 if empty)
    total_exp = filtered_expenses['Amount'].sum() if not filtered_expenses.empty else 0
    net_profit = real_revenue - total_exp
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Real Revenue (Collected)", f"${real_revenue:,.0f}")
    m2.metric("Expenses", f"${total_exp:,.0f}")
    m3.metric("Net Profit", f"${net_profit:,.0f}", delta=f"Margin: {(net_profit/real_revenue*100) if real_revenue else 0:.1f}%")

    st.divider()
    
    if not active_df.empty:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Revenue by Room")
            st.bar_chart(active_df.groupby("Room")["Paid Amount"].sum(), color="#00CC96")
        with c2:
            st.subheader("Revenue by Day")
            day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            st.bar_chart(active_df.groupby("Day")["Paid Amount"].sum().reindex(day_order), color="#636EFA")

# === VIEW 2: PIPELINE ===
elif view_mode == "🚀 Pipeline (Future)":
    if df.empty:
        st.info("No data.")
        st.stop()
        
    pipeline_df = df[(df['Status'].isin(["Partially Paid", "Unpaid"])) & (df['Status'] != "Cancelled")]
    
    pending_collection = pipeline_df['Outstanding'].sum()
    deposits_held = pipeline_df['Paid Amount'].sum()
    
    st.info("💡 **Pipeline** shows money for bookings that haven't fully paid yet (e.g. Pay at Door or Deposits).")
    
    k1, k2, k3 = st.columns(3)
    k1.metric("Uncollected (Pay at Door)", f"${pending_collection:,.0f}", delta="Potential Revenue")
    k2.metric("Deposits Held", f"${deposits_held:,.0f}")
    k3.metric("Pending Bookings", len(pipeline_df))
    
    st.divider()
    st.subheader("📝 Pending Payments List")
    st.dataframe(
        pipeline_df[["Event Date", "Customer", "Room", "Status", "Outstanding"]].sort_values("Event Date"),
        use_container_width=True,
        hide_index=True
    )

# === VIEW 3: CANCELLATION ANALYSIS ===
elif view_mode == "📉 Cancellation Analysis":
    if df.empty:
        st.info("No data.")
        st.stop()

    cancel_df = df[df['Status'] == "Cancelled"]
    total_bookings = len(df)
    cancel_count = len(cancel_df)
    cancel_rate = (cancel_count / total_bookings * 100) if total_bookings > 0 else 0
    lost_revenue = cancel_df['Total Price'].sum()
    
    avg_lead_cancel = cancel_df['Lead Days'].mean() if not cancel_df.empty else 0
    avg_lead_all = df['Lead Days'].mean()
    
    st.error(f"⚠️ You have lost **${lost_revenue:,.0f}** to cancellations in this period.")
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Cancellation Rate", f"{cancel_rate:.1f}%")
    m2.metric("Lost Bookings", cancel_count)
    m3.metric("Avg Lead Time (Cancelled)", f"{avg_lead_cancel:.1f} days")
    
    st.divider()
    
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Which Room gets cancelled most?")
        if not cancel_df.empty:
            st.bar_chart(cancel_df['Room'].value_counts(), color="#EF553B")
        
    with c2:
        st.subheader("Lead Time Analysis")
        st.write(f"Average Booking Lead Time: **{avg_lead_all:.1f} days**")
        st.write(f"Average Cancelled Lead Time: **{avg_lead_cancel:.1f} days**")
        if avg_lead_cancel < 2:
            st.warning("⚠️ **Insight:** People are cancelling last-minute bookings.")
        elif avg_lead_cancel > 14:
            st.warning("⚠️ **Insight:** People booking far in advance are cancelling.")
            
    st.subheader("Recent Cancellations")
    st.dataframe(cancel_df[["Event Date", "Customer", "Room", "Lead Days", "Total Price"]], use_container_width=True)
