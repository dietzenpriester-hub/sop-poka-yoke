"""MES/ERP 接口适配器（占位）"""

from loguru import logger


class MESAdapter:

    def __init__(self, api_url: str = "") -> None:
        self.api_url = api_url

    async def push_workorder_result(self, sn: str, status: str, data: dict) -> bool:
        if not self.api_url:
            logger.debug("MES 未配置，跳过推送")
            return False
        logger.info("推送 MES: sn={} status={}", sn, status)
        return True
