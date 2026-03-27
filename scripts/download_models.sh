#!/usr/bin/env bash
set -euo pipefail

# 检查依赖
if ! command -v ollama &>/dev/null; then
    echo "错误: 未安装 ollama，请先安装: https://ollama.ai"
    exit 1
fi

echo "=== 下载 AI 模型 ==="

# Ollama 模型
echo "拉取 Ollama 模型..."
ollama pull qwen2-vl:2b 2>/dev/null || echo "qwen2-vl:2b 拉取失败或已存在"
ollama pull qwen2.5-vl:7b 2>/dev/null || echo "qwen2.5-vl:7b 拉取失败或已存在"

# YOLO 模型（ultralytics 自动下载）
echo "YOLO 模型将在首次运行时自动下载"

echo "=== 模型下载完成 ==="
