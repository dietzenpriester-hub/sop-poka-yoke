#!/usr/bin/env bash
set -euo pipefail

echo "=== SOP 防呆系统部署 ==="

# 1. 启动基础服务
docker compose up -d postgres redis minio mqtt

# 2. 等待 PostgreSQL 就绪
echo "等待 PostgreSQL 启动..."
until docker compose exec -T postgres pg_isready -U sop_admin -d sop_pokayoke 2>/dev/null; do
    echo "  PostgreSQL 未就绪，等待..."
    sleep 2
done
echo "PostgreSQL 已就绪"

# 3. 数据库迁移
echo "执行数据库迁移..."
cd packages/server
alembic upgrade head
cd ../..

# 4. 启动应用服务
docker compose up -d server web

# 5. 初始化 MinIO bucket
bash scripts/init_minio.sh

echo "=== 部署完成 ==="
echo "  API:   http://localhost:8000/docs"
echo "  前端:  http://localhost:8080"
echo "  MinIO: http://localhost:9001"
