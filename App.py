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
    
    st.divider()
    show_debug = st.checkbox("Show Sync Log (Debug)", value=False)
    
    date_label = f"{start_val.strftime('%b %d, %Y')} - {end_val.strftime('%b %d, %Y')}"

# --- 4. DATA ENGINE (RATE LIMIT PROOF) ---
@st.cache_data(ttl=900) 
def fetch_bookeo(start_d, end_d):
    all_bookings = []
    log_messages = []
    
    current_start = datetime.combine(start_d, datetime.min.time())
    final_end = datetime.combine(end_d, datetime.max.time().replace(microsecond=0))
    
    progress_bar = st.progress(0, text="Initializing Smart Sync...")
    total_seconds = (final_end - current_start).total_seconds()
    if total_seconds <= 0: total_seconds = 1
    
    CHUNK_DAYS = 10 
    
    while current_start < final_end:
        chunk_end = current_start + timedelta(days=CHUNK_DAYS)
        if chunk_end > final_end: chunk_end = final_end
            
        elapsed = (current_start - datetime.combine(start_d, datetime.min.time())).total_seconds()
        pct = min(elapsed / total_seconds, 1.0)
        progress_bar.progress(pct, text=f"Syncing: {current_start.strftime('%b %d')} - {chunk_end.strftime('%b %d')}...")
        
        start_str = current_start.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = chunk_end.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        page_token = ""
        chunk_count = 0
        chunk_success = False
        
        for attempt in range(5):
            try:
                inner_success = True
                temp_bookings = [] 
                
                for _ in range(50): 
                    url = (f"https://api.bookeo.com/v2/bookings"
                           f"?apiKey={API_KEY}"
                           f"&secretKey={SECRET_KEY}"
                           f"&startTime={start_str}"
                           f"&endTime={end_str}"
                           f"&itemsPerPage=100")
                    
                    if page_token: url += f"&pageNavigationToken={page_token}"

                    response = requests.get(url, timeout=15)
                    
                    if response.status_code == 429:
                        wait_time = (attempt + 1) * 5 
                        log_messages.append(f"⚠️ Rate Limit (429) at {start_str}. Pausing {wait_time}s...")
                        time.sleep(wait_time)
                        inner_success = False 
                        break 
                    
                    if response.status_code == 200:
                        data = response.json()
                        bookings = data.get('data', [])
                        
                        if bookings: temp_bookings.extend(bookings)
                        
                        page_token = data.get('info', {}).get('pageNavigationToken')
                        if not page_token: break 
                        time.sleep(0.2) 
                    else:
                        log_messages.append(f"⚠️ Error {response.status_code}. Retrying...")
                        inner_success = False
                        time.sleep(2)
                        break
                
                if inner_success:
                    all_bookings.extend(temp_bookings)
                    chunk_count = len(temp_bookings)
                    log_messages.append(f"✅ {current_start.strftime('%b %d')}: {chunk_count} bookings")
                    chunk_success = True
                    break 
                
            except Exception as e:
                log_messages.append(f"❌ Connection Error: {e}")
                time.sleep(2)
        
        if not chunk_success:
             log_messages.append(f"❌ FAILED chunk {start_str} after 5 attempts.")

        if chunk_end == final_end: break
        current_start = chunk_end + timedelta(seconds=1)
            
    progress_bar.empty()
    return all_bookings, log_messages

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
raw_bookings, debug_logs = fetch_bookeo(start_val, end_val)
raw_expenses = fetch_expenses()

