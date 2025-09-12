from csv import excel
import io
from unittest.mock import DEFAULT
import numpy as np
import pandas as pd
import streamlit as st
import pydeck as pdk
import altair as alt

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
# CSV
data = pd.read_csv(csv_data, sep=',', encoding='utf-8')

# Excel (첫 시트 선택 로직 포함)
xls = pd.ExcelFile(DEFAULT_EXCEL_PATH, engine="openpyxl")
if sheet_name is None:
    sheet_to_use = xls.sheet_names[0]   # 첫 시트
else:
    sheet_to_use = sheet_name

group_data = xls.parse(sheet_name=sheet_to_use)

# =========================
# 병합 전 정규화 (공백/대소문자)
# =========================
def _norm_key(series):
    return series.astype(str).str.strip().str.casefold()

# 컬럼 존재 확인 (없으면 명확한 에러 메시지)
if "Display Name" not in data.columns:
    raise KeyError("CSV에 'Display Name' 컬럼이 없습니다.")
if "Display Name" not in group_data.columns:
    raise KeyError(f"Excel 시트('{sheet_to_use}')에 'Display Name' 컬럼이 없습니다.")

data["_key"] = _norm_key(data["Display Name"])
group_data["_key"] = _norm_key(group_data["Display Name"])

# 그룹 데이터에서 중복 키 제거(있다면 첫 번째만 사용)
group_data = group_data.drop_duplicates(subset=["_key"], keep="first")

# =========================
# 병합
# =========================
merged_data = pd.merge(
    data,
    group_data,
    on="_key",
    how="left",
    suffixes=("_csv", "_xlsx")
).drop(columns=["_key"])

# =========================
# 병합 후 불필요한 데이터 제거
# =========================
if "Group" in merged_data.columns:
    merged_data = merged_data[
        merged_data["Group"].notna() & (merged_data["Group"] != "Compta")
    ]
else:
    st.warning("no 'Group' on the Excel file.")

# =========================
# 1. Personne별 차트 (envoyé / reçu)
# =========================
st.header("1. Charge e-mails par personne")

bar_data = (
    merged_data
    .groupby('Display Name_csv', as_index=False)
    .agg(envoyé=('Send Count', 'sum'),
         reçu=('Receive Count', 'sum'))
    .fillna({'envoyé': 0, 'reçu': 0})
)

# 사람 선택
all_names = bar_data['Display Name_csv'].unique().tolist()
selected_names = st.multiselect(
    "Choisissez les personnes à afficher :",
    options=all_names,
    default=all_names[:10]
)
if selected_names:
    bar_data = bar_data[bar_data['Display Name_csv'].isin(selected_names)]

bar_data_long = bar_data.melt(
    id_vars='Display Name_csv',
    value_vars=['envoyé', 'reçu'],
    var_name='Type',
    value_name='Nombre'
)

chart = (
    alt.Chart(bar_data_long)
    .mark_bar()
    .encode(
        x=alt.X('Display Name_csv:N', sort='-y', title='Personne'),
        y=alt.Y('Nombre:Q', title="Nombre d'e-mails"),
        color=alt.Color('Type:N', title='Type'),
        xOffset='Type',
        tooltip=['Display Name_csv', 'Type', 'Nombre']
    )
    .properties(width=800, height=500)
)

st.altair_chart(chart, use_container_width=True)


# =========================
# 2. Groupe별 차트 (envoyé / reçu)
# =========================
st.header("2. Charge e-mails par groupe")

if "Group" in merged_data.columns:
    group_bar = (
        merged_data
        .groupby('Group', as_index=False)
        .agg(envoyé=('Send Count', 'sum'),
             reçu=('Receive Count', 'sum'))
        .fillna({'envoyé': 0, 'reçu': 0})
    )

    all_groups = group_bar['Group'].unique().tolist()
    selected_groups = st.multiselect(
        "Choisissez les groupes à afficher :",
        options=all_groups,
        default=all_groups
    )
    if selected_groups:
        group_bar = group_bar[group_bar['Group'].isin(selected_groups)]

    group_bar_long = group_bar.melt(
        id_vars='Group',
        value_vars=['envoyé', 'reçu'],
        var_name='Type',
        value_name='Nombre'
    )

    chart_group = (
        alt.Chart(group_bar_long)
        .mark_bar()
        .encode(
            x=alt.X('Group:N', sort='-y', title='Groupe'),
            y=alt.Y('Nombre:Q', title="Nombre d'e-mails"),
            color=alt.Color('Type:N', title='Type'),
            xOffset='Type',
            tooltip=['Group', 'Type', 'Nombre']
        )
        .properties(width=800, height=500)
    )

    st.altair_chart(chart_group, use_container_width=True)
else:
    st.warning("no 'Group' on the Excel file.")
