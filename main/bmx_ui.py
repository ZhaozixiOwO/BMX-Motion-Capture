import os
import platform
import sys
import time  # 用于真实时间轴

from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtWidgets import (
  QApplication
)
from PyQt6.QtWidgets import (
  QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
  QPushButton, QStackedWidget, QComboBox, QMessageBox,
  QGroupBox, QGridLayout, QScrollArea
)

from imu_receive import DataBridge, IMUWebSocketServer
from video_process import process_video

# 时间轴速度（控制“时间过得快不快”）
# 1.0 = 真实时间；<1 略慢；>1 略快
TIME_SCALE = 0.95

# 图上可见的时间窗口长度（控制“能同时看到多少秒”）
# 比如：10 表示只看最近 10 秒；30 表示最近 30 秒
WINDOW_SECONDS = 30


# 一个简单的拖拽控件，用来接收本地视频文件
class VideoDropWidget(QLabel):
  def __init__(self, parent=None):
    super().__init__(parent)
    self.setText("Drag your local video file (mp4 / avi / mov / mkv) here.")
    self.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self.setStyleSheet("""
      QLabel {
        border: 2px dashed #888;
        border-radius: 8px;
        padding: 20px;
        font-size: 14px;
        color: #555;
      }
    """)
    self.setAcceptDrops(True)
    self.video_path = None  # 保存当前被拖进来的视频路径
  
  def dragEnterEvent(self, event):
    # 仅当拖入的是文件路径时才接受
    if event.mimeData().hasUrls():
      event.acceptProposedAction()
    else:
      event.ignore()
  
  def dropEvent(self, event):
    urls = event.mimeData().urls()
    if not urls:
      return
    
    # 默认取第一个文件
    local_path = urls[0].toLocalFile()
    if not local_path:
      return
    
    # 简单过滤一下常见视频后缀
    allowed_ext = (".mp4", ".avi", ".mov", ".mkv")
    if not local_path.lower().endswith(allowed_ext):
      self.setText("不支持的文件类型，请拖入视频文件（mp4 / avi / mov / mkv）")
      self.video_path = None
      return
    
    self.video_path = local_path
    self.setText(f"已选择视频：\n{local_path}")


def open_in_file_manager(path: str):
  """
  根据当前操作系统，在文件管理器中打开指定路径（文件或文件夹）。
  - Windows: 资源管理器
  - macOS: Finder
  - Linux: 默认文件管理器（xdg-open）
  """
  if not os.path.exists(path):
    print(f"[WARN] 路径不存在：{path}")
    return
  
  # 如果传进来的是文件，就取它的上级目录
  if os.path.isfile(path):
    dir_path = os.path.dirname(path)
  else:
    dir_path = path
  
  system = platform.system()
  
  try:
    if system == "Windows":
      # 资源管理器
      os.startfile(dir_path)  # type: ignore[attr-defined]
    elif system == "Darwin":
      # macOS Finder
      import subprocess
      subprocess.run(["open", dir_path])
    else:
      # Linux / 其他 Unix 系
      import subprocess
      subprocess.run(["xdg-open", dir_path])
  except Exception as e:
    print(f"[ERROR] 打开文件管理器失败：{e}")


class ProcessWorker(QThread):
  finished = pyqtSignal(dict)
  error = pyqtSignal(str)
  
  def __init__(self, video_path: str, model_key: str, parent=None):
    super().__init__(parent)
    self.video_path = video_path
    self.model_key = model_key
  
  def run(self):
    try:
      result = process_video(self.video_path, model_key=self.model_key)
      self.finished.emit(result)
    except Exception as e:
      self.error.emit(str(e))