# --- 5. PROCESSING (UPDATED FOR TIME ANALYSIS) ---
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

        # --- NEW: Extract Time of Day ---
        full_dt = pd.to_datetime(b.get('startTime', ''))
        event_date = full_dt.date()
        created = pd.to_datetime(b.get('creationTime', ''))
        lead_time = (full_dt - created).days

        # Format Hour (e.g., "14" -> "02 PM")
        # We store the integer for sorting, string for display
        hour_int = full_dt.hour
        hour_str = full_dt.strftime("%I %p") # "02 PM"

        room_name = b.get('productName', 'Unknown')
        part_list = b.get('participants', {}).get('numbers', [])
        count = sum([p.get('number', 0) for p in part_list])

        data_list.append({
            "Booking ID": booking_id,
            "Event Date": pd.to_datetime(event_date),
            "Room": room_name,
            "Total Price": total_gross,
            "Paid Amount": total_paid,
            "Outstanding": total_gross - total_paid,
            "Status": status,
            "Participants": count,
            "Lead Days": lead_time,
            "Customer": b.get('title', 'Unknown'),
            "Day": full_dt.strftime("%A"),
            "Month": full_dt.strftime("%Y-%m"),
            "Hour Int": hour_int,   # Used for sorting chart
            "Hour Label": hour_str  # Used for displaying chart
        })

df = pd.DataFrame(data_list)
if not df.empty:
    df.drop_duplicates(subset=['Booking ID'], inplace=True)
    df.sort_values(by="Event Date", ascending=False, inplace=True)

if not raw_expenses.empty and 'Date' in raw_expenses.columns:
    mask = (raw_expenses['Date'] >= pd.to_datetime(start_val)) & (raw_expenses['Date'] <= pd.to_datetime(end_val))
    filtered_expenses = raw_expenses.loc[mask]
else:
    filtered_expenses = pd.DataFrame(columns=["Date", "Category", "Amount"])

# --- 6. DASHBOARD ---
st.title(f"{view_mode}")
st.caption(f"Range: {date_label}")

if show_debug:
    with st.expander("🛠️ View Sync Logs (Debug)", expanded=True):
        for log in debug_logs:
            if "❌" in log: st.error(log)
            elif "⚠️" in log: st.warning(log)
            else: st.write(log)

if df.empty:
    st.warning(f"No bookings found.")
    st.stop()

# === VIEW 1: REVENUE & PROFIT (WITH TIME ANALYSIS) ===
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
        insp_df = active_df[['Event Date', 'Hour Label', 'Customer', 'Room', 'Paid Amount']].copy()
        insp_df['Event Date'] = insp_df['Event Date'].dt.strftime('%Y-%m-%d')
        insp_df['Paid Amount'] = insp_df['Paid Amount'].apply(lambda x: f"${x:,.2f}")
        st.dataframe(insp_df, use_container_width=True, hide_index=True)

    st.divider()
    
    if not active_df.empty:
        # Row 1: Room & Day
        c1, c2 = st.columns(2)
        c1.subheader("Revenue by Room")
        c1.bar_chart(active_df.groupby("Room")["Paid Amount"].sum(), color="#00CC96")
        
        c2.subheader("Revenue by Day")
        day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        c2.bar_chart(active_df.groupby("Day")["Paid Amount"].sum().reindex(day_order), color="#636EFA")
        
        # Row 2: TIME OF DAY ANALYSIS (NEW)
        st.divider()
        st.subheader("🕒 Busiest Times of Day")
        st.caption("When are we making the most money? (Aggregated by Start Hour)")
        
        # Group by Hour Integer to ensure 1pm comes after 12pm
        time_data = active_df.groupby(["Hour Int", "Hour Label"])["Paid Amount"].sum().reset_index()
        time_data.sort_values("Hour Int", inplace=True)
        
        # Display Chart
        st.bar_chart(time_data.set_index("Hour Label")["Paid Amount"], color="#FFA15A")

# === VIEW 2: TRENDS ===
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
    st.dataframe(display_trend, use_container_width=True, hide_index=True)

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
        st.dataframe(pipeline_df[["Event Date", "Customer", "Room", "Status", "Outstanding"]], use_container_width=True, hide_index=True)

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
        st.dataframe(cancel_df[["Event Date", "Customer", "Room", "Lead Days"]], use_container_width=True, hide_index=True)
