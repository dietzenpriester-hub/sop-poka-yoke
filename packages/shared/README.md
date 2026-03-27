# packages/shared — 共享协议包

## 协议变更流程

1. 修改 `schemas/*.schema.json` 中的 JSON Schema 定义
2. 运行 `bash codegen.sh` 自动生成 Python 类和 TypeScript 接口
3. CI 流水线自动校验生成文件与 Schema 一致性
4. 前后端字段 100% 同步，杜绝手动维护导致的字段不一致

## 目录结构

- `schemas/` — JSON Schema 源文件（唯一真实源头）
- `generated/python/` — 自动生成的 Pydantic v2 模型（勿手动编辑）
- `generated/typescript/` — 自动生成的 TypeScript 接口（勿手动编辑）
- `mqtt_topics.py` — MQTT 主题定义
- `event_types.py` — 事件类型枚举
- `alert_codes.py` — 报警代码定义
- `constants.py` — 全局常量
