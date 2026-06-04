"""统一的 Embedding 函数，延迟加载避免 import 时触发模型下载。"""

import config
from config import EMBEDDING_MODEL_PATH

_local_model = str(EMBEDDING_MODEL_PATH) if EMBEDDING_MODEL_PATH.exists() else config.ADV_EMBEDDING_MODEL
_embedding_fn = None


def get_embedding_fn():
    """获取 SentenceTransformer embedding 函数（延迟加载，全局单例）。"""
    global _embedding_fn
    if _embedding_fn is None:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        _embedding_fn = SentenceTransformerEmbeddingFunction(model_name=_local_model)
    return _embedding_fn