class MainWindow(QMainWindow):
  def __init__(self):
    super().__init__()
    
    self.device_plots = {}
    self.setWindowTitle("Smart BMX Visualize System")
    
    # ======== 上位机通讯桥 + WebSocket 服务器（自动启动） ========
    self.bridge = DataBridge()
    self.bridge.imu_data_signal.connect(self.on_imu_data)
    self.bridge.status_signal.connect(self.on_status)
    
    # 监听 0.0.0.0:5123，和你 ESP 代码里的端口一致
    self.server = IMUWebSocketServer(host="0.0.0.0", port=5123, bridge=self.bridge)
    self.server.start()  # 直接在这里启动
    # ===================================================
    
    self.current_video_path = None
    
    # 新增：用于存储每个 device_id 的显示组件（QGroupBox 和内部标签）
    self.device_displays: Dict[str, Dict[str, QLabel]] = {}
    # 新增：用于在网格布局中给每个 device plot 编号
    self.device_plot_count = 0
    
    # === 整体主Widget ===
    central = QWidget()
    self.setCentralWidget(central)
    
    main_layout = QVBoxLayout(central)
    main_layout.setContentsMargins(8, 8, 8, 8)
    main_layout.setSpacing(8)
    
    # === 顶部“Excel sheet 按钮”区域 ===
    top_bar = QHBoxLayout()
    top_bar.setSpacing(6)
    
    # 左侧：两个页面按钮
    btn_bar = QHBoxLayout()
    btn_bar.setSpacing(6)
    
    # 只保留两个按钮
    self.btn_hw = QPushButton("BMX Hardware Analysis")
    self.btn_vis = QPushButton("BMX Visualize Inference")
    
    for btn in [self.btn_hw, self.btn_vis]:
      btn.setCheckable(True)
      btn_bar.addWidget(btn)
    
    top_bar.addLayout(btn_bar)
    
    # 把 top_bar 放到主布局
    main_layout.addLayout(top_bar)
    
    # === 中间多页面区域 ===
    self.stack = QStackedWidget()
    main_layout.addWidget(self.stack, 1)
    
    # 只保留两个页面：硬件实时分析 + 推理可视化
    self.page_hw = self._create_original_page()  # index 0
    self.page_vis = self._create_drag_infer_page()  # index 1
    
    self.stack.addWidget(self.page_hw)
    self.stack.addWidget(self.page_vis)
    
    # 默认选中第一个按钮和页面
    self.btn_hw.setChecked(True)
    self.stack.setCurrentIndex(0)
    
    # 连接信号
    self.btn_hw.clicked.connect(lambda: self.switch_page(0))
    self.btn_vis.clicked.connect(lambda: self.switch_page(1))
  
  # 切换页面逻辑：保证只有一个按钮是 checked
  def switch_page(self, index: int):
    self.stack.setCurrentIndex(index)
    buttons = [self.btn_hw, self.btn_vis]
    for i, b in enumerate(buttons):
      b.setChecked(i == index)
  
  # ======== IMU 状态 / 数据回调 ========
  def on_status(self, msg: str):
    print("[IMU STATUS]", msg)
  
  def on_imu_data(self, data: dict):
    """
    收到 IMU JSON 数据，根据 device_id 更新对应设备的显示
    如果是新设备，动态添加一个 GroupBox
    """
    device_id = data.get("device_id", "unknown")
    ax = data.get("acceleration_x", 0.0)
    ay = data.get("acceleration_y", 0.0)
    az = data.get("acceleration_z", 0.0)
    gx = data.get("gyro_x", 0.0)
    gy = data.get("gyro_y", 0.0)
    gz = data.get("gyro_z", 0.0)
    temp = data.get("temperature", 0.0)
    wdt = data.get("watchdog", "unknown")
    
    if device_id not in self.device_displays:
      # 新设备：创建 GroupBox 和标签
      group_box = QGroupBox(f"Device: {device_id}")
      group_layout = QGridLayout(group_box)
      
      if device_id not in self.device_plots:
        self._create_device_plot(device_id)
      
      label_acc = QLabel(f"Accel: x={ax:.3f} y={ay:.3f} z={az:.3f}")
      label_gyro = QLabel(f"Gyro:  x={gx:.3f} y={gy:.3f} z={gz:.3f}")
      label_temp = QLabel(f"Temp: {temp:.1f} °C")
      label_wdt = QLabel(f"Watchdog: {wdt}")
      
      group_layout.addWidget(label_acc, 0, 0)
      group_layout.addWidget(label_gyro, 1, 0)
      group_layout.addWidget(label_temp, 2, 0)
      group_layout.addWidget(label_wdt, 3, 0)
      
      # 添加到页面布局（self.original_layout 是 _create_original_page 中定义的）
      self.original_layout.addWidget(group_box)
      
      # 存储标签以便后续更新
      self.device_displays[device_id] = {
        "group_box": group_box,
        "label_acc": label_acc,
        "label_gyro": label_gyro,
        "label_temp": label_temp,
        "label_wdt": label_wdt
      }
    else:
      # 更新现有标签
      displays = self.device_displays[device_id]
      displays["label_acc"].setText(f"Accel: x={ax:.3f} y={ay:.3f} z={az:.3f}")
      displays["label_gyro"].setText(f"Gyro:  x={gx:.3f} y={gy:.3f} z={gz:.3f}")
      displays["label_temp"].setText(f"Temp: {temp:.1f} °C")
      displays["label_wdt"].setText(f"Watchdog: {wdt}")
      # ======== 实时绘图 ========
      self._update_plot(device_id, ax, ay, az, gx, gy, gz)
  
  def _update_plot(self, device_id, ax, ay, az, gx, gy, gz):
    dp = self.device_plots[device_id]
    
    # 使用真实时间轴，并加 TIME_SCALE 做放大/缩小
    now = time.monotonic()
    if dp.get("t0") is None:
      dp["t0"] = now
    t_real = now - dp["t0"]  # 真实经过的秒数
    t = t_real * TIME_SCALE  # 显示用的时间
    
    # 追加数据点（加速度）
    dp["time"].append(t)
    dp["acc_x"].append(ax)
    dp["acc_y"].append(ay)
    dp["acc_z"].append(az)
    
    # 追加数据点（陀螺仪）
    dp["gyr_x"].append(gx)
    dp["gyr_y"].append(gy)
    dp["gyr_z"].append(gz)
    
    # 更新加速度曲线
    dp["acc_curves"]["x"].setData(dp["time"], dp["acc_x"])
    dp["acc_curves"]["y"].setData(dp["time"], dp["acc_y"])
    dp["acc_curves"]["z"].setData(dp["time"], dp["acc_z"])
    
    # 更新陀螺仪曲线
    dp["gyro_curves"]["x"].setData(dp["time"], dp["gyr_x"])
    dp["gyro_curves"]["y"].setData(dp["time"], dp["gyr_y"])
    dp["gyro_curves"]["z"].setData(dp["time"], dp["gyr_z"])
    
    # 视窗自动滚动最近 WINDOW_SECONDS 秒（只动 X 轴）
    left = max(t - WINDOW_SECONDS, 0)
    right = t
    dp["acc_plot"].setXRange(left, right)
    dp["gyro_plot"].setXRange(left, right)
  
  def _create_device_plot(self, device_id: str):
    """
    为某个 device 创建一块包含 Acc + Gyro 的大 GroupBox，
    并把它放到 plot_area 的网格里（一行两个）。
    """
    # 容器：一块显示 Acc + Gyro 的大框
    box = QGroupBox(f"Device {device_id} - Acc  Gyro (last {int(WINDOW_SECONDS)} s)")
    layout = QVBoxLayout(box)
    
    # ===== 加速度 Plot =====
    acc_plot = pg.PlotWidget(title="Acceleration (m/s²)")
    acc_plot.setDownsampling(mode=None)  # 不做 downsampling，保留所有点更丝滑
    acc_plot.setClipToView(True)
    
    # 让单个 plot 的纵向高度更高
    acc_plot.setMinimumHeight(250)
    
    # 只锁定 X 轴范围，用 WINDOW_SECONDS 控制时长
    acc_plot.setRange(xRange=[0, WINDOW_SECONDS])
    
    # Y 轴自动根据数据缩放，填满竖直空间
    acc_plot.enableAutoRange(axis='y', enable=True)
    
    acc_plot.setMouseEnabled(x=False, y=False)
    acc_plot.showGrid(x=True, y=True)
    acc_plot.addLegend()
    
    # 在布局中给它一个较大的 stretch，让图本身更“高”
    layout.addWidget(acc_plot, stretch=3)
    
    # 三条加速度曲线
    acc_curve_x = acc_plot.plot(pen='r', name="Ax", antialias=True)
    acc_curve_y = acc_plot.plot(pen='g', name="Ay", antialias=True)
    acc_curve_z = acc_plot.plot(pen='b', name="Az", antialias=True)
    
    # ===== 陀螺仪 Plot =====
    gyro_plot = pg.PlotWidget(title="Gyroscope (rad/s)")
    gyro_plot.setDownsampling(mode=None)
    gyro_plot.setClipToView(True)
    
    gyro_plot.setMinimumHeight(200)
    gyro_plot.setRange(xRange=[0, WINDOW_SECONDS])
    gyro_plot.enableAutoRange(axis='y', enable=True)
    
    gyro_plot.setMouseEnabled(x=False, y=False)
    gyro_plot.showGrid(x=True, y=True)
    gyro_plot.addLegend()
    layout.addWidget(gyro_plot, stretch=3)
    
    # 三条陀螺仪曲线
    gyro_curve_x = gyro_plot.plot(pen='r', name="Gx", antialias=True)
    gyro_curve_y = gyro_plot.plot(pen='g', name="Gy", antialias=True)
    gyro_curve_z = gyro_plot.plot(pen='b', name="Gz", antialias=True)
    
    # ===== 把这个 box 放到网格布局：一行两个 =====
    index = self.device_plot_count
    row = index // 2
    col = index % 2
    self.plot_area.addWidget(box, row, col)
    self.device_plot_count += 1
    
    # 保存对象（用于后面 _update_plot）
    self.device_plots[device_id] = {
      "time": deque(maxlen=2000),
      
      "acc_x": deque(maxlen=2000),
      "acc_y": deque(maxlen=2000),
      "acc_z": deque(maxlen=2000),
      
      "gyr_x": deque(maxlen=2000),
      "gyr_y": deque(maxlen=2000),
      "gyr_z": deque(maxlen=2000),
      
      "acc_plot": acc_plot,
      "gyro_plot": gyro_plot,
      
      "acc_curves": {
        "x": acc_curve_x,
        "y": acc_curve_y,
        "z": acc_curve_z,
      },
      "gyro_curves": {
        "x": gyro_curve_x,
        "y": gyro_curve_y,
        "z": gyro_curve_z,
      },
      
      "t0": None,  # 记录该设备的时间起点
    }
  
  def closeEvent(self, event):
    # 窗口关闭时，把 IMU 服务器也关掉
    try:
      if hasattr(self, "server") and self.server is not None:
        self.server.stop()
    except Exception as e:
      print("Error stopping IMU server:", e)
    super().closeEvent(event)
  
  # === 第一页：IMU 数据展示页（支持多个设备） ===
  def _create_original_page(self) -> QWidget:
    w = QWidget()
    self.original_layout = QVBoxLayout(w)
    self.original_layout.setContentsMargins(20, 20, 20, 20)
    self.original_layout.setSpacing(10)
    self.original_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
    
    title = QLabel("BMX 车把 / 车身姿态分析（实时 IMU 数据 + 可视化）")
    title.setStyleSheet("font-size: 16px; font-weight: bold;")
    self.original_layout.addWidget(title)
    
    # ====== 容纳多个设备 plot 的区域：改成网格布局，一行放两个 ======
    self.plot_area = QGridLayout()
    self.plot_area.setSpacing(20)
    self.plot_area.setAlignment(Qt.AlignmentFlag.AlignTop)
    
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll_content = QWidget()
    scroll_content.setLayout(self.plot_area)
    scroll.setWidget(scroll_content)
    
    self.original_layout.addWidget(scroll, 1)
    
    return w
  
  def _create_skeleton_page(self) -> QWidget:
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    
    label = QLabel("这里放骨架视频预览 / 实时骨架渲染")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(label)
    
    return w
  
  def _create_analysis_page(self) -> QWidget:
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    
    label = QLabel("这里放动作分析图表 / 参数设置面板")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(label)
    
    return w
  
  def _create_drag_infer_page(self) -> QWidget:
    """
    你原来的 Video Processing 页面，这里直接保留
    """
    w = QWidget()
    layout = QHBoxLayout(w)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(20)
    
    # 左侧拖拽区域
    self.video_drop = VideoDropWidget()
    layout.addWidget(self.video_drop, 2)
    
    # 右侧按钮和说明区域
    right_panel = QVBoxLayout()
    right_panel.setSpacing(12)
    
    info_label = QLabel(
      "步骤：\n"
      "1. 把本地视频文件拖到左侧框内\n"
      "2. 在下方选择要使用的模型\n"
      "3. 点击 Process 开始推理\n"
    )
    info_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
    info_label.setWordWrap(True)
    
    model_label = QLabel("选择模型：")
    self.model_combo = QComboBox()
    self.model_combo.addItem("Athlete Body", userData="Athlete Body")
    self.model_combo.addItem("BMX Handler & Body", userData="BMX Handler & Body")
    
    self.status_label = QLabel("Processing...")
    self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self.status_label.setStyleSheet("""
      QLabel {
        font-size: 14px;
        color: #0078d7;
      }
    """)
    self.status_label.setVisible(False)
    
    self.btn_process = QPushButton("Process")
    self.btn_process.setFixedHeight(40)
    self.btn_process.clicked.connect(self.on_process_clicked)
    
    right_panel.addWidget(info_label)
    right_panel.addWidget(model_label)
    right_panel.addWidget(self.model_combo)
    right_panel.addWidget(self.status_label)
    right_panel.addStretch(1)
    right_panel.addWidget(self.btn_process)
    
    layout.addLayout(right_panel, 1)
    return w
  
  # ======= 以下保留你原来的 Process 相关逻辑 =======
  def on_process_clicked(self):
    video_path = self.video_drop.video_path
    if not video_path:
      QMessageBox.warning(self, "提示", "请先拖拽一个本地视频文件到左侧框中。")
      return
    
    self.current_video_path = video_path
    model_key = self.model_combo.currentData()
    if model_key is None:
      QMessageBox.warning(self, "提示", "请选择一个模型。")
      return
    
    self.status_label.setText(f"Processing with model: {model_key} ...")
    self.status_label.setVisible(True)
    self.btn_process.setEnabled(False)
    
    self.worker = ProcessWorker(self.current_video_path, model_key, self)
    self.worker.finished.connect(self.on_process_finished)
    self.worker.error.connect(self.on_process_error)
    self.worker.start()
  
  def on_process_finished(self, result: dict):
    self.status_label.setVisible(False)
    self.btn_process.setEnabled(True)
    
    processed_path = result.get("processed_path")
    model_key = result.get("model_key", "unknown")
    
    QMessageBox.information(
      self,
      "推理完成",
      f"推理成功！\n\n"
      f"模型：{model_key}\n"
      f"上传副本：{result.get('uploaded_file', '')}\n"
      f"推理输出目录：\n{processed_path}\n\n"
      f"即将为你打开该目录。"
    )
    
    if processed_path:
      open_in_file_manager(processed_path)
  
  def on_process_error(self, message: str):
    self.status_label.setVisible(False)
    self.btn_process.setEnabled(True)
    
    QMessageBox.critical(
      self,
      "推理错误",
      f"推理过程中发生错误：\n{message}"
    )


