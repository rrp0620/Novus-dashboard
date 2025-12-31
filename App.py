import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timedelta

# --- 1. SETUP ---
st.set_page_config(page_title="Novus Command Center", page_icon="🗝️", layout="wide")

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

# --- 3. SIDEBAR CONTROLS ---
with st.sidebar:
    st.header("🔍 Filters")
    
    # Date Range Picker (Default to last 30 days)
    today = datetime.now()
    default_start = today - timedelta(days=30)
    
    date_range = st.date_input(
        "Select Date Range",
        (default_start, today),
        format="MM/DD/YYYY"
    )
    
    # Handle the case where user picks only one date so far
    if len(date_range) == 2:
        start_val, end_val = date_range
    else:
        start_val, end_val = default_start, today

    st.info("💡 Tip: Shorter ranges load faster.")

# --- 4. DATA ENGINE (Dynamic) ---
@st.cache_data(ttl=600)
def fetch_bookeo(start_d, end_d):
    # Convert Sidebar Dates to Bookeo Format
    start_str = start_d.strftime("%Y-%m-%dT00:00:00Z")
    end_str = end_d.strftime("%Y-%m-%dT23:59:59Z") # End of day

    all_bookings = []
    page_token = ""
    
    # Safety Cap: 10 Pages (1000 bookings max) to prevent crashing
    for _ in range(10): 
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
                time.sleep(1) # Polite pause
            else:
                break
        except:
            break
    return all_bookings

def fetch_expenses():
    try:
        df = pd.read_csv(SHEET_URL)
        if 'Amount' in df.columns:
            df['Amount'] = pd.to_numeric(df['Amount'].astype(str).str.replace(r'[$,]', '', regex=True), errors='coerce').fillna(0)
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'])
        return df
    except:
        return pd.DataFrame(columns=["Date", "Category", "Amount"])

# --- 5. LOAD DATA ---
with st.spinner('Syncing Data...'):
    raw_bookings = fetch_bookeo(start_val, end_val)
    raw_expenses = fetch_expenses()

# --- 6. PROCESS DATA INTO DATAFRAME ---
if raw_bookings:
    data_list = []
    for b in raw_bookings:
        # Extract Price
        gross = b.get('price', {}).get('totalGross', {})
        val = float(gross.get('amount', 0))
        
        # Extract Dates
        created = pd.to_datetime(b.get('creationTime', '')[:10])
        event = pd.to_datetime(b.get('startTime', '')[:10])
        
        # Lead Time (Days between booking and playing)
        lead_time = (event - created).days
        
        # Extract Participants
        part_list = b.get('participants', {}).get('numbers', [])
        count = sum([p.get('number', 0) for p in part_list])

        data_list.append({
            "Event Date": event,
            "Room": b.get('productName', 'Unknown'),
            "Revenue": val,
            "Participants": count,
            "Lead Days": lead_time,
            "Customer": b.get('title', 'Unknown'),
            "Day": event.strftime("%A") # Monday, Tuesday...
        })
    
    df = pd.DataFrame(data_list)
else:
    df = pd.DataFrame()

# --- 7. FILTERING LOGIC ---
if not df.empty:
    with st.sidebar:
        st.divider()
        st.header("🎯 Drill Down")
        
        # Room Filter
        all_rooms = ["All Rooms"] + list(df['Room'].unique())
        selected_room = st.selectbox("Filter by Room:", all_rooms)
        
        if selected_room != "All Rooms":
            df = df[df['Room'] == selected_room]
            
        # Participant Filter
        min_p, max_p = int(df['Participants'].min()), int(df['Participants'].max())
        if min_p < max_p:
            p_range = st.slider("Group Size:", min_p, max_p, (min_p, max_p))
            df = df[(df['Participants'] >= p_range[0]) & (df['Participants'] <= p_range[1])]

# Filter Expenses by Date
if not raw_expenses.empty:
    mask = (raw_expenses['Date'] >= pd.to_datetime(start_val)) & (raw_expenses['Date'] <= pd.to_datetime(end_val))
    filtered_expenses = raw_expenses.loc[mask]
else:
    filtered_expenses = pd.DataFrame()

# --- 8. DASHBOARD LAYOUT ---
st.title("📊 Novus Command Center")

if df.empty:
    st.warning("No bookings found for this period. Try extending the date range.")
    st.stop()

# TOP METRICS
total_rev = df['Revenue'].sum()
total_exp = filtered_expenses['Amount'].sum() if not filtered_expenses.empty else 0
net_profit = total_rev - total_exp
avg_order = df['Revenue'].mean()
total_games = len(df)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Net Profit", f"${net_profit:,.0f}", delta=f"Rev: ${total_rev:,.0f}")
m2.metric("Total Games", total_games)
m3.metric("Avg Order Value", f"${avg_order:.0f}")
m4.metric("Expenses", f"${total_exp:,.0f}")

st.divider()

# CHARTS ROW 1
c1, c2 = st.columns(2)

with c1:
    st.subheader("💰 Revenue by Room")
    # Group by Room and Sum Revenue
    room_rev = df.groupby("Room")["Revenue"].sum().sort_values(ascending=False)
    st.bar_chart(room_rev, color="#00CC96") # Green bars

with c2:
    st.subheader("📅 Busiest Days")
    # Sort days correctly (Mon -> Sun)
    days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_counts = df['Day'].value_counts().reindex(days_order).fillna(0)
    st.bar_chart(day_counts, color="#636EFA") # Blue bars

# CHARTS ROW 2
c3, c4 = st.columns(2)

with c3:
    st.subheader("👥 Group Size Trends")
    st.caption("Are we getting couples or parties?")
    # Simple histogram of participants
    group_data = df['Participants'].value_counts().sort_index()
    st.bar_chart(group_data)

with c4:
    st.subheader("⏳ Booking Lead Time")
    st.caption("0 = Same Day Walk-in")
    # Average Lead time per Room
    lead_data = df.groupby("Room")["Lead Days"].mean()
    st.bar_chart(lead_data)

st.divider()

# DETAILED TABLE
st.subheader("📝 Booking Log")
# Format for display
display_df = df.copy()
display_df['Event Date'] = display_df['Event Date'].dt.strftime('%Y-%m-%d')
display_df['Revenue'] = display_df['Revenue'].apply(lambda x: f"${x:,.2f}")

st.dataframe(
    display_df,
    column_order=("Event Date", "Room", "Customer", "Participants", "Revenue", "Lead Days", "Day"),
    hide_index=True,
    use_container_width=True
)
