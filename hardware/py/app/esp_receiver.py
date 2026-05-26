import asyncio
import websockets
import json
from datetime import datetime

async def handle_client(websocket):
    client_ip = websocket.remote_address[0]
    print(f"客户端连接来自: {client_ip}")
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"\n[{timestamp}] 来自 {client_ip} 的数据:")
                print(f"加速度 X: {data.get('acceleration_x', 'N/A'):.2f} m/s² 加速度 Y: {data.get('acceleration_y', 'N/A'):.2f} m/s² 加速度 Z: {data.get('acceleration_z', 'N/A'):.2f} m/s²")
                print(f"陀螺仪 X: {data.get('gyro_x', 'N/A'):.2f} rad/s 陀螺仪 Y: {data.get('gyro_y', 'N/A'):.2f} rad/s 陀螺仪 Z: {data.get('gyro_z', 'N/A'):.2f} rad/s")
                print(f"温度: {data.get('temperature', 'N/A'):.2f} °C")
            except json.JSONDecodeError:
                print(f"无效的JSON数据: {message}")
    except websockets.exceptions.ConnectionClosed:
        print(f"客户端 {client_ip} 断开连接")

async def main_async():
    server_ip = "0.0.0.0"
    port = 5123
    print(f"ESP WebSocket 接收器启动，监听 {server_ip}:{port}")
    async with websockets.serve(handle_client, server_ip, port, ping_interval=None):
        await asyncio.Future()



def start_receiver():
    asyncio.run(main_async())