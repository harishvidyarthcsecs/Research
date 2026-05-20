"""
Memory store for the research system - manages persistent storage and retrieval.
Uses JSON-only serialization (no pickle) for stability across Python versions.
"""
import json
import os
from typing import Any, Dict, List, Optional
from datetime import datetime
import asyncio
from pathlib import Path

from ..models.data_models import KnowledgeNode, KnowledgeEdge


class _JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return {"__datetime__": obj.isoformat()}
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        return super().default(obj)


def _json_decoder(dct):
    if "__datetime__" in dct:
        return datetime.fromisoformat(dct["__datetime__"])
    return dct


class MemoryStore:
    """Persistent memory store for research data using JSON serialization."""

    def __init__(self, storage_path: str = "data/memory"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.cache: Dict[str, Any] = {}
        self.knowledge_graph: Dict[str, KnowledgeNode] = {}
        self.edges: List[KnowledgeEdge] = []
        self._loaded = False

    async def _ensure_loaded(self):
        if not self._loaded:
            await self._load_persistent_data()
            self._loaded = True

    async def store(self, key: str, data: Any) -> None:
        await self._ensure_loaded()
        self.cache[key] = data
        await self._persist_data(key, data)

    async def retrieve(self, key: str) -> Optional[Any]:
        await self._ensure_loaded()
        if key in self.cache:
            return self.cache[key]
        data = await self._load_data(key)
        if data is not None:
            self.cache[key] = data
        return data

    async def store_knowledge_node(self, node: KnowledgeNode) -> None:
        await self._ensure_loaded()
        self.knowledge_graph[node.id] = node
        await self._persist_knowledge_graph()

    async def store_knowledge_edge(self, edge: KnowledgeEdge) -> None:
        await self._ensure_loaded()
        self.edges.append(edge)
        await self._persist_knowledge_graph()

    async def get_knowledge_node(self, node_id: str) -> Optional[KnowledgeNode]:
        await self._ensure_loaded()
        return self.knowledge_graph.get(node_id)

    async def get_related_nodes(self, node_id: str, relationship: str = None) -> List[KnowledgeNode]:
        await self._ensure_loaded()
        related = []
        for edge in self.edges:
            if edge.source_id == node_id:
                if relationship is None or edge.relationship == relationship:
                    node = self.knowledge_graph.get(edge.target_id)
                    if node:
                        related.append(node)
            elif edge.target_id == node_id:
                if relationship is None or edge.relationship == relationship:
                    node = self.knowledge_graph.get(edge.source_id)
                    if node:
                        related.append(node)
        return related

    async def search_nodes(self, node_type: str = None, **filters) -> List[KnowledgeNode]:
        await self._ensure_loaded()
        results = []
        for node in self.knowledge_graph.values():
            if node_type and node.type != node_type:
                continue
            match = all(
                key in node.data and node.data[key] == value
                for key, value in filters.items()
            )
            if match:
                results.append(node)
        return results

    async def check_paper_processed(self, paper_id: str) -> bool:
        """Return True if this paper has already been processed in a prior session."""
        await self._ensure_loaded()
        return f"paper_{paper_id}" in self.cache

    async def clear_cache(self) -> None:
        self.cache.clear()

    async def get_cache_stats(self) -> Dict[str, Any]:
        await self._ensure_loaded()
        return {
            "cache_size": len(self.cache),
            "knowledge_nodes": len(self.knowledge_graph),
            "knowledge_edges": len(self.edges),
            "storage_path": str(self.storage_path),
        }

    # ------------------------------------------------------------------ #
    # Private helpers                                                       #
    # ------------------------------------------------------------------ #

    async def _persist_data(self, key: str, data: Any) -> None:
        safe_key = key.replace("/", "_").replace("\\", "_")
        file_path = self.storage_path / f"{safe_key}.json"
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, cls=_JSONEncoder)
        except Exception as e:
            print(f"[MemoryStore] Error persisting key '{key}': {e}")

    async def _load_data(self, key: str) -> Optional[Any]:
        safe_key = key.replace("/", "_").replace("\\", "_")
        json_path = self.storage_path / f"{safe_key}.json"
        if json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    return json.load(f, object_hook=_json_decoder)
            except Exception as e:
                print(f"[MemoryStore] Error loading key '{key}': {e}")
        return None

    async def _persist_knowledge_graph(self) -> None:
        try:
            nodes_data = {
                nid: {
                    "id": node.id,
                    "type": node.type,
                    "data": node.data,
                    "created_at": node.created_at.isoformat(),
                }
                for nid, node in self.knowledge_graph.items()
            }
            with open(self.storage_path / "knowledge_nodes.json", "w", encoding="utf-8") as f:
                json.dump(nodes_data, f, indent=2, default=str)

            edges_data = [
                {
                    "source_id": e.source_id,
                    "target_id": e.target_id,
                    "relationship": e.relationship,
                    "weight": e.weight,
                    "metadata": e.metadata,
                }
                for e in self.edges
            ]
            with open(self.storage_path / "knowledge_edges.json", "w", encoding="utf-8") as f:
                json.dump(edges_data, f, indent=2, default=str)
        except Exception as e:
            print(f"[MemoryStore] Error persisting knowledge graph: {e}")

    async def _load_persistent_data(self) -> None:
        try:
            nodes_path = self.storage_path / "knowledge_nodes.json"
            if nodes_path.exists():
                with open(nodes_path, "r", encoding="utf-8") as f:
                    nodes_data = json.load(f)
                for nid, nd in nodes_data.items():
                    node = KnowledgeNode(
                        id=nd["id"],
                        type=nd["type"],
                        data=nd["data"],
                        created_at=datetime.fromisoformat(nd["created_at"]),
                    )
                    self.knowledge_graph[nid] = node

            edges_path = self.storage_path / "knowledge_edges.json"
            if edges_path.exists():
                with open(edges_path, "r", encoding="utf-8") as f:
                    edges_data = json.load(f)
                for ed in edges_data:
                    edge = KnowledgeEdge(
                        source_id=ed["source_id"],
                        target_id=ed["target_id"],
                        relationship=ed["relationship"],
                        weight=ed["weight"],
                        metadata=ed["metadata"],
                    )
                    self.edges.append(edge)
        except Exception as e:
            print(f"[MemoryStore] Error loading persistent data: {e}")
