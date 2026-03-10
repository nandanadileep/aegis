from typing import Any, Dict, List

from mcp.server.fastmcp import FastMCP

from app import load_env, env_var, get_neo4j_driver

# Load environment variables at startup
load_env()

DATABASE = env_var("NEO4J_DATABASE")
NEO4J_DRIVER = get_neo4j_driver()

# Create the FastMCP instance
mcp = FastMCP("aegis")


@mcp.tool()
def get_memory(person_id: str) -> Dict[str, Any]:
    """Fetch a structured memory summary for a person from the Aegis memory graph."""
    query = """
    MATCH (p:Person {id: $person_id})
    OPTIONAL MATCH (p)-[r]-(n)
    RETURN properties(p) AS person_props,
           type(r) AS relationship_type,
           properties(r) AS relationship_props,
           labels(n) AS node_labels,
           properties(n) AS node_props
    """

    with NEO4J_DRIVER.session(database=DATABASE) as session:
        records = session.run(query, person_id=person_id).data()

    if not records:
        return {
            "person_id": person_id,
            "found": False,
            "summary": "No memory found for this person.",
            "person": {},
            "facts": [],
            "relationships": [],
            "attributes": {},
        }

    person_props = records[0].get("person_props") or {}
    facts: List[Dict[str, Any]] = []
    relationships: List[Dict[str, Any]] = []
    attributes: Dict[str, List[Any]] = {}

    for rec in records:
        node_props = rec.get("node_props") or {}
        node_labels = rec.get("node_labels") or []
        relationship_type = rec.get("relationship_type")
        relationship_props = rec.get("relationship_props") or {}

        if not relationship_type or not node_props:
            continue

        node_name = node_props.get("name") or node_props.get("key") or node_props.get("id") or "unknown"
        node_value = node_props.get("value")

        fact = {
            "relationship": relationship_type,
            "labels": node_labels,
            "node": node_props,
        }
        facts.append(fact)

        relationships.append(
            {
                "type": relationship_type,
                "target_labels": node_labels,
                "target": node_props,
                "properties": relationship_props,
            }
        )

        if node_value is not None:
            attributes.setdefault(node_name, []).append(node_value)
        else:
            attributes.setdefault(node_name, []).append(node_props)

    summary_parts: List[str] = []
    if person_props:
        summary_parts.append(f"Found memory for {person_props.get('name') or person_id}.")
    if attributes:
        summary_parts.append(f"Captured {len(attributes)} attribute groups.")
    if relationships:
        summary_parts.append(f"Observed {len(relationships)} relationships.")
    if not summary_parts:
        summary_parts.append("Person found, but no related memory entries were stored yet.")

    return {
        "person_id": person_id,
        "found": True,
        "summary": " ".join(summary_parts),
        "person": person_props,
        "facts": facts,
        "relationships": relationships,
        "attributes": attributes,
    }


if __name__ == "__main__":
    mcp.run()