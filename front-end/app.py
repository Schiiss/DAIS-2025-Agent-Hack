import pandas as pd
import numpy as np
import streamlit as st
from databricks.sdk import WorkspaceClient
import io
import base64
import re
import json
from databricks import sql
from databricks.sdk import WorkspaceClient
from langchain_core.messages import AIMessage, HumanMessage

from graph import invoke_our_graph, sqlQuery
from st_callable_util import get_streamlit_cb

w = WorkspaceClient()

w = WorkspaceClient()
st.set_page_config(layout="wide")

st.title("AccessCity")

df = pd.DataFrame(
    np.random.randn(1000, 2) / [50, 50] + [37.76, -122.4],
    columns=["lat", "lon"],
)
st.map(df)

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
        # — grab user’s token/email from Databricks Apps headers —
        user_token = st.context.headers.get("X-Forwarded-Access-Token")
        user_email = st.context.headers.get("X-Forwarded-Email")

        # Print to stdout
        print(f"[Debug] User Token: {user_token} this message get's messed up and redacted idk")
        print(f"[Debug] User Email: {user_email}")

        # invoke the graph…
        st_callback = get_streamlit_cb(st.container())
        response = invoke_our_graph(st.session_state.messages, [st_callback])

        # DEBUG—console
        print("Full invoke response:", repr(response))

        # Append the model’s final AIMessage (so the UI still shows it)
        last = response["messages"][-1].content
        st.session_state.messages.append(AIMessage(content=last))
        print("Extracted last content:", repr(last))

        # find the first message whose content is valid JSON list-of-dicts
        records = None
        for msg in response["messages"]:
            try:
                payload = json.loads(msg.content)
                if isinstance(payload, list) and payload and isinstance(payload[0], dict):
                    records = payload
                    break
            except Exception:
                continue