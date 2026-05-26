# imu_receive.py
import asyncio
import json
from datetime import datetime
import threading

import websockets

# ======【给 PyQt 用：信号桥接】======
from PyQt6.QtCore import QObject, pyqtSignal


class DataBridge(QObject):
  """
  桥接线程和 UI 线程：
    - imu_data_signal: 传 IMU 的 dict
    - status_signal:   传字符串状态（连接/断开/错误等）
  """
  imu_data_signal = pyqtSignal(dict)
  status_signal = pyqtSignal(str)


# ======【通用格式化函数：终端 + UI 都可以用】======
def fmt(value, digits=2):
  """
  安全格式化：
  - 数字 -> 保留 digits 位小数
  - 其他 -> 原样转字符串
  """
  try:
    return f"{float(value):.{digits}f}"
  except (TypeError, ValueError):
    return str(value)


# ======【给 PyQt 用的 WebSocket 服务器（后台线程 + asyncio）】======
class IMUWebSocketServer:
  """
  在后台线程跑 asyncio WebSocket server，
  收到 JSON 后通过 DataBridge 抛给 UI。
  """
  def __init__(self, host: str, port: int, bridge: DataBridge):
    self.host = host
    self.port = port
    self.bridge = bridge
    self.server = None
    self.loop = None
    self.thread = None

  async def handler(self, websocket, path):
    client_ip = websocket.remote_address[0] if websocket.remote_address else "unknown"
    self.bridge.status_signal.emit(f"ESP32 Connected: {client_ip}")
    try:
      async for message in websocket:
        try:
          data = json.loads(message)
          # 直接把原始 dict 发给 UI（包含 device_id 等全部字段）
          self.bridge.imu_data_signal.emit(data)
        except json.JSONDecodeError:
          self.bridge.status_signal.emit("Received non-JSON message")
    except websockets.exceptions.ConnectionClosed:
      self.bridge.status_signal.emit(f"ESP32 Disconnected: {client_ip}")
    except Exception as e:
      self.bridge.status_signal.emit(f"WS handler error: {e}")

  async def start_server(self):
    self.server = await websockets.serve(
      self.handler, self.host, self.port, ping_interval=None
    )
    self.bridge.status_signal.emit(f"Server started on {self.host}:{self.port}")
    await self.server.wait_closed()

  def _run_loop(self):
    self.loop = asyncio.new_event_loop()
    asyncio.set_event_loop(self.loop)
    try:
      self.loop.run_until_complete(self.start_server())
    except Exception as e:
      self.bridge.status_signal.emit(f"Loop error: {e}")
    finally:
      self.loop.close()

  def start(self):
    """
    给 MainWindow 调用：
      self.server = IMUWebSocketServer("0.0.0.0", 5123, self.bridge)
      self.server.start()
    """
    self.thread = threading.Thread(target=self._run_loop, daemon=True)
    self.thread.start()

  def stop(self):
    """
    给 MainWindow 调用：
      self.server.stop()
    """
    if self.loop is not None:
      if self.server is not None:
        try:
          self.loop.call_soon_threadsafe(self.server.close)
        except Exception:
          pass
      self.loop.call_soon_threadsafe(self.loop.stop)
    if self.thread is not None and self.thread.is_alive():
      self.thread.join(timeout=1.0)
    self.bridge.status_signal.emit("Server stopped")


# ======【终端版接收器：沿用你原来的打印逻辑，兼容 device_id】======
async def handle_client_console(websocket):
  client_ip = websocket.remote_address[0] if websocket.remote_address else "unknown"
  print(f"客户端连接来自: {client_ip}")
  try:
    async for message in websocket:
      try:
        data = json.loads(message)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        device_id = data.get("device_id", "UNKNOWN_ID")
        ax = data.get("acceleration_x", "N/A")
        ay = data.get("acceleration_y", "N/A")
        az = data.get("acceleration_z", "N/A")
        gx = data.get("gyro_x", "N/A")
        gy = data.get("gyro_y", "N/A")
        gz = data.get("gyro_z", "N/A")
        temp = data.get("temperature", "N/A")
        watchdog = data.get("watchdog", "N/A")

        print("\n" + "=" * 60)
        print(f"[{timestamp}] 来自 {client_ip} 的数据")
        print(f"设备 ID: {device_id}")
        print(
          f"加速度 X: {fmt(ax)} m/s²  "
          f"加速度 Y: {fmt(ay)} m/s²  "
          f"加速度 Z: {fmt(az)} m/s²"
        )
        print(
          f"陀螺仪 X: {fmt(gx)} rad/s  "
          f"陀螺仪 Y: {fmt(gy)} rad/s  "
          f"陀螺仪 Z: {fmt(gz)} rad/s"
        )
        print(f"温度: {fmt(temp)} °C")
        print(f"Watchdog: {watchdog}")
      except json.JSONDecodeError:
        print(f"无效的JSON数据: {message}")
  except websockets.exceptions.ConnectionClosed:
    print(f"客户端 {client_ip} 断开连接")


async def main_async_console():
  server_ip = "0.0.0.0"
  port = 5123
  print(f"ESP WebSocket 接收器启动，监听 {server_ip}:{port}")
  async with websockets.serve(handle_client_console, server_ip, port, ping_interval=None):
    await asyncio.Future()  # 一直挂起直到 Ctrl+C


def start_receiver():
  """
  终端版入口：
    python imu_receive.py
  或者在别的脚本里：
    from imu_receive import start_receiver
    start_receiver()
  """
  asyncio.run(main_async_console())


# 如果直接运行这个文件，就当“终端调试版”用
if __name__ == "__main__":
  start_receiver()