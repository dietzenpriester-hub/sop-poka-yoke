#!/usr/bin/env bash
# ============================================================
# SOP 防呆系统 — 数据库恢复脚本
# 功能：从备份文件恢复 PostgreSQL 数据库 / MinIO 对象存储
# 用法：bash scripts/restore.sh <备份文件>
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT"

DB_CONTAINER="sop-poka-yoke-postgres-1"
DB_NAME="sop_pokayoke"
DB_USER="sop_admin"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

usage() {
    echo "用法: bash scripts/restore.sh <备份文件>"
    echo ""
    echo "支持的备份文件类型:"
    echo "  db_*.sql.gz       恢复 PostgreSQL 数据库"
    echo "  minio_*.tar.gz    恢复 MinIO 对象存储"
    echo ""
    echo "示例:"
    echo "  bash scripts/restore.sh backups/db_20260330_120000.sql.gz"
    echo "  bash scripts/restore.sh backups/minio_20260330_120000.tar.gz"
    exit 1
}

if [ $# -lt 1 ] || [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    usage
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    log "错误: 备份文件不存在: $BACKUP_FILE"
    exit 1
fi

FILENAME=$(basename "$BACKUP_FILE")

# ---- PostgreSQL 恢复 ----
restore_database() {
    log "========== 恢复 PostgreSQL 数据库 =========="
    log "备份文件: $BACKUP_FILE"

    if ! docker inspect "$DB_CONTAINER" --format '{{.State.Running}}' 2>/dev/null | grep -q true; then
        log "错误: PostgreSQL 容器未运行，请先启动: docker compose up -d postgres"
        exit 1
    fi

    echo ""
    echo "⚠️  警告: 此操作将覆盖当前数据库中的所有数据！"
    echo "   数据库: $DB_NAME"
    echo "   备份文件: $FILENAME"
    echo ""
    read -rp "确认恢复？(输入 yes 继续): " confirm
    if [ "$confirm" != "yes" ]; then
        log "已取消恢复"
        exit 0
    fi

    log "停止 server 服务以避免连接冲突..."
    docker compose stop server 2>/dev/null || true

    log "正在恢复数据库..."
    gunzip -c "$BACKUP_FILE" | docker exec -i "$DB_CONTAINER" \
        psql -U "$DB_USER" -d "$DB_NAME" --quiet --single-transaction 2>&1 \
        | grep -v "^SET$\|^DROP\|^ALTER\|^CREATE\|^COMMENT" || true

    log "重新启动 server 服务..."
    docker compose start server 2>/dev/null || true

    log "数据库恢复完成"
}

# ---- MinIO 恢复 ----
restore_minio() {
    log "========== 恢复 MinIO 对象存储 =========="
    log "备份文件: $BACKUP_FILE"

    echo ""
    echo "⚠️  警告: 此操作将覆盖当前 MinIO 存储中的所有数据！"
    echo "   备份文件: $FILENAME"
    echo ""
    read -rp "确认恢复？(输入 yes 继续): " confirm
    if [ "$confirm" != "yes" ]; then
        log "已取消恢复"
        exit 0
    fi

    log "停止 MinIO 容器..."
    docker compose stop minio server 2>/dev/null || true

    log "正在恢复 MinIO 数据..."
    docker run --rm \
        -v sop-poka-yoke_miniodata:/data \
        -v "$(cd "$(dirname "$BACKUP_FILE")" && pwd)":/backup:ro \
        alpine:3.19 \
        sh -c "rm -rf /data/* && tar xzf /backup/$FILENAME -C /data"

    log "重新启动服务..."
    docker compose start minio 2>/dev/null || true
    sleep 3
    docker compose start server 2>/dev/null || true

    log "MinIO 恢复完成"
}

# ---- 根据文件名判断恢复类型 ----
case "$FILENAME" in
    db_*.sql.gz)
        restore_database
        ;;
    minio_*.tar.gz)
        restore_minio
        ;;
    *)
        log "错误: 无法识别的备份文件格式: $FILENAME"
        log "文件名必须以 'db_' 或 'minio_' 开头"
        exit 1
        ;;
esac
