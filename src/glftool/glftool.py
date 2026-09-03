"""
glftool.py

"""

import streamlit as st

from glftool.ui import stage


def run():
    st.set_page_config(
        page_title="DePeak",
        page_icon="📉",
        layout="wide",
    )
    stage.render()
