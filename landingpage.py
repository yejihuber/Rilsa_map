import streamlit as st

st.set_page_config(
    page_title="Hello",
    page_icon="👋",
)

st.write("# Welcome to RILSA Data analyse 👋")

st.sidebar.success("Select a demo above.")

st.markdown(
    """
    - [RILSA map](https://github.com/yejihuber/Rilsa_map/blob/main/streamlit_app.py)
"""
)