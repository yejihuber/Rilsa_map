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

        st.success(f"Fichier chargé : {uploaded_file.name} / Feuille : {sheet}")

        # -------------------- Filtres --------------------
        st.sidebar.header("Filtres")

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

        # -------------------- Adresse & Géocodage --------------------
        required_cols = ["Désignation", "NPA", "Lieu", "Canton"]
        missing = [c for c in required_cols if c not in df_filtered.columns]
        if not missing and not df_filtered.empty:
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

            st.markdown("### Carte (points colorés par Gérant)")
            if not plotted.empty:
                # Palette fixe de couleurs (R, G, B)
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

                if "Gérant" in plotted.columns:
                    unique_gerants = sorted(plotted["Gérant"].unique().tolist())
                    color_map = {g: palette[i % len(palette)] for i, g in enumerate(unique_gerants)}
                    plotted["color"] = plotted["Gérant"].map(color_map)
                else:
                    plotted["color"] = [[0, 0, 200]] * len(plotted)

                # Pydeck Layer
                layer = pdk.Layer(
                    "ScatterplotLayer",
                    data=plotted,
                    get_position='[longitude, latitude]',
                    get_fill_color="color",
                    get_radius=70,
                    pickable=True,
                )

                view_state = pdk.ViewState(
                    latitude=plotted["latitude"].mean(),
                    longitude=plotted["longitude"].mean(),
                    zoom=9
                )

                st.pydeck_chart(
                    pdk.Deck(
                        layers=[layer],
                        initial_view_state=view_state,
                        tooltip={"text": "{Gérant}\n{Type}\n{adresse}"}
                    )
                )
            else:
                st.info("Aucun point géocodé valide à afficher.")

    except Exception as e:
        st.error(f"Erreur : {e}")
