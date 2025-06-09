import io
import base64
import re
import json
import pandas as pd

import streamlit as st
from databricks import sql
from databricks.sdk import WorkspaceClient
from langchain_core.messages import AIMessage, HumanMessage

from graph import invoke_our_graph, sqlQuery
from st_callable_util import get_streamlit_cb

w = WorkspaceClient()
st.set_page_config(layout="wide")

st.title("hello")