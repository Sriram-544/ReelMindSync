"""
indexer.py — ChromaDB vector indexing for ReelMind.

Loads processed JSON files, generates sentence embeddings,
and stores them in a local ChromaDB collection for semantic search.
"""

import json
from pathlib import Path
from typing import Callable, Optional


class ReelIndexer:
    COLLECTION_NAME = "reels"

    def __init__(self, index_dir: str):
        self.index_dir = index_dir
        self._client = None
        self._collection = None
        self._embed_model = None

    # ── Lazy initializers ─────────────────────────────────────────────────────
    def _get_client(self):
        if self._client is None:
            import chromadb
            self._client = chromadb.PersistentClient(path=self.index_dir)
        return self._client

    def _get_collection(self):
        if self._collection is None:
            client = self._get_client()
            self._collection = client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def _get_embed_model(self):
        if self._embed_model is None:
            from sentence_transformers import SentenceTransformer
            self._embed_model = SentenceTransformer("all-MiniLM-L6-v2")
        return self._embed_model

    # ── Count ─────────────────────────────────────────────────────────────────
    def count(self) -> int:
        try:
            return self._get_collection().count()
        except Exception:
            return 0

    # ── List reels ────────────────────────────────────────────────────────────
    def list_reels(self) -> list[dict]:
        """Returns metadata for all indexed reels, newest first."""
        try:
            col = self._get_collection()
            results = col.get(include=["metadatas"])
            metas = results.get("metadatas", [])
            # Sort by timestamp descending (newest first)
            metas.sort(key=lambda m: m.get("timestamp", ""), reverse=True)
            return metas
        except Exception:
            return []

    def index_one(self, json_file: Path) -> bool:
        """Indexes a single JSON file into ChromaDB. Returns True if successful."""
        if not json_file.exists():
            return False

        shortcode = json_file.stem
        model = self._get_embed_model()
        col = self._get_collection()
        
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            content = data.get("content", "")
            if not content.strip():
                return False

            metadata = {
                "shortcode":  shortcode,
                "filename":   data.get("filename", f"{shortcode}.mp4"),
                "caption":    data.get("caption", "")[:500],
                "timestamp":  str(data.get("timestamp", "")),
                "username":   data.get("username", ""),
                "like_count": str(data.get("like_count", 0)),
                "thumbnail":  data.get("thumbnail") or "",
            }

            existing = col.get(ids=[shortcode], include=[])
            if existing and existing["ids"]:
                col.update(ids=[shortcode], metadatas=[metadata])
                return True
            
            embedding = model.encode(content).tolist()
            col.add(
                ids=[shortcode],
                embeddings=[embedding],
                documents=[content],
                metadatas=[metadata]
            )
            return True
        except Exception as e:
            print(f"[Indexer] Failed to index {shortcode}: {e}")
            return False

    # ── Batch index ───────────────────────────────────────────────────────────
    def index_all(
        self,
        processed_dir: str,
        progress_cb: Optional[Callable[[int, int, str], None]] = None,
    ) -> int:
        """
        Indexes all processed JSON files that aren't already in ChromaDB.
        Returns number of newly indexed reels.
        """
        processed_path = Path(processed_dir)
        json_files = sorted(processed_path.glob("*.json"))
        total = len(json_files)

        if total == 0:
            _report(progress_cb, 0, 0, "No processed files to index.")
            return 0

        _report(progress_cb, 0, total, "Loading embedding model…")
        model = self._get_embed_model()
        col = self._get_collection()

        # Get already-indexed IDs
        existing = set(col.get(include=[])["ids"])

        indexed = 0
        for i, json_file in enumerate(json_files):
            shortcode = json_file.stem

            if shortcode in existing:
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    col.update(
                        ids=[shortcode],
                        metadatas=[{
                            "shortcode":  shortcode,
                            "filename":   data.get("filename", f"{shortcode}.mp4"),
                            "caption":    data.get("caption", "")[:500],
                            "timestamp":  str(data.get("timestamp", "")),
                            "username":   data.get("username", ""),
                            "like_count": str(data.get("like_count", 0)),
                            "thumbnail":  data.get("thumbnail") or "",
                        }]
                    )
                except Exception as e:
                    pass
                indexed += 1
                _report(progress_cb, indexed, total,
                        f"Updated metadata (already indexed): {shortcode}")
                continue

            _report(progress_cb, indexed, total,
                    f"Indexing {i + 1}/{total}: {shortcode}")

            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                content = data.get("content", "")
                if not content.strip():
                    continue

                embedding = model.encode(content).tolist()

                col.add(
                    ids=[shortcode],
                    embeddings=[embedding],
                    documents=[content],
                    metadatas=[{
                        "shortcode":  shortcode,
                        "filename":   data.get("filename", f"{shortcode}.mp4"),
                        "caption":    data.get("caption", "")[:500],  # ChromaDB meta limit
                        "timestamp":  data.get("timestamp", ""),
                        "username":   data.get("username", ""),
                        "like_count": str(data.get("like_count", 0)),
                        "thumbnail":  data.get("thumbnail") or "",
                    }],
                )
                indexed += 1
            except Exception as e:
                print(f"[Indexer] Warning: failed to index {shortcode}: {e}")
                indexed += 1

        _report(progress_cb, total, total,
                f"Indexing complete — {indexed} reels in database")
        return indexed

    # ── Semantic search ───────────────────────────────────────────────────────
    def search(self, query: str, k: int = 5) -> list[dict]:
        """Returns top-k most semantically similar reels for a query."""
        model = self._get_embed_model()
        query_embedding = model.encode(query).tolist()

        results = self._get_collection().query(
            query_embeddings=[query_embedding],
            n_results=min(k, self.count()),
            include=["documents", "metadatas", "distances"],
        )

        hits = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            hits.append({
                "content":   doc,
                "metadata":  meta,
                "score":     round(1 - dist, 4),  # cosine similarity
            })
        return hits


# ── Helpers ──────────────────────────────────────────────────────────────────
def _report(cb, current, total, msg=""):
    if cb:
        cb(current, total, msg)
    else:
        print(f"[Index] {msg} ({current}/{total})")
