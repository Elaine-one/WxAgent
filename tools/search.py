"""工具搜索引擎 - BM25 风格的按需工具发现。

替代全量工具注入，通过语义搜索按需发现和加载工具，
大幅减少每轮 API 调用的 token 消耗（"MCP 工具税"）。

参考: Hermes Agent Tool Search (Nous Research)
"""

import logging
import math
import re
from collections import Counter
from typing import Optional

from tools.base import ToolDef, ToolMeta
from tools.registry import ToolRegistry

logger = logging.getLogger("wxagent.tools.search")


def _tokenize(text: str) -> list[str]:
    """分词：英文按空格/下划线拆分，中文按字符拆分，统一小写。"""
    text = text.lower()
    # 按下划线和空格拆分英文
    tokens = re.split(r"[\s_]+", text)
    # 提取中文字符
    cn_chars = re.findall(r"[\u4e00-\u9fff]", text)
    # 提取英文单词
    en_words = [t for t in tokens if t and re.match(r"[a-z0-9]+", t)]
    return en_words + cn_chars


class ToolSearchEngine:
    """BM25 风格的工具搜索引擎。

    对 ToolRegistry 中所有已注册工具建立索引，
    支持按名称、描述、参数名进行模糊搜索。
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._index: dict[str, dict] = {}  # tool_name -> doc
        self._df: Counter = Counter()       # term -> document frequency
        self._avg_dl: float = 0.0
        self._n_docs: int = 0

    def build_index(self) -> None:
        """从 ToolRegistry 构建搜索索引。"""
        self._index.clear()
        self._df.clear()
        self._avg_dl = 0.0

        all_defs = ToolRegistry.get_all_defs()
        all_metas = {m.name: m for m in ToolRegistry.get_all_metas()}
        total_len = 0

        for tool_def in all_defs:
            # 跳过桥接工具自身
            if tool_def.name in ("tool_search", "tool_describe", "tool_call"):
                continue

            meta = all_metas.get(tool_def.name)
            # 拼接可搜索文本：名称 + 描述 + 参数名
            parts = [tool_def.name, tool_def.description or ""]
            if tool_def.parameters:
                parts.extend(tool_def.parameters.keys())
                for prop in tool_def.parameters.values():
                    if isinstance(prop, dict):
                        desc = prop.get("description", "")
                        if desc:
                            parts.append(desc)
            if meta and meta.tags:
                parts.extend(meta.tags)
            if meta and meta.triggers:
                parts.extend(meta.triggers)

            text = " ".join(parts)
            tokens = _tokenize(text)
            tf = Counter(tokens)

            self._index[tool_def.name] = {
                "def": tool_def,
                "meta": meta,
                "tokens": tokens,
                "tf": tf,
                "dl": len(tokens),
            }

            for term in set(tokens):
                self._df[term] += 1
            total_len += len(tokens)

        self._n_docs = len(self._index)
        self._avg_dl = total_len / self._n_docs if self._n_docs > 0 else 1.0
        logger.info(f"Tool search index built: {self._n_docs} tools, avg_dl={self._avg_dl:.1f}")

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """搜索与 query 最相关的工具。

        Returns:
            list of {"name": str, "description": str, "score": float, "type": str}
        """
        if not self._index:
            self.build_index()

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        scores: list[tuple[str, float]] = []
        for name, doc in self._index.items():
            score = self._bm25_score(query_tokens, doc)
            if score > 0:
                scores.append((name, score))

        # BM25 结果
        scores.sort(key=lambda x: x[1], reverse=True)
        results = []
        seen = set()
        for name, score in scores[:top_k]:
            doc = self._index[name]
            meta = doc["meta"]
            results.append({
                "name": name,
                "description": doc["def"].description or "",
                "type": meta.type.value if meta else "builtin",
                "score": round(score, 3),
            })
            seen.add(name)

        # 降级：子串匹配补充
        if len(results) < top_k:
            query_lower = query.lower()
            for name, doc in self._index.items():
                if name in seen:
                    continue
                if query_lower in name.lower() or query_lower in (doc["def"].description or "").lower():
                    meta = doc["meta"]
                    results.append({
                        "name": name,
                        "description": doc["def"].description or "",
                        "type": meta.type.value if meta else "builtin",
                        "score": 0.1,
                    })
                    seen.add(name)
                    if len(results) >= top_k:
                        break

        return results

    def describe(self, tool_name: str) -> Optional[dict]:
        """获取工具的完整 schema 描述。"""
        if not self._index:
            self.build_index()

        doc = self._index.get(tool_name)
        if not doc:
            # 尝试直接从 Registry 获取
            tool_def = None
            for td in ToolRegistry.get_all_defs():
                if td.name == tool_name:
                    tool_def = td
                    break
            if not tool_def:
                return None
            meta = ToolRegistry.get_meta(tool_name)
            return {
                "name": tool_def.name,
                "description": tool_def.description,
                "parameters": tool_def.parameters,
                "required": tool_def.required,
                "type": meta.type.value if meta else "builtin",
            }

        tool_def = doc["def"]
        meta = doc["meta"]
        return {
            "name": tool_def.name,
            "description": tool_def.description,
            "parameters": tool_def.parameters,
            "required": tool_def.required,
            "type": meta.type.value if meta else "builtin",
        }

    def _bm25_score(self, query_tokens: list[str], doc: dict) -> float:
        """计算 BM25 分数。"""
        score = 0.0
        dl = doc["dl"]
        tf = doc["tf"]
        for term in query_tokens:
            if term not in tf:
                continue
            df = self._df.get(term, 0)
            idf = math.log((self._n_docs - df + 0.5) / (df + 0.5) + 1)
            tf_val = tf[term]
            numerator = tf_val * (self.k1 + 1)
            denominator = tf_val + self.k1 * (1 - self.b + self.b * dl / self._avg_dl)
            score += idf * numerator / denominator
        return score


# 全局搜索引擎实例
engine = ToolSearchEngine()
