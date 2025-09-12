import io
import numpy as np
import pandas as pd
import streamlit as st
import pydeck as pdk

# =========================
# 기본 데이터 경로(원하는 경로로 바꿔도 됨)
# =========================
DEFAULT_CSV_PATH = "EmailActivityUserDetail9_11_2025 3_44_29 PM.csv"        # 기본 CSV
DEFAULT_SHEET_NAME = None  # None이면 첫 시트

st.set_page_config(page_title="RILSA Email", layout="wide")
st.title("RILSA Email Data Analyse")

