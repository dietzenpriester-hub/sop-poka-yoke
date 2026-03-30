"""模型注册表：启动时校验本地文件与 SHA256，不匹配则从 MinIO 拉取。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml
from loguru import logger

try:
    from minio import Minio
except ImportError:
    Minio = None  # type: ignore


@dataclass
class ModelSpec:
    key: str
    name: str
    version: str
    relative_path: str
    hash_sha256: str
    min_code_version: str
    minio_bucket: str | None
    minio_key: str | None


class ModelManager:

    def __init__(self, repo_root: Path | None = None, models_root: Path | None = None) -> None:
        self.repo_root = repo_root or Path(__file__).resolve().parents[4]
        self.models_root = models_root or (self.repo_root / "models")
        self.registry_path = self.models_root / "registry.yaml"
        self._specs: dict[str, ModelSpec] = {}

    def load_registry(self) -> None:
        if not self.registry_path.is_file():
            raise FileNotFoundError(f"未找到 registry: {self.registry_path}")
        with open(self.registry_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        models = raw.get("models") or {}
        self._specs.clear()
        for key, m in models.items():
            storage = m.get("storage") or {}
            self._specs[key] = ModelSpec(
                key=key, name=m["name"], version=m["version"],
                relative_path=m["file"], hash_sha256=m["hash_sha256"],
                min_code_version=m.get("min_code_version", "0.0.0"),
                minio_bucket=storage.get("minio_bucket"), minio_key=storage.get("minio_key"),
            )

    def get_spec(self, model_key: str) -> ModelSpec:
        if not self._specs:
            self.load_registry()
        if model_key not in self._specs:
            raise KeyError(f"registry 中无模型: {model_key}")
        return self._specs[model_key]

    def resolved_path(self, model_key: str) -> Path:
        return (self.models_root / self.get_spec(model_key).relative_path).resolve()

    @staticmethod
    def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(chunk_size):
                h.update(chunk)
        return h.hexdigest()

    def ensure_local_model(
        self, model_key: str, *, app_version: str | None = None,
        minio_endpoint: str | None = None, minio_access_key: str | None = None,
        minio_secret_key: str | None = None, minio_secure: bool = False,
    ) -> Path:
        self.load_registry()
        spec = self.get_spec(model_key)
        if app_version:
            logger.info("模型 {} 要求应用版本 >= {}，当前 {}", spec.key, spec.min_code_version, app_version)
        target = self.resolved_path(model_key)
        target.parent.mkdir(parents=True, exist_ok=True)

        def _verify(p: Path) -> bool:
            if not p.is_file():
                return False
            digest = self._sha256_file(p)
            ok = digest.lower() == spec.hash_sha256.lower()
            if not ok:
                logger.error("模型哈希不匹配: {} 期望 {} 实际 {}", p, spec.hash_sha256, digest)
            return ok

        if target.is_file() and _verify(target):
            logger.info("模型已就绪: {} ({})", target, spec.version)
            return target
        if not spec.minio_bucket or not spec.minio_key:
            raise RuntimeError(f"本地模型缺失或校验失败，且 registry 未配置 MinIO: {model_key}")
        if Minio is None:
            raise RuntimeError("未安装 minio 库，无法自动下载模型")
        if not minio_endpoint or not minio_access_key or not minio_secret_key:
            raise RuntimeError("自动下载需提供 minio_endpoint / access_key / secret_key")
        logger.warning("开始从 MinIO 下载模型: {} -> {}", spec.minio_key, target)
        client = Minio(minio_endpoint, access_key=minio_access_key, secret_key=minio_secret_key, secure=minio_secure)
        client.fget_object(spec.minio_bucket, spec.minio_key, str(target))
        if not _verify(target):
            target.unlink(missing_ok=True)
            raise RuntimeError(f"下载后哈希仍不匹配: {model_key}")
        logger.info("模型下载并校验通过: {} ({})", target, spec.version)
        return target
