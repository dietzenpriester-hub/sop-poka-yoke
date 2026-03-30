"""基于 VLM Embedding 的动作相似度比对"""

import threading

import numpy as np

MIN_NORM_EPS = 1e-8


class ActionEmbeddingComparator:

    def __init__(self, similarity_threshold: float = 0.85, warn_threshold: float = 0.60) -> None:
        self.similarity_threshold = similarity_threshold
        self.warn_threshold = warn_threshold
        self._reference_lock = threading.Lock()
        self.reference_embeddings: dict[int, np.ndarray] = {}

    def set_reference(self, step_index: int, embedding: np.ndarray) -> None:
        norm = np.linalg.norm(embedding)
        if norm < MIN_NORM_EPS:
            raise ValueError(f"参考 embedding 范数接近零: step_index={step_index}")
        with self._reference_lock:
            self.reference_embeddings[step_index] = embedding / norm

    def compare(self, step_index: int, current_embedding: np.ndarray) -> dict:
        with self._reference_lock:
            if step_index not in self.reference_embeddings:
                return {"similarity": 0.0, "status": "UNKNOWN"}
            ref = self.reference_embeddings[step_index]
        norm = np.linalg.norm(current_embedding)
        if norm < MIN_NORM_EPS:
            return {"similarity": 0.0, "status": "UNKNOWN"}
        cur = current_embedding / norm
        similarity = float(np.dot(ref, cur))
        if similarity >= self.similarity_threshold:
            status = "OK"
        elif similarity >= self.warn_threshold:
            status = "WARN"
        else:
            status = "NG"
        return {"similarity": similarity, "status": status}

    def clear(self, step_index: int | None = None) -> None:
        """清除参考 embedding。step_index=None 清除所有。"""
        with self._reference_lock:
            if step_index is None:
                self.reference_embeddings.clear()
            else:
                self.reference_embeddings.pop(step_index, None)
