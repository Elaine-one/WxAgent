"""统一的 Embedding 函数，离线优先，自动镜像加速。"""

import os

import config
from config import EMBEDDING_MODEL_PATH

os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")

_local_model = str(EMBEDDING_MODEL_PATH) if EMBEDDING_MODEL_PATH.exists() else config.ADV_EMBEDDING_MODEL
_embedding_fn = None
_model = None


def _load_model():
    """延迟加载 SentenceTransformer（全局单例，离线优先 + 镜像兜底）。"""
    global _model
    if _model is not None:
        return _model

    from sentence_transformers import SentenceTransformer

    # 本地路径：直接加载
    if EMBEDDING_MODEL_PATH.exists():
        _model = SentenceTransformer(str(EMBEDDING_MODEL_PATH), local_files_only=True)
        return _model

    # 远程模型：先尝试完全离线（已缓存时零网络请求）
    try:
        _model = SentenceTransformer(_local_model, local_files_only=True)
        return _model
    except Exception:
        pass

    # 未缓存 → 尝试 HF 镜像
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    _model = SentenceTransformer(_local_model)
    return _model


class _EmbeddingFn:
    """适配 chromadb EmbeddingFunction 接口。"""
    def __call__(self, texts: list[str]) -> list[list[float]]:
        return _load_model().encode(texts, show_progress_bar=False).tolist()


def get_embedding_fn():
    global _embedding_fn
    if _embedding_fn is None:
        _embedding_fn = _EmbeddingFn()
    return _embedding_fn
