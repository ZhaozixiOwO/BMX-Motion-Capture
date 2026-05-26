# Smart BMX — Intelligent Posture Visualization System

A full-stack BMX cycling posture analysis system combining embedded sensors, real-time data visualization, and AI-powered pose estimation.

## System Architecture

```
[BMX Bike]
  │
  ├── ESP32-S3 + MPU6050 (IMU) ──WiFi── WebSocket ──┐
  └── ESP32-S3 + A3144 (Hall)  ──WiFi── WebSocket ──┤
                                                     ▼
                                         ┌───────────────────┐
                                         │  Python Backend   │
                                         │  WebSocket :5123  │
                                         └───────┬───────────┘
                                                 │
                          ┌──────────────────────┼──────────────────────┐
                          ▼                      ▼                      ▼
               ┌─────────────────┐   ┌─────────────────────┐   ┌──────────────┐
               │  PyQt6 Desktop  │   │  Flask Web Server   │   │  YOLO Pose   │
               │  pyqtgraph      │   │  Socket.IO :5050    │   │  Detection   │
               │  Real-time      │   │  Madgwick AHRS      │   │  :5000       │
               └─────────────────┘   └──────────┬──────────┘   └──────────────┘
                                                │
                                     ┌──────────┴──────────┐
                                     ▼                     ▼
                              ┌──────────────┐   ┌──────────────────┐
                              │  Three.js 3D │   │  Chart.js        │
                              │  Orientation │   │  Accel & Gyro    │
                              │  Box         │   │  Time-series     │
                              └──────────────┘   └──────────────────┘
```

## Project Structure

```
FYP-BMX/
├── main/                          # PyQt6 desktop application
│   ├── bmx_ui.py                  # Main window: IMU monitor + video inference UI
│   ├── video_process.py           # YOLO pose estimation engine
│   └── imu_receive.py             # WebSocket server for ESP32 data
│
├── yolo/                          # YOLO model training & inference
│   ├── train.py                   # Training script (YOLO11x-pose on MCBMX dataset)
│   ├── predict.py                 # Standalone video inference with custom skeleton
│   ├── pose-model/                # Pre-trained & fine-tuned model checkpoints
│   │   ├── yolo11x-pose.pt        # Base model (Ultralytics official)
│   │   ├── yolo11m-pose.pt        # Medium variant
│   │   └── ours/
│   │       ├── bmx04-x-50.pt      # Fine-tuned: 50 epochs
│   │       └── bmx05-x-100.pt     # Fine-tuned: 100 epochs
│   └── data/                      # MCBMX dataset (YOLOv8 format)
│       ├── MCBMX.v6i.yolov8.zip
│       └── MCBMX.v7i.yolov8.zip
│
├── Hardware/
│   ├── esp32_IMU_BMX/             # ESP32-S3 IMU firmware (MPU6050)
│   │   └── esp32_IMU_BMX.ino
│   ├── esp32_A3144_BMX/           # ESP32-S3 Hall sensor firmware
│   │   └── esp32_A3144_BMX.ino
│   ├── arduino_requirements.txt   # Arduino library dependencies
│   └── py/                        # Flask web backend
│       ├── run.py                 # Server entry point
│       ├── requirements.txt
│       ├── vis.py                 # Standalone matplotlib 3D visualization
│       ├── app/
│       │   ├── imu_server.py      # WebSocket receiver + Socket.IO broadcaster
│       │   ├── madgwick.py        # Madgwick AHRS sensor fusion algorithm
│       │   └── yolo_pose_detection.py  # YOLO pose detection API endpoint
│       └── static/
│           ├── index.html         # Landing page
│           ├── mpu_vis.html       # 3D orientation + live charts dashboard
│           ├── pose_detection.html # Video upload & pose detection page
│           └── js/
│               └── mpu-vis.js     # Three.js + Chart.js + Socket.IO client
│
└── requirements.txt               # Desktop app Python dependencies
```

## Features

### Real-time IMU Monitoring
- ESP32-S3 streams MPU6050 accelerometer (m/s²) and gyroscope (rad/s) data over WiFi via WebSocket at 2 Hz.
- **Multi-device support** — connect multiple ESP32s simultaneously (e.g., handlebars + frame), each identified by eFuse MAC.
- **Hardware watchdog** (3s timer) + **software watchdog** (5s loop / 10s data timeout) for field reliability.
- **LED status indicator**: solid = connecting/error, blinking (500 ms) = operational.

