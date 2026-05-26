import eventlet
eventlet.monkey_patch()  # 必须放在所有 import 之前

from flask import Flask
from app.imu_server import socketio, register_routes, start_esp_receiver
import threading

app = Flask(__name__, static_folder='static')

register_routes(app)

if __name__ == '__main__':
    host = "0.0.0.0"
    port = 5050
    print(f"\n🚀 服务已启动，请访问: http://{host}:{port}\n")

    # 启动 ESP WebSocket 接收器（后台线程）
    threading.Thread(
        target=lambda: start_esp_receiver(app),  # 把 app 传进去
        daemon=True
    ).start()

    socketio.run(app, host=host, port=port)