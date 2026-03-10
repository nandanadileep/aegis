import os
from mcp.server.fastmcp import FastMCP

from app import load_env, env_var, fetch_memory_summary, format_memory_context

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


if __name__ == "__main__":
    mcp.run()