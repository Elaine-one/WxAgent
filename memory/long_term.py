import time

from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from config import EMBEDDING_MODEL_PATH, WORKSPACE_DIR

_local_model = str(EMBEDDING_MODEL_PATH) if EMBEDDING_MODEL_PATH.exists() else "BAAI/bge-small-zh"
_embedding_fn = SentenceTransformerEmbeddingFunction(model_name=_local_model)


class LongTermMemory:
    def __init__(self, db_path: str | None = None):
        if db_path is None:
            db_path = str(WORKSPACE_DIR / "data" / "chroma")
        try:
            import chromadb
            from chromadb.config import Settings
            self.client = chromadb.PersistentClient(
                path=db_path,
                settings=Settings(anonymized_telemetry=False),
            )
            self.facts = self.client.get_or_create_collection(
                "facts", embedding_function=_embedding_fn,
            )
            self.prefs = self.client.get_or_create_collection(
                "preferences", embedding_function=_embedding_fn,
            )
            self.conversations = self.client.get_or_create_collection(
                "conversations", embedding_function=_embedding_fn,
            )
            self._available = True
        except Exception:
            self._available = False

    def store_fact(self, user_id: str, key: str, value: str):
        if not self._available:
            return
        doc = f"{key}: {value}"
        self.facts.upsert(
            ids=[f"{user_id}_{key}"],
            documents=[doc],
            metadatas=[{"user_id": user_id, "key": key, "value": value}],
        )

    def retrieve_facts(self, user_id: str, query: str, top_k: int = 5) -> list[dict]:
        if not self._available:
            return []
        try:
            results = self.facts.query(
                query_texts=[query],
                n_results=top_k,
                where={"user_id": user_id},
            )
            return [
                {"key": m["key"], "value": m["value"], "score": 1 - d}
                for m, d in zip(results["metadatas"][0], results["distances"][0])
            ]
        except Exception:
            return []

    def store_preference(self, user_id: str, key: str, value: str):
        if not self._available:
            return
        self.prefs.upsert(
            ids=[f"{user_id}_{key}"],
            documents=[f"{key}: {value}"],
            metadatas=[{"user_id": user_id, "key": key, "value": value}],
        )

    def get_preference(self, user_id: str, key: str) -> str | None:
        if not self._available:
            return None
        try:
            results = self.prefs.get(ids=[f"{user_id}_{key}"])
            if results["metadatas"]:
                return results["metadatas"][0].get("value")
        except Exception:
            pass
        return None

    def get_all_preferences(self, user_id: str) -> dict[str, str]:
        if not self._available:
            return {}
        try:
            results = self.prefs.get(where={"user_id": user_id})
            return {
                m["key"]: m["value"]
                for m in results["metadatas"]
            }
        except Exception:
            return {}

    def store_conversation(self, user_id: str, messages: list[dict],
                           max_messages: int = 20):
        if not self._available:
            return
        text = "\n".join(
            f"[{m['role']}]: {str(m.get('content', ''))[:300]}"
            for m in messages[-max_messages:]
        )
        ts = int(time.time())
        self.conversations.upsert(
            ids=[f"{user_id}_{ts}"],
            documents=[text],
            metadatas=[{"user_id": user_id, "timestamp": ts}],
        )

    def search_conversations(self, user_id: str, query: str,
                             top_k: int = 5) -> list[dict]:
        if not self._available:
            return []
        try:
            results = self.conversations.query(
                query_texts=[query], n_results=top_k,
                where={"user_id": user_id},
            )
            return [
                {"content": doc, "score": 1 - dist, "metadata": meta}
                for doc, meta, dist in zip(
                    results["documents"][0],
                    results["metadatas"][0],
                    results["distances"][0],
                )
            ]
        except Exception:
            return []