import pyqtgraph as pg
from collections import deque
from typing import Dict


class IMUDisplayPage(QWidget):
  def __init__(self, parent=None):
    super().__init__(parent)
    
    # 存储历史数据用于绘图（滑动窗口）
    self.history_len = 200
    self.acc_x = deque(maxlen=self.history_len)
    self.acc_y = deque(maxlen=self.history_len)
    self.acc_z = deque(maxlen=self.history_len)
    self.gyr_x = deque(maxlen=self.history_len)
    self.gyr_y = deque(maxlen=self.history_len)
    self.gyr_z = deque(maxlen=self.history_len)
    
    self._init_ui()
  
  # ------------------------
  # UI
  # ------------------------
  def _init_ui(self):
    layout = QVBoxLayout(self)
    
    # --- 数值显示 ---
    self.label_acc = QLabel("Accel: x=0.000 y=0.000 z=0.000")
    self.label_gyro = QLabel("Gyro: x=0.000 y=0.000 z=0.000")
    self.label_temp = QLabel("Temperature: 0.0 °C")
    self.label_wdt = QLabel("Watchdog: unknown")
    
    for lab in (self.label_acc, self.label_gyro, self.label_temp, self.label_wdt):
      lab.setAlignment(Qt.AlignmentFlag.AlignLeft)
    
    layout.addWidget(self.label_acc)
    layout.addWidget(self.label_gyro)
    layout.addWidget(self.label_temp)
    layout.addWidget(self.label_wdt)
    
    # --- 加速度图 ---
    self.acc_plot = pg.PlotWidget(title="Acceleration")
    self.acc_plot.showGrid(x=True, y=True)
    layout.addWidget(self.acc_plot)
    
    self.acc_x_curve = self.acc_plot.plot(pen="r", name="ax")
    self.acc_y_curve = self.acc_plot.plot(pen="g", name="ay")
    self.acc_z_curve = self.acc_plot.plot(pen="b", name="az")
    
    # --- 角速度图 ---
    self.gyro_plot = pg.PlotWidget(title="Gyroscope")
    self.gyro_plot.showGrid(x=True, y=True)
    layout.addWidget(self.gyro_plot)
    
    self.gx_curve = self.gyro_plot.plot(pen="r", name="gx")
    self.gy_curve = self.gyro_plot.plot(pen="g", name="gy")
    self.gz_curve = self.gyro_plot.plot(pen="b", name="gz")
  
  # ------------------------
  # 更新数据与图
  # ------------------------
  def update_from_imu(self, data: Dict):
    # --- 读取 ---
    ax = data.get("acceleration_x", 0.0)
    ay = data.get("acceleration_y", 0.0)
    az = data.get("acceleration_z", 0.0)
    gx = data.get("gyro_x", 0.0)
    gy = data.get("gyro_y", 0.0)
    gz = data.get("gyro_z", 0.0)
    temp = data.get("temperature", 0.0)
    wdt = data.get("watchdog", "unknown")
    
    # --- 写文本 ---
    self.label_acc.setText(f"Accel: x={ax:.3f} y={ay:.3f} z={az:.3f}")
    self.label_gyro.setText(f"Gyro: x={gx:.3f} y={gy:.3f} z={gz:.3f}")
    self.label_temp.setText(f"Temperature: {temp:.1f} °C")
    self.label_wdt.setText(f"Watchdog: {wdt}")
    
    # --- 保存到历史数据 ---
    self.acc_x.append(ax)
    self.acc_y.append(ay)
    self.acc_z.append(az)
    self.gyr_x.append(gx)
    self.gyr_y.append(gy)
    self.gyr_z.append(gz)
    
    # --- 刷新加速度图 ---
    self.acc_x_curve.setData(self.acc_x)
    self.acc_y_curve.setData(self.acc_y)
    self.acc_z_curve.setData(self.acc_z)
    
    # --- 刷新角速度图 ---
    self.gx_curve.setData(self.gyr_x)
    self.gy_curve.setData(self.gyr_y)
    self.gz_curve.setData(self.gyr_z)


def main():
  app = QApplication(sys.argv)
  window = MainWindow()
  window.resize(1600, 1000)
  window.show()
  sys.exit(app.exec())


if __name__ == "__main__":
  main()
