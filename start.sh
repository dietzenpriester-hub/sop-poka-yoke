#!/bin/bash
# SOP 防呆系统一键启动脚本
# 用法: ./start.sh        (启动所有服务)
#       ./start.sh stop   (停止所有服务)

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
MINIO_DATA="/tmp/minio-data"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR" "$MINIO_DATA"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$PROJECT_DIR/.env"
    set +a
fi

check_port() {
    lsof -i :"$1" -t >/dev/null 2>&1
}

wait_for_port() {
    local port=$1 name=$2 max_wait=${3:-15}
    for i in $(seq 1 $max_wait); do
        if check_port "$port"; then
            echo -e "  ${GREEN}✓${NC} $name 已启动 (端口 $port)"
            return 0
        fi
        sleep 1
    done
    echo -e "  ${RED}✗${NC} $name 启动超时 (端口 $port)"
    return 1
}

stop_all() {
    echo -e "${YELLOW}正在停止所有服务...${NC}"
    # 11434: Ollama 默认端口。若 Ollama 由系统服务/其他方式常驻，停止该端口可能影响全局实例；
    # 仅当由本脚本内「ollama serve」启动并占用 11434 时，此处停止才与启动流程一致。
    for port in 5173 8000 9000 11434; do
        pid=$(lsof -i :"$port" -t 2>/dev/null | head -1)
        if [ -n "$pid" ]; then
            kill "$pid" 2>/dev/null && echo -e "  ${GREEN}✓${NC} 端口 $port 进程 ($pid) 已停止"
        fi
    done
    echo -e "${GREEN}所有服务已停止${NC}"
    exit 0
}

[ "$1" = "stop" ] && stop_all

echo -e "${YELLOW}═══════════════════════════════════════${NC}"
echo -e "${YELLOW}       SOP 防呆系统一键启动            ${NC}"
echo -e "${YELLOW}═══════════════════════════════════════${NC}"
echo ""

# 1. Ollama
echo -e "${YELLOW}[1/4] 检查 Ollama...${NC}"
if pgrep -x ollama >/dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} Ollama 已在运行"
else
    echo -e "  启动 Ollama..."
    ollama serve >"$LOG_DIR/ollama.log" 2>&1 &
    sleep 2
    echo -e "  ${GREEN}✓${NC} Ollama 已启动"
fi

if curl -s http://localhost:11434/api/tags | grep -q "qwen2.5vl"; then
    echo -e "  ${GREEN}✓${NC} qwen2.5vl:3b 模型已就绪"
else
    echo -e "  ${YELLOW}!${NC} qwen2.5vl:3b 模型未找到，正在拉取（约 3GB）..."
    ollama pull qwen2.5vl:3b
fi

# 2. MinIO
echo -e "${YELLOW}[2/4] 检查 MinIO...${NC}"
if check_port 9000; then
    echo -e "  ${GREEN}✓${NC} MinIO 已在运行 (端口 9000)"
else
    echo -e "  启动 MinIO..."
    MINIO_ROOT_USER=minioadmin MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-changeme}" \
        minio server "$MINIO_DATA" --console-address ":9001" \
        >"$LOG_DIR/minio.log" 2>&1 &
    wait_for_port 9000 "MinIO"
fi

# 3. 后端
echo -e "${YELLOW}[3/4] 检查后端服务...${NC}"
if check_port 8000; then
    echo -e "  ${GREEN}✓${NC} 后端已在运行 (端口 8000)"
else
    echo -e "  启动后端..."
    cd "$PROJECT_DIR/packages/server"
    source .venv/bin/activate
    python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload \
        >"$LOG_DIR/backend.log" 2>&1 &
    wait_for_port 8000 "后端"
fi

# 4. 前端
echo -e "${YELLOW}[4/4] 检查前端服务...${NC}"
if check_port 5173; then
    echo -e "  ${GREEN}✓${NC} 前端已在运行 (端口 5173)"
else
    echo -e "  启动前端..."
    cd "$PROJECT_DIR/packages/web"
    if command -v pnpm &>/dev/null; then
        pnpm dev >"$LOG_DIR/frontend.log" 2>&1 &
    else
        npm run dev >"$LOG_DIR/frontend.log" 2>&1 &
    fi
    wait_for_port 5173 "前端"
fi

echo ""
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo -e "${GREEN}       所有服务已就绪！                ${NC}"
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo ""
echo -e "  前端:    ${GREEN}http://localhost:5173${NC}"
echo -e "  后端:    ${GREEN}http://localhost:8000${NC}"
echo -e "  MinIO:   ${GREEN}http://localhost:9001${NC} (控制台)"
echo -e "  Ollama:  ${GREEN}http://localhost:11434${NC}"
echo ""
echo -e "  登录账号: 请查阅数据库或管理员配置"
echo ""
echo -e "  停止所有服务: ${YELLOW}./start.sh stop${NC}"
echo -e "  查看日志: ${YELLOW}tail -f logs/*.log${NC}"
