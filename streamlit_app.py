import streamlit as st
import pandas as pd
import numpy as np

# title
st.title("RILSA map")

# File type csv and xlsx uploader
uploaded_file = st.file_uploader("Upload a document", type=["csv", "xlsx"])
if uploaded_file:
    df = pd.read_csv(uploaded_file)
    df = pd.read_excel(uploaded_file)
    st.dataframe(df)

# Display data in a table format
st.table(df)