import streamlit as st
import pandas as pd
import pydeck as pdk

# Géocodage
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter

st.set_page_config(page_title="RILSA map", layout="wide")
st.title("RILSA map")

uploaded_file = st.file_uploader("Téléversez un fichier Excel (.xlsx)", type=["xlsx"])

df = None

if uploaded_file is not None:
    try:
        # Charger Excel
        xls = pd.ExcelFile(uploaded_file, engine="openpyxl")
        sheet = st.selectbox("Choisissez une feuille", xls.sheet_names, index=0)

        df = pd.read_excel(xls, sheet_name=sheet, engine="openpyxl", skiprows=4)

        # ✅ Supprimer les lignes avec Gérant = "REM4you (Support User)"
        if "Gérant" in df.columns:
            df = df[df["Gérant"] != "REM4you (Support User) "].reset_index(drop=True)
            mask = pd.Series(True, index=df.index)   # df와 같은 인덱스로 생성

        # Conversion de "Référence" et ajout "Type"
        if "Référence" in df.columns:
            df["Référence"] = pd.to_numeric(
                df["Référence"].astype(str).str.replace(r"[^\d]", "", regex=True),
                errors="coerce"
            )

            def classify_type(ref):
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

            df["Type"] = df["Référence"].apply(classify_type)

        # ✅ Nouveau: créer la colonne "Gérant group"
        def compute_gerant_group(name):
            if pd.isna(name):
                return None
            n = str(name).strip()
            if n in {"NIGGLI Lucy", "BENISTANT Audrey"}:
                return "Nyon"
            if n in {"CURCHOD Merry", "DE PREUX Joanna"}:
                return "Montreux"
            return n  # les autres gardent la valeur d'origine

        if "Gérant" in df.columns:
            df["Gérant group"] = df["Gérant"].apply(compute_gerant_group)
        else:
            st.warning("⚠️ Colonne 'Gérant' introuvable — impossible de créer 'Gérant group'.")

        st.success(f"Fichier chargé : {uploaded_file.name} / Feuille : {sheet}")

        # -------------------- Filtres --------------------
        st.sidebar.header("Filtres")

        # On garde les filtres existants
        gerant_selected = None
        if "Gérant" in df.columns:
            gerant_options = sorted(df["Gérant"].dropna().unique().tolist())
            gerant_selected = st.sidebar.multiselect("Gérant", options=gerant_options, default=gerant_options)

        type_selected = None
        if "Type" in df.columns:
            type_options = sorted(df["Type"].dropna().unique().tolist())
            type_selected = st.sidebar.multiselect("Type", options=type_options, default=type_options)

        mask = pd.Series([True] * len(df))
        if gerant_selected is not None:
            mask &= df["Gérant"].isin(gerant_selected)
        if type_selected is not None:
            mask &= df["Type"].isin(type_selected)
        
        df_filtered = df[mask].copy()

        st.subheader("Tableau filtré")
        st.dataframe(df_filtered, use_container_width=True)

        # -------------------- Adresse & Géocodage (optimisé) --------------------
        required_cols = ["Désignation", "NPA", "Lieu", "Canton"]
        missing = [c for c in required_cols if c not in df_filtered.columns]
        if missing or df_filtered.empty:
            if missing:
                st.error(f"Colonnes manquantes pour construire l'adresse : {', '.join(missing)}")
            else:
                st.info("Aucune ligne après filtrage.")
        else:
            df_filtered["adresse"] = (
                df_filtered["Désignation"].astype(str).str.strip() + ", " +
                df_filtered["NPA"].astype(str).str.strip() + " " +
                df_filtered["Lieu"].astype(str).str.strip() + ", " +
                df_filtered["Canton"].astype(str).str.strip() + ", Suisse"
            )

            # 1) 먼저 좌표 있는 행만 즉시 지도 표시
            has_latlon = ("latitude" in df_filtered.columns) and ("longitude" in df_filtered.columns)
            plotted_now = df_filtered.dropna(subset=["latitude","longitude"]).copy() if has_latlon else pd.DataFrame()

            # 컬러 맵 준비 (Gérant group 우선)
            palette = [
                [230,25,75],[60,180,75],[0,130,200],[245,130,48],[145,30,180],
                [70,240,240],[240,50,230],[210,245,60],[250,190,190],[170,110,40]
            ]
            def apply_colors(df_points, key):
                if key in df_points.columns:
                    keys = sorted(df_points[key].astype(str).unique().tolist())
                    cmap = {k: palette[i % len(palette)] for i,k in enumerate(keys)}
                    df_points["color"] = df_points[key].astype(str).map(cmap)
                    return keys, cmap
                df_points["color"] = [[0,0,200]] * len(df_points)
                return [], {}

            color_key = "Gérant group" if "Gérant group" in df_filtered.columns else ("Gérant" if "Gérant" in df_filtered.columns else None)
            if not plotted_now.empty:
                keys, cmap = apply_colors(plotted_now, color_key) if color_key else ([], {})
                view_state = pdk.ViewState(
                    latitude=float(plotted_now["latitude"].mean()) if not plotted_now["latitude"].empty else 46.8182,
                    longitude=float(plotted_now["longitude"].mean()) if not plotted_now["longitude"].empty else 8.2275,
                    zoom=9
                )
                layer = pdk.Layer(
                    "ScatterplotLayer",
                    data=plotted_now[["longitude","latitude","adresse","Type","Gérant","Gérant group","color"] if "Gérant group" in df_filtered.columns else ["longitude","latitude","adresse","Type","Gérant","color"]],
                    get_position='[longitude, latitude]',
                    get_fill_color="color",
                    get_radius=60,
                    pickable=True,
                )
                st.markdown("### Carte (coordonnées existantes)")
                st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state,
                                        tooltip={"text": "{Gérant group}\n{Gérant}\n{Type}\n{adresse}"}))

            # 2) 결측 좌표만 버튼으로 지오코딩 (Nominatim 느림 → 배치 제한)
            #    캐시 + 파일 저장(영구)로 다음 실행 가속
            geolocator = Nominatim(user_agent="rilsa_map_app", timeout=10)
            rate_limited_geocode = RateLimiter(geolocator.geocode, min_delay_seconds=3, max_retries=2, swallow_exceptions=True)

            import hashlib, json, os, pathlib
            CACHE_DIR = pathlib.Path("./.geo_cache")
            CACHE_DIR.mkdir(exist_ok=True)
            file_sig = hashlib.md5(f"{uploaded_file.name}|{sheet}".encode("utf-8")).hexdigest()
            cache_path = CACHE_DIR / f"geocode_cache_{file_sig}.json"

            # 디스크 캐시 로드
            if cache_path.exists():
                with open(cache_path, "r", encoding="utf-8") as f:
                    disk_cache = json.load(f)
            else:
                disk_cache = {}

            # 이미 캐시/좌표 있는 행 제외하고 주소 목록 구성
            need_geo_df = df_filtered.copy()
            if has_latlon:
                need_geo_df = need_geo_df[need_geo_df["latitude"].isna() | need_geo_df["longitude"].isna()].copy()
            to_geocode_all = [a for a in need_geo_df["adresse"].dropna().unique().tolist() if a not in disk_cache]

            st.subheader("Géocodage des adresses manquantes (Nominatim)")
            limit = st.slider("Limite de géocodage pour cette exécution", 10, 500, 100, 10)
            to_geocode = to_geocode_all[:limit]

            col1, col2 = st.columns(2)
            with col1:
                st.write(f"Adresses à géocoder (hors cache) : **{len(to_geocode_all)}**")
            with col2:
                start_geo = st.button("🚀 Lancer le géocodage (lot limité)")

            @st.cache_data(show_spinner=False)
            def geocode_batch(addresses: tuple):
                # cache_data는 메모리 캐시(세션용). 디스크 캐시는 별도로 관리.
                out = {}
                progress = st.progress(0)
                total = len(addresses)
                for i, addr in enumerate(addresses, start=1):
                    loc = rate_limited_geocode(addr)
                    if loc:
                        out[addr] = (loc.latitude, loc.longitude)
                    else:
                        out[addr] = (None, None)
                    progress.progress(i/total)
                return out

            if start_geo and to_geocode:
                new_mapping = geocode_batch(tuple(to_geocode))
                # 디스크 캐시 병합/저장
                disk_cache.update({k: v for k, v in new_mapping.items() if k})
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(disk_cache, f, ensure_ascii=False)

            # 캐시(메모리+디스크) 모아서 좌표 주입
            def get_coords(addr):
                if addr in disk_cache:
                    return disk_cache[addr]
                return (None, None)

            df_filtered["latitude"]  = df_filtered.get("latitude")
            df_filtered["longitude"] = df_filtered.get("longitude")
            coords_series = df_filtered["adresse"].map(get_coords)
            df_filtered.loc[df_filtered["latitude"].isna(),  "latitude"]  = coords_series.map(lambda x: x[0])
            df_filtered.loc[df_filtered["longitude"].isna(), "longitude"] = coords_series.map(lambda x: x[1])

            plotted_final = df_filtered.dropna(subset=["latitude","longitude"]).copy()

            st.markdown("### Carte (mise à jour après géocodage)")
            if not plotted_final.empty:
                keys, cmap = apply_colors(plotted_final, color_key) if color_key else ([], {})
                view_state2 = pdk.ViewState(
                    latitude=float(plotted_final["latitude"].mean()),
                    longitude=float(plotted_final["longitude"].mean()),
                    zoom=9
                )
                layer2 = pdk.Layer(
                    "ScatterplotLayer",
                    data=plotted_final[["longitude","latitude","adresse","Type","Gérant","Gérant group","color"] if "Gérant group" in df_filtered.columns else ["longitude","latitude","adresse","Type","Gérant","color"]],
                    get_position='[longitude, latitude]',
                    get_fill_color="color",
                    get_radius=60,
                    pickable=True,
                )
                st.pydeck_chart(pdk.Deck(layers=[layer2], initial_view_state=view_state2,
                                        tooltip={"text": "{Gérant group}\n{Gérant}\n{Type}\n{adresse}"}))
            else:
                st.info("Coordonnées encore insuffisantes. 다음 배치로 추가 지오코딩 하세요.")
