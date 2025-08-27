import streamlit as st
import pandas as pd

# Géocodage
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter

st.set_page_config(page_title="RILSA map", layout="wide")
st.title("RILSA map")

# Autoriser uniquement les fichiers Excel
uploaded_file = st.file_uploader("Téléversez un fichier Excel (.xlsx)", type=["xlsx"])

df = None

if uploaded_file is not None:
    try:
        # Charger la liste des feuilles Excel (openpyxl requis)
        xls = pd.ExcelFile(uploaded_file, engine="openpyxl")
        sheet = st.selectbox("Choisissez une feuille", xls.sheet_names, index=0)

        # Lire le fichier en ignorant les 4 premières lignes
        df = pd.read_excel(
            xls, 
            sheet_name=sheet, 
            engine="openpyxl", 
            skiprows=4
        )

        # --- Créer "Type" à partir de "Référence" (colonne convertie en numérique) ---
        if "Référence" in df.columns:
            df["Référence"] = pd.to_numeric(df["Référence"], errors="coerce")

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
            st.warning("⚠️ La colonne 'Référence' est absente du fichier, impossible de créer 'Type'.")

        st.success(f"Fichier chargé : {uploaded_file.name} / Feuille : {sheet}")

        # -------------------- Filtres (barre latérale) --------------------
        st.sidebar.header("Filtres")

        # Filtre Gérant (si présent)
        gerant_selected = None
        if "Gérant" in df.columns:
            gerant_options = sorted([g for g in df["Gérant"].dropna().unique().tolist()])
            gerant_selected = st.sidebar.multiselect(
                "Gérant",
                options=gerant_options,
                default=gerant_options
            )
        else:
            st.sidebar.info("Colonne 'Gérant' introuvable — filtre désactivé.")

        # Filtre Type (si présent)
        type_selected = None
        if "Type" in df.columns:
            type_options = sorted([t for t in df["Type"].dropna().unique().tolist()])
            type_selected = st.sidebar.multiselect(
                "Type",
                options=type_options,
                default=type_options
            )
        else:
            st.sidebar.info("Colonne 'Type' introuvable — filtre désactivé.")

        # Construire le masque de filtre
        mask = pd.Series([True] * len(df))
        if gerant_selected is not None:
            mask &= df["Gérant"].isin(gerant_selected)
        if type_selected is not None:
            mask &= df["Type"].isin(type_selected)

        df_filtered = df[mask].copy()

        # Afficher les données filtrées (avant géocodage)
        st.subheader("Tableau (filtré)")
        st.dataframe(df_filtered, use_container_width=True)

        # -------------------- Adresse & Géocodage (sur les lignes filtrées) --------------------
        required_cols = ["Désignation", "NPA", "Lieu", "Canton"]
        missing = [c for c in required_cols if c not in df_filtered.columns]
        if missing:
            st.error(f"Colonnes manquantes pour construire l'adresse : {', '.join(missing)}")
        elif df_filtered.empty:
            st.info("Aucune ligne après filtrage.")
        else:
            # Construire l'adresse (ajout 'Suisse' pour la précision)
            df_filtered["adresse"] = (
                df_filtered["Désignation"].astype(str).str.strip() + ", " +
                df_filtered["NPA"].astype(str).str.strip() + " " +
                df_filtered["Lieu"].astype(str).str.strip() + ", " +
                df_filtered["Canton"].astype(str).str.strip() + ", Suisse"
            )

            # Géocoder avec cache et respect du rate-limit
            geolocator = Nominatim(user_agent="rilsa_map_app", timeout=10)
            rate_limited_geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1, swallow_exceptions=True)

            @st.cache_data(show_spinner=False)
            def geocode_addresses(unique_addresses):
                results = {}
                progress = st.progress(0)
                total = len(unique_addresses)
                for i, addr in enumerate(unique_addresses, start=1):
                    loc = rate_limited_geocode(addr)
                    if loc:
                        results[addr] = (loc.latitude, loc.longitude)
                    else:
                        results[addr] = (None, None)
                    progress.progress(i / total)
                return results

            st.subheader("Géocodage des adresses (sur les données filtrées)")
            uniq = df_filtered["adresse"].dropna().unique().tolist()
            st.write(f"{len(uniq)} adresses uniques à géocoder…")
            mapping = geocode_addresses(tuple(uniq))  # tuple pour la clé du cache

            df_filtered["latitude"]  = df_filtered["adresse"].map(lambda a: mapping.get(a, (None, None))[0])
            df_filtered["longitude"] = df_filtered["adresse"].map(lambda a: mapping.get(a, (None, None))[1])

            # Filtrer les points géocodés valides
            plotted = df_filtered.dropna(subset=["latitude", "longitude"]).copy()

            st.markdown("### Résultats du géocodage (filtré)")
            st.write(f"Points géocodés : {len(plotted)} / {len(df_filtered)}")
            cols_to_show = [c for c in required_cols + ["Gérant", "Type", "adresse", "latitude", "longitude"] if c in df_filtered.columns]
            st.dataframe(plotted[cols_to_show], use_container_width=True)

            # Afficher la carte (uniquement les points filtrés)
            st.markdown("### Carte (filtrée)")
            if not plotted.empty:
                st.map(plotted.rename(columns={"latitude": "lat", "longitude": "lon"})[["lat", "lon"]])
            else:
                st.info("Aucun point géocodé valide à afficher pour les filtres actuels.")

    except ImportError:
        st.error(
            "Les modules requis manquent. Installez-les :\n"
            "`pip install openpyxl geopy` ou ajoutez-les à `requirements.txt`."
        )
    except Exception as e:
        st.error(f"Erreur lors du chargement ou du traitement : {e}")