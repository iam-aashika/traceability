import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.config import settings

logger = logging.getLogger(__name__)

class JsonDocumentStore:
    """
    Lightweight, ACID-compliant JSON document store for LLM-generated test cases.
    Persists immutable generations under storage/generations/ with index lookups.
    Zero external daemon dependency ensures immediate portability and reliability.
    """
    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or settings.GENERATIONS_STORAGE_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._index_file = self.base_dir / "_index.json"
        self._ensure_index()

    def _ensure_index(self):
        if not self._index_file.exists():
            with open(self._index_file, "w", encoding="utf-8") as f:
                json.dump({"by_id": {}, "by_selection": {}, "by_node": {}}, f)

    def _read_index(self) -> Dict[str, Any]:
        try:
            with open(self._index_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"by_id": {}, "by_selection": {}, "by_node": {}}

    def _write_index(self, index: Dict[str, Any]):
        temp_file = self.base_dir / "_index.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)
        temp_file.replace(self._index_file)

    def save_generation(self, generation_data: Dict[str, Any]) -> str:
        """Save a new generation document and update indexes."""
        gen_id = generation_data["generation_id"]
        doc_path = self.base_dir / f"{gen_id}.json"

        # Format datetimes
        def serialize_helper(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            return str(obj)

        with open(doc_path, "w", encoding="utf-8") as f:
            json.dump(generation_data, f, default=serialize_helper, indent=2)

        # Update index
        index = self._read_index()
        index["by_id"][gen_id] = str(doc_path)
        
        sel_id = generation_data.get("selection_id")
        if sel_id:
            if sel_id not in index["by_selection"]:
                index["by_selection"][sel_id] = []
            index["by_selection"][sel_id].append(gen_id)

        for node_id in generation_data.get("source_node_ids", []):
            if node_id not in index["by_node"]:
                index["by_node"][node_id] = []
            if gen_id not in index["by_node"][node_id]:
                index["by_node"][node_id].append(gen_id)

        self._write_index(index)
        return gen_id

    def get_by_id(self, generation_id: str) -> Optional[Dict[str, Any]]:
        doc_path = self.base_dir / f"{generation_id}.json"
        if not doc_path.exists():
            return None
        with open(doc_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_by_selection_id(self, selection_id: str) -> List[Dict[str, Any]]:
        index = self._read_index()
        gen_ids = index.get("by_selection", {}).get(selection_id, [])
        results = []
        for gid in gen_ids:
            doc = self.get_by_id(gid)
            if doc:
                results.append(doc)
        return results

    def get_by_node_id(self, node_id: str) -> List[Dict[str, Any]]:
        index = self._read_index()
        gen_ids = index.get("by_node", {}).get(node_id, [])
        results = []
        for gid in gen_ids:
            doc = self.get_by_id(gid)
            if doc:
                results.append(doc)
        return results

doc_store = JsonDocumentStore()
