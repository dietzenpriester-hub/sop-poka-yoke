"""SOP 模板加载与管理"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger


class SOPTemplateLoader:

    def __init__(self) -> None:
        self._templates: dict[str, dict] = {}

    def load_from_file(self, path: str | Path) -> dict:
        p = Path(path)
        with open(p, "r", encoding="utf-8") as f:
            template = json.load(f)
        self._templates[template["name"]] = template
        logger.info("SOP 模板已加载: {} ({})", template["name"], template.get("version", "N/A"))
        return template

    def load_from_dict(self, template: dict) -> dict:
        self._templates[template["name"]] = template
        return template

    def get(self, name: str) -> dict | None:
        return self._templates.get(name)

    def list_templates(self) -> list[str]:
        return list(self._templates.keys())
