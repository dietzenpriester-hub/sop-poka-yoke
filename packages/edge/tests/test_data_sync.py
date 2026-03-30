"""数据同步 / MinIO 上传安全名单元测试（不连真实服务）"""

from unittest.mock import MagicMock, patch

import pytest

from src.comm.data_sync import MinIOUploader


@pytest.fixture
def mock_minio_env(monkeypatch, tmp_path):
    """提供 MinIO 凭证与假本地文件，避免真实连接。"""
    monkeypatch.setenv("SOP_MINIO_ACCESS_KEY", "test-ak")
    monkeypatch.setenv("SOP_MINIO_SECRET_KEY", "test-sk")
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"fake")
    return f


@patch("src.comm.data_sync.Minio")
def test_path_traversal_rejected(mock_minio_cls, mock_minio_env):
    """object_name 含 .. 或以 / 开头时拒绝上传。"""
    mock_client = MagicMock()
    mock_client.bucket_exists.return_value = True
    mock_minio_cls.return_value = mock_client
    up = MinIOUploader(endpoint="localhost:9000", bucket="b", secure=False)
    with pytest.raises(ValueError, match="不安全"):
        up.upload_file(str(mock_minio_env), object_name="../etc/passwd")
    with pytest.raises(ValueError, match="不安全"):
        up.upload_file(str(mock_minio_env), object_name="/abs/path")


@patch("src.comm.data_sync.Minio")
def test_valid_object_name(mock_minio_cls, mock_minio_env):
    """合法对象名通过校验并调用 fput_object。"""
    mock_client = MagicMock()
    mock_client.bucket_exists.return_value = True
    mock_minio_cls.return_value = mock_client
    up = MinIOUploader(endpoint="localhost:9000", bucket="my-bucket", secure=False)
    url = up.upload_file(str(mock_minio_env), object_name="safe/prefix/clip.mp4")
    assert url == "my-bucket/safe/prefix/clip.mp4"
    mock_client.fput_object.assert_called_once()
    call_kw = mock_client.fput_object.call_args
    assert call_kw[0][1] == "safe/prefix/clip.mp4"
