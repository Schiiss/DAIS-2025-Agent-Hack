import pandas as pd
import numpy as np
import streamlit as st
from databricks.sdk import WorkspaceClient
import io
import base64
import re
import json
import ast
from databricks import sql
from databricks.sdk import WorkspaceClient
from langchain_core.messages import AIMessage, HumanMessage

from graph import invoke_our_graph, sqlQuery
from st_callable_util import get_streamlit_cb

w = WorkspaceClient()

st.set_page_config(layout="wide")

st.title("AccessCity")

# Show random map for demo purposes
random_df = pd.DataFrame(
    np.random.randn(1000, 2) / [50, 50] + [37.76, -122.4],
    columns=["lat", "lon"],
)
st.map(random_df)

# Chat state initialization
if "expander_open" not in st.session_state:
    st.session_state.expander_open = True

if "messages" not in st.session_state:
    st.session_state["messages"] = [AIMessage(content="How can I help you?")]

prompt = st.chat_input()

if prompt is not None:
    st.session_state.expander_open = False

# Render chat history
for msg in st.session_state.messages:
    if isinstance(msg, AIMessage):
        st.chat_message("assistant").write(msg.content)
    elif isinstance(msg, HumanMessage):
        st.chat_message("user").write(msg.content)

if prompt:
    st.session_state.messages.append(HumanMessage(content=prompt))
    st.chat_message("user").write(prompt)

    with st.chat_message("assistant"):
        user_token = st.context.headers.get("X-Forwarded-Access-Token")
        user_email = st.context.headers.get("X-Forwarded-Email")

        print(f"[Debug] User Email: {user_email}")

        st_callback = get_streamlit_cb(st.container())
        response = invoke_our_graph(st.session_state.messages, [st_callback])

        print("[Debug] Full invoke response:", repr(response))

        last = response["messages"][-1].content
        st.session_state.messages.append(AIMessage(content=last))
        print("[Debug] Extracted last content:", repr(last))

        # Try to extract valid Python list of dicts
        raw = None
        for msg in response["messages"]:
            if hasattr(msg, "content") and "array(" in msg.content:
                raw = msg.content
                break
        if raw is None:
            st.error("No records found")
            print("[Debug] No raw output containing array()")
        else:
            # Clean numpy arrays and datetime objects for parsing
            cleaned = re.sub(
                r"array\(\s*(\[[\s\S]*?\])\s*,\s*dtype=object\s*\)",
                r"\1",
                raw,
                flags=re.DOTALL
            )
            cleaned = re.sub(
                r"datetime\.date\(\s*(\d{4})\s*,\s*(\d{1,2})\s*,\s*(\d{1,2})\s*\)",
                r"'\1-\2-\3'",
                cleaned
            )
            try:
                records = ast.literal_eval(cleaned)
                print("[Debug] Parsed records:", records[:1])
            except Exception as e:
                records = None
                st.error(f"Failed to parse cleaned output: {e}")
                print("[Error] Failed to parse cleaned output:", e)
                print(cleaned)

        if records:
            try:
                df_places = pd.json_normalize(records)
                df_places["latitude"] = df_places["latitude"].astype(float)
                df_places["longitude"] = df_places["longitude"].astype(float)
                df_map = df_places.rename(columns={"latitude": "lat", "longitude": "lon"})

                col1, col2 = st.columns([1, 3])
                with col1:
                    st.markdown("### Returned Locations")
                    st.map(df_map)
            except Exception as e:
                st.error(f"Error displaying map: {e}")
                print("[Error] Failed to display map:", e)