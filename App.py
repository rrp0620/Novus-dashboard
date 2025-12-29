import streamlit as st
import requests

st.set_page_config(page_title="Novus Diagnostic", page_icon="🔧")
st.title("🔧 Connection Doctor")

# 1. Fetch Keys
try:
    API_KEY = st.secrets["API_KEY"]
    SECRET_KEY = st.secrets["SECRET_KEY"]
    st.success("✅ Keys found in Secrets!")
except:
    st.error("❌ Secrets are missing. Check Streamlit Settings.")
    st.stop()

# 2. Check for "Invisible Space" (Common iPhone Bug)
if " " in API_KEY or " " in SECRET_KEY:
    st.warning("⚠️ Warning: Your keys might have spaces in them!")
    st.write(f"API Key length: {len(API_KEY)} characters")
    st.write(f"Secret Key length: {len(SECRET_KEY)} characters")

# 3. The Test Connection
url = f"https://api.bookeo.com/v2/settings/apikeyinfo?apiKey={API_KEY}&secretKey={SECRET_KEY}"

if st.button("Run Diagnostics"):
    response = requests.get(url)
    
    st.write(f"**Status Code:** {response.status_code}")
    
    if response.status_code == 200:
        st.balloons()
        st.success("SUCCESS! The keys are perfect.")
        st.json(response.json())
    else:
        st.error("❌ Connection Failed. Here is the exact message from Bookeo:")
        st.code(response.text) # <--- This is the important part!
