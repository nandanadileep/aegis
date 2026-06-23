"""
Demo / smoke-test for the Zep-style Entity-Relation-Fact graph memory.

Run without LLM calls (uses hard-coded mock extraction):
    python scripts/demo_graph_memory.py --mock

Run with real LLM (requires env vars + Neo4j + Redis is not needed):
    python scripts/demo_graph_memory.py

The script will:
1. Ensure indexes exist.
2. Create an episode.
3. Run the ERF pipeline on a sample message.
4. Run it again on a follow-up to show entity resolution + fact invalidation.
5. Retrieve relevant facts for a query.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

# Make sure we can import from scripts/ regardless of cwd.
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from neo4j import GraphDatabase

from scripts.graph_memory import (
    Entity,
    Fact,
    ensure_indexes,
    create_episode,
    run_graph_pipeline,
    fetch_existing_entities,
    retrieve_facts,
    format_context,
)


def load_env() -> None:
    try:
        from dotenv import load_dotenv as _load
        _load()
    except Exception:
        pass


def get_driver() -> Any:
    return GraphDatabase.driver(
        os.getenv("NEO4J_URI"),
        auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")),
        notifications_min_severity="OFF",
    )


def mock_extract_entities(current_message: str, **kw) -> List[Entity]:
    """Return deterministic mock entities for testing schema writes."""
    if "Python" in current_message:
        return [
            Entity(name="Nandana", entity_type="Person", summary="User building an AI memory app"),
            Entity(name="Python", entity_type="Skill", summary="Programming language"),
            Entity(name="AI Memory App", entity_type="Project", summary="Agent memory system"),
        ]
    return [
        Entity(name="Nandana", entity_type="Person", summary="User building an AI memory app"),
        Entity(name="Neo4j", entity_type="Technology", summary="Graph database"),
        Entity(name="AI Memory App", entity_type="Project", summary="Agent memory system"),
    ]


def mock_extract_facts(entities: List[Entity], current_message: str, **kw) -> List[Fact]:
    """Return deterministic mock facts."""
    by_name = {e.name: e for e in entities}
    if "Python" in current_message:
        return [
            Fact(
                source=by_name["Nandana"],
                target=by_name["Python"],
                relation_type="KNOWS",
                fact="Nandana knows Python and uses it to build the AI memory app.",
            ),
            Fact(
                source=by_name["Nandana"],
                target=by_name["AI Memory App"],
                relation_type="BUILDS",
                fact="Nandana is building an AI memory app.",
            ),
        ]
    return [
        Fact(
            source=by_name["Nandana"],
            target=by_name["Neo4j"],
            relation_type="USES",
            fact="Nandana uses Neo4j as the graph database for the AI memory app.",
        ),
        Fact(
            source=by_name["AI Memory App"],
            target=by_name["Neo4j"],
            relation_type="USES",
            fact="The AI memory app uses Neo4j to store entity-relation-fact data.",
        ),
    ]


_RESOLVED_NAMES: Dict[str, str] = {}


def _mock_resolve_entities(prompt: str) -> str:
    """Deterministic entity resolution: same name == same entity."""
    import re as _re
    # Pull out new entity name
    new_match = _re.search(r"NEW ENTITY:\nName: ([^\n]+)", prompt)
    new_name = (new_match.group(1).strip() if new_match else "").lower()
    # Pull out existing candidates
    existing_uuids = _re.findall(r"- UUID: ([^\n]+)\n\s*Name: ([^\n]+)", prompt)
    for uid, name in existing_uuids:
        if name.strip().lower() == new_name:
            return json.dumps({"is_duplicate": True, "uuid": uid.strip(), "name": name.strip()})
    return json.dumps({"is_duplicate": False})


def _mock_resolve_facts(prompt: str) -> str:
    """Deterministic fact resolution.

    If the new fact mentions Memgraph and an existing fact mentions Neo4j,
    treat it as a contradiction. Otherwise duplicate if text is close.
    """
    import re as _re
    new_match = _re.search(r"NEW FACT:\n(.+)", prompt)
    new_fact = (new_match.group(1).strip() if new_match else "").lower()
    existing_facts = _re.findall(r"- UUID: ([^\n]+)\n\s*Fact: (.+)", prompt)

    for uid, fact in existing_facts:
        fact_l = fact.lower()
        # Contradiction: user stopped using X.
        if ("no longer" in new_fact or "switched" in new_fact or "instead of" in new_fact) and "neo4j" in fact_l:
            return json.dumps({"decision": "contradiction", "uuid": uid.strip()})
        # Duplicate checks.
        if "neo4j" in new_fact and "neo4j" in fact_l:
            return json.dumps({"decision": "duplicate", "uuid": uid.strip()})
        if "python" in new_fact and "python" in fact_l:
            return json.dumps({"decision": "duplicate", "uuid": uid.strip()})
        if "memory app" in new_fact and "memory app" in fact_l:
            return json.dumps({"decision": "duplicate", "uuid": uid.strip()})
    return json.dumps({"decision": "new"})


def mock_llm_fn(messages: List[Dict[str, str]], **kw) -> Any:
    """A context-aware LLM mock for resolution/temporal prompts."""
    content = messages[-1]["content"]
    response_text = "{}"
    if "NEW ENTITY" in content and "EXISTING ENTITIES" in content:
        response_text = _mock_resolve_entities(content)
    elif "NEW FACT" in content and "EXISTING FACTS" in content:
        response_text = _mock_resolve_facts(content)

    class _Choice:
        class _Message:
            content = response_text
        message = _Message()
    class _Resp:
        choices = [_Choice()]
    return _Resp()


def _clear_demo_data(driver, database: str, person_id: str) -> None:
    """Remove old :Entity and :Episode nodes for the demo person id."""
    with driver.session(database=database) as session:
        session.run(
            """
            MATCH (p:Person {id: $person_id})
            OPTIONAL MATCH (p)-[:HAS_ENTITY]->(e:Entity)
            OPTIONAL MATCH (p)-[:HAS_EPISODE]->(ep:Episode)
            DETACH DELETE e, ep
            """,
            person_id=person_id,
        )


def run_mock_demo(driver, database: str, person_id: str) -> None:
    print("\n=== MOCK DEMO: Zep-style Entity-Relation-Fact Graph ===\n")

    ensure_indexes(driver, database)
    _clear_demo_data(driver, database, person_id)
    print(f"Cleared old demo data for person_id={person_id}\n")

    # Patch extraction functions at module level for the demo.
    import scripts.graph_memory as gm
    gm.extract_entities = mock_extract_entities
    gm.extract_facts = mock_extract_facts
    # Let the real hybrid temporal extractor run on mock facts.

    # Turn 1
    msg1 = "I'm Nandana, building an AI memory app using Neo4j."
    ep1 = create_episode(driver, database, person_id, body=msg1)
    print(f"Turn 1 episode: {ep1}")
    result1 = run_graph_pipeline(
        conversation=msg1,
        person_id=person_id,
        driver=driver,
        database=database,
        episode_id=ep1,
        llm_fn=mock_llm_fn,
    )
    print("Created entities:", json.dumps(result1["entities"], indent=2))
    print("Created facts:", json.dumps(result1["facts"], indent=2))

    # Turn 2: entity resolution should merge Nandana and AI Memory App.
    msg2 = "Nandana is also fluent in Python and uses it for the memory app."
    ep2 = create_episode(driver, database, person_id, body=msg2)
    print(f"\nTurn 2 episode: {ep2}")
    result2 = run_graph_pipeline(
        conversation=msg2,
        person_id=person_id,
        driver=driver,
        database=database,
        episode_id=ep2,
        llm_fn=mock_llm_fn,
    )
    print("Created/resolved entities:", json.dumps(result2["entities"], indent=2))
    print("Created facts:", json.dumps(result2["facts"], indent=2))

    # Turn 3: contradiction / invalidation demo
    msg3 = "Actually, Nandana no longer uses Neo4j; she switched to Memgraph."
    ep3 = create_episode(driver, database, person_id, body=msg3)
    print(f"\nTurn 3 episode: {ep3}")
    # We need a Memgraph entity in the mock for this turn.
    def mock_extract_entities_v3(current_message: str, **kw):
        return [
            Entity(name="Nandana", entity_type="Person", summary="User building an AI memory app"),
            Entity(name="Neo4j", entity_type="Technology", summary="Graph database"),
            Entity(name="Memgraph", entity_type="Technology", summary="Graph database"),
            Entity(name="AI Memory App", entity_type="Project", summary="Agent memory system"),
        ]
    def mock_extract_facts_v3(entities: List[Entity], current_message: str, **kw):
        by_name = {e.name: e for e in entities}
        return [
            # This contradicts the existing Neo4j fact between Nandana and Neo4j.
            Fact(
                source=by_name["Nandana"],
                target=by_name["Neo4j"],
                relation_type="USES",
                fact="Nandana no longer uses Neo4j for the AI memory app.",
            ),
            # This adds a new fact to the new Memgraph entity.
            Fact(
                source=by_name["Nandana"],
                target=by_name["Memgraph"],
                relation_type="USES",
                fact="Nandana now uses Memgraph for the AI memory app.",
            ),
        ]
    gm.extract_entities = mock_extract_entities_v3
    gm.extract_facts = mock_extract_facts_v3
    result3 = run_graph_pipeline(
        conversation=msg3,
        person_id=person_id,
        driver=driver,
        database=database,
        episode_id=ep3,
        llm_fn=mock_llm_fn,
    )
    print("Created/resolved entities:", json.dumps(result3["entities"], indent=2))
    print("Created facts:", json.dumps(result3["facts"], indent=2))

    # Show relevant facts via vector + BM25 + BFS retrieval.
    print("\n=== Retrieval demo (vector + BM25 + BFS) ===")
    for q in ["What database does Nandana use?", "Tell me about the AI memory app."]:
        print(f"\nQuery: {q}")
        hits = retrieve_facts(driver, database, person_id, q, top_k=5)
        for h in hits:
            print(
                f"  - {h['source_name']} -[{h['relation_type']}]-> {h['target_name']}: "
                f"{h['fact']} (score={h.get('score', 0):.3f}, valid_from={h.get('valid_from')}, valid_to={h.get('valid_to')})"
            )
        if not hits:
            print("  (no currently valid facts)")


def run_real_demo(driver, database: str, person_id: str) -> None:
    print("\n=== REAL LLM DEMO ===\n")
    ensure_indexes(driver, database)
    _clear_demo_data(driver, database, person_id)
    print(f"Cleared old demo data for person_id={person_id}\n")

    msg = "I'm Nandana, based in Bangalore, building an AI memory app with Python and Neo4j."
    ep = create_episode(driver, database, person_id, body=msg)
    print(f"Episode: {ep}")
    print(f"Processing: {msg}")

    result = run_graph_pipeline(
        conversation=msg,
        person_id=person_id,
        driver=driver,
        database=database,
        episode_id=ep,
    )
    print("\nCreated entities:")
    for e in result["entities"]:
        print(f"  - {e['name']} ({e['type']})")
    print("\nCreated facts:")
    for f in result["facts"]:
        print(f"  - {f['relation_type']}: {f['fact']}")

    q = "What is Nandana building?"
    print(f"\nQuery: {q}")
    hits = retrieve_facts(driver, database, person_id, q, top_k=5)
    print(format_context(hits))


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo the ERF graph memory.")
    parser.add_argument("--mock", action="store_true", help="Use deterministic mock extraction instead of real LLM.")
    parser.add_argument("--person-id", default="erf_demo_test", help="Person id to write to.")
    args = parser.parse_args()

    load_env()
    driver = get_driver()
    database = os.getenv("NEO4J_DATABASE", "neo4j")

    try:
        if args.mock:
            run_mock_demo(driver, database, args.person_id)
        else:
            run_real_demo(driver, database, args.person_id)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
