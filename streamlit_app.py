import streamlit as st
import pandas as pd

st.set_page_config(page_title="RILSA map", layout="wide")
st.title("RILSA map")

st.set_page_config(page_title="RILSA map", layout="wide")
st.title("RILSA map")

# Autoriser uniquement les fichiers Excel
uploaded_file = st.file_uploader("Téléversez un fichier Excel (.xlsx)", type=["xlsx"])

df = None

if uploaded_file is not None:
    try:
        # Charger la liste des feuilles Excel (nécessite openpyxl)
        xls = pd.ExcelFile(uploaded_file, engine="openpyxl")
        sheet = st.selectbox("Choisissez une feuille", xls.sheet_names, index=0)
        df = pd.read_excel(xls, sheet_name=sheet, engine="openpyxl")

        st.success(f"Fichier chargé : {uploaded_file.name} / Feuille : {sheet}")
        st.dataframe(df, use_container_width=True)

    except ImportError:
        st.error(
            "Le module `openpyxl` est requis pour lire les fichiers `.xlsx`.\n"
            "Installez-le avec `pip install openpyxl` ou ajoutez-le à `requirements.txt`."
        )
    except Exception as e:
        st.error(f"Erreur lors de la lecture du fichier : {e}")

# Options disponibles uniquement si un tableau est chargé
if df is not None:
    st.download_button(
        label="Télécharger les données en CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="rilsa_data.csv",
        mime="text/csv",
    )