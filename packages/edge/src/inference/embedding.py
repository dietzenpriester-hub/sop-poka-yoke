"""基于 VLM Embedding 的动作相似度比对"""

import numpy as np
from loguru import logger


class ActionEmbeddingComparator:

    def __init__(self, similarity_threshold: float = 0.85, warn_threshold: float = 0.60) -> None:
        self.similarity_threshold = similarity_threshold
        self.warn_threshold = warn_threshold
        self.reference_embeddings: dict[int, np.ndarray] = {}

    def set_reference(self, step_index: int, embedding: np.ndarray) -> None:
        self.reference_embeddings[step_index] = embedding / np.linalg.norm(embedding)

    def compare(self, step_index: int, current_embedding: np.ndarray) -> dict:
        if step_index not in self.reference_embeddings:
            return {"similarity": 0.0, "status": "UNKNOWN"}
        ref = self.reference_embeddings[step_index]
        cur = current_embedding / np.linalg.norm(current_embedding)
        similarity = float(np.dot(ref, cur))
        if similarity >= self.similarity_threshold:
            status = "OK"
        elif similarity >= self.warn_threshold:
            status = "WARN"
        else:
            status = "NG"
        return {"similarity": similarity, "status": status}
