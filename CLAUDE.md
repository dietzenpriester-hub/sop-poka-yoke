# SOP 防呆系统 — 项目上下文

## 项目概述
基于多模态大模型的 SOP（标准作业程序）主动防错系统，通过 AI 视觉识别实时监控产线操作，自动检测步骤顺序、物料正确性和完工质量。

## Monorepo 结构
- `packages/edge/` — 边缘计算层（Python）：视频采集 → AI 推理 → SOP 状态机 → 硬件控制
- `packages/server/` — 服务端（FastAPI）：REST API、数据持久化、MES 集成
- `packages/web/` — 管理端前端（Vue 3 + Element Plus）：实时监控、SOP 配置、视频回放
- `packages/shared/` — 共享协议（JSON Schema → 代码生成）：MQTT 主题、事件类型、数据模型
- `models/` — AI 模型文件（不入 Git，通过 registry.yaml 管理版本）
- `scripts/` — 运维与工具脚本
- `deploy/` — 部署配置（Prometheus、Mosquitto 等）

## 技术栈
- **边缘端**：Python 3.12, OpenCV, YOLOv11 (TensorRT), Qwen2-VL (Ollama), Redis, SQLite
- **服务端**：FastAPI, SQLAlchemy 2.0 (asyncpg), PostgreSQL, MinIO, MQTT (EMQX/Mosquitto)
- **前端**：Vue 3, TypeScript, Element Plus, Pinia, ECharts, WebSocket
- **部署**：Docker Compose, Prometheus + Grafana

## 编码规范
- Python：类型注解必须、loguru 日志、ruff 格式化、pytest 测试
- Vue：Composition API + `<script setup lang="ts">`、ESLint + Prettier
- 中文注释和文档
- 环境变量前缀：`SOP_`
- Commit 规范：Conventional Commits

## 四层架构
产线现场（传感采集）→ 边缘计算（AI 推理 + 业务判定）→ 服务端（数据持久化 + 集成）→ 管理端（可视化 + 配置）

## 核心原则
- 离线自治：边缘端有完整本地存储和业务逻辑，不依赖服务端运行
- 两级 AI 过滤：YOLO (~5ms) 过滤 90% 无效帧 → VLM (~80ms) 语义理解
- 协议统一：shared 包集中定义 MQTT 主题、事件类型、SOP Schema
- 容器化交付：Docker Compose 一键启动
