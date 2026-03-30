# SOP 防呆系统 — 生产部署指南

## 目录

1. [系统架构](#1-系统架构)
2. [硬件需求](#2-硬件需求)
3. [网络拓扑](#3-网络拓扑)
4. [部署前准备](#4-部署前准备)
5. [Step 1：服务器部署](#5-step-1服务器部署)
6. [Step 2：边缘设备部署](#6-step-2边缘设备部署)
7. [Step 3：安全加固](#7-step-3安全加固)
8. [Step 4：初始化与验证](#8-step-4初始化与验证)
9. [远程访问配置](#9-远程访问配置)
10. [日常运维](#10-日常运维)
11. [故障排查](#11-故障排查)
12. [升级流程](#12-升级流程)

---

## 1. 系统架构

```
┌──────────────────────────────────────────────────────┐
│                    产 线 网 络                        │
│                                                      │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐     │
│  │ Edge 工位1  │  │ Edge 工位2  │  │ Edge 工位N  │     │
│  │  Camera     │  │  Camera     │  │  Camera     │     │
│  │  YOLO+VLM   │  │  YOLO+VLM   │  │  YOLO+VLM   │     │
│  └──────┬─────┘  └──────┬─────┘  └──────┬─────┘     │
│         │               │               │           │
│         └───────────┬───┴───────────────┘           │
│                     │ MQTT + HTTP                    │
│              ┌──────┴──────┐                         │
│              │   Server    │                         │
│              │  (Docker)   │                         │
│              │  ┌────────┐ │                         │
│              │  │ FastAPI │ │                         │
│              │  │ Postgres│ │                         │
│              │  │ Redis   │ │                         │
│              │  │ MinIO   │ │                         │
│              │  │ MQTT    │ │                         │
│              │  └────────┘ │                         │
│              └──────┬──────┘                         │
│                     │ HTTPS                          │
│              ┌──────┴──────┐                         │
│              │  Web(Nginx) │ ← 浏览器/平板            │
│              └─────────────┘                         │
└──────────────────────────────────────────────────────┘
```

| 组件 | 技术栈 | 运行位置 |
|------|--------|---------|
| **Server** | FastAPI + PostgreSQL + Redis + MinIO + MQTT | 中央服务器 (Docker) |
| **Edge** | Python + YOLO11 + Qwen2.5-VL + OpenCV | 每个工位的边缘计算盒 |
| **Web** | Vue 3 + Element Plus + Nginx | 中央服务器 (Docker) |
| **Monitoring** | Prometheus + Grafana | 中央服务器 (Docker, 可选) |

---

## 2. 硬件需求

### 2.1 中央服务器

| 项目 | 最低配置 | 推荐配置 |
|------|---------|---------|
| CPU | 4 核 | 8 核 |
| 内存 | 8 GB | 16 GB |
| 存储 | 100 GB SSD | 500 GB SSD (NVMe) |
| 网络 | 千兆以太网 | 千兆以太网 |
| OS | Ubuntu 22.04 LTS / CentOS 8+ | Ubuntu 22.04 LTS |

### 2.2 边缘计算设备（每个工位）

| 项目 | 最低配置 | 推荐配置 |
|------|---------|---------|
| 平台 | Thundercomm TurboX / Jetson Orin Nano | Thundercomm TurboX C8550 |
| GPU/NPU | 支持 ONNX 推理 | NVIDIA GPU (4GB+ VRAM) 或 Qualcomm NPU |
| 内存 | 4 GB | 8 GB |
| 存储 | 32 GB | 64 GB |
| 摄像头 | USB UVC 200万像素 | 海康威视 U64 Pro (500万像素) |
| 网络 | WiFi / 以太网 | 以太网 (推荐) |

### 2.3 网络设备

- 工业交换机（支持 VLAN）
- 可选：无线 AP（工位平板显示用）

---

## 3. 网络拓扑

### 建议网络分区

| VLAN | 用途 | IP 段 (示例) |
|------|------|-------------|
| VLAN 10 | 管理网（服务器、监控） | 10.10.10.0/24 |
| VLAN 20 | 产线网（Edge 设备） | 10.10.20.0/24 |
| VLAN 30 | 摄像头网 | 10.10.30.0/24 |

### 防火墙规则

| 源 → 目标 | 端口 | 协议 | 说明 |
|-----------|------|------|------|
| Edge → Server | 8000 | TCP/HTTPS | API 通信 |
| Edge → Server | 1883/8883 | TCP | MQTT (明文/TLS) |
| Edge → Server | 9000 | TCP/HTTPS | MinIO 上传 |
| 浏览器 → Server | 80/443 | TCP/HTTPS | Web 界面 |
| Server → Edge | — | — | 无主动连接 |

---

## 4. 部署前准备

### 4.1 安装 Docker

```bash
# Ubuntu 22.04
sudo apt update && sudo apt install -y docker.io docker-compose-plugin
sudo systemctl enable docker
sudo usermod -aG docker $USER
# 重新登录生效
```

### 4.2 克隆代码

```bash
git clone <repo-url> /opt/sop-poka-yoke
cd /opt/sop-poka-yoke
```

### 4.3 配置环境变量

```bash
cp .env.example .env
```

**必须修改以下变量**（所有 `changeme` 必须替换为强密码）：

```bash
# 生成强密码的命令：
openssl rand -base64 32

# .env 中需修改的关键项：
DB_PASSWORD=<32位随机密码>
REDIS_PASSWORD=<32位随机密码>
MINIO_PASSWORD=<32位随机密码>
SOP_JWT_SECRET=<至少32字符的随机密钥>
GRAFANA_PASSWORD=<管理员密码>
```

同时更新 `.env` 中的关联变量：
```bash
SOP_DATABASE_URL=postgresql+asyncpg://sop_admin:<DB_PASSWORD>@localhost:5432/sop_pokayoke
SOP_REDIS_URL=redis://:<REDIS_PASSWORD>@localhost:6379/0
SOP_MINIO_SECRET_KEY=<MINIO_PASSWORD>
```

### 4.4 配置 CORS

```bash
# .env 中设置实际的前端域名
CORS_ORIGINS=["https://sop.your-domain.com"]
```

---

## 5. Step 1：服务器部署

### 5.1 一键部署

```bash
bash scripts/deploy.sh
```

该脚本会自动：
1. 启动 PostgreSQL、Redis、MinIO、MQTT
2. 等待 PostgreSQL 就绪
3. 执行数据库迁移（Alembic）
4. 启动 Server + Web
5. 初始化 MinIO 存储桶

### 5.2 手动分步部署

如果一键脚本失败，可以手动执行：

```bash
# 1. 启动基础设施
docker compose up -d postgres redis minio mqtt

# 2. 等待 PG 就绪
docker compose exec postgres pg_isready -U sop_admin -d sop_pokayoke

# 3. 数据库迁移
cd packages/server
source /opt/sop-poka-yoke/.env
alembic upgrade head
cd ../..

# 4. 启动应用
docker compose up -d server web

# 5. 初始化 MinIO
bash scripts/init_minio.sh
```

### 5.3 启动监控（可选）

```bash
docker compose up -d prometheus grafana
```

- Grafana: http://localhost:3000 (admin / `GRAFANA_PASSWORD`)
- Prometheus: http://localhost:9090

### 5.4 验证部署

```bash
# API 健康检查
curl http://localhost:8000/api/health

# Web 页面
curl -I http://localhost:8080

# 检查容器状态
docker compose ps
```

---

## 6. Step 2：边缘设备部署

### 6.1 环境准备

每台边缘设备需要：

```bash
# Python 3.11+
python3 --version

# 创建虚拟环境
cd /opt/sop-edge
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 6.2 GPU/NPU 驱动

```bash
# NVIDIA GPU
nvidia-smi  # 确认驱动已安装

# Thundercomm NPU - 参照 Thundercomm SDK 文档安装
```

### 6.3 AI 模型准备

```bash
# YOLO 模型 — 首次运行时自动下载，或手动放置：
mkdir -p models/
# 将 yolo11n.pt 放入 models/

# VLM (Ollama)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5-vl:3b
```

### 6.4 配置边缘端

```bash
# 创建 .env
cat > .env << 'EOF'
SOP_STATION_ID=ST-01
SOP_RTSP_URL=rtsp://admin:password@10.10.30.101:554/Streaming/Channels/101
SOP_MQTT_BROKER_HOST=10.10.10.100
SOP_MQTT_BROKER_PORT=1883
SOP_MINIO_ENDPOINT=10.10.10.100:9000
SOP_MINIO_ACCESS_KEY=minioadmin
SOP_MINIO_SECRET_KEY=<与服务器一致>
SOP_API_BASE=http://10.10.10.100:8000
SOP_OLLAMA_URL=http://localhost:11434
SOP_VLM_MODEL=qwen2.5-vl:3b
SOP_YOLO_MODEL=yolo11n.pt
EOF
```

### 6.5 启动边缘服务

```bash
source .venv/bin/activate
python -m src.main
```

建议使用 systemd 管理：

```ini
# /etc/systemd/system/sop-edge.service
[Unit]
Description=SOP Edge Service
After=network.target ollama.service

[Service]
Type=simple
User=sop
WorkingDirectory=/opt/sop-edge
EnvironmentFile=/opt/sop-edge/.env
ExecStart=/opt/sop-edge/.venv/bin/python -m src.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable sop-edge
sudo systemctl start sop-edge
```

### 6.6 摄像头验证

```bash
# 测试 USB 摄像头
python3 -c "
import cv2
cap = cv2.VideoCapture(0)
ret, frame = cap.read()
print(f'分辨率: {frame.shape[1]}x{frame.shape[0]}' if ret else '摄像头打开失败')
cap.release()
"

# 测试 RTSP
python3 -c "
import cv2
cap = cv2.VideoCapture('rtsp://admin:password@10.10.30.101:554/Streaming/Channels/101')
ret, frame = cap.read()
print(f'RTSP OK: {frame.shape[1]}x{frame.shape[0]}' if ret else 'RTSP 连接失败')
cap.release()
"
```

---

## 7. Step 3：安全加固

### 7.1 HTTPS（TLS 证书）

使用 Nginx 反向代理 + Let's Encrypt 或自签证书：

```bash
# 安装 certbot（公网环境）
sudo apt install certbot
sudo certbot certonly --standalone -d sop.your-domain.com

# 或自签证书（内网环境）
openssl req -x509 -nodes -days 365 \
  -newkey rsa:2048 \
  -keyout /etc/ssl/sop.key \
  -out /etc/ssl/sop.crt \
  -subj "/CN=sop.your-domain.com"
```

修改 `nginx.conf` 添加 HTTPS：

```nginx
server {
    listen 443 ssl;
    server_name sop.your-domain.com;
    ssl_certificate /etc/ssl/sop.crt;
    ssl_certificate_key /etc/ssl/sop.key;
    # ... 其余配置同原有 nginx.conf
}
server {
    listen 80;
    server_name sop.your-domain.com;
    return 301 https://$host$request_uri;
}
```

### 7.2 MQTT 安全

```bash
# 1. 生成密码文件
docker compose exec mqtt mosquitto_passwd -c /mosquitto/config/passwd sop_mqtt_user
# 输入密码

# 2. 修改 deploy/mosquitto.conf
#    取消注释 allow_anonymous false 和 password_file 行

# 3. 更新 .env
SOP_MQTT_USERNAME=sop_mqtt_user
SOP_MQTT_PASSWORD=<mqtt密码>

# 4. 重启
docker compose restart mqtt
```

### 7.3 端口安全

生产环境中，`docker-compose.yml` 已将所有端口绑定到 `127.0.0.1`。
如果从外部访问，通过宿主机 Nginx 反向代理暴露，而不是直接开放端口。

### 7.4 数据库备份

```bash
# 创建备份脚本
cat > /opt/sop-poka-yoke/scripts/backup.sh << 'BEOF'
#!/bin/bash
BACKUP_DIR="/opt/backups/sop"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

# PostgreSQL
docker compose exec -T postgres pg_dump -U sop_admin sop_pokayoke | \
  gzip > "$BACKUP_DIR/db_${TIMESTAMP}.sql.gz"

# MinIO (可选 - 使用 mc mirror)
# mc mirror sop/ "$BACKUP_DIR/minio_${TIMESTAMP}/"

# 清理 30 天前的备份
find "$BACKUP_DIR" -name "*.gz" -mtime +30 -delete

echo "备份完成: $BACKUP_DIR/db_${TIMESTAMP}.sql.gz"
BEOF
chmod +x /opt/sop-poka-yoke/scripts/backup.sh

# 配置 crontab（每天凌晨 2 点备份）
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/sop-poka-yoke/scripts/backup.sh >> /var/log/sop-backup.log 2>&1") | crontab -
```

---

## 8. Step 4：初始化与验证

### 8.1 创建管理员账户

```bash
# 通过 API 创建（首次部署后）
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "Admin@2024!Strong",
    "display_name": "管理员",
    "role": "admin"
  }'
```

### 8.2 创建工位

登录 Web 界面（http://localhost:8080），进入「工位管理」：

1. 新增工位，填写名称、产线、边缘设备 ID、摄像头 URL
2. 确保工位名称与边缘端 `.env` 中的 `SOP_STATION_ID` 一致

### 8.3 上传 SOP 模板

进入「SOP 配置」 → 「新建模板」：

1. 填写模板名称、版本、产品型号
2. 添加步骤（名称、描述、动作类型、超时时间、必需对象）
3. 保存

或使用「标准学习」功能：上传标准作业视频 → AI 自动分析生成模板。

### 8.4 端到端验证

1. **登录** → Web 界面登录
2. **工位管理** → 确认工位状态正常
3. **新建工单** → 创建一个测试工单
4. **观察 Dashboard** → 确认实时数据更新
5. **边缘端日志** → 确认 YOLO + VLM 推理正常
6. **报警** → 模拟一个 NG 场景，确认报警触发
7. **视频回放** → 确认录像可回放

---

## 9. 远程访问配置

### 9.1 内网访问（宿主机 Nginx 反向代理）

Docker 内所有端口绑定在 `127.0.0.1`，外部无法直接访问。
通过宿主机 Nginx 反向代理，让局域网内其他设备可以访问系统。

**安装并配置：**

```bash
# 1. 安装 Nginx
sudo apt install -y nginx

# 2. 部署配置文件
sudo cp deploy/nginx-host.conf /etc/nginx/sites-available/sop
sudo ln -s /etc/nginx/sites-available/sop /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default  # 移除默认站点

# 3. 测试并重载
sudo nginx -t
sudo systemctl reload nginx
```

配置完成后，局域网内其他设备通过 `http://<服务器IP>` 即可访问系统。

**可选：HTTPS 支持**

`deploy/nginx-host.conf` 中有完整的 HTTPS 配置（已注释），取消注释并提供证书即可启用。

内网自签证书：
```bash
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/sop.key -out /etc/ssl/sop.crt \
  -subj "/CN=sop.thundercomm.local"
```

### 9.2 外网远程访问（Cloudflare Tunnel）

Cloudflare Tunnel 可以在不暴露公网 IP 的情况下，安全地让外网用户访问系统。

**前置条件：**
- Cloudflare 账号（免费）
- 一个域名（已托管在 Cloudflare DNS）

**安装步骤：**

```bash
# 1. 安装 cloudflared
curl -L --output cloudflared.deb \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb

# 2. 登录 Cloudflare
cloudflared tunnel login
# 浏览器打开链接完成授权

# 3. 创建隧道
cloudflared tunnel create sop-poka-yoke
# 记录输出的 Tunnel ID

# 4. 配置隧道
cat > ~/.cloudflared/config.yml << EOF
tunnel: <Tunnel-ID>
credentials-file: /root/.cloudflared/<Tunnel-ID>.json

ingress:
  - hostname: sop.your-domain.com
    service: http://127.0.0.1:8080
  - hostname: sop.your-domain.com
    path: /api/ws/
    service: http://127.0.0.1:8080
    originRequest:
      httpHostHeader: sop.your-domain.com
  - service: http_status:404
EOF

# 5. 配置 DNS
cloudflared tunnel route dns sop-poka-yoke sop.your-domain.com

# 6. 运行隧道
cloudflared tunnel run sop-poka-yoke
```

**设为系统服务（自动启动）：**

```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

配置完成后，外网用户通过 `https://sop.your-domain.com` 即可安全访问系统。
Cloudflare 自动提供 HTTPS 证书，无需手动配置 TLS。

### 9.3 访问方案对比

| 方案 | 适用场景 | 安全性 | 是否需要公网 IP |
|------|---------|--------|---------------|
| 宿主机 Nginx | 局域网内操作员/管理员 | 中 | 不需要 |
| Cloudflare Tunnel | 远程管理员/技术支持 | 高 | 不需要 |
| VPN (WireGuard) | 远程团队常驻使用 | 最高 | 需要 |
| 公网直连 | 不推荐 | 低 | 需要 |

---

## 10. 日常运维

### 9.1 查看日志

```bash
# 服务器端
docker compose logs -f server     # API 日志
docker compose logs -f postgres   # 数据库日志
docker compose logs -f mqtt       # MQTT 日志

# 边缘端
journalctl -u sop-edge -f
```

### 9.2 服务重启

```bash
# 重启单个服务
docker compose restart server

# 重启全部
docker compose restart

# 停止全部
docker compose down

# 启动全部
docker compose up -d
```

### 9.3 数据清理

通过 Web 界面「数据管理」页面：

1. 查看过期数据统计
2. 预览清理（不删除，仅统计）
3. 执行清理（按保留策略永久删除）

### 9.4 监控告警

Grafana 推荐监控面板：

| 指标 | 告警阈值 |
|------|---------|
| API 响应时间 P95 | > 2s |
| 工位离线时间 | > 5min |
| 磁盘使用率 | > 85% |
| NG 连续次数 | > 3 次 |
| 未确认报警数 | > 10 |

---

## 11. 故障排查

### 10.1 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| 登录失败 401 | JWT 密钥不一致 | 检查 `.env` 中 `SOP_JWT_SECRET` |
| 边缘端无法连接 MQTT | 防火墙 / 密码错误 | `telnet <server> 1883`；检查 MQTT 凭证 |
| 上传文件失败 | MinIO 密码不匹配 | 对比 `.env` 中 `MINIO_PASSWORD` 与 `SOP_MINIO_SECRET_KEY` |
| 摄像头画面卡顿 | USB 带宽 / RTSP 超时 | 降低分辨率；检查网线连接 |
| YOLO 推理慢 | 无 GPU 加速 | 安装 CUDA；或使用 ONNX Runtime |
| 数据库连接池耗尽 | 并发过高 | 增大 `pool_size` 和 `max_overflow` |

### 10.2 健康检查命令

```bash
# 全部容器状态
docker compose ps

# 数据库连通性
docker compose exec postgres pg_isready -U sop_admin -d sop_pokayoke

# Redis
docker compose exec redis redis-cli -a <password> ping

# MinIO
curl -s http://localhost:9000/minio/health/live

# MQTT
mosquitto_sub -h localhost -t '$SYS/#' -C 1 -W 3

# API
curl http://localhost:8000/api/health
```

---

## 12. 升级流程

### 11.1 标准升级

```bash
cd /opt/sop-poka-yoke

# 1. 备份
bash scripts/backup.sh

# 2. 拉取最新代码
git pull origin main

# 3. 重新构建
docker compose build server web

# 4. 数据库迁移
source .env
cd packages/server && alembic upgrade head && cd ../..

# 5. 滚动重启
docker compose up -d server web

# 6. 验证
curl http://localhost:8000/api/health
```

### 11.2 边缘端升级

```bash
# 每台边缘设备
cd /opt/sop-edge
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart sop-edge
```

### 11.3 回滚

```bash
# 代码回滚
git checkout <previous-tag>
docker compose build server web
docker compose up -d server web

# 数据库回滚（如有迁移）
cd packages/server && alembic downgrade -1 && cd ../..
```

---

## 附录

### A. 端口映射表

| 服务 | 容器端口 | 宿主机映射 | 说明 |
|------|---------|-----------|------|
| PostgreSQL | 5432 | 127.0.0.1:5432 | 仅本机访问 |
| Redis | 6379 | 127.0.0.1:6379 | 仅本机访问 |
| MinIO API | 9000 | 127.0.0.1:9000 | 仅本机访问 |
| MinIO Console | 9001 | 127.0.0.1:9001 | 仅本机访问 |
| MQTT | 1883 | 127.0.0.1:1883 | 仅本机访问 |
| MQTT WebSocket | 9883 | 127.0.0.1:9883 | 仅本机访问 |
| API Server | 8000 | 127.0.0.1:8000 | 通过 Nginx 反向代理 |
| Web | 80 | 127.0.0.1:8080 | 通过 Nginx 反向代理 |
| Prometheus | 9090 | 127.0.0.1:9090 | 仅本机访问 |
| Grafana | 3000 | 127.0.0.1:3000 | 仅本机访问 |

### B. 文件结构

```
/opt/sop-poka-yoke/
├── .env                      # 环境变量（不提交 git）
├── docker-compose.yml        # 生产 Docker 编排
├── docker-compose.dev.yml    # 开发环境
├── deploy/
│   ├── mosquitto.conf        # MQTT 配置
│   └── prometheus.yml        # Prometheus 配置
├── scripts/
│   ├── deploy.sh             # 一键部署脚本
│   ├── init_minio.sh         # MinIO 初始化
│   └── backup.sh             # 数据库备份
├── packages/
│   ├── server/               # 后端 API
│   ├── web/                  # 前端 SPA
│   ├── edge/                 # 边缘推理
│   └── shared/               # 共享代码
└── DEPLOY.md                 # 本文档
```

### C. 检查清单

部署前检查：

- [ ] `.env` 中所有 `changeme` 已替换为强密码
- [ ] `SOP_JWT_SECRET` 已设置为至少 32 字符的随机密钥
- [ ] CORS_ORIGINS 已设置为实际域名
- [ ] MQTT 已启用密码认证（生产环境）
- [ ] HTTPS 已配置（公网环境）
- [ ] 数据库备份 crontab 已配置
- [ ] 防火墙规则已配置
- [ ] 摄像头已连接并测试通过
- [ ] 边缘端 GPU/NPU 驱动已安装
- [ ] AI 模型（YOLO + VLM）已下载

部署后验证：

- [ ] `docker compose ps` 所有容器 healthy
- [ ] API 健康检查通过
- [ ] Web 界面可正常登录
- [ ] 管理员账户已创建
- [ ] 至少一个工位已配置
- [ ] 至少一个 SOP 模板已创建
- [ ] 边缘端推理正常工作
- [ ] MQTT 消息可正常收发
- [ ] MinIO 上传/下载正常
- [ ] 报警触发和通知正常
