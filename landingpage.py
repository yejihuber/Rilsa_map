import streamlit as st

st.set_page_config(
    page_title="Hello",
    page_icon="👋",
)

st.write("# Welcome to RILSA Data analyse 👋")

st.sidebar.success("Select a demo above.")

st.markdown(
    """
    - [RILSA map](https://rilsamap.streamlit.app/)
    - [RILSA email data analyse](https://rilsaemail.streamlit.app/)
"""
)