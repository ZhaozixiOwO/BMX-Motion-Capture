# 🚴 Smart BMX

### Intelligent BMX Posture Visualization & Motion Analysis System  
### 智能 BMX 姿态可视化与动作分析系统

An end-to-end BMX analysis platform integrating embedded sensors, real-time visualization, and AI pose estimation.  
一个结合嵌入式传感器、实时数据可视化与 AI 姿态识别的 BMX 全栈分析平台。

---

## ✨ Features | 功能特性

### 📡 Real-time Sensor Streaming | 实时传感器数据流

- ESP32-S3 + MPU6050 streams accelerometer and gyroscope data via WebSocket  
  ESP32-S3 + MPU6050 通过 WebSocket 实时传输加速度计与陀螺仪数据

- Multi-device synchronization support  
  支持多设备同步连接

- Hardware & software watchdog for stability  
  内置硬件与软件 Watchdog 提升稳定性

- Live device status indicator  
  实时设备状态指示

---

### 🧠 Sensor Fusion (Madgwick AHRS) | 传感器融合

- Converts raw IMU data into stable orientation estimation  
  将原始 IMU 数据转换为稳定姿态角

- Real-time Roll / Pitch / Yaw output  
  实时输出 Roll / Pitch / Yaw

- Quaternion-based orientation calculation  
  基于四元数的姿态解算

---

### 📊 Visualization Dashboard | 可视化仪表盘

#### Desktop Application | 桌面端

- PyQt6 + pyqtgraph
- Real-time IMU charts  
  实时 IMU 曲线图
- 30-second rolling window  
  30 秒动态窗口

#### Web Dashboard | Web 端

- Three.js 3D orientation visualization  
  Three.js 三维姿态可视化

- Chart.js live sensor charts  
  Chart.js 实时数据图表

- Socket.IO real-time communication  
  Socket.IO 实时通信

---

### 🤖 YOLO Pose Detection | YOLO 姿态识别

- Custom-trained YOLO11x-pose model  
  自定义训练 YOLO11x-pose 模型

- BMX rider + bike skeleton detection  
  BMX 车手与车架骨架识别

- Supports custom 6-point BMX skeleton  
  支持自定义 6 点 BMX 骨架

- Video drag-and-drop inference  
  支持视频拖拽推理

---

# 🏗️ System Architecture | 系统架构

```text
ESP32-S3 Sensors
        │
   WebSocket
        │
 ┌──────────────┐
 │ Python Server│
 └──────┬───────┘
        │
 ┌──────┼─────────────┐
 │      │             │
 ▼      ▼             ▼
PyQt6  Flask       YOLO Pose
GUI    Dashboard   Detection
```

---

# 📂 Project Structure | 项目结构

```text
FYP-BMX/
├── main/              # Desktop application
├── yolo/              # YOLO training & inference
├── Hardware/          # ESP32 firmware & backend
└── requirements.txt
```

---

# 🚀 Quick Start | 快速开始

## 1️⃣ Install Dependencies | 安装依赖

```bash
pip install -r requirements.txt
```

---

## 2️⃣ Launch Desktop Application | 启动桌面应用

```bash
python main/bmx_ui.py
```

---

## 3️⃣ Launch Web Dashboard | 启动 Web 可视化

```bash
pip install -r Hardware/py/requirements.txt
python Hardware/py/run.py
```

Open in browser / 浏览器访问：

```text
http://localhost:5050
```

---

## 4️⃣ Flash ESP32 Firmware | 烧录 ESP32 固件

1. Install Arduino dependencies  
   安装 Arduino 依赖库

2. Configure WiFi credentials  
   配置 WiFi 信息

3. Upload `.ino` firmware to ESP32-S3  
   将 `.ino` 固件烧录至 ESP32-S3

---

# 🧩 Tech Stack | 技术栈

| Layer 层级 | Technology 技术 |
|---|---|
| Embedded | ESP32-S3, MPU6050, WiFi |
| Backend | Python, Flask, Socket.IO |
| Desktop | PyQt6, pyqtgraph |
| Frontend | Three.js, Chart.js |
| AI | YOLO11x-pose, OpenCV, PyTorch |
| Communication | WebSocket |

---

# 📌 Custom BMX Skeleton | 自定义 BMX 骨架

```text
0  Front Wheel
1  Body Point 1
2  Center Hub
3  Rear Wheel
4  Body Point 3
5  Body Point 4
```

---

# 📜 License | 许可证

Academic Final Year Project (FYP).  
仅用于毕业设计与学术研究用途。
