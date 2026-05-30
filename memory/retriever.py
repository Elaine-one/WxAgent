import logging
import time

import chromadb
import yaml

from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from config import EMBEDDING_MODEL_PATH, PROJECT_ROOT, WORKSPACE_DIR

_local_model = str(EMBEDDING_MODEL_PATH) if EMBEDDING_MODEL_PATH.exists() else "BAAI/bge-small-zh"
_embedding_fn = SentenceTransformerEmbeddingFunction(model_name=_local_model)

logger = logging.getLogger(__name__)


class MemoryRetriever:
    def __init__(self, db_path: str | None = None):
        cfg = self._load_config()
        self.vector_w = cfg.get("vector_weight", 0.5)
        self.keyword_w = cfg.get("keyword_weight", 0.3)
        self.time_w = cfg.get("time_decay_weight", 0.2)
        self.half_life_days = cfg.get("time_decay_half_life_days", 30)
        self.default_scope = cfg.get("default_scope", ["files", "facts"])
        self.default_top_k = cfg.get("default_top_k", 10)

        path = db_path or str(WORKSPACE_DIR / "data" / "chroma")
        from chromadb.config import Settings
        self.client = chromadb.PersistentClient(
            path=path, settings=Settings(anonymized_telemetry=False),
        )

    def _load_config(self) -> dict:
        try:
            with open(PROJECT_ROOT / "config.yaml", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            return cfg.get("retriever", {})
        except Exception:
            return {}

    def search(self, query: str, scope: list[str] | None = None,
               top_k: int | None = None, user_id: str | None = None) -> list[dict]:
        if scope is None:
            scope = list(self.default_scope)
        if top_k is None:
            top_k = self.default_top_k

        all_results = []
        tokens = self._tokenize(query)

        for col_name in scope:
            try:
                col = self.client.get_collection(col_name, embedding_function=_embedding_fn)
                where_filter = {"user_id": user_id} if user_id else None
                r = col.query(
                    query_texts=[query], n_results=top_k,
                    where=where_filter,
                )
                for doc, meta, dist in zip(
                    r["documents"][0], r["metadatas"][0], r["distances"][0],
                ):
                    vector_score = max(1.0 - dist, 0.0)
                    keyword_score = self._keyword_match(tokens, doc)
                    time_score = self._time_decay(meta)
                    combined = (
                        vector_score * self.vector_w
                        + keyword_score * self.keyword_w
                        + time_score * self.time_w
                    )
                    all_results.append({
                        "collection": col_name,
                        "score": round(combined, 3),
                        "content": doc[:200],
                        "metadata": meta,
                    })
            except Exception as e:
                logger.debug("检索 collection %s 失败: %s", col_name, e)
                continue

        all_results.sort(key=lambda x: x["score"], reverse=True)
        return all_results[:top_k]

    def _tokenize(self, text: str) -> list[str]:
        try:
            import jieba
            return [t for t in jieba.cut(text) if t.strip()]
        except ImportError:
            return text.split()

    def _keyword_match(self, tokens: list[str], doc: str) -> float:
        if not tokens:
            return 0.0
        doc_lower = doc.lower()
        hits = sum(1 for t in tokens if t.lower() in doc_lower)
        return min(hits / len(tokens), 1.0)

    def _time_decay(self, metadata: dict) -> float:
        ts = metadata.get("timestamp") or metadata.get("created_at")
        if not ts:
            return 0.5
        try:
            age_days = (time.time() - float(ts)) / 86400
            return 0.5 ** (age_days / self.half_life_days)
        except (ValueError, TypeError):
            return 0.5
