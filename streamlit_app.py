import io
import numpy as np
import pandas as pd
import requests
import streamlit as st
import pydeck as pdk

# =========================
# 기본 데이터 경로(원하는 경로로 바꿔도 됨)
# =========================
DEFAULT_XLSX_PATH = "KPI_-_Repartition_portefeuille-20250716.xlsx"        # 기본 엑셀
DEFAULT_COORDS_CSV_PATH = "rilsa_coords.csv" # 기본 좌표 CSV
DEFAULT_SHEET_NAME = None  # None이면 첫 시트

st.set_page_config(page_title="RILSA map", layout="wide")
st.title("RILSA map")

# =========================
# Tooltip HTML (Nom : Valeur)
# =========================
TOOLTIP_HTML = """
<div style="font-family: ui-sans-serif,system-ui; font-size:12px; line-height:1.25;">
  <div><b>Gérant :</b> {Gérant}</div>
  <div><b>Gérant group :</b> {Gérant group}</div>
  <div><b>Type :</b> {Type}</div>
  <div><b>Adresse :</b> {adresse}</div>
  <div><b>Nombre total d'appartements :</b> {Nombre total d'appartements}</div>
  <div><b>Nombre total d'entreprises :</b> {Nombre total d'entreprises}</div>
  <div><b>Propriétaire :</b> {Propriétaire}</div>
</div>
"""

# =========================
# 레전드(표) 렌더러
# =========================
def render_table_legend(keys, cmap, title="Légende", cols_per_row=4):
    if not keys:
        return
    st.markdown(f"#### {title} (tableau)")
    cols = st.columns(min(cols_per_row, max(1, len(keys))))
    for i, k in enumerate(keys):
        with cols[i % len(cols)]:
            st.markdown(
                f'''
                <div style="display:flex;align-items:center;gap:8px;margin:6px 0;">
                    <span style="width:14px;height:14px;display:inline-block;border-radius:3px;
                                 border:1px solid #0003;background:rgb({cmap[k][0]},{cmap[k][1]},{cmap[k][2]},{cmap[k][3] if len(cmap[k])>3 else 255});"></span>
                    <span style="font-size:13px">{k}</span>
                </div>
                ''',
                unsafe_allow_html=True
            )

# =========================
# 멀티셀렉트 내부에 "Tout" 옵션 내장
# =========================
def multiselect_with_select_all(label: str, options: list, key: str):
    ALL = "Tout"
    opts = [ALL] + options
    selected_real = st.session_state.get(key, options)  # 초기엔 전체 선택
    default_widget = [ALL] + options if set(selected_real) == set(options) else selected_real
    sel = st.multiselect(label, options=opts, default=default_widget, key=f"{key}__widget")
    chosen = options if ALL in sel else [x for x in sel if x != ALL]
    st.session_state[key] = chosen
    return chosen

# =========================
# 색상 팔레트 + 색상 적용(반투명)
# =========================
PALETTE = [
    [230, 25, 75], [60, 180, 75], [0, 130, 200], [245, 130, 48], [145, 30, 180],
    [70, 240, 240], [240, 50, 230], [210, 245, 60], [250, 190, 190], [170, 110, 40],
]

def assign_colors(df_points, color_key, palette=PALETTE, alpha=120):
    if (not color_key) or (color_key not in df_points.columns):
        df_points["color"] = [[0, 0, 200, alpha]] * len(df_points)
        return [], {}
    keys = sorted(df_points[color_key].astype(str).unique().tolist())
    cmap = {k: palette[i % len(palette)] + [alpha] for i, k in enumerate(keys)}
    df_points["color"] = df_points[color_key].astype(str).map(cmap)
    return keys, cmap

# =========================
# 분류/그룹 유틸
# =========================
def classify_type_from_ref(ref):
    if pd.isna(ref):
        return "Inconnu"
    ref = int(ref)
    if 100000 <= ref <= 499000:
        return "Immeuble"
    elif 500000 <= ref <= 599000:
        return "Lot isolé"
    elif 800000 <= ref <= 950000:
        return "PPE"
    else:
        return "Autre"

def compute_gerant_group(name):
    if pd.isna(name):
        return None
    n = str(name).strip()
    if n in {"NIGGLI Lucy", "BENISTANT Audrey"}:
        return "Nyon"
    if n in {"CURCHOD Merry", "DE PREUX Joanna"}:
        return "Montreux"
    return n

