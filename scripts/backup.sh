#!/usr/bin/env bash
# ============================================================
# SOP 防呆系统 — 数据库备份脚本
# 功能：备份 PostgreSQL 数据库 + MinIO 对象存储
# 用法：bash scripts/backup.sh [--db-only | --minio-only]
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT"

# ---- 配置 ----
BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"
KEEP_DAYS="${KEEP_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

DB_CONTAINER="sop-poka-yoke-postgres-1"
DB_NAME="sop_pokayoke"
DB_USER="sop_admin"

MINIO_CONTAINER="sop-poka-yoke-minio-1"
MINIO_ALIAS="sop-local"
MINIO_ENDPOINT="http://127.0.0.1:9000"
MINIO_ACCESS_KEY="minioadmin"
MINIO_SECRET_KEY="${MINIO_PASSWORD:-changeme}"

BACKUP_DB=true
BACKUP_MINIO=true

for arg in "$@"; do
    case "$arg" in
        --db-only) BACKUP_MINIO=false ;;
        --minio-only) BACKUP_DB=false ;;
        --help|-h)
            echo "用法: bash scripts/backup.sh [选项]"
            echo "  --db-only      仅备份数据库"
            echo "  --minio-only   仅备份 MinIO 对象存储"
            echo "  --help         显示帮助"
            echo ""
            echo "环境变量:"
            echo "  BACKUP_DIR     备份存放目录 (默认: \$ROOT/backups)"
            echo "  KEEP_DAYS      保留天数 (默认: 30)"
            exit 0
            ;;
    esac
done

mkdir -p "$BACKUP_DIR"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

# ---- 检查 Docker 容器状态 ----
check_container() {
    local container=$1
    if ! docker inspect "$container" --format '{{.State.Running}}' 2>/dev/null | grep -q true; then
        log "错误: 容器 $container 未运行"
        return 1
    fi
}

# ---- PostgreSQL 备份 ----
backup_database() {
    local backup_file="$BACKUP_DIR/db_${TIMESTAMP}.sql.gz"

    log "开始备份 PostgreSQL..."
    check_container "$DB_CONTAINER"

    docker exec -t "$DB_CONTAINER" \
        pg_dump -U "$DB_USER" -d "$DB_NAME" \
        --no-owner --no-privileges --clean --if-exists \
        | gzip > "$backup_file"

    local size
    size=$(du -h "$backup_file" | cut -f1)
    log "数据库备份完成: $backup_file ($size)"
}

# ---- MinIO 备份 ----
backup_minio() {
    local backup_file="$BACKUP_DIR/minio_${TIMESTAMP}.tar.gz"

    log "开始备份 MinIO 对象存储..."
    check_container "$MINIO_CONTAINER"

    if ! command -v mc &>/dev/null; then
        log "mc (MinIO Client) 未安装，使用 Docker volume 方式备份..."
        docker run --rm \
            -v sop-poka-yoke_miniodata:/data:ro \
            -v "$BACKUP_DIR":/backup \
            alpine:3.19 \
            tar czf "/backup/minio_${TIMESTAMP}.tar.gz" -C /data .
    else
        local minio_tmp="$BACKUP_DIR/minio_tmp_${TIMESTAMP}"
        mkdir -p "$minio_tmp"

        mc alias set "$MINIO_ALIAS" "$MINIO_ENDPOINT" "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" --api S3v4 2>/dev/null

        for bucket in $(mc ls "$MINIO_ALIAS" 2>/dev/null | awk '{print $NF}' | tr -d '/'); do
            log "  备份 bucket: $bucket"
            mc mirror "$MINIO_ALIAS/$bucket" "$minio_tmp/$bucket" --quiet 2>/dev/null || true
        done

        tar czf "$backup_file" -C "$minio_tmp" .
        rm -rf "$minio_tmp"
    fi

    local size
    size=$(du -h "$backup_file" | cut -f1)
    log "MinIO 备份完成: $backup_file ($size)"
}

# ---- 清理旧备份 ----
cleanup_old_backups() {
    log "清理 ${KEEP_DAYS} 天前的旧备份..."
    local count
    count=$(find "$BACKUP_DIR" -name "*.gz" -mtime +"$KEEP_DAYS" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$count" -gt 0 ]; then
        find "$BACKUP_DIR" -name "*.gz" -mtime +"$KEEP_DAYS" -delete
        log "已清理 $count 个旧备份文件"
    else
        log "没有需要清理的旧备份"
    fi
}

# ---- 主流程 ----
log "========== SOP 防呆系统备份 =========="
log "备份目录: $BACKUP_DIR"
log "保留天数: $KEEP_DAYS"

if [ "$BACKUP_DB" = true ]; then
    backup_database
fi

if [ "$BACKUP_MINIO" = true ]; then
    backup_minio
fi

cleanup_old_backups

log "========== 备份完成 =========="
echo ""
echo "备份文件列表:"
ls -lh "$BACKUP_DIR"/*_${TIMESTAMP}.* 2>/dev/null || echo "  (无)"
