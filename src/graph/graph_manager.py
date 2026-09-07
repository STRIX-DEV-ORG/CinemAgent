import structlog
from typing import List, Dict, Any, Optional
from src.db.clickhouse_client import get_clickhouse_client
from src.db.schemas import KGNode, KGEdge

logger = structlog.get_logger(__name__)

class GraphManager:
    """
    Manages Knowledge Graph construction, insertion, and traversal in ClickHouse.
    """
    def __init__(self):
        try:
            self.client = get_clickhouse_client()
        except Exception as e:
            logger.warn("GraphManager running in offline/disconnected mode", error=str(e))\
            self.client = None

    def add_node(self, node: KGNode) -> None:
        """
        Insert or update a node in the Knowledge Graph.
        """
        logger.info("Adding node to Knowledge Graph", node_id=node.id, name=node.name)
        try:
            # We map properties to Dict(String, String) or Map(String, String)
            data = [[
                node.id,
                node.name,
                node.type,
                node.description,
                node.embedding or [],
                node.properties,
                node.updated_at
            ]]
            self.client.insert(
                'kg_nodes',
                data,
                column_names=['id', 'name', 'type', 'description', 'embedding', 'properties', 'updated_at']
            )
        except Exception as e:
            logger.error("Failed to add node to ClickHouse", node_id=node.id, error=str(e))
            raise e

    def add_edge(self, edge: KGEdge) -> None:
        """
        Insert a new relation edge in the Knowledge Graph.
        """
        logger.info("Adding edge to Knowledge Graph", source=edge.source_id, relation=edge.relation, target=edge.target_id)
        try:
            data = [[
                edge.id,
                edge.source_id,
                edge.target_id,
                edge.relation,
                edge.description,
                edge.weight,
                edge.properties,
                edge.updated_at
            ]]
            self.client.insert(
                'kg_edges',
                data,
                column_names=['id', 'source_id', 'target_id', 'relation', 'description', 'weight', 'properties', 'updated_at']
            )
        except Exception as e:
            logger.error("Failed to add edge to ClickHouse", edge_id=edge.id, error=str(e))
            raise e

    def get_node(self, node_id: str) -> Optional[KGNode]:
        """
        Fetch a node by its unique ID.
        """
        query = "SELECT id, name, type, description, embedding, properties, updated_at FROM kg_nodes WHERE id = %s"
        result = self.client.query(query, parameters=[node_id])
        if not result.result_rows:
            return None
        
        row = result.result_rows[0]
        return KGNode(
            id=row[0],
            name=row[1],
            type=row[2],
            description=row[3],
            embedding=row[4],
            properties=row[5]
        )

    def get_neighbors(self, node_id: str) -> List[Dict[str, Any]]:
        """
        Get all one-hop outgoing relations and target nodes for a given node.
        """
        query = """
        SELECT 
            e.relation, 
            e.description, 
            e.weight, 
            n.id, 
            n.name, 
            n.type
        FROM kg_edges e
        JOIN kg_nodes n ON e.target_id = n.id
        WHERE e.source_id = %s
        """
        try:
            result = self.client.query(query, parameters=[node_id])
            neighbors = []
            for row in result.result_rows:
                neighbors.append({
                    "relation": row[0],
                    "relation_description": row[1],
                    "weight": row[2],
                    "target_id": row[3],
                    "target_name": row[4],
                    "target_type": row[5]
                })
            return neighbors
        except Exception as e:
            logger.error("Failed to fetch graph neighbors", node_id=node_id, error=str(e))
            return []

    def get_graph_neighborhood_context(self, entity_names: List[str]) -> str:
        """
        Builds a textual representation of the sub-graph matching the query entities.
        This string context will be injected directly into the RAG system prompt.
        """
        if not entity_names or not self.client:
            return "No Graph relations found."

        logger.info("Building subgraph context for entities", entities=entity_names)
        
        context_parts = []
        for entity in entity_names:
            # Query nodes containing entity name in ID or Name
            query_nodes = """
            SELECT id, name, type, description FROM kg_nodes 
            WHERE id = {entity:String} OR name ILIKE {entity_pattern:String}
            LIMIT 5
            """
            params = {
                "entity": entity,
                "entity_pattern": f"%{entity}%"
            }
            nodes_result = self.client.query(query_nodes, parameters=params)
            
            for row in nodes_result.result_rows:
                node_id, node_name, node_type, node_desc = row
                context_parts.append(f"Entity: {node_name} ({node_type}) - {node_desc or 'No description'}")
                
                # Fetch its neighbors
                neighbors = self.get_neighbors(node_id)
                if neighbors:
                    context_parts.append(f"  Relations for {node_name}:")
                    for neb in neighbors:
                        context_parts.append(
                            f"    - [{node_name}] --({neb['relation']})--> [{neb['target_name']}] ({neb['target_type']})"
                        )
        
        return "\n".join(context_parts) if context_parts else "No matching subgraphs found in ClickHouse."
