import pandas as pd
import numpy as np
import streamlit as st
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
st.set_page_config(layout="wide")

st.title("hello")

df = pd.DataFrame(
    np.random.randn(1000, 2) / [50, 50] + [37.76, -122.4],
    columns=["lat", "lon"],
)
st.map(df)