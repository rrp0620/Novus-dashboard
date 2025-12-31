import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timedelta

# --- 1. SETUP ---
st.set_page_config(page_title="Novus Analytics", page_icon="🗝️", layout="wide")

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
    
    # Defaults: Current Year to Date
    today = datetime.now()
    start_of_year = today.replace(month=1, day=1)
    
    date_range = st.date_input("Select Period", (start_of_year, today), format="MM/DD/YYYY")
    if len(date_range) == 2:
        start_val, end_val = date_range
    else:
        start_val, end_val = start_of_year, today

    st.divider()
    view_mode = st.radio("Select View:", 
        ["💰 Revenue & Profit", 
         "📈 Business Trends (MoM)", 
         "🚀 Pipeline (Future)", 
         "📉 Cancellation Analysis"]
    )
    date_label = f"{start_val.strftime('%b %d, %Y')} - {end_val.strftime('%b %d, %Y')}"

# --- 4. DATA ENGINE (FIXED) ---
@st.cache_data(ttl=900) 
def fetch_bookeo(start_d, end_d):
    # FIX: Convert 'date' objects to 'datetime' before formatting
    # This prevents the crash that caused "No bookings found"
    start_dt = datetime.combine(start_d, datetime.min.time())
    end_dt = datetime.combine(end_d, datetime.max.time())
    
    start_str = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    all_bookings = []
    page_token = ""
    
    progress_text = "Downloading Data..."
    my_bar = st.progress(0, text=progress_text)
    
    max_pages = 100
    
    for i in range(max_pages): 
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
                if not bookings: break
                
                all_bookings.extend(bookings)
                
                percent_complete = min((i + 1) / 20, 1.0)
                my_bar.progress(percent_complete, text=f"Fetched {len(all_bookings)} bookings...")
                
                page_token = data.get('info', {}).get('pageNavigationToken')
                if not page_token: break
                
                time.sleep(0.2) 
            else:
                # If error, print it to the UI for debugging
                st.error(f"API Error: {response.status_code} - {response.text}")
                break
        except Exception as e:
            st.error(f"Connection Error: {e}")
            break
            
    my_bar.empty()
    return all_bookings

def fetch_expenses():
    default_df = pd.DataFrame(columns=["Date", "Category", "Amount"])
    try:
        df = pd.read_csv(SHEET_URL)
        df.columns = df.columns.str.strip()
        if 'Amount' not in df.columns:
            if 'amount' in df.columns: df.rename(columns={'amount': 'Amount'}, inplace=True)
            else: return default_df 
        df['Amount'] = pd.to_numeric(df['Amount'].astype(str).str.replace(r'[$,]', '', regex=True), errors='coerce').fillna(0)
        if 'Date' in df.columns: df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        return df
    except:
        return default_df

# Trigger Fetch
raw_bookings = fetch_bookeo(start_val, end_val)
raw_expenses = fetch_expenses()

# --- 5. PROCESSING ---
data_list = []
if raw_bookings:
    for b in raw_bookings:
        booking_id = b.get('bookingNumber')
        price_info = b.get('price', {})
        total_gross = float(price_info.get('totalGross', {}).get('amount', 0))
        total_paid = float(price_info.get('totalPaid', {}).get('amount', 0))
        
        is_canceled = b.get('canceled', False)
        if is_canceled: status = "Cancelled"
        elif total_paid >= total_gross and total_gross > 0: status = "Fully Paid"
        elif total_paid > 0: status = "Partially Paid"
        else: status = "Unpaid"

        created = pd.to_datetime(b.get('creationTime', '')[:10])
        event = pd.to_datetime(b.get('startTime', '')[:10])
        lead_time = (event - created).days

        room_name = b.get('productName', 'Unknown')
        part_list = b.get('participants', {}).get('numbers', [])
        count = sum([p.get('number', 0) for p in part_list])

        data_list.append({
            "Booking ID": booking_id,
            "Event Date": event,
            "Room": room_name,
            "Total Price": total_gross,
            "Paid Amount": total_paid,
            "Outstanding": total_gross - total_paid,
            "Status": status,
            "Participants": count,
            "Lead Days": lead_time,
            "Customer": b.get('title', 'Unknown'),
            "Day": event.strftime("%A"),
            "Month": event.strftime("%Y-%m")
        })

df = pd.DataFrame(data_list)
if not df.empty:
    df.drop_duplicates(subset=['Booking ID'], inplace=True)
    df.sort_values(by="Event Date", ascending=False, inplace=True)