### Sensor Fusion — Madgwick AHRS
- Converts raw 6-axis IMU data into stable roll/pitch/yaw orientation estimates using the Madgwick filter.
- Output broadcast to web clients via Socket.IO at ~10 Hz.

### Real-time Visualization

| Platform | Charts | 3D | Tech |
|----------|--------|----|------|
| Desktop (macOS/Windows/Linux) | Acceleration + gyroscope, 30s rolling window | — | PyQt6 + pyqtgraph |
| Web dashboard | Acceleration + gyroscope, 10s rolling window | Three.js orientation box | Chart.js + Three.js |

- Spacebar toggles Madgwick filter on/off in the web dashboard to compare raw vs. fused orientation.

### YOLO Pose Detection
- **Custom-trained YOLO11x-pose model** on a self-annotated MCBMX dataset.
- Detects **6 custom keypoints**: front wheel, rear wheel, and 4 body-points connecting the rider and bike frame.
- Two inference modes:
  - **Athlete Body** — standard COCO human pose (17 keypoints).
  - **BMX Handler & Body** — custom bike + rider skeleton with green skeleton lines and blue keypoints.
- Supports drag-and-drop video input (.mp4, .mov, .avi, .mkv).

## Getting Started

### Prerequisites
- Python 3.10+
- Node.js (for Three.js / Chart.js static files are already vendored)
- ESP32-S3 SuperMini with Arduino IDE

### 1. Desktop App

```bash
pip install -r requirements.txt
python main/bmx_ui.py
```

Two tabs are available:
- **BMX Hardware Analysis** — real-time IMU values and scrolling line charts (starts WebSocket server on :5123 automatically).
- **BMX Visualize Inference** — drag a video, select a model, and run pose detection.

### 2. Web Dashboard

```bash
pip install -r Hardware/py/requirements.txt
python Hardware/py/run.py
```

Open `http://localhost:5050` in a browser. Available pages:
- `/mpu-vis` — 3D orientation box + live acceleration/gyroscope charts.
- `/pose-detection` — upload a video and run YOLO pose detection.

### 3. ESP32 Firmware

1. Install the Arduino libraries listed in `Hardware/arduino_requirements.txt`.
2. Open the `.ino` file in Arduino IDE.
3. Set `YOUR_WIFI_SSID`, `YOUR_WIFI_PASSWORD`, and `YOUR_SERVER_IP` to match your network.
4. Flash to ESP32-S3 SuperMini.

### 4. YOLO Training (Optional)

```bash
# Extract the MCBMX dataset
unzip yolo/data/MCBMX.v7i.yolov8.zip -d yolo/data/

# Run training
python yolo/train.py
```

## Hardware Pinout (ESP32-S3 SuperMini)

| Component | Pin | Notes |
|-----------|-----|-------|
| MPU6050 SDA | GPIO 4 | I²C data |
| MPU6050 SCL | GPIO 5 | I²C clock |
| A3144 Hall | GPIO 5 | Digital input (alternate use) |
| Status LED | GPIO 2 | Built-in LED |

## Custom BMX Skeleton Keypoints

```
Index  Name    Description
  0     fw     Front wheel
  1     b1     Body point 1
  2     b2     Body point 2 (center hub)
  3     bw     Rear wheel
  4     b3     Body point 3
  5     b4     Body point 4

Skeleton connections: b3→b2, b1→b2, b2→bw, bw→b3, b3→b4, b4→fw, b1→b4
```

## Key Technologies

| Layer | Stack |
|-------|-------|
| Embedded | ESP32-S3, WiFi, WebSocket, I²C, MPU6050, A3144 |
| Sensor Fusion | Madgwick AHRS, quaternion to Euler conversion |
| Backend | Python, asyncio, Flask-SocketIO, PyQt6, eventlet |
| Computer Vision | YOLO11x-pose, OpenCV, PyTorch (CUDA / Apple MPS) |
| Frontend | Three.js, Chart.js, pyqtgraph, matplotlib |
| Communication | WebSocket (JSON), Socket.IO |

## License

This project is an academic Final Year Project (FYP). All rights reserved.
