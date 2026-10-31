"""In-memory MongoDB mock for fast, isolated unit and cascade testing.

Complies with AGENTS.md Rule 5: Every function in Sections 6 and 7 must be
importable and testable without a running API server or live database.
"""

from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional


class MockCollection:
    def __init__(self, name: str):
        self.name = name
        self.docs: Dict[str, Dict[str, Any]] = {}

    def insert_one(self, doc: Dict[str, Any]) -> Any:
        d = deepcopy(doc)
        if "_id" not in d:
            d["_id"] = str(len(self.docs) + 1)
        self.docs[d["_id"]] = d
        return type("InsertResult", (), {"inserted_id": d["_id"]})()

    def insert_many(self, docs: List[Dict[str, Any]]) -> Any:
        ids = []
        for doc in docs:
            res = self.insert_one(doc)
            ids.append(res.inserted_id)
        return type("InsertManyResult", (), {"inserted_ids": ids})()

    def drop(self) -> None:
        self.docs.clear()

    def _matches(self, doc: Dict[str, Any], query: Dict[str, Any]) -> bool:
        for k, v in query.items():
            if k == "$and":
                if not all(self._matches(doc, cond) for cond in v):
                    return False
                continue

            doc_val = doc.get(k)

            if isinstance(v, dict):
                for op, op_val in v.items():
                    if op == "$gt":
                        if doc_val is None or not (doc_val > op_val):
                            return False
                    elif op == "$gte":
                        if doc_val is None or not (doc_val >= op_val):
                            return False
                    elif op == "$lt":
                        if doc_val is None or not (doc_val < op_val):
                            return False
                    elif op == "$lte":
                        if doc_val is None or not (doc_val <= op_val):
                            return False
                    elif op == "$in":
                        if isinstance(doc_val, list):
                            if not any(item in op_val for item in doc_val):
                                return False
                        else:
                            if doc_val not in op_val:
                                return False
                    elif op == "$ne":
                        if doc_val == op_val:
                            return False
                    elif op == "$exists":
                        exists = k in doc
                        if exists != op_val:
                            return False
            else:
                if isinstance(doc_val, list):
                    if v not in doc_val:
                        return False
                else:
                    if doc_val != v:
                        return False
        return True

    def find_one(self, query: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        results = self.find(query)
        return results[0] if results else None

    def find(self, query: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if not query:
            return [deepcopy(d) for d in self.docs.values()]
        return [deepcopy(d) for d in self.docs.values() if self._matches(d, query)]

    def update_one(self, filter_q: Dict[str, Any], update: Dict[str, Any], upsert: bool = False) -> Any:
        matched = [d for d in self.docs.values() if self._matches(d, filter_q)]
        if not matched:
            if upsert:
                new_doc = deepcopy(filter_q)
                self._apply_update(new_doc, update)
                self.insert_one(new_doc)
                return type("UpdateResult", (), {"matched_count": 0, "modified_count": 1})()
            return type("UpdateResult", (), {"matched_count": 0, "modified_count": 0})()

        doc = matched[0]
        self._apply_update(doc, update)
        return type("UpdateResult", (), {"matched_count": 1, "modified_count": 1})()

    def update_many(self, filter_q: Dict[str, Any], update: Dict[str, Any]) -> Any:
        matched = [d for d in self.docs.values() if self._matches(d, filter_q)]
        for doc in matched:
            self._apply_update(doc, update)
        return type("UpdateResult", (), {"matched_count": len(matched), "modified_count": len(matched)})()

    def _apply_update(self, doc: Dict[str, Any], update: Dict[str, Any]) -> None:
        if "$set" in update:
            for k, v in update["$set"].items():
                doc[k] = deepcopy(v)
        if "$inc" in update:
            for k, v in update["$inc"].items():
                doc[k] = doc.get(k, 0) + v
        if "$push" in update:
            for k, v in update["$push"].items():
                if k not in doc or not isinstance(doc[k], list):
                    doc[k] = []
                doc[k].append(deepcopy(v))
        if "$addToSet" in update:
            for k, v in update["$addToSet"].items():
                if k not in doc or not isinstance(doc[k], list):
                    doc[k] = []
                if v not in doc[k]:
                    doc[k].append(deepcopy(v))
        if "$unset" in update:
            for k in update["$unset"]:
                doc.pop(k, None)

    def aggregate(self, pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results = [deepcopy(d) for d in self.docs.values()]
        for stage in pipeline:
            if "$match" in stage:
                results = [d for d in results if self._matches(d, stage["$match"])]
            elif "$graphLookup" in stage:
                gl = stage["$graphLookup"]
                from_coll_name = gl["from"]
                start_with_field = gl["startWith"].lstrip("$")
                connect_from = gl["connectFromField"]
                connect_to = gl["connectToField"]
                as_field = gl["as"]

                from_coll = self.db[from_coll_name]
                for r in results:
                    start_val = r.get(start_with_field, [])
                    if not isinstance(start_val, list):
                        start_val = [start_val]
                    visited = set()
                    queue = list(start_val)
                    dependents = []
                    while queue:
                        curr = queue.pop(0)
                        if curr in visited:
                            continue
                        visited.add(curr)
                        found = from_coll.find({connect_to: curr})
                        for f in found:
                            dependents.append(f)
                            nxt = f.get(connect_from, [])
                            if not isinstance(nxt, list):
                                nxt = [nxt]
                            for n in nxt:
                                if n not in visited:
                                    queue.append(n)
                    r[as_field] = dependents
        return results


class MockDatabase:
    def __init__(self, name: str = "metrologic"):
        self.name = name
        self.collections: Dict[str, MockCollection] = {}

    def __getitem__(self, name: str) -> MockCollection:
        if name not in self.collections:
            coll = MockCollection(name)
            coll.db = self
            self.collections[name] = coll
        return self.collections[name]

    def __getattr__(self, name: str) -> MockCollection:
        return self[name]

    def list_collection_names(self) -> List[str]:
        return list(self.collections.keys())

    def create_collection(self, name: str) -> MockCollection:
        return self[name]

    def command(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        return {"ok": 1}