def safe_mean(series, default):
    try:
        v = float(series.mean())
        return v if not np.isnan(v) else default
    except:
        return default

# =========================
# Google Geocoding
# =========================
def gmaps_geocode_one(address: str, key: str):
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": key, "region": "ch", "language": "fr"}
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if data.get("status") == "OK" and data.get("results"):
            loc = data["results"][0]["geometry"]["location"]
            return (loc["lat"], loc["lng"])
        else:
            return (None, None)
    except Exception:
        return (None, None)

@st.cache_data(show_spinner=False)
def gmaps_geocode_batch(addresses: tuple, key: str):
    out = {}
    progress = st.progress(0)
    total = len(addresses)
    for i, addr in enumerate(addresses, start=1):
        out[addr] = gmaps_geocode_one(addr, key)
        progress.progress(i/total)
    return out

# =========================
# 업로드 / 기본 데이터 선택
# =========================
uploaded_file = st.file_uploader("Téléversez un fichier Excel (.xlsx)", type=["xlsx"])
use_default = st.sidebar.toggle(
    "Utiliser les données par défaut (Excel + CSV lat/lon)",
    value=(uploaded_file is None)
)

# =========================
# 데이터 로딩 (업로드 또는 기본)
# =========================
df = None
source_desc = ""
try:
    if not use_default and uploaded_file is not None:
        xls = pd.ExcelFile(uploaded_file, engine="openpyxl")
        sheet = st.selectbox("Choisissez une feuille", xls.sheet_names, index=0)
        df = pd.read_excel(xls, sheet_name=sheet, engine="openpyxl", skiprows=4)
        source_desc = f"Fichier chargé : {uploaded_file.name} / Feuille : {sheet}"
    else:
        xls = pd.ExcelFile(DEFAULT_XLSX_PATH, engine="openpyxl")
        sheet_names = xls.sheet_names
        sheet = DEFAULT_SHEET_NAME if (DEFAULT_SHEET_NAME in sheet_names) else sheet_names[0]
        df = pd.read_excel(xls, sheet_name=sheet, engine="openpyxl", skiprows=4)
        source_desc = f"Données par défaut : {DEFAULT_XLSX_PATH} / Feuille : {sheet}"
except Exception as e:
    st.error(f"Impossible de charger le fichier Excel: {e}")
    st.stop()

# =========================
# 전처리
# =========================
# 1) Support User 제거
if "Gérant" in df.columns:
    df["Gérant"] = df["Gérant"].astype(str)
    df = df[df["Gérant"].str.strip() != "REM4you (Support User)"].reset_index(drop=True)

# 2) Référence → Type
if "Référence" in df.columns:
    df["Référence"] = pd.to_numeric(df["Référence"].astype(str).str.replace(r"[^\d]", "", regex=True), errors="coerce")
    df["Type"] = df["Référence"].apply(classify_type_from_ref)
else:
    st.warning("⚠️ Colonne 'Référence' absente : 'Type' ne sera pas créé.")

# 3) Gérant group
if "Gérant" in df.columns:
    df["Gérant group"] = df["Gérant"].apply(compute_gerant_group)
else:
    st.warning("⚠️ Colonne 'Gérant' introuvable — impossible de créer 'Gérant group'.")

st.success(source_desc)

# =========================
# 필터
# =========================
st.sidebar.header("Filtres")
with st.sidebar:
    if "Gérant" in df.columns:
        gerant_opts = sorted(df["Gérant"].dropna().astype(str).unique().tolist())
        gerant_sel = multiselect_with_select_all("Gérant", gerant_opts, key="gerant")
    else:
        gerant_sel = None
        st.info("Colonne 'Gérant' introuvable — filtre désactivé.")

    if "Type" in df.columns:
        type_opts = sorted(df["Type"].dropna().astype(str).unique().tolist())
        type_sel = multiselect_with_select_all("Type", type_opts, key="type")
    else:
        type_sel = None
        st.info("Colonne 'Type' introuvable — filtre désactivé.")

# 필터 적용
df_filtered = df.copy()
if gerant_sel is not None:
    df_filtered = df_filtered[df_filtered["Gérant"].astype(str).isin(gerant_sel)]
if type_sel is not None and "Type" in df_filtered.columns:
    df_filtered = df_filtered[df_filtered["Type"].astype(str).isin(type_sel)]

#st.subheader("Tableau filtré")
#st.dataframe(df_filtered, use_container_width=True)

# =========================
# 주소 생성
# =========================
required_cols = ["Désignation", "NPA", "Lieu", "Canton"]
missing = [c for c in required_cols if c not in df_filtered.columns]
if missing:
    st.error(f"Colonnes manquantes pour construire l'adresse : {', '.join(missing)}")
    st.stop()
if df_filtered.empty:
    st.info("Aucune ligne après filtrage.")
    st.stop()

df_filtered["adresse"] = (
    df_filtered["Désignation"].astype(str).str.strip() + ", " +
    df_filtered["NPA"].astype(str).str.strip() + " " +
    df_filtered["Lieu"].astype(str).str.strip() + ", " +
    df_filtered["Canton"].astype(str).str.strip() + ", Suisse"
)

# 좌표 컬럼 보장
if "latitude" not in df_filtered.columns:
    df_filtered["latitude"] = np.nan
if "longitude" not in df_filtered.columns:
    df_filtered["longitude"] = np.nan

# =========================
# 기본 좌표 CSV 자동 병합
# =========================
try:
    default_coords = pd.read_csv(DEFAULT_COORDS_CSV_PATH)
    merged = False
    if {"adresse","latitude","longitude"}.issubset(default_coords.columns):
        df_filtered = df_filtered.merge(
            default_coords[["adresse","latitude","longitude"]],
            on="adresse", how="left", suffixes=("", "_def")
        )
        if "latitude_def" in df_filtered.columns and "longitude_def" in df_filtered.columns:
            df_filtered["latitude"]  = df_filtered["latitude"].fillna(df_filtered["latitude_def"])
            df_filtered["longitude"] = df_filtered["longitude"].fillna(df_filtered["longitude_def"])
            df_filtered.drop(columns=["latitude_def","longitude_def"], inplace=True)
        merged = True
    if (not merged) and {"Référence","latitude","longitude"}.issubset(default_coords.columns) and "Référence" in df_filtered.columns:
        df_filtered = df_filtered.merge(
            default_coords[["Référence","latitude","longitude"]],
            on="Référence", how="left", suffixes=("", "_def")
        )
        if "latitude_def" in df_filtered.columns and "longitude_def" in df_filtered.columns:
            df_filtered["latitude"]  = df_filtered["latitude"].fillna(df_filtered["latitude_def"])
            df_filtered["longitude"] = df_filtered["longitude"].fillna(df_filtered["longitude_def"])
            df_filtered.drop(columns=["latitude_def","longitude_def"], inplace=True)
        merged = True
    if merged:
        st.success("Coordonnées par défaut appliquées.")
except FileNotFoundError:
    st.warning(f"CSV lat/lon par défaut introuvable: {DEFAULT_COORDS_CSV_PATH}")
except Exception as e:
    st.warning(f"Impossible de fusionner le CSV par défaut: {e}")

# =========================
# (옵션) 좌표 CSV 업로드로 추가 재사용
# =========================
st.sidebar.markdown("### Recharger des coordonnées (CSV)")
coords_file = st.sidebar.file_uploader(
    "CSV avec 'adresse,latitude,longitude' ou 'Référence,latitude,longitude'",
    type=["csv"], key="coords_csv"
)
if coords_file is not None:
    try:
        coords_df = pd.read_csv(coords_file)
        merged = False
        if {"adresse","latitude","longitude"}.issubset(coords_df.columns):
            df_filtered = df_filtered.merge(
                coords_df[["adresse","latitude","longitude"]],
                on="adresse", how="left", suffixes=("", "_cache")
            )
            if "latitude_cache" in df_filtered.columns and "longitude_cache" in df_filtered.columns:
                df_filtered["latitude"]  = df_filtered["latitude"].fillna(df_filtered["latitude_cache"])
                df_filtered["longitude"] = df_filtered["longitude"].fillna(df_filtered["longitude_cache"])
                df_filtered.drop(columns=["latitude_cache","longitude_cache"], inplace=True)
            merged = True
        if (not merged) and {"Référence","latitude","longitude"}.issubset(coords_df.columns) and "Référence" in df_filtered.columns:
            df_filtered = df_filtered.merge(
                coords_df[["Référence","latitude","longitude"]],
                on="Référence", how="left", suffixes=("", "_cache")
            )
            if "latitude_cache" in df_filtered.columns and "longitude_cache" in df_filtered.columns:
                df_filtered["latitude"]  = df_filtered["latitude"].fillna(df_filtered["latitude_cache"])
                df_filtered["longitude"] = df_filtered["longitude"].fillna(df_filtered["longitude_cache"])
                df_filtered.drop(columns=["latitude_cache","longitude_cache"], inplace=True)
            merged = True
        if merged:
            st.success("Coordonnées rechargées depuis le CSV (upload).")
    except Exception as e:
        st.sidebar.error(f"Erreur CSV coords: {e}")

# =========================
# Google 지오코딩 (결측만)
# =========================
st.subheader("Géocodage Google Maps (compléter les manquants)")
limit = st.slider("Limiter le nombre d'adresses à géocoder maintenant", 10, 1000, 200, 10)

need_geo = df_filtered[
    df_filtered["adresse"].notna() &
    (
        ("latitude" not in df_filtered.columns) |
        ("longitude" not in df_filtered.columns) |
        df_filtered["latitude"].isna() | df_filtered["longitude"].isna()
    )
].copy()

to_geocode = need_geo["adresse"].dropna().unique().tolist()[:limit]

col1, col2 = st.columns(2)
with col1:
    st.write(f"Adresses sans coordonnées (sélection) : **{len(to_geocode)}**")
with col2:
    start_geo = st.button("🚀 Lancer le géocodage Google")

if start_geo:
    if not api_key:
        st.error("Veuillez saisir votre **Google Maps API Key**.")
        st.stop()
    mapping = gmaps_geocode_batch(tuple(to_geocode), api_key)
    mask_map = df_filtered["adresse"].isin(mapping.keys())
    df_filtered.loc[mask_map, "latitude"]  = df_filtered.loc[mask_map, "adresse"].map(lambda a: mapping.get(a,(None,None))[0])
    df_filtered.loc[mask_map, "longitude"] = df_filtered.loc[mask_map, "adresse"].map(lambda a: mapping.get(a,(None,None))[1])
    st.success("Géocodage Google terminé pour le lot courant.")

# =========================
# 최종 지도 + 레전드 + CSV 다운로드
# =========================
plotted_final = df_filtered.dropna(subset=["latitude","longitude"]).copy()
st.markdown("### Carte (mise à jour)")
if not plotted_final.empty:
    color_key = "Gérant group" if "Gérant group" in plotted_final.columns else ("Gérant" if "Gérant" in plotted_final.columns else None)
    keys_final, cmap_final = assign_colors(plotted_final, color_key)

    # 툴팁 필드 보정
    for c in ["Gérant","Gérant group","Type","adresse","Nombre total d'appartements","Nombre total d'entreprises","Propriétaire"]:
        if c not in plotted_final.columns:
            plotted_final[c] = ""

    view_state2 = pdk.ViewState(
        latitude=safe_mean(plotted_final["latitude"], 46.8182),
        longitude=safe_mean(plotted_final["longitude"], 8.2275),
        zoom=9
    )
    layer2 = pdk.Layer(
        "ScatterplotLayer",
        data=plotted_final,
        get_position='[longitude, latitude]',
        get_fill_color="color",
        get_radius=200,      # 점 크기 — 필요시 조절
        pickable=True,
    )
    st.pydeck_chart(pdk.Deck(
        layers=[layer2],
        initial_view_state=view_state2,
        tooltip={"html": TOOLTIP_HTML, "style": {"backgroundColor":"rgba(255,255,255,0.95)", "color":"black"}}
    ))

    legend_title_final = color_key if color_key else "Catégorie"
    render_table_legend(keys_final, cmap_final, f"Légende — {legend_title_final}", cols_per_row=4)

    # 좌표 CSV 다운로드
    st.markdown("### Télécharger les coordonnées")
    save_cols = [c for c in [
        "Référence","Gérant","Gérant group","Type",
        "Désignation","NPA","Lieu","Canton",
        "adresse","latitude","longitude",
        "Nombre total d'appartements","Nombre total d'entreprises","Propriétaire"
    ] if c in plotted_final.columns]
    export_df = plotted_final[save_cols].copy()
    st.download_button(
        label="⬇️ Télécharger CSV (lat/lon inclus)",
        data=export_df.to_csv(index=False).encode("utf-8"),
        file_name="rilsa_coords.csv",
        mime="text/csv"
    )
else:
    st.info("Aucun point avec coordonnées pour l’instant. Lancez le géocodage Google ou vérifiez vos filtres.")

# =========================
# API Key
# =========================
api_key = st.secrets.get("GOOGLE_MAPS_API_KEY", None)
if not api_key:
    api_key = st.text_input("Entrez votre Google Maps API Key", type="password")
