import streamlit as st
import pandas as pd
import numpy as np

uploaded_file = st.file_uploader("Upload a document", type=["csv", "xlsx"])
if uploaded_file:
    df = pd.read_csv(uploaded_file)
    st.dataframe(df)
