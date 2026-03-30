#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
set -a
[ -f "$ROOT/.env" ] && . "$ROOT/.env"
set +a

# 与 .env.example 一致：MINIO_PASSWORD 可与 MINIO_ROOT_PASSWORD 互换
MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-${MINIO_PASSWORD:-changeme}}"

echo "初始化 MinIO buckets..."

# 使用 mc 客户端（需先安装: brew install minio/stable/mc）
mc alias set sop http://localhost:9000 "${MINIO_ROOT_USER:-minioadmin}" "$MINIO_ROOT_PASSWORD" 2>/dev/null || true

for bucket in sop-videos sop-models sop-learning sop-snapshots; do
    mc mb "sop/$bucket" 2>/dev/null || echo "Bucket $bucket 已存在"
done

# 设置生命周期策略
mc ilm rule add sop/sop-videos --prefix "snapshots/" --expire-days 30 2>/dev/null || true
mc ilm rule add sop/sop-videos --prefix "clips/ng/" --expire-days 180 2>/dev/null || true

echo "MinIO 初始化完成"
