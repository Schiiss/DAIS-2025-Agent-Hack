import streamlit as st
import pydeck as pdk
import pandas as pd
import numpy as np
import io
import re
import ast
import json
from databricks.sdk import WorkspaceClient
from databricks import sql
from langchain_core.messages import AIMessage, HumanMessage
from graph import invoke_our_graph, sqlQuery
from st_callable_util import get_streamlit_cb

# Initialize Databricks client
w = WorkspaceClient()

# Streamlit page config
st.set_page_config(layout="wide")

# Title
st.title("AccessCity")

# -- Demo map using pydeck instead of st.map --
random_df = pd.DataFrame(
    np.random.randn(1000, 2) / [50, 50] + [37.76, -122.4],
    columns=["lat", "lon"],
)
# prepare for pydeck
random_df = random_df.rename(columns={"lat": "latitude", "lon": "longitude"})
random_df["size"] = 100  # fixed radius for demo

demo_layer = pdk.Layer(
    "ScatterplotLayer",
    data=random_df,
    pickable=True,
    auto_highlight=True,
    get_position=["longitude", "latitude"],
    get_radius="size",
    get_fill_color=[200, 30, 0, 160],
)
demo_view = pdk.ViewState(latitude=37.76, longitude=-122.4, zoom=10, pitch=50)
demo_tooltip = {"text": "Lat: {latitude}\nLon: {longitude}"}

demo_deck = pdk.Deck(
    layers=[demo_layer],
    initial_view_state=demo_view,
    tooltip=demo_tooltip,
)

st.pydeck_chart(demo_deck)

# -- Chat state initialization --
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

# Handle new user prompt
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

        # Extract raw records
        raw = None
        records = []  # ensure defined to avoid NameError
        for msg in response["messages"]:
            if hasattr(msg, "content") and "array(" in msg.content:
                raw = msg.content
                break
        if raw is None:
            print("[Error] No array() found in response")
        else:
            # Clean numpy array syntax and dates
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
                records = []
                st.error(f"Failed to parse cleaned output: {e}")
                print("[Error] Failed to parse cleaned output:", e)
                print(cleaned)

        # Display map of returned places if any
        if records:
            try:
                df_places = pd.json_normalize(records)
                # rename nested review summary
                df_places = df_places.rename(columns={
                    "review_summary.overall_rating": "rating",
                    "review_summary.review_count": "review_count",
                })
                df_places["latitude"] = df_places["latitude"].astype(float)
                df_places["longitude"] = df_places["longitude"].astype(float)

                # center map
                center_lat = df_places["latitude"].mean()
                center_lng = df_places["longitude"].mean()

                # build layer
                place_layer = pdk.Layer(
                    "ScatterplotLayer",
                    data=df_places,
                    pickable=True,
                    auto_highlight=True,
                    get_position=["longitude", "latitude"],
                    get_radius=200,
                    get_fill_color=[30, 144, 255],
                )
                view_state = pdk.ViewState(
                    latitude=center_lat,
                    longitude=center_lng,
                    zoom=12,
                    pitch=45,
                )
                tooltip = {
                    "html": """
                      <div style=\"max-width:250px;\">\n\                        <h4>{title}</h4>\n\                        <div>{address}</div>\n\                        <div>⭐ {rating} ({review_count} reviews)</div>\n\                        <br/>\n\                        <a href=\"{place_url}\" target=\"_blank\">Open in Google Maps</a>\n\                        </div>\n\                    """,
                    "style": {
                        "backgroundColor": "rgba(0, 0, 0, 0.75)",
                        "color": "white",
                        "fontSize": "11px",
                        "padding": "8px",
                        "borderRadius": "4px",
                    },
                }
                deck = pdk.Deck(
                    layers=[place_layer],
                    initial_view_state=view_state,
                    tooltip=tooltip,
                )
                st.pydeck_chart(deck, on_select="rerun", selection_mode="multi-object")
            except Exception as e:
                st.error(f"Error displaying map: {e}")
                print("[Error] Failed to display map:", e)
        else:
            st.warning("No locations to display.")