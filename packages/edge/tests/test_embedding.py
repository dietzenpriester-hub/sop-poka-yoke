"""动作嵌入比对单元测试"""

import numpy as np
import pytest

from src.inference.embedding import MIN_NORM_EPS, ActionEmbeddingComparator


def test_set_reference():
    """设置参考嵌入后，内部存为归一化向量。"""
    cmp = ActionEmbeddingComparator()
    emb = np.array([3.0, 4.0], dtype=np.float64)
    cmp.set_reference(0, emb)
    with cmp._reference_lock:
        ref = cmp.reference_embeddings[0].copy()
    assert np.allclose(np.linalg.norm(ref), 1.0)
    assert np.allclose(ref, emb / np.linalg.norm(emb))


def test_compare_identical():
    """与参考向量相同方向时相似度为 1.0，状态 OK。"""
    cmp = ActionEmbeddingComparator(similarity_threshold=0.85, warn_threshold=0.6)
    v = np.array([1.0, 0.0, 0.0])
    cmp.set_reference(0, v)
    out = cmp.compare(0, v.copy())
    assert abs(out["similarity"] - 1.0) < 1e-6
    assert out["status"] == "OK"


def test_compare_orthogonal():
    """与参考向量正交时相似度为 0.0。"""
    cmp = ActionEmbeddingComparator(similarity_threshold=0.85, warn_threshold=0.6)
    cmp.set_reference(0, np.array([1.0, 0.0]))
    out = cmp.compare(0, np.array([0.0, 1.0]))
    assert abs(out["similarity"]) < 1e-6
    assert out["status"] == "NG"


def test_compare_no_reference():
    """未设置参考 step 时返回 UNKNOWN。"""
    cmp = ActionEmbeddingComparator()
    out = cmp.compare(99, np.array([1.0, 0.0]))
    assert out["similarity"] == 0.0
    assert out["status"] == "UNKNOWN"


def test_zero_vector_handling():
    """零向量：当前向量为零范数时返回 UNKNOWN；参考向量为零范数时无法设置。"""
    cmp = ActionEmbeddingComparator()
    cmp.set_reference(0, np.array([1.0, 0.0]))
    out = cmp.compare(0, np.zeros(2))
    assert out["similarity"] == 0.0
    assert out["status"] == "UNKNOWN"
    with pytest.raises(ValueError, match="范数"):
        cmp.set_reference(1, np.zeros(3))
    with pytest.raises(ValueError):
        cmp.set_reference(2, np.full(3, MIN_NORM_EPS / 10.0))


def test_clear_references():
    """clear(None) 清除全部参考；clear(i) 仅清除指定步。"""
    cmp = ActionEmbeddingComparator()
    cmp.set_reference(0, np.array([1.0, 0.0]))
    cmp.set_reference(1, np.array([0.0, 1.0]))
    cmp.clear(0)
    assert 0 not in cmp.reference_embeddings
    assert 1 in cmp.reference_embeddings
    cmp.clear()
    assert len(cmp.reference_embeddings) == 0
