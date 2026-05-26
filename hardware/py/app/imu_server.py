import asyncio
import json
import time
from datetime import datetime

import numpy as np
import websockets
from app.madgwick import MadgwickAHRS
from engineio.async_drivers import threading, eventlet
from flask import send_from_directory, Flask, request
from flask_socketio import SocketIO

# 初始化 SocketIO
socketio = SocketIO(cors_allowed_origins='*', async_mode='eventlet', ping_timeout=5, ping_interval=10)

# Madgwick 姿态解算器
ahrs = MadgwickAHRS(sample_period=1 / 20.0, beta=0.1)
last_update = None
last_broadcast_time = 0
broadcast_interval = 0.2  # 每200ms广播一次


# ------------------ Flask 路由 ------------------
def register_routes(app):
  socketio.init_app(app)
  
# ------------------ 页面注册 ------------------
  @app.route('/')
  def index():
    return send_from_directory(app.static_folder, 'index.html')
  
  @app.route('/mpu-vis')
  def mpu_vis():
    return send_from_directory(app.static_folder, 'mpu_vis.html')
  
  @app.route('/pose-detection')
  def yolo_pose_detection():
    return send_from_directory(app.static_folder, 'pose_detection.html')
  
# ------------------   ------------------
  @app.route('/<path:path>')
  def static_proxy(path):
    return send_from_directory(app.static_folder, path)
  
  @app.route('/api/data', methods=['POST'])
  def receive_data():
    data = request.json
    process_and_broadcast(data)
    return {'status': 'ok'}
  
  @socketio.on('esp_data', namespace='/')
  def handle_esp_data(data):
    process_and_broadcast(data)
  
  @socketio.on('connect', namespace='/')
  def handle_connect():
    client_sid = request.sid
    print(f"Client connected: {client_sid}")
    eventlet.spawn(some_async_task, client_sid)  # 传递 sid
  
  def some_async_task(sid):
    while True:
      eventlet.sleep(1)  # 每秒发送一次
      socketio.emit('sensor_data', {'test': 'Hello'}, namespace='/', to=sid)


# ------------------ 处理 & 广播函数 ------------------
# 在 process_and_broadcast 之前添加全局变量
last_broadcast_time = 0
broadcast_interval = 0.1  # second


def process_and_broadcast(data):
  global last_update, last_broadcast_time
  current_time = time.time()
  
  if current_time - last_broadcast_time < broadcast_interval:
    print(f"时间间隔未到，跳过广播 (间隔: {current_time - last_broadcast_time}s)")
    return
  
  print(f"处理数据: {data}")
  start_time = time.time()
  acc = [
    data.get('acceleration_x', 0.0),
    data.get('acceleration_y', 0.0),
    data.get('acceleration_z', 0.0)
  ]
  gyro = [
    data.get('gyro_x', 0.0),
    data.get('gyro_y', 0.0),
    data.get('gyro_z', 0.0)
  ]
  
  now = time.time()
  if last_update is not None:
    ahrs.sample_period = now - last_update
  last_update = now
  
  ahrs.update(gyro, acc)
  roll, pitch, yaw = MadgwickAHRS.quaternion_to_euler(ahrs.q)
  
  out = {
    'acceleration_x': float(acc[0]),
    'acceleration_y': float(acc[1]),
    'acceleration_z': float(acc[2]),
    'gyro_x': float(gyro[0]),
    'gyro_y': float(gyro[1]),
    'gyro_z': float(gyro[2]),
    'temperature': float(data.get('temperature', 0.0)),
    'roll': float(np.degrees(roll)) if not isinstance(roll, (int, float)) else float(roll),
    'pitch': float(np.degrees(pitch)) if not isinstance(pitch, (int, float)) else float(pitch),
    'yaw': float(np.degrees(yaw)) if not isinstance(yaw, (int, float)) else float(yaw)
  }
  
  print(f"准备广播 sensor_data: {out}")
  try:
    socketio.emit('sensor_data', out, namespace='/')
    print(
      f"广播 sensor_data 成功，数据: {out}, 处理时间: {(time.time() - start_time) * 1000:.2f}ms, 客户端: {list(socketio.server.eio.sockets.keys())}")
    last_broadcast_time = current_time
  except Exception as e:
    print(f"广播 sensor_data 失败: {e}")


# ------------------ ESP 原生 WebSocket 接收 ------------------
async def handle_esp_client(websocket):
  client_ip = websocket.remote_address[0]
  print(f"ESP 客户端连接来自: {client_ip}")
  try:
    async for message in websocket:
      try:
        data = json.loads(message)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{timestamp}] 来自 {client_ip} 的数据:")
        print(f"加速度 X: {data.get('acceleration_x', 0):.2f} m/s²  "
              f"Y: {data.get('acceleration_y', 0):.2f} m/s²  "
              f"Z: {data.get('acceleration_z', 0):.2f} m/s²")
        print(f"陀螺仪 X: {data.get('gyro_x', 0):.2f} rad/s  "
              f"Y: {data.get('gyro_y', 0):.2f} rad/s  "
              f"Z: {data.get('gyro_z', 0):.2f} rad/s")
        print(f"温度: {data.get('temperature', 0):.2f} °C")
        
        process_and_broadcast(data)
      except json.JSONDecodeError:
        print(f"无效的JSON数据: {message}")
  except websockets.exceptions.ConnectionClosed:
    print(f"ESP 客户端 {client_ip} 断开连接")


async def esp_websocket_server(app):
  server_ip = "0.0.0.0"
  port = 5123
  print(f"ESP WebSocket 接收器启动，监听 {server_ip}:{port}")
  async with websockets.serve(handle_esp_client, server_ip, port, ping_interval=None):
    await asyncio.Future()


def start_esp_receiver(app):
  asyncio.run(esp_websocket_server(app))


# ------------------ 主程序 ------------------
if __name__ == '__main__':
  app = Flask(__name__, static_folder="static")
  register_routes(app)
  
  threading.Thread(
    target=lambda: start_esp_receiver(app),
    daemon=True
  ).start()
  
  socketio.run(app, host="0.0.0.0", port=5050)
