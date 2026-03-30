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

    def write_register(self, address: int, value: int) -> None:
        if self._client:
            resp = self._client.write_register(address, value)
            if resp.isError():
                logger.error("PLC 写寄存器失败: addr={} value={} resp={}", address, value, resp)

    def read_register(self, address: int, count: int = 1) -> list[int]:
        if self._client:
            result = self._client.read_holding_registers(address, count)
            if not result.isError():
                return result.registers
        return []

    def disconnect(self) -> None:
        if self._client:
            self._client.close()
