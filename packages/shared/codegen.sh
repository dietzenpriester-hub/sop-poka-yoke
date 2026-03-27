#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PY_OUT="generated/python"
TS_OUT="generated/typescript"

mkdir -p "$PY_OUT" "$TS_OUT"

echo "从 JSON Schema 生成 Python Pydantic 模型..."
datamodel-codegen \
  --input schemas/ \
  --input-file-type jsonschema \
  --output "$PY_OUT" \
  --output-model-type pydantic_v2.BaseModel \
  --use-standard-collections \
  --use-schema-description

echo "从 JSON Schema 生成 TypeScript 接口..."
npx json2ts \
  -i schemas/ \
  -o "$TS_OUT" \
  --unreachableDefinitions false

echo "codegen 完成: $PY_OUT , $TS_OUT"
