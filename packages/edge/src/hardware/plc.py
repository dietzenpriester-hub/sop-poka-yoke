"""PLC 通信（Modbus TCP）"""

from loguru import logger
from pymodbus.client import ModbusTcpClient


class PLCController:

    def __init__(self, host: str = "192.168.1.200", port: int = 502) -> None:
        self.host = host
        self.port = port
        self._client: ModbusTcpClient | None = None

    def connect(self) -> None:
        self._client = ModbusTcpClient(self.host, port=self.port)
        if self._client.connect():
            logger.info("PLC 已连接: {}:{}", self.host, self.port)
        else:
            logger.error("PLC 连接失败: {}:{}", self.host, self.port)

    def write_register(self, address: int, value: int) -> bool:
        if not self._client:
            logger.warning("PLC 未连接，写寄存器失败: addr={} value={}", address, value)
            return False
        resp = self._client.write_register(address, value)
        if resp.isError():
            logger.warning("PLC 写寄存器失败: addr={} value={} resp={}", address, value, resp)
            return False
        return True

    def read_register(self, address: int, count: int = 1) -> list[int] | None:
        if not self._client:
            logger.warning("PLC 未连接，读寄存器失败: addr={} count={}", address, count)
            return None
        result = self._client.read_holding_registers(address, count)
        if result.isError():
            logger.warning("PLC 读寄存器失败: addr={} count={} resp={}", address, count, result)
            return None
        return result.registers

    def disconnect(self) -> None:
        if self._client:
            self._client.close()
