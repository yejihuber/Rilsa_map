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
# data treatment
# =========================
# CSV 파일 읽기
data = pd.read_csv(csv_data, sep=',', encoding='utf-8')

# Excel 파일 읽기
excel_df = pd.read_excel(excel_data, sheet_name=sheet_name)

# to data frame
df_excel = pd.DataFrame(excel_df)
df_csv = pd.DataFrame(data)
# merge two data frame on 'Display Name'
df_merged = pd.merge(df_csv, df_excel, left_on='Display Name', right_on='Display Name', how='left')

# =========================
# 메인 페이지 - 데이터 표시
# =========================
st.header("2. Data Overview")
st.write("DataFrame from CSV file:")
st.dataframe(df_csv)
st.write("DataFrame from Excel file:")
st.dataframe(df_excel)
st.write("Merged DataFrame:")
st.dataframe(df_merged)