import asyncio
import json
import platform
import queue
import threading
from datetime import datetime

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import websockets
from matplotlib.animation import FuncAnimation
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

FILTER_SHAKE = True
FILTER_ALPHA = 0.3


class MadgwickAHRS:
  """
  Implements the Madgwick AHRS algorithm.
  This filter fuses accelerometer and gyroscope data to produce a stable orientation estimate.
  """
  
  def __init__(self, sample_period=1 / 50, beta=0.1):
    """
    Initializes the Madgwick filter.
    Args:
        sample_period (float): The sample period, in seconds.
        beta (float): A parameter that controls the rate of convergence.
                      A smaller value relies more on the gyroscope, while a larger value
                      relies more on the accelerometer.
    """
    self.sample_period = sample_period
    self.beta = beta
    # Initialize the orientation quaternion to represent a level device
    self.q = np.array([1.0, 0.0, 0.0, 0.0])
  
  def update(self, gyro, acc):
    """
    Updates the orientation estimate with new sensor readings.
    Args:
        gyro (list or np.array): A 3-element array of gyroscope readings [gx, gy, gz] in rad/s.
        acc (list or np.array): A 3-element array of accelerometer readings [ax, ay, az] in m/s^2.
    """
    q = self.q
    
    # Convert sensor readings to numpy arrays
    gyro = np.array(gyro, dtype=float)
    acc = np.array(acc, dtype=float)
    
    # Normalize accelerometer measurement
    norm_acc = np.linalg.norm(acc)
    if norm_acc == 0.0:
      # Avoid division by zero if accelerometer reading is all zeros
      return
    acc /= norm_acc
    
    # Gradient descent algorithm corrective step
    # Reference quaternion of gravity vector
    f = np.array([
      2 * (q[1] * q[3] - q[0] * q[2]) - acc[0],
      2 * (q[0] * q[1] + q[2] * q[3]) - acc[1],
      2 * (0.5 - q[1] ** 2 - q[2] ** 2) - acc[2]
    ])
    # Jacobian matrix
    j = np.array([
      [-2 * q[2], 2 * q[3], -2 * q[0], 2 * q[1]],
      [2 * q[1], 2 * q[0], 2 * q[3], 2 * q[2]],
      [0, -4 * q[1], -4 * q[2], 0]
    ])
    
    step = j.T.dot(f)
    # --- FIX: Prevent division by zero ---
    # Normalize step only if the norm is not zero
    norm_step = np.linalg.norm(step)
    if norm_step > 1e-8:
      step /= norm_step
    
    # Compute rate of change of quaternion
    q_dot = 0.5 * self.quaternion_multiply(q, np.insert(gyro, 0, 0)) - self.beta * step
    
    # Integrate to yield new quaternion
    self.q += q_dot * self.sample_period
    self.q /= np.linalg.norm(self.q)  # Normalize quaternion
  
  @staticmethod
  def quaternion_to_rotation_matrix(q):
    """Converts a quaternion into a 3x3 rotation matrix."""
    q0, q1, q2, q3 = q
    return np.array([
      [1 - 2 * q2 ** 2 - 2 * q3 ** 2, 2 * q1 * q2 - 2 * q0 * q3, 2 * q1 * q3 + 2 * q0 * q2],
      [2 * q1 * q2 + 2 * q0 * q3, 1 - 2 * q1 ** 2 - 2 * q3 ** 2, 2 * q2 * q3 - 2 * q0 * q1],
      [2 * q1 * q3 - 2 * q0 * q2, 2 * q2 * q3 + 2 * q0 * q1, 1 - 2 * q1 ** 2 - 2 * q2 ** 2]
    ])
  
  @staticmethod
  def quaternion_to_euler(q):
    """Converts a quaternion into Euler angles (roll, pitch, yaw)."""
    q0, q1, q2, q3 = q
    # Roll (x-axis rotation)
    sinr_cosp = 2 * (q0 * q1 + q2 * q3)
    cosr_cosp = 1 - 2 * (q1 ** 2 + q2 ** 2)
    roll = np.arctan2(sinr_cosp, cosr_cosp)
    
    # Pitch (y-axis rotation)
    sinp = 2 * (q0 * q2 - q3 * q1)
    if abs(sinp) >= 1:
      pitch = np.copysign(np.pi / 2, sinp)  # use 90 degrees if out of range
    else:
      pitch = np.arcsin(sinp)
    
    # Yaw (z-axis rotation)
    siny_cosp = 2 * (q0 * q3 + q1 * q2)
    cosy_cosp = 1 - 2 * (q2 ** 2 + q3 ** 2)
    yaw = np.arctan2(siny_cosp, cosy_cosp)
    
    return roll, pitch, yaw
  
  @staticmethod
  def quaternion_multiply(q1, q2):
    """Multiplies two quaternions."""
    w1, x1, y1, z1 = q1
    w2, x2, y2, z2 = q2
    w = w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2
    x = w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2
    y = w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2
    z = w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2
    return np.array([w, x, y, z])