# Expense Filter
if not raw_expenses.empty and 'Date' in raw_expenses.columns:
    mask = (raw_expenses['Date'] >= pd.to_datetime(start_val)) & (raw_expenses['Date'] <= pd.to_datetime(end_val))
    filtered_expenses = raw_expenses.loc[mask]
else:
    filtered_expenses = pd.DataFrame(columns=["Date", "Category", "Amount"])

# --- 6. VIEWS ---
st.title(f"{view_mode}")
st.caption(f"Range: {date_label}")

if df.empty:
    st.warning(f"No bookings found.")
    st.info("Debugging: If you see this, the API returned an empty list. Try a shorter date range (e.g., last 30 days) to test connection.")
    st.stop()

# === VIEW 1: REVENUE & PROFIT ===
if view_mode == "💰 Revenue & Profit":
    active_df = df[df['Status'] != "Cancelled"]
    real_revenue = active_df['Paid Amount'].sum() if not active_df.empty else 0
    total_exp = filtered_expenses['Amount'].sum() if not filtered_expenses.empty else 0
    net_profit = real_revenue - total_exp
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Revenue (Collected)", f"${real_revenue:,.0f}")
    m2.metric("Expenses", f"${total_exp:,.0f}")
    m3.metric("Net Profit", f"${net_profit:,.0f}")
    
    with st.expander("🔎 Inspect Revenue Source"):
        st.dataframe(active_df[['Event Date', 'Customer', 'Room', 'Paid Amount']], use_container_width=True)

    st.divider()
    if not active_df.empty:
        c1, c2 = st.columns(2)
        c1.subheader("Revenue by Room")
        c1.bar_chart(active_df.groupby("Room")["Paid Amount"].sum(), color="#00CC96")
        c2.subheader("Revenue by Day")
        day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        c2.bar_chart(active_df.groupby("Day")["Paid Amount"].sum().reindex(day_order), color="#636EFA")

# === VIEW 2: TRENDS (MOM & YOY) ===
elif view_mode == "📈 Business Trends (MoM)":
    active_df = df[df['Status'] != "Cancelled"].copy()
    
    monthly_data = active_df.groupby("Month")["Paid Amount"].sum().reset_index()
    monthly_data = monthly_data.sort_values("Month")
    monthly_data['Growth %'] = monthly_data['Paid Amount'].pct_change() * 100
    
    st.subheader("📊 Monthly Revenue Curve")
    st.line_chart(monthly_data.set_index("Month")["Paid Amount"], color="#00CC96")
    
    st.divider()
    
    st.subheader("📅 Month-over-Month Performance")
    display_trend = monthly_data.copy()
    display_trend['Paid Amount'] = display_trend['Paid Amount'].apply(lambda x: f"${x:,.0f}")
    display_trend['Growth %'] = display_trend['Growth %'].apply(lambda x: f"{x:+.1f}%" if pd.notnull(x) else "-")
    
    st.dataframe(
        display_trend,
        column_order=("Month", "Paid Amount", "Growth %"),
        use_container_width=True,
        hide_index=True
    )

# === VIEW 3: PIPELINE ===
elif view_mode == "🚀 Pipeline (Future)":
    pipeline_df = df[(df['Status'].isin(["Partially Paid", "Unpaid"])) & (df['Status'] != "Cancelled")]
    if pipeline_df.empty:
        st.info("No pipeline data found.")
    else:
        pending_collection = pipeline_df['Outstanding'].sum()
        deposits_held = pipeline_df['Paid Amount'].sum()
        k1, k2, k3 = st.columns(3)
        k1.metric("Uncollected (Pay at Door)", f"${pending_collection:,.0f}")
        k2.metric("Deposits Held", f"${deposits_held:,.0f}")
        k3.metric("Pending Bookings", len(pipeline_df))
        st.dataframe(pipeline_df[["Event Date", "Customer", "Room", "Status", "Outstanding"]], use_container_width=True)

# === VIEW 4: CANCELLATIONS ===
elif view_mode == "📉 Cancellation Analysis":
    cancel_df = df[df['Status'] == "Cancelled"]
    if cancel_df.empty:
        st.success("No cancellations found!")
    else:
        lost_rev = cancel_df['Total Price'].sum()
        m1, m2 = st.columns(2)
        m1.metric("Lost Revenue", f"${lost_rev:,.0f}")
        m1.metric("Count", len(cancel_df))
        st.dataframe(cancel_df[["Event Date", "Customer", "Room", "Lead Days"]], use_container_width=True)
