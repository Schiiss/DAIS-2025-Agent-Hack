import os
from datetime import datetime

import pandas as pd
from databricks import sql
from databricks.sdk.core import Config
from databricks_langchain import DatabricksVectorSearch

from langchain_core.tools import tool, StructuredTool
from langchain.tools import tool as deprecated_tool  # If you're using both versions

from langgraph.graph import START, StateGraph
from langgraph.graph.message import AnyMessage, add_messages
from langgraph.prebuilt import ToolNode
from langchain_openai import AzureChatOpenAI
openai_key = os.getenv('SECRET_KEY')
openai_model = os.getenv('SECRET_MODEL')
from typing import Annotated, TypedDict, Literal

def sqlQuery(query: str) -> pd.DataFrame:
    """
    Run the given SQL against Databricks and return a pandas DataFrame.
    """
    cfg = Config()
    with sql.connect(
        server_hostname=cfg.host,
        http_path="/sql/1.0/warehouses/39e461a44e28010b",
        credentials_provider=lambda: cfg.authenticate
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            # return the raw DataFrame, not markdown
            return cursor.fetchall_arrow().to_pandas()
        
@tool
def get_wheel_chair_accessibility(city: str, accessibility: str, business_category: str) -> str:
    """
    Searches the Nimble Google Maps dataset for places in the specified city that match the given accessibility feature and business category.
    The agent should provide the city name, specify 'wheelchair' or related accessibility terms for the accessibility parameter,
    and specify the type of business (e.g., restaurant, hotel) for the business_category parameter.
    Returns: up to 5 matching places as JSON.
    """
    query = f"""
    SELECT *
    FROM `dais-hackathon-2025`.nimble.dbx_google_maps_search_daily
    WHERE city = '{city}'
      AND exists(
        accessibility,
        a -> a.display_name ILIKE '%{accessibility}%'
      )
      AND exists(
        business_category_ids,
        category -> category ILIKE '%{business_category}%'
      )
    LIMIT 5;
    """
    df = sqlQuery(query)
    return df.to_dict(orient="records")


# List of tools that will be accessible to the graph via the ToolNode
tools = [get_wheel_chair_accessibility]
tool_node = ToolNode(tools)

# This is the default state same as "MessageState" TypedDict but allows us accessibility to custom keys
class GraphsState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    # Custom keys for additional data can be added here such as - conversation_id: str

graph = StateGraph(GraphsState)

# Function to decide whether to continue tool usage or end the process
def should_continue(state: GraphsState) -> Literal["tools", "__end__"]:
    messages = state["messages"]
    last_message = messages[-1]
    if last_message.tool_calls:  # Check if the last message has any tool calls
        return "tools"  # Continue to tool execution
    return "__end__"  # End the conversation if no tool is needed
# Core invocation of the model
def _call_model(state: GraphsState):
    messages = state["messages"]
    llm = AzureChatOpenAI(
        temperature=0,
        streaming=True,
        deployment_name=openai_model,
        api_version="2025-01-01-preview",
        api_key=openai_key,
        azure_endpoint="https://northcentralus.api.cognitive.microsoft.com/"
    ).bind_tools(tools, parallel_tool_calls=False)
    response = llm.invoke(messages)
    return {"messages": [response]}  # add the response to the messages using LangGraph reducer paradigm

# Define the structure (nodes and directional edges between nodes) of the graph
graph.add_edge(START, "modelNode")
graph.add_node("tools", tool_node)
graph.add_node("modelNode", _call_model)

# Add conditional logic to determine the next step based on the state (to continue or to end)
graph.add_conditional_edges(
    "modelNode",
    should_continue,  # This function will decide the flow of execution
)
graph.add_edge("tools", "modelNode")

# Compile the state graph into a runnable object
graph_runnable = graph.compile()
def invoke_our_graph(st_messages, callables):
    if not isinstance(callables, list):
        raise TypeError("callables must be a list")
    return graph_runnable.invoke({"messages": st_messages}, config={"callbacks": callables})