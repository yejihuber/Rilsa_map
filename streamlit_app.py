import streamlit as st
import pandas as pd
import numpy as np
import requests
import pydeck as pdk
from streamlit.components.v1 import html as st_html

def render_map_legend(keys, cmap, title="Légende"):
    # 디버그: 키가 비면 안내 출력
    if not keys:
        st.info("ℹ️ Légende: aucune catégorie à afficher (liste vide).")
        return

    items = "".join(
        f'''
        <div style="display:flex;align-items:center;gap:8px;margin:2px 0;">
            <span style="width:14px;height:14px;display:inline-block;border-radius:3px;
                         border:1px solid #0003;background:rgb({cmap[k][0]},{cmap[k][1]},{cmap[k][2]});"></span>
            <span style="font-size:13px">{k}</span>
        </div>
        '''
        for k in keys
    )
    html = f'''
    <div style="
        position:fixed; right:16px; top:100px; z-index:99999;
        background:rgba(255,255,255,.95); padding:10px 12px;
        border:1px solid #ddd; border-radius:8px; box-shadow:0 2px 8px rgba(0,0,0,.08);
        max-height:60vh; overflow:auto; font-family:ui-sans-serif,system-ui,-apple-system;">
        <div style="font-weight:600; margin-bottom:6px">{title}</div>
        {items}
    </div>
    '''
    # components.html로 주입하면 pydeck 위에 안정적으로 뜹니다.
    st_html(html, height=0)  # height는 오버레이라 0~1이면 충분



st.set_page_config(page_title="RILSA map", layout="wide")
st.title("RILSA map")

# --- Google API Key: secrets 우선, 없으면 입력받기 ---
api_key = st.secrets.get("GOOGLE_MAPS_API_KEY", None)
if not api_key:
    api_key = st.text_input("Entrez votre Google Maps API Key", type="password")

uploaded_file = st.file_uploader("Téléversez un fichier Excel (.xlsx)", type=["xlsx"])

# -------------------- 유틸 --------------------
def classify_type_from_ref(ref):
    if pd.isna(ref):
        return "Inconnu"
    ref = int(ref)
    if 100000 <= ref <= 499000:
        return "Immeuble"
    elif 500000 <= ref <= 599000:
        return "Lot"
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
    return n  # 나머지는 원래 Gérant 유지

def safe_mean(series, default):
    try:
        v = float(series.mean())
        return v if not np.isnan(v) else default
    except:
        return default

# Google Geocoding 한 건
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

# -------------------- 메인 --------------------
if uploaded_file is not None:
    try:
        # Excel 로드
        xls = pd.ExcelFile(uploaded_file, engine="openpyxl")
        sheet = st.selectbox("Choisissez une feuille", xls.sheet_names, index=0)
        df = pd.read_excel(xls, sheet_name=sheet, engine="openpyxl", skiprows=4)

        # 1) Gérant == "REM4you (Support User)" 제거 (공백 방지)
        if "Gérant" in df.columns:
            df["Gérant"] = df["Gérant"].astype(str)
            df = df[df["Gérant"].str.strip() != "REM4you (Support User)"].reset_index(drop=True)

        # 2) Référence -> 숫자 + Type 생성
        if "Référence" in df.columns:
            df["Référence"] = pd.to_numeric(
                df["Référence"].astype(str).str.replace(r"[^\d]", "", regex=True),
                errors="coerce"
            )
            df["Type"] = df["Référence"].apply(classify_type_from_ref)
        else:
            st.warning("⚠️ Colonne 'Référence' absente : 'Type' ne sera pas créé.")

        # 3) Gérant group 생성
        if "Gérant" in df.columns:
            df["Gérant group"] = df["Gérant"].apply(compute_gerant_group)
        else:
            st.warning("⚠️ Colonne 'Gérant' introuvable — impossible de créer 'Gérant group'.")

        st.success(f"Fichier chargé : {uploaded_file.name} / Feuille : {sheet}")

        # -------------------- Filtres --------------------
        st.sidebar.header("Filtres")

        if "Gérant" in df.columns:
            gerant_opts = sorted(df["Gérant"].dropna().astype(str).unique().tolist())
            gerant_sel = st.sidebar.multiselect("Gérant", gerant_opts, default=gerant_opts)
        else:
            gerant_sel = None
            st.sidebar.info("Colonne 'Gérant' introuvable — filtre désactivé.")

        if "Type" in df.columns:
            type_opts = sorted(df["Type"].dropna().astype(str).unique().tolist())
            type_sel = st.sidebar.multiselect("Type", type_opts, default=type_opts)
        else:
            type_sel = None
            st.sidebar.info("Colonne 'Type' introuvable — filtre désactivé.")

        # 체이닝 필터(인덱스 문제 방지)
        df_filtered = df.copy()
        if gerant_sel is not None:
            df_filtered = df_filtered[df_filtered["Gérant"].astype(str).isin(gerant_sel)]
        if type_sel is not None and "Type" in df_filtered.columns:
            df_filtered = df_filtered[df_filtered["Type"].astype(str).isin(type_sel)]
        
        st.subheader("Tableau filtré")
        st.dataframe(df_filtered, use_container_width=True)

        # -------------------- 주소 만들기 --------------------
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

                # 좌표 컬럼이 없으면 미리 생성
        if "latitude" not in df_filtered.columns:
            df_filtered["latitude"] = np.nan
        if "longitude" not in df_filtered.columns:
            df_filtered["longitude"] = np.nan

        # -------------------- (옵션) 좌표 CSV 업로드로 재사용 --------------------
        st.sidebar.markdown("### Recharger des coordonnées (CSV)")
        coords_file = st.sidebar.file_uploader(
            "CSV avec 'adresse,latitude,longitude' ou 'Référence,latitude,longitude'",
            type=["csv"], key="coords_csv"
        )
        if coords_file is not None:
            try:
                coords_df = pd.read_csv(coords_file)
                merged = False
                # 1순위: adresse 기준
                if {"adresse","latitude","longitude"}.issubset(coords_df.columns):
                    df_filtered = df_filtered.merge(
                        coords_df[["adresse","latitude","longitude"]],
                        on="adresse", how="left", suffixes=("", "_cache")
                    )
                    if "latitude_cache" in df_filtered.columns and "longitude_cache" in df_filtered.columns:
                        df_filtered["latitude"]  = df_filtered.get("latitude")
                        df_filtered["longitude"] = df_filtered.get("longitude")
                        df_filtered["latitude"]  = df_filtered["latitude"].fillna(df_filtered["latitude_cache"])
                        df_filtered["longitude"] = df_filtered["longitude"].fillna(df_filtered["longitude_cache"])
                        df_filtered.drop(columns=[c for c in ["latitude_cache","longitude_cache"] if c in df_filtered.columns], inplace=True)
                    merged = True
                # 2순위: Référence 기준
                if (not merged) and {"Référence","latitude","longitude"}.issubset(coords_df.columns) and "Référence" in df_filtered.columns:
                    df_filtered = df_filtered.merge(
                        coords_df[["Référence","latitude","longitude"]],
                        on="Référence", how="left", suffixes=("", "_cache")
                    )
                    if "latitude_cache" in df_filtered.columns and "longitude_cache" in df_filtered.columns:
                        df_filtered["latitude"]  = df_filtered.get("latitude")
                        df_filtered["longitude"] = df_filtered.get("longitude")
                        df_filtered["latitude"]  = df_filtered["latitude"].fillna(df_filtered["latitude_cache"])
                        df_filtered["longitude"] = df_filtered["longitude"].fillna(df_filtered["longitude_cache"])
                        df_filtered.drop(columns=[c for c in ["latitude_cache","longitude_cache"] if c in df_filtered.columns], inplace=True)
                    merged = True
                if merged:
                    st.success("Coordonnées rechargées depuis le CSV. Les lignes manquantes seulement seront géocodées.")
                else:
                    st.sidebar.warning("CSV에 'adresse,latitude,longitude' 또는 'Référence,latitude,longitude' 컬럼이 필요합니다.")
            except Exception as e:
                st.sidebar.error(f"좌표 CSV 로드 오류: {e}")

        # -------------------- 기존 좌표 즉시 지도 --------------------
        has_coords = ("latitude" in df_filtered.columns) and ("longitude" in df_filtered.columns)
        plotted_now = df_filtered.dropna(subset=["latitude","longitude"]).copy() if has_coords else pd.DataFrame()

        palette = [
            [230, 25, 75], [60, 180, 75], [0, 130, 200], [245, 130, 48], [145, 30, 180],
            [70, 240, 240], [240, 50, 230], [210, 245, 60], [250, 190, 190], [170, 110, 40],
        ]
        color_key = "Gérant group" if "Gérant group" in df_filtered.columns else ("Gérant" if "Gérant" in df_filtered.columns else None)

        def assign_colors(df_points):
            if color_key and color_key in df_points.columns:
                keys = sorted(df_points[color_key].astype(str).unique().tolist())
                cmap = {k: palette[i % len(palette)] for i, k in enumerate(keys)}
                df_points["color"] = df_points[color_key].astype(str).map(cmap)
                return keys, cmap
            else:
                df_points["color"] = [[0,0,200]] * len(df_points)
                return [], {}

        st.markdown("### Carte (coordonnées existantes)")
        if not plotted_now.empty:
            keys_now, cmap_now = assign_colors(plotted_now)
            view_state_now = pdk.ViewState(
                latitude=safe_mean(plotted_now["latitude"], 46.8182),
                longitude=safe_mean(plotted_now["longitude"], 8.2275),
                zoom=9
            )
            layer_now = pdk.Layer(
                "ScatterplotLayer",
                data=plotted_now,
                get_position='[longitude, latitude]',
                get_fill_color="color",
                get_radius=60,
                pickable=True,
            )
            st.pydeck_chart(pdk.Deck(layers=[layer_now], initial_view_state=view_state_now,
                                     tooltip={"text": "{Gérant}\n{adresse}\n{Nombre total d'appartements}\n{Nombre total d'entreprises}\n{Propriétaire}"}))
            
            # 색상 키/맵이 실제로 채워졌는지 확인
            st.write("🔎 Legend debug:", {"count": len(keys_now) if 'keys_now' in locals() else 0})

            legend_title = "Gérant group" if "Gérant group" in plotted_now.columns else "Gérant"
            render_map_legend(keys_now, cmap_now, f"Légende — {legend_title}")

            if keys_now:
                st.markdown("#### Légende (tableau)")
                cols = st.columns(min(4, max(1, len(keys_now))))
                for i, k in enumerate(keys_now):
                    with cols[i % len(cols)]:
                        st.markdown(
                            f'''
                            <div style="display:flex;align-items:center;gap:8px;margin:6px 0;">
                                <span style="width:14px;height:14px;display:inline-block;border-radius:3px;
                                            border:1px solid #0003;background:rgb({cmap_now[k][0]},{cmap_now[k][1]},{cmap_now[k][2]});"></span>
                                <span style="font-size:13px">{k}</span>
                            </div>
                            ''', unsafe_allow_html=True
                        )

        else:
            st.info("Aucune coordonnée existante — utilisez le géocodage pour compléter.")

        # -------------------- Google 지오코딩 (버튼 + 제한) --------------------
        st.subheader("Géocodage Google Maps")
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

            # 좌표 갱신
            df_filtered["latitude"]  = df_filtered.get("latitude")
            df_filtered["longitude"] = df_filtered.get("longitude")
            mask_map = df_filtered["adresse"].isin(mapping.keys())
            df_filtered.loc[mask_map, "latitude"]  = df_filtered.loc[mask_map, "adresse"].map(lambda a: mapping.get(a,(None,None))[0])
            df_filtered.loc[mask_map, "longitude"] = df_filtered.loc[mask_map, "adresse"].map(lambda a: mapping.get(a,(None,None))[1])
            st.success("Géocodage Google terminé pour le lot courant.")

        # -------------------- 지도 최종 표시 + CSV 다운로드 --------------------
        plotted_final = df_filtered.dropna(subset=["latitude","longitude"]).copy()
        st.markdown("### Carte (mise à jour)")
        if not plotted_final.empty:
            keys_final, cmap_final = assign_colors(plotted_final)
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
                get_radius=60,
                pickable=True,
            )
            st.pydeck_chart(pdk.Deck(layers=[layer2], initial_view_state=view_state2,
                                     tooltip={"text": "{Gérant}\n{adresse}\n{Nombre total d'appartements}\n{Nombre total d'entreprises}\n{Propriétaire}"}))

            # 좌표 CSV 다운로드 (다음 실행에서 재사용)
            st.markdown("### Télécharger les coordonnées")
            save_cols = [c for c in [
                "Référence","Gérant","Gérant group","Type",
                "Désignation","NPA","Lieu","Canton",
                "adresse","latitude","longitude"
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

    except Exception as e:
        st.error(f"Erreur : {e}")
