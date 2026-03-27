"""通过 Modbus TCP 控制三色灯和蜂鸣器"""

from enum import IntEnum

from loguru import logger
from pymodbus.client import ModbusTcpClient


class LightColor(IntEnum):
    OFF = 0
    GREEN = 1
    YELLOW = 2
    RED = 3
    RED_BLINK = 4


class ModbusAlertController:

    def __init__(self, host: str = "192.168.1.100", port: int = 502,
                 light_register: int = 0, buzzer_register: int = 1) -> None:
        self.host = host
        self.port = port
        self.light_reg = light_register
        self.buzzer_reg = buzzer_register
        self._client: ModbusTcpClient | None = None

    def connect(self) -> None:
        self._client = ModbusTcpClient(self.host, port=self.port)
        if self._client.connect():
            logger.info("Modbus 已连接: {}:{}", self.host, self.port)
        else:
            logger.error("Modbus 连接失败: {}:{}", self.host, self.port)

    def set_status(self, color: LightColor, buzzer: bool = False) -> None:
        if not self._client or not self._client.is_socket_open():
            self.connect()
        if self._client:
            self._client.write_register(self.light_reg, color.value)
            self._client.write_register(self.buzzer_reg, 1 if buzzer else 0)

    def alert_ok(self) -> None:
        self.set_status(LightColor.GREEN, buzzer=False)

    def alert_warning(self) -> None:
        self.set_status(LightColor.YELLOW, buzzer=True)

    def alert_error(self) -> None:
        self.set_status(LightColor.RED_BLINK, buzzer=True)

    def alert_idle(self) -> None:
        self.set_status(LightColor.OFF, buzzer=False)

    def disconnect(self) -> None:
        if self._client:
            self._client.close()
