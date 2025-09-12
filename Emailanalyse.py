from csv import excel
import io
from unittest.mock import DEFAULT
import numpy as np
import pandas as pd
import streamlit as st
import pydeck as pdk

# =========================
# 기본 데이터 경로(원하는 경로로 바꿔도 됨)
# =========================
DEFAULT_CSV_PATH = "EmailActivityUserDetail9_11_2025 3_44_29 PM.csv"        # 기본 CSV
DEFAULT_EXCEL_PATH = "Group.xlsx"  # 기본 Excel
DEFAULT_SHEET_NAME = None  # None이면 첫 시트

st.set_page_config(page_title="RILSA Email", layout="wide")
st.title("RILSA Email Data Analyse")

# =========================
# 사이드바 - 파일 업로드
# =========================
st.sidebar.header("1. Upload your CSV data")
uploaded_file = st.sidebar.file_uploader("Upload your input CSV file", type=["csv"])
if uploaded_file is not None:
    # 업로드된 파일이 있으면 해당 파일 사용
    csv_data = uploaded_file
    sheet_name = None
else:
    # 업로드된 파일이 없으면 기본 파일 사용
    csv_data = DEFAULT_CSV_PATH 
    excel_data = DEFAULT_EXCEL_PATH
    sheet_name = DEFAULT_SHEET_NAME
st.sidebar.markdown(f"Using default CSV file: `{DEFAULT_CSV_PATH}`")
st.sidebar.markdown("---")

# =========================
# 데이터 로드
# =========================
# CSV 파일 읽기
data = pd.read_csv(csv_data, sep=',', encoding='utf-8')

# Excel 파일 읽기 (첫 시트 or 지정된 시트)
xls = pd.ExcelFile(DEFAULT_EXCEL_PATH, engine="openpyxl")
group_data = xls.parse(sheet_name=sheet_name)

# =========================
# 데이터 병합
# =========================
# 공통 컬럼 "Display name" 기준으로 merge
merged_data = pd.merge(
    data,
    group_data,
    on="Display Name",      # 공통 키
    how="left"              # left join → CSV 기준으로 Excel 데이터 붙임
)

# =========================
# 데이터 표시
# =========================
st.header("1. Data Overview")
st.subheader("1.1 Email Data")  
st.write(data)

st.subheader("1.2 Group Data")
st.write(group_data)

st.subheader("1.3 Merged Data (CSV + Excel)")
st.write(merged_data)

st.markdown("---")

