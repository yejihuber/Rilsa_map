import streamlit as st
import pandas as pd

st.set_page_config(page_title="RILSA map", layout="wide")
st.title("RILSA map")

uploaded_file = st.file_uploader("Upload a document", type=["xlsx", "csv"])

df = None

if uploaded_file is not None:
    try:
        if uploaded_file.name.lower().endswith(".csv"):
            # Support CSV
            df = pd.read_csv(uploaded_file)
        else:
            # Excel : nécessite openpyxl
            # Lis d'abord la liste des feuilles pour proposer un sélecteur
            xls = pd.ExcelFile(uploaded_file, engine="openpyxl")
            sheet = st.selectbox("Feuille Excel", xls.sheet_names, index=0)
            df = pd.read_excel(xls, sheet_name=sheet)

        st.success(f"Fichier chargé : {uploaded_file.name}")
        st.dataframe(df, use_container_width=True)

    except ImportError as e:
        st.error(
            "Le module `openpyxl` est requis pour lire les fichiers .xlsx.\n"
            "Installe-le avec `pip install openpyxl` et/ou ajoute-le à `requirements.txt`."
        )
    except Exception as e:
        st.error(f"Impossible de lire le fichier : {e}")

# N'affiche la table que si df existe
if df is not None:
    st.download_button(
        "Télécharger les données en CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="rilsa_data.csv",
        mime="text/csv",
    )
