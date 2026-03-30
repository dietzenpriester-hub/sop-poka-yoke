.PHONY: dev-up dev-down server-test edge-test web-install web-dev db-migrate codegen prod-up prod-down

# === 开发环境 ===
dev-up:
	docker compose -f docker-compose.dev.yml up -d

dev-down:
	docker compose -f docker-compose.dev.yml down

# === 服务端 ===
server-dev:
	cd packages/server && uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

server-test:
	cd packages/server && pytest -q

# === 边缘端 ===
edge-test:
	cd packages/edge && pytest -q

# === 前端 ===
web-install:
	cd packages/web && pnpm install

web-dev:
	cd packages/web && pnpm dev

# === 数据库 ===
db-migrate:
	cd packages/server && alembic upgrade head

db-revision:
	@if [ -z "$(msg)" ]; then echo "用法: make db-revision msg=\"描述\""; exit 1; fi
	cd packages/server && alembic revision --autogenerate -m "$(msg)"

# === 协议生成 ===
codegen:
	bash $(CURDIR)/packages/shared/codegen.sh

# === 生产部署 ===
prod-up:
	@test -f .env || (echo "错误: 请先复制 .env.example 为 .env 并配置密钥" && exit 1)
	docker compose up -d --build

prod-down:
	docker compose down
