import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk

# Geo
import geopandas as gpd
from shapely.geometry import Point

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

        # --- "Référence" -> numérique + "Type" ---
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
        else:
            st.warning("⚠️ Colonne 'Référence' absente : 'Type' ne sera pas créé.")

        st.success(f"Fichier chargé : {uploaded_file.name} / Feuille : {sheet}")

        # -------------------- Filtres --------------------
        st.sidebar.header("Filtres")

        if "Gérant" in df.columns:
            gerant_options = sorted(df["Gérant"].dropna().astype(str).unique().tolist())
            gerant_selected = st.sidebar.multiselect("Gérant", options=gerant_options, default=gerant_options)
        else:
            gerant_selected = None
            st.sidebar.info("Colonne 'Gérant' introuvable — filtre désactivé.")

        if "Type" in df.columns:
            type_options = sorted(df["Type"].dropna().astype(str).unique().tolist())
            type_selected = st.sidebar.multiselect("Type", options=type_options, default=type_options)
        else:
            type_selected = None
            st.sidebar.info("Colonne 'Type' introuvable — filtre désactivé.")

        mask = pd.Series(True, index=df.index)
        if gerant_selected is not None:
            mask &= df["Gérant"].astype(str).isin(gerant_selected)
        if type_selected is not None:
            mask &= df["Type"].astype(str).isin(type_selected)

        df_filtered = df[mask].copy()

        st.subheader("Tableau filtré")
        st.dataframe(df_filtered, use_container_width=True)

        # -------------------- Adresse & Géocodage (sur les filtrés) --------------------
        required_cols = ["Désignation", "NPA", "Lieu", "Canton"]
        missing = [c for c in required_cols if c not in df_filtered.columns]

        if missing:
            st.error(f"Colonnes manquantes pour construire l'adresse : {', '.join(missing)}")
        elif df_filtered.empty:
            st.info("Aucune ligne après filtrage.")
        else:
            df_filtered["adresse"] = (
                df_filtered["Désignation"].astype(str).str.strip() + ", " +
                df_filtered["NPA"].astype(str).str.strip() + " " +
                df_filtered["Lieu"].astype(str).str.strip() + ", " +
                df_filtered["Canton"].astype(str).str.strip() + ", Suisse"
            )

            geolocator = Nominatim(user_agent="rilsa_map_app", timeout=10)
            rate_limited_geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1, swallow_exceptions=True)

            @st.cache_data(show_spinner=False)
            def geocode_addresses(unique_addresses):
                results = {}
                for addr in unique_addresses:
                    loc = rate_limited_geocode(addr)
                    if loc:
                        results[addr] = (loc.latitude, loc.longitude)
                    else:
                        results[addr] = (None, None)
                return results

            uniq = df_filtered["adresse"].dropna().unique().tolist()
            mapping = geocode_addresses(tuple(uniq))

            df_filtered["latitude"]  = df_filtered["adresse"].map(lambda a: mapping.get(a, (None, None))[0])
            df_filtered["longitude"] = df_filtered["adresse"].map(lambda a: mapping.get(a, (None, None))[1])

            plotted = df_filtered.dropna(subset=["latitude", "longitude"]).copy()

            st.markdown("### Carte (GeoPandas + GeoJSON, couleurs par Gérant)")
            if not plotted.empty:
                # ---------- GeoPandas : DataFrame -> GeoDataFrame ----------
                gdf = gpd.GeoDataFrame(
                    plotted.copy(),
                    geometry=[Point(xy) for xy in zip(plotted["longitude"], plotted["latitude"])],
                    crs="EPSG:4326"
                )

                # Palette de couleurs fixe (R,G,B)
                palette = [
                    [230, 25, 75],   # rouge
                    [60, 180, 75],   # vert
                    [0, 130, 200],   # bleu
                    [245, 130, 48],  # orange
                    [145, 30, 180],  # violet
                    [70, 240, 240],  # turquoise
                    [240, 50, 230],  # rose
                    [210, 245, 60],  # lime
                    [250, 190, 190], # rose clair
                    [170, 110, 40],  # marron
                ]
                if "Gérant" in gdf.columns:
                    unique_gerants = sorted(gdf["Gérant"].astype(str).unique().tolist())
                    color_map = {g: palette[i % len(palette)] for i, g in enumerate(unique_gerants)}
                    gdf["color"] = gdf["Gérant"].astype(str).map(color_map)
                else:
                    unique_gerants, color_map = [], {}
                    gdf["color"] = [[0, 0, 200]] * len(gdf)

                # ---------- GeoJSON ----------
                geojson_str = gdf.to_json()  # FeatureCollection JSON string

                # ---------- Vue sûre ----------
                def _safe_mean(s, default):
                    try:
                        v = float(s.mean())
                        return v if not np.isnan(v) else default
                    except:
                        return default
                center_lat = _safe_mean(gdf["latitude"], 46.8182)   # Suisse
                center_lon = _safe_mean(gdf["longitude"], 8.2275)

                view_state = pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=9)

                # ---------- Pydeck GeoJsonLayer ----------
                layer = pdk.Layer(
                    "GeoJsonLayer",
                    data=geojson_str,
                    pointType="circle",
                    get_point_radius=70,
                    get_fill_color="properties.color",
                    pickable=True,
                )
                deck = pdk.Deck(
                    layers=[layer],
                    initial_view_state=view_state,
                    tooltip={"text": "{Gérant}\n{Type}\n{adresse}"}
                )
                st.pydeck_chart(deck)

                # Légende
                if unique_gerants:
                    st.markdown("**Légende (Gérant → Couleur)**")
                    for g in unique_gerants:
                        st.write(f"- {g} : rgb{tuple(color_map[g])}")

            else:
                st.info("Aucun point géocodé valide à afficher.")

    except ImportError as e:
        st.error(
            "Modules requis manquants. Ajoutez à `requirements.txt` :\n"
            "streamlit, pandas, openpyxl, geopy, pydeck, geopandas, shapely\n\n"
            f"Détail: {e}"
        )
    except Exception as e:
        st.error(f"Erreur : {e}")

