import os
from mcp.server.fastmcp import FastMCP

from app import load_env, env_var, get_neo4j_driver
from scripts.graph_memory import (
    retrieve_facts,
    format_context,
    create_episode,
    run_graph_pipeline,
)

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
def get_memory(person_id: str, query: str = "") -> str:
    """Fetch relevant memory for a person from the Aegis ERF graph.

    Args:
        person_id: the user's stable identifier.
        query: optional topic to retrieve facts about. If empty, recent facts are returned.
    """
    driver = get_neo4j_driver()
    facts = retrieve_facts(driver, DATABASE, person_id, query, top_k=50)
    return format_context(facts)


@mcp.tool()
def add_memory(transcript: str, person_id: str = "nandana_dileep") -> str:
    """Add new information about the user to the Aegis ERF graph.
    Call this when the user shares something new about themselves —
    new goals, projects, preferences, life changes, or anything worth remembering.
    Pass the relevant part of the conversation as transcript."""
    driver = get_neo4j_driver()
    episode_id = create_episode(driver, DATABASE, person_id, body=transcript, source="mcp")
    run_graph_pipeline(
        conversation=transcript,
        person_id=person_id,
        driver=driver,
        database=DATABASE,
        episode_id=episode_id,
    )
    return "Memory updated."


if __name__ == "__main__":
    mcp.run()