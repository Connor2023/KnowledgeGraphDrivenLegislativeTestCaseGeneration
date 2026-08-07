from neo4j import GraphDatabase, Driver
from graph_database import DatabaseAPI

class Neo4JGDB(DatabaseAPI):
    def __init__(self, uri, auth):
        self.__uri = uri
        self.__auth = auth
        self.__driver: Driver | None = None

    def start(self):
        """Start driver connection."""
        if self.__driver is None:
            self.__driver = GraphDatabase.driver(self.__uri, auth=self.__auth)
            self.__driver.verify_connectivity()
            self.__driver.verify_authentication()
        return self.__driver is not None
    
    def shutdown(self):
        """Close driver connection."""
        if self.__driver is not None:
            self.__driver.close()
            self.__driver = None
        return self.__driver is None

    def create_new_entity(self, type: str, entity: str):
        """Create a node if it doesn't exist."""
        if not self.__driver:
            raise RuntimeError("Driver not started.")
        cypher_query = f"""
        MERGE (n:{type} {{entity: $entity}})
        RETURN n
        """
        with self.__driver.session() as session:
            result = session.run(cypher_query, entity=entity)
            record = result.single()
            return record["n"] if record else None

            
    def check_entity_exists(self, type: str, entity: str) -> bool:
        """Check if a node exists."""
        if not self.__driver:
            raise RuntimeError("Driver not started.")
        cypher_query = f"""
        MATCH (n:{type} {{entity: $entity}})
        RETURN n LIMIT 1
        """
        with self.__driver.session() as session:
            result = session.run(cypher_query, entity=entity)
            return result.single() is not None

    def list_nodes(self, type: str | None = None):
        """
        Return all node entities, optionally filtered by label type.
        
        Args:
            type (str | None): Optional label type (e.g., 'Person', 'Company').
                            If None, returns all nodes.
        Returns:
            list[dict]: A list of {'entity': str, 'labels': list[str]} for each node.
        """
        if not self.__driver:
            raise RuntimeError("Driver not started.")

        if type:
            cypher_query = f"""
            MATCH (n:{type})
            RETURN labels(n) AS labels, n.entity AS entity
            """
            params = {}
        else:
            cypher_query = """
            MATCH (n)
            RETURN labels(n) AS labels, n.entity AS entity
            """
            params = {}

        with self.__driver.session() as session:
            result = session.run(cypher_query, **params)
            return [
                {"entity": record["entity"], "labels": record["labels"]}
                for record in result
                if record["entity"] is not None
            ]


    def update_relationship(
        self,
        entity1_type: str,
        entity1: str,
        entity2_type: str,
        entity2: str,
        relationship: str,
        strength: float,
    ):
        """
        Create or update a directional relationship between two nodes.
        Dynamically handles different node types (labels).
        """
        if not self.__driver:
            raise RuntimeError("Driver not started.")
        
        cypher_query = f"""
        MERGE (a:{entity1_type} {{entity: $entity1}})
        MERGE (b:{entity2_type} {{entity: $entity2}})
        MERGE (a)-[r:RELATED_TO]->(b)
        SET r.relationship = $relationship,
            r.strength = $strength
        RETURN a.entity AS from_node, 
            b.entity AS to_node, 
            r.relationship AS relationship, 
            r.strength AS strength
        """

        with self.__driver.session() as session:
            result = session.run(
                cypher_query,
                entity1=entity1,
                entity2=entity2,
                relationship=relationship,
                strength=strength,
            )
            record = result.single()
            return record.data() if record else None


    def get_relationship(
        self,
        entity1_type: str,
        entity1: str,
        entity2_type: str,
        entity2: str,
        relationship: str,
    ):
        """
        Get details for a specific relationship (with given 'relationship' property)
        between two nodes of specified types.
        """
        if not self.__driver:
            raise RuntimeError("Driver not started.")
        
        cypher_query = f"""
        MATCH (a:{entity1_type} {{entity: $entity1}})-[r:RELATED_TO]->(b:{entity2_type} {{entity: $entity2}})
        WHERE r.relationship = $relationship
        RETURN r.strength AS strength
        """
        with self.__driver.session() as session:
            record = session.run(
                cypher_query,
                entity1=entity1,
                entity2=entity2,
                relationship=relationship,
            ).single()
            return record.data() if record else None


    def relationship_exists(
        self,
        entity1_type: str,
        entity1: str,
        entity2_type: str,
        entity2: str,
        relationship: str,
    ) -> bool:
        """
        Check if a specific relationship (with given 'relationship' property)
        exists between two nodes of specified types.
        """
        if not self.__driver:
            raise RuntimeError("Driver not started.")
        
        cypher_query = f"""
        MATCH (a:{entity1_type} {{entity: $entity1}})-[r:RELATED_TO]->(b:{entity2_type} {{entity: $entity2}})
        WHERE r.relationship = $relationship
        RETURN COUNT(r) > 0 AS exists
        """
        with self.__driver.session() as session:
            record = session.run(
                cypher_query,
                entity1=entity1,
                entity2=entity2,
                relationship=relationship,
            ).single()
            return record["exists"] if record else False


    def list_relationships(self, entity_type: str, entity: str):
        """
        List all outgoing and incoming relationships for a given node type and entity.
        Returns both connected node labels and relationship details.
        """
        if not self.__driver:
            raise RuntimeError("Driver not started.")
        
        cypher_query = f"""
        MATCH (n:{entity_type} {{entity: $entity}})-[r:RELATED_TO]-(m)
        RETURN 
            labels(m) AS connected_labels,
            m.entity AS connected_node, 
            r.relationship AS relationship, 
            r.strength AS strength
        """
        with self.__driver.session() as session:
            result = session.run(cypher_query, entity=entity)
            return [
                {
                    "connected_node": record["connected_node"],
                    "connected_labels": record["connected_labels"],
                    "relationship": record["relationship"],
                    "strength": record["strength"],
                }
                for record in result
                if record["connected_node"] is not None
            ]


    def clear(self):
        """Remove all nodes and relationships."""
        if not self.__driver:
            raise RuntimeError("Driver not started.")
        with self.__driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
