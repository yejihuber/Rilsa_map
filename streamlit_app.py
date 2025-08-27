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
            skiprows=4  # <<--- Ignore les 4 premières lignes
        )

        st.success(f"Fichier chargé : {uploaded_file.name} / Feuille : {sheet}")
        st.dataframe(df, use_container_width=True)

        # 🔹 Créer une nouvelle colonne "Type" selon la valeur de "Référence"
        def classify_type(ref):
            try:
                if 100000 <= ref <= 499000:
                    return "Immeuble"
                elif 500000 <= ref <= 599000:
                    return "Lot"
                elif 800000 <= ref <= 950000:
                    return "PPE"
                else:
                    return "Autre"
            except:
                return "Inconnu"

        if "Référence" in df.columns:
            df["Type"] = df["Référence"].apply(classify_type)
        else:
            st.warning("⚠️ La colonne 'Référence' est absente du fichier, impossible de créer 'Type'.")

        st.dataframe(df, use_container_width=True)

        # ✅ (le reste de ton code géocodage + affichage carte vient ici, inchangé)

        # Vérifier les colonnes requises
        required_cols = ["Désignation", "NPA", "Lieu", "Canton"]
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            st.error(f"Colonnes manquantes pour construire l'adresse : {', '.join(missing)}")
        else:
            # Construire l'adresse (ajout de 'Suisse' pour améliorer la précision)
            df["adresse"] = (
                df["Désignation"].astype(str).str.strip() + ", " +
                df["NPA"].astype(str).str.strip() + " " +
                df["Lieu"].astype(str).str.strip() + ", " +
                df["Canton"].astype(str).str.strip() + ", Suisse"
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

            st.subheader("Géocodage des adresses")
            uniq = df["adresse"].dropna().unique().tolist()
            st.write(f"{len(uniq)} adresses uniques à géocoder…")
            mapping = geocode_addresses(tuple(uniq))  # tuple pour la clé du cache

            df["latitude"]  = df["adresse"].map(lambda a: mapping.get(a, (None, None))[0])
            df["longitude"] = df["adresse"].map(lambda a: mapping.get(a, (None, None))[1])

            # Filtrer les points géocodés
            plotted = df.dropna(subset=["latitude", "longitude"]).copy()

            st.markdown("### Résultats du géocodage")
            st.write(f"Points géocodés : {len(plotted)} / {len(df)}")
            st.dataframe(plotted[required_cols + ["adresse", "latitude", "longitude"]], use_container_width=True)

            # Afficher la carte (utilise automatiquement latitude/longitude)
            st.markdown("### Carte")
            if not plotted.empty:
                st.map(plotted.rename(columns={"latitude": "lat", "longitude": "lon"})[["lat", "lon"]])
            else:
                st.info("Aucun point géocodé valide à afficher pour le moment.")

    except ImportError:
        st.error(
            "Le module `openpyxl` est requis pour lire les fichiers `.xlsx`.\n"
            "Installez-le avec `pip install openpyxl` ou ajoutez-le à `requirements.txt`."
        )
    except Exception as e:
        st.error(f"Erreur lors du chargement ou du traitement : {e}")

