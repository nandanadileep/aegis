"""Neo4j helpers for isolated benchmark person graphs."""
from __future__ import annotations

import os

from neo4j import GraphDatabase

try:
    from neo4j import NotificationMinimumSeverity
except ImportError:
    NotificationMinimumSeverity = None


def bench_person_id(instance_id: str) -> str:
    return f"bench-lme-{instance_id}"


def get_driver():
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")
    kwargs = {}
    if NotificationMinimumSeverity is not None:
        kwargs["notifications_min_severity"] = NotificationMinimumSeverity.OFF
    return GraphDatabase.driver(uri, auth=(user, password), **kwargs)


def wipe_person(driver, database: str, person_id: str) -> None:
    """Delete all graph data for a benchmark person."""
    queries = [
        """
        MATCH ()-[r:FACT {person_id: $person_id}]->()
        DELETE r
        """,
        """
        MATCH ()-[r:MENTIONED_IN {person_id: $person_id}]->()
        DELETE r
        """,
        """
        MATCH (n)
        WHERE n.person_id = $person_id
        DETACH DELETE n
        """,
        """
        MATCH (p:Person {id: $person_id})
        DETACH DELETE p
        """,
    ]
    with driver.session(database=database) as session:
        for query in queries:
            session.run(query, person_id=person_id)


def wipe_session(driver, database: str, person_id: str, session_id: str) -> None:
    """Delete one ingested session so it can be re-processed."""
    queries = [
        """
        MATCH ()-[f:FACT {person_id: $person_id, source_episode_id: $session_id}]->()
        DELETE f
        """,
        """
        MATCH (ep:Episode {id: $session_id, person_id: $person_id})
        DETACH DELETE ep
        """,
    ]
    with driver.session(database=database) as session:
        for query in queries:
            session.run(query, person_id=person_id, session_id=session_id)
