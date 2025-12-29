import streamlit as st
import requests
import pandas as pd

# 1. Access Secrets
try:
    API_KEY = st.secrets["API_KEY"]
    SECRET_KEY = st.secrets["SECRET_KEY"]
except:
    st.error("Secrets are missing! Go to Streamlit Settings > Secrets.")

st.title("Novus API Diagnostic")

# 2. Test Connection
url = f"https://api.bookeo.com/v2/settings/apikeyinfo?apiKey={API_KEY}&secretKey={SECRET_KEY}"

if st.button("Test Connection Now"):
    response = requests.get(url)
    
    if response.status_code == 200:
        st.success("✅ SUCCESS! Bookeo is connected.")
        st.json(response.json()) # This will show your business name
    elif response.status_code == 401:
        st.error("❌ Error 401: Your SECRET_KEY is wrong. Check the Developer Dashboard.")
    elif response.status_code == 403:
        st.error("❌ Error 403: Your API_KEY is wrong or not yet active. Check the Email Key.")
    else:
        st.error(f"❌ Error {response.status_code}: {response.text}")
