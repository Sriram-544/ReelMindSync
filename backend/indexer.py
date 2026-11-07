"""
indexer.py — ChromaDB vector indexing for ReelMind.

Loads processed JSON files, generates sentence embeddings,
and stores them in a local ChromaDB collection for semantic search.
"""

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Callable, Optional


def _tokenize(text: str) -> list[str]:
    return [w.lower() for w in re.findall(r"\w+", text) if len(w) > 1]


class SimpleBM25:
    """Lightweight in-memory Okapi BM25 for hybrid search."""
    def __init__(self, corpus_docs: list[dict], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs = corpus_docs
        self.corpus_size = len(corpus_docs)
        self.tokenized_corpus = [_tokenize(d["text"]) for d in corpus_docs]
        self.doc_lens = [len(doc) for doc in self.tokenized_corpus]
        self.avgdl = (sum(self.doc_lens) / self.corpus_size) if self.corpus_size > 0 else 1.0

        self.df = Counter()
        for doc in self.tokenized_corpus:
            for term in set(doc):
                self.df[term] += 1

        self.idf = {}
        for term, freq in self.df.items():
            self.idf[term] = math.log(1 + (self.corpus_size - freq + 0.5) / (freq + 0.5))

    def score(self, query: str) -> list[tuple[float, dict]]:
        query_terms = _tokenize(query)
        if not query_terms or self.corpus_size == 0:
            return []

        scores = [0.0] * self.corpus_size
        for term in query_terms:
            if term not in self.idf:
                continue
            idf_val = self.idf[term]
            for idx, doc in enumerate(self.tokenized_corpus):
                count = doc.count(term)
                if count == 0:
                    continue
                num = count * (self.k1 + 1)
                den = count + self.k1 * (1 - self.b + self.b * (self.doc_lens[idx] / self.avgdl))
                scores[idx] += idf_val * (num / den)

        results = [(scores[i], self.docs[i]) for i in range(self.corpus_size) if scores[i] > 0]
        results.sort(key=lambda x: x[0], reverse=True)
        return results


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

    # ── Hybrid search (BM25 + Semantic ChromaDB) ──────────────────────────────
    def search_hybrid(self, query: str, k: int = 5, where: Optional[dict] = None) -> list[dict]:
        """
        Hybrid search combining BM25 keyword matching and ChromaDB dense embeddings
        using Reciprocal Rank Fusion (RRF).
        """
        total_count = self.count()
        if total_count == 0:
            return []

        col = self._get_collection()
        fetch_limit = min(max(k * 3, 20), total_count)

        # 1. Dense Semantic Retrieval
        dense_hits = []
        try:
            model = self._get_embed_model()
            q_emb = model.encode(query).tolist()
            query_kwargs = {
                "query_embeddings": [q_emb],
                "n_results": fetch_limit,
                "include": ["documents", "metadatas", "distances"],
            }
            if where:
                query_kwargs["where"] = where

            dense_res = col.query(**query_kwargs)
            if dense_res and dense_res.get("ids") and dense_res["ids"][0]:
                for doc_id, doc, meta, dist in zip(
                    dense_res["ids"][0],
                    dense_res["documents"][0],
                    dense_res["metadatas"][0],
                    dense_res["distances"][0],
                ):
                    dense_hits.append({
                        "id": doc_id,
                        "content": doc,
                        "metadata": meta,
                        "score": round(1 - dist, 4),
                    })
        except Exception as e:
            print(f"[HybridSearch] Dense search error: {e}")

        # 2. Sparse / Lexical Retrieval via BM25
        sparse_hits = []
        try:
            get_kwargs = {"include": ["documents", "metadatas"]}
            if where:
                get_kwargs["where"] = where
            all_records = col.get(**get_kwargs)
            if all_records and all_records.get("ids"):
                corpus = []
                for doc_id, doc, meta in zip(
                    all_records["ids"],
                    all_records["documents"],
                    all_records["metadatas"],
                ):
                    meta_dict = meta or {}
                    combined_text = f"{meta_dict.get('caption', '')} {meta_dict.get('username', '')} {doc}"
                    corpus.append({
                        "id": doc_id,
                        "content": doc,
                        "metadata": meta_dict,
                        "text": combined_text,
                    })

                bm25 = SimpleBM25(corpus)
                bm25_scored = bm25.score(query)
                for score, item in bm25_scored[:fetch_limit]:
                    sparse_hits.append({
                        "id": item["id"],
                        "content": item["content"],
                        "metadata": item["metadata"],
                        "score": score,
                    })
        except Exception as e:
            print(f"[HybridSearch] BM25 search error: {e}")

        # 3. Reciprocal Rank Fusion (RRF)
        rrf_k = 60
        fused_scores: dict[str, float] = {}
        items_map: dict[str, dict] = {}

        for rank, hit in enumerate(dense_hits):
            doc_id = hit["id"]
            fused_scores[doc_id] = fused_scores.get(doc_id, 0.0) + (1.0 / (rrf_k + rank + 1))
            items_map[doc_id] = hit

        for rank, hit in enumerate(sparse_hits):
            doc_id = hit["id"]
            fused_scores[doc_id] = fused_scores.get(doc_id, 0.0) + (1.0 / (rrf_k + rank + 1))
            if doc_id not in items_map:
                items_map[doc_id] = hit

        sorted_ids = sorted(fused_scores.keys(), key=lambda x: fused_scores[x], reverse=True)
        final_results = []
        for doc_id in sorted_ids[:k]:
            item = items_map[doc_id]
            final_results.append({
                "content": item["content"],
                "metadata": item["metadata"],
                "score": round(fused_scores[doc_id], 4),
            })

        return final_results


# ── Helpers ──────────────────────────────────────────────────────────────────
def _report(cb, current, total, msg=""):
    if cb:
        cb(current, total, msg)
    else:
        print(f"[Index] {msg} ({current}/{total})")