class CubeVisualizer:
  def __init__(self, filter_alpha=0.2):
    # 初始化开关
    self.filter_shake_enabled = True
    self.filter_alpha = 0.3
    self.prev_filtered = None
    
    # 初始化窗口数据
    # self.window_size = 5
    self.data_buffer = {
      'acceleration_x': [],
      'acceleration_y': [],
      'acceleration_z': [],
      'gyro_x': [],
      'gyro_y': [],
      'gyro_z': []
    }
    
    # 添加过滤开关变量
    self.filter_enabled = True  # 默认启用过滤
    
    # Set matplotlib style
    plt.style.use('dark_background')
    mpl.rcParams['toolbar'] = 'None'
    
    # Create figure and axes
    self.fig = plt.figure(figsize=(16, 10), facecolor='#2c2c2c')
    self.fig.canvas.manager.set_window_title('MPU6050 Sensor Data Visualization (Optimized)')
    
    # 使用GridSpec来创建更灵活的布局
    from matplotlib.gridspec import GridSpec
    gs = GridSpec(2, 2, figure=self.fig, hspace=0.2, wspace=0.2)
    
    # 3D plot for the cube
    self.ax1 = self.fig.add_subplot(gs[0, 0], projection='3d', facecolor='#1c1c1c')
    self.ax1.set_title('Orientation Visualization', color='white', fontsize=12, pad=5)
    
    # 2D plot for acceleration data
    self.ax2 = self.fig.add_subplot(gs[0, 1], facecolor='#1c1c1c')
    self.ax2.set_title('Acceleration Data', color='white', fontsize=12, pad=5)
    
    # 实时折线图显示加速度变化
    self.ax3 = self.fig.add_subplot(gs[1, 0], facecolor='#1c1c1c')
    self.ax3.set_title('Acceleration Over Time (Last 10s)', color='white', fontsize=12, pad=5)
    self.ax3.set_xlabel('Time (s)', color='white', fontsize=10)
    self.ax3.set_ylabel('Acceleration (m/s²)', color='white', fontsize=10)
    self.ax3.grid(True, color='gray', alpha=0.3)
    
    # 实时折线图显示陀螺仪变化
    self.ax4 = self.fig.add_subplot(gs[1, 1], facecolor='#1c1c1c')
    self.ax4.set_title('Gyroscope Over Time (Last 10s)', color='white', fontsize=12, pad=5)
    self.ax4.set_xlabel('Time (s)', color='white', fontsize=10)
    self.ax4.set_ylabel('Angular Velocity (rad/s)', color='white', fontsize=10)
    self.ax4.grid(True, color='gray', alpha=0.3)
    
    # Data queue for thread-safe data passing
    self.data_queue = queue.Queue(maxsize=1)
    
    # Default sensor data
    self.sensor_data = {
      'acceleration_x': 0, 'acceleration_y': 0, 'acceleration_z': 9.8,
      'gyro_x': 0, 'gyro_y': 0, 'gyro_z': 0,
      'temperature': 25
    }
    
    # 时间序列数据存储 (10秒数据)
    self.time_data = []
    self.acc_x_data = []
    self.acc_y_data = []
    self.acc_z_data = []
    self.gyro_x_data = []
    self.gyro_y_data = []
    self.gyro_z_data = []
    self.start_time = datetime.now()
    
    # --- OPTIMIZATION: Initialize Madgwick AHRS filter ---
    self.ahrs = MadgwickAHRS(sample_period=1 / 20.0, beta=0.1)  # 20Hz update rate
    self.last_update = datetime.now()
    
    # Define cube dimensions (10x10x2)
    self.width, self.height, self.depth = 10, 10, 2
    self.vertices = np.array([
      [-self.width / 2, -self.height / 2, -self.depth / 2], [self.width / 2, -self.height / 2, -self.depth / 2],
      [self.width / 2, self.height / 2, -self.depth / 2], [-self.width / 2, self.height / 2, -self.depth / 2],
      [-self.width / 2, -self.height / 2, self.depth / 2], [self.width / 2, -self.height / 2, self.depth / 2],
      [self.width / 2, self.height / 2, self.depth / 2], [-self.width / 2, self.height / 2, self.depth / 2]
    ])
    
    # Define cube faces
    self.faces = [
      [self.vertices[0], self.vertices[1], self.vertices[2], self.vertices[3]],  # Back
      [self.vertices[4], self.vertices[5], self.vertices[6], self.vertices[7]],  # Front
      [self.vertices[0], self.vertices[1], self.vertices[5], self.vertices[4]],  # Bottom
      [self.vertices[3], self.vertices[2], self.vertices[6], self.vertices[7]],  # Top
      [self.vertices[0], self.vertices[3], self.vertices[7], self.vertices[4]],  # Left
      [self.vertices[1], self.vertices[2], self.vertices[6], self.vertices[5]]  # Right
    ]
    
    # Define face colors
    self.face_colors = ['#1f77b4', '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
    
    # Create the initial cube
    self.cube = Poly3DCollection(self.faces, alpha=1, facecolors=self.face_colors, edgecolors='w', linewidths=1)
    self.ax1.add_collection3d(self.cube)
    
    # Setup 3D plot axes
    self.ax1.set_xlim(-15, 15)
    self.ax1.set_ylim(-15, 15)
    self.ax1.set_zlim(-15, 15)
    self.ax1.set_xlabel('X', fontsize=10)
    self.ax1.set_ylabel('Y', fontsize=10)
    self.ax1.set_zlabel('Z', fontsize=10)
    self.ax1.quiver(0, 0, 0, 10, 0, 0, color='r', linewidth=2, arrow_length_ratio=0.1, label='X')
    self.ax1.quiver(0, 0, 0, 0, 10, 0, color='g', linewidth=2, arrow_length_ratio=0.1, label='Y')
    self.ax1.quiver(0, 0, 0, 0, 0, 10, color='b', linewidth=2, arrow_length_ratio=0.1, label='Z')
    self.ax1.legend(loc='upper right', fontsize=8)
    self.ax1.view_init(elev=25, azim=-45)
    
    # Setup 2D acceleration plot
    self.ax2.set_xlim(-20, 20)
    self.ax2.set_ylim(-20, 20)
    self.ax2.grid(True, color='gray', alpha=0.3)
    self.ax2.set_aspect('equal', 'box')
    self.ax2.axhline(0, color='white', linestyle='--', linewidth=0.5)
    self.ax2.axvline(0, color='white', linestyle='--', linewidth=0.5)
    self.acc_vector = self.ax2.quiver(0, 0, 0, 0, angles='xy', scale_units='xy', scale=1, color='cyan', width=0.015)
    self.acc_text = self.ax2.text(0.05, 0.95, '', transform=self.ax2.transAxes, fontsize=12, color='white',
                                  va='top', bbox=dict(facecolor='#1c1c1c', alpha=0.8))
    
    # Setup text displays
    self.sensor_text = self.ax1.text2D(0.05, 0.8, '', transform=self.ax1.transAxes, fontsize=12, color='white',
                                       va='top', bbox=dict(facecolor='#1c1c1c', alpha=0.8))
    self.time_text = self.ax1.text2D(0.05, 0.1, '', transform=self.ax1.transAxes, fontsize=10, color='yellow')
    self.connection_text = self.ax1.text2D(0.05, 0.05, 'Waiting for connection...', transform=self.ax1.transAxes,
                                           fontsize=12, color='orange', bbox=dict(facecolor='#1c1c1c', alpha=0.8))
    
    # 添加过滤状态显示
    self.filter_text = self.ax1.text2D(0.05, 0.9, f'Filter: {"ON" if self.filter_enabled else "OFF"}',
                                       transform=self.ax1.transAxes, fontsize=12,
                                       color='lightgreen' if self.filter_enabled else 'red',
                                       bbox=dict(facecolor='#1c1c1c', alpha=0.8))
    
    # 初始化折线图
    self.acc_line_x, = self.ax3.plot([], [], 'r-', label='X', linewidth=1.5)
    self.acc_line_y, = self.ax3.plot([], [], 'g-', label='Y', linewidth=1.5)
    self.acc_line_z, = self.ax3.plot([], [], 'b-', label='Z', linewidth=1.5)
    self.ax3.legend(fontsize=8)
    
    self.gyro_line_x, = self.ax4.plot([], [], 'r-', label='X', linewidth=1.5)
    self.gyro_line_y, = self.ax4.plot([], [], 'g-', label='Y', linewidth=1.5)
    self.gyro_line_z, = self.ax4.plot([], [], 'b-', label='Z', linewidth=1.5)
    self.ax4.legend(fontsize=8)
  
  def on_key_press(self, event):
    if event.key == ' ':
      self.filter_enabled = not self.filter_enabled
      print(f"Filter set to {'ON' if self.filter_enabled else 'OFF'}")
      # 更新显示文本
      self.filter_text.set_text(f'Filter: {"ON" if self.filter_enabled else "OFF"}')
      self.filter_text.set_color('lightgreen' if self.filter_enabled else 'red')
  
  def filter_shake(self, data, alpha=None):
    if alpha is None:
      alpha = self.filter_alpha
    if self.prev_filtered is None:
      self.prev_filtered = data.copy()
    filtered = {}
    for key in data:
      filtered[key] = alpha * data[key] + (1 - alpha) * self.prev_filtered[key]
    self.prev_filtered = filtered
    return filtered
  
  def update_cube(self, frame):
    """Animation update function."""
    try:
      # Get the latest data from the queue
      self.sensor_data = self.data_queue.get_nowait()
      self.connection_text.set_text('Connected to device')
      self.connection_text.set_color('lightgreen')
    except queue.Empty:
      # If no new data, keep using the old data
      self.connection_text.set_text('Waiting for data...')
      self.connection_text.set_color('orange')
    
    # Extract raw sensor data
    acc = [self.sensor_data['acceleration_x'], self.sensor_data['acceleration_y'],
           self.sensor_data['acceleration_z']]
    gyro = [self.sensor_data['gyro_x'], self.sensor_data['gyro_y'], self.sensor_data['gyro_z']]
    temp = self.sensor_data['temperature']
    
    # 更新时间序列数据
    current_time = (datetime.now() - self.start_time).total_seconds()
    
    # 添加新数据点
    self.time_data.append(current_time)
    self.acc_x_data.append(acc[0])
    self.acc_y_data.append(acc[1])
    self.acc_z_data.append(acc[2])
    self.gyro_x_data.append(gyro[0])
    self.gyro_y_data.append(gyro[1])
    self.gyro_z_data.append(gyro[2])
    
    # 保持最近10秒的数据
    cutoff_time = current_time - 10.0
    while self.time_data and self.time_data[0] < cutoff_time:
      self.time_data.pop(0)
      self.acc_x_data.pop(0)
      self.acc_y_data.pop(0)
      self.acc_z_data.pop(0)
      self.gyro_x_data.pop(0)
      self.gyro_y_data.pop(0)
      self.gyro_z_data.pop(0)
    
    # 根据过滤开关决定是否使用AHRS滤波器
    if self.filter_enabled:
      # --- OPTIMIZATION: Update the AHRS filter ---
      now = datetime.now()
      dt = (now - self.last_update).total_seconds()
      # Ensure dt is not zero to avoid division errors in the filter
      if dt > 0:
        self.ahrs.sample_period = dt
        self.ahrs.update(gyro, acc)
      self.last_update = now
      
      # --- OPTIMIZATION: Get rotation matrix from the AHRS quaternion ---
      R = self.ahrs.quaternion_to_rotation_matrix(self.ahrs.q)
      # --- FIX: Use the transpose of the rotation matrix ---
      # The rotation matrix R transforms from world to body frame. To rotate the
      # vertices (defined in body frame) to the world frame for visualization,
      # we need the inverse rotation, which is the transpose of R.
      rotated_vertices = np.dot(self.vertices, R.T)
      
      # Get orientation angles from AHRS
      roll, pitch, yaw = self.ahrs.quaternion_to_euler(self.ahrs.q)
    else:
      # 不使用滤波器，直接使用原始传感器数据计算姿态
      now = datetime.now()
      
      # 简单计算俯仰角和滚转角（不考虑偏航）
      ax, ay, az = acc
      pitch = np.arctan2(-ax, np.sqrt(ay ** 2 + az ** 2))
      roll = np.arctan2(ay, az)
      yaw = 0  # 不使用偏航
      
      # 创建旋转矩阵
      R_x = np.array([[1, 0, 0],
                      [0, np.cos(roll), -np.sin(roll)],
                      [0, np.sin(roll), np.cos(roll)]])
      
      R_y = np.array([[np.cos(pitch), 0, np.sin(pitch)],
                      [0, 1, 0],
                      [-np.sin(pitch), 0, np.cos(pitch)]])
      
      R = np.dot(R_y, R_x)
      rotated_vertices = np.dot(self.vertices, R)
    
    # Update cube vertices
    new_faces = [
      [rotated_vertices[0], rotated_vertices[1], rotated_vertices[2], rotated_vertices[3]],
      [rotated_vertices[4], rotated_vertices[5], rotated_vertices[6], rotated_vertices[7]],
      [rotated_vertices[0], rotated_vertices[1], rotated_vertices[5], rotated_vertices[4]],
      [rotated_vertices[3], rotated_vertices[2], rotated_vertices[6], rotated_vertices[7]],
      [rotated_vertices[0], rotated_vertices[3], rotated_vertices[7], rotated_vertices[4]],
      [rotated_vertices[1], rotated_vertices[2], rotated_vertices[6], rotated_vertices[5]]
    ]
    self.cube.set_verts(new_faces)
    
    # Update acceleration vector visualization
    ax, ay, az = acc
    acc_scale = 1.5  # Scale factor for better visibility
    self.acc_vector.set_UVC(ax * acc_scale, ay * acc_scale)
    
    # Update text information
    acc_mag = np.sqrt(ax ** 2 + ay ** 2 + az ** 2)
    acc_text_str = f'Acceleration:\n  X: {ax:.2f} m/s²\n  Y: {ay:.2f} m/s²\n  Z: {az:.2f} m/s²\n  Mag: {acc_mag:.2f} m/s²'
    self.acc_text.set_text(acc_text_str)
    
    gx, gy, gz = gyro
    
    gyro_text = f'Gyroscope:\n  X: {gx:.2f} rad/s\n  Y: {gy:.2f} rad/s\n  Z: {gz:.2f} rad/s'
    orientation_text = f'Orientation (Euler):\n  Pitch: {np.degrees(pitch):.2f}°\n  Roll: {np.degrees(roll):.2f}°\n  Yaw: {np.degrees(yaw):.2f}°'
    sensor_info = f'{gyro_text}\n\n{orientation_text}\n\nTemperature: {temp:.2f}°C'
    self.sensor_text.set_text(sensor_info)
    
    current_time = now.strftime("%Y-%m-%d %H:%M:%S")
    self.time_text.set_text(f"Last Update: {current_time}")
    
    # 更新折线图
    if self.time_data:
      # 更新加速度折线图
      self.acc_line_x.set_data(self.time_data, self.acc_x_data)
      self.acc_line_y.set_data(self.time_data, self.acc_y_data)
      self.acc_line_z.set_data(self.time_data, self.acc_z_data)
      
      # 更新陀螺仪折线图
      self.gyro_line_x.set_data(self.time_data, self.gyro_x_data)
      self.gyro_line_y.set_data(self.time_data, self.gyro_y_data)
      self.gyro_line_z.set_data(self.time_data, self.gyro_z_data)
      
      # 动态调整Y轴范围
      if self.acc_x_data or self.acc_y_data or self.acc_z_data:
        acc_min = min(min(self.acc_x_data), min(self.acc_y_data), min(self.acc_z_data))
        acc_max = max(max(self.acc_x_data), max(self.acc_y_data), max(self.acc_z_data))
        acc_range = acc_max - acc_min
        if acc_range > 0:
          self.ax3.set_ylim(acc_min - acc_range * 0.1, acc_max + acc_range * 0.1)
      
      if self.gyro_x_data or self.gyro_y_data or self.gyro_z_data:
        gyro_min = min(min(self.gyro_x_data), min(self.gyro_y_data), min(self.gyro_z_data))
        gyro_max = max(max(self.gyro_x_data), max(self.gyro_y_data), max(self.gyro_z_data))
        gyro_range = gyro_max - gyro_min
        if gyro_range > 0:
          self.ax4.set_ylim(gyro_min - gyro_range * 0.1, gyro_max + gyro_range * 0.1)
      
      # 设置X轴范围为最近10秒
      if self.time_data:
        self.ax3.set_xlim(max(0, self.time_data[-1] - 10), self.time_data[-1])
        self.ax4.set_xlim(max(0, self.time_data[-1] - 10), self.time_data[-1])
    
    return self.cube, self.acc_vector, self.acc_text, self.sensor_text, self.time_text, self.connection_text, self.filter_text, self.acc_line_x, self.acc_line_y, self.acc_line_z, self.gyro_line_x, self.gyro_line_y, self.gyro_line_z
  
  def start_animation(self):
    """Starts the matplotlib animation."""
    # 确保键盘事件绑定在动画开始前
    self.fig.canvas.mpl_connect('key_press_event', self.on_key_press)
    self.ani = FuncAnimation(self.fig, self.update_cube, interval=50, blit=False)
    plt.show()
  
  async def websocket_handler(self, websocket):
    """Handles WebSocket connections and receives data."""
    client_ip = websocket.remote_address[0]
    print(f"Device connected from: {client_ip}")
    try:
      async for message in websocket:
        try:
          data = json.loads(message)
          if FILTER_SHAKE:
            data = self.filter_shake(data)
          keys = ['acceleration_x', 'acceleration_y', 'acceleration_z',
                  'gyro_x', 'gyro_y', 'gyro_z', 'temperature']
          if all(key in data for key in keys):
            if self.data_queue.full():
              self.data_queue.get_nowait()  # Discard old data if queue is full
            self.data_queue.put_nowait(data)
        except json.JSONDecodeError:
          print(f"Invalid JSON data received: {message}")
    except websockets.exceptions.ConnectionClosed:
      print(f"Device disconnected: {client_ip}")
  
  async def start_server(self):
    """Starts the WebSocket server."""
    server_ip = "0.0.0.0"
    port = 5123
    print(f"WebSocket server started on ws://{server_ip}:{port}")
    async with websockets.serve(self.websocket_handler, server_ip, port):
      await asyncio.Future()  # Run forever
  
  def start_async_server(self):
    """Runs the async server in a separate thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(self.start_server())


def main():
  print("MPU6050 Sensor Data Visualization - Optimized with Madgwick Filter")
  print(f"Running on: {platform.system()} {platform.release()}")
  print("Press SPACE to toggle filter on/off")
  
  # Create the visualizer instance
  visualizer = CubeVisualizer()
  
  # Start the WebSocket server in a daemon thread
  server_thread = threading.Thread(target=visualizer.start_async_server, daemon=True)
  server_thread.start()
  
  print("Starting visualization system...")
  print("Ensure the ESP32 device is connected and sending data.")
  print("Press Ctrl+C in the console to exit.")
  try:
    visualizer.start_animation()
  except KeyboardInterrupt:
    print("\nApplication terminated.")


if __name__ == "__main__":
  main()
