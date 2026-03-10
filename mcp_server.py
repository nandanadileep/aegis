import os
from mcp.server.fastmcp import FastMCP

from app import load_env, env_var, fetch_memory_summary, format_memory_context
from scripts.memory_pipeline import run_pipeline

# Load environment variables at startup
load_env()

DATABASE = env_var("NEO4J_DATABASE")

# Create the FastMCP instance
mcp = FastMCP("aegis", instructions="""
At the start of every conversation, always call get_memory 
with person_id "nandana_dileep" before responding to anything.
Use the result naturally without referencing that you fetched it.
""")


@mcp.tool()
def get_memory(person_id: str) -> str:
    """Fetch the full memory profile for a person from the Aegis memory graph."""
    records = fetch_memory_summary(person_id, DATABASE)
    return format_memory_context(records)


@mcp.tool()
def add_memory(transcript: str, person_id: str = "nandana_dileep") -> str:
    """Add new information about the user to the Aegis memory graph.
    Call this when the user shares something new about themselves — 
    new goals, projects, preferences, life changes, or anything worth remembering.
    Pass the relevant part of the conversation as transcript."""
    run_pipeline(transcript, use_mock_llm=False, person_id=person_id)
    return "Memory updated."


if __name__ == "__main__":
    mcp.run()