import numpy as np
import cv2
import os
from pathlib import Path
from ultralytics import YOLO
import torch

# --- 1. 定义骨架连接规则 (0-based 索引) ---
# 关键点顺序: fw(0), b1(1), b2(2), bw(3), b3(4), b4(5)
BMX_BODY_SKELETON = [
  (4, 2),  # b3(4) -> b2(2)
  (1, 2),  # b1(1) -> b2(2)
  (2, 3),  # b2(2) -> bw(3)
  (3, 4),  # bw(3) -> b3(4)
  (4, 5),  # b3(4) -> b4(5)
  (5, 0),  # b4(5) -> fw(0)
  (1, 5)  # b1(1) -> b4(5)
]

# --- 2. 设置 GPU 设备 ---
# 检查是否支持 MPS (Apple Silicon GPU)
if torch.backends.mps.is_available():
  DEVICE = torch.device("mps")
  print("✅ 检测到 Apple Silicon GPU (MPS)，将使用 MPS 进行加速。")
else:
  DEVICE = torch.device("cpu")
  print("⚠️ MPS 不可用，将使用 CPU 进行推理。")
# --- GPU 设备设置结束 ---


# --- 3. 初始化模型和视频读写器 ---

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 加载模型
model = YOLO(str(PROJECT_ROOT / "yolo/pose-model/ours/bmx05-x-100.pt"))

# 关键步骤：将模型移动到 MPS 设备上
model.to(DEVICE)

# 视频路径和输出路径配置（替换为你的测试视频路径）
video_path = str(PROJECT_ROOT / "yolo/data/your-test-video.MOV")

# 定义输出文件夹
OUTPUT_DIR = str(PROJECT_ROOT / "yolo/runs/output_video")
input_file_name = Path(video_path).stem
base_output_file = Path(OUTPUT_DIR) / f"{input_file_name}_manual_skeleton.mp4"

# 确保输出目录存在
os.makedirs(OUTPUT_DIR, exist_ok=True)
print(f"✅ 输出目录已确认/创建: {OUTPUT_DIR}")

# 处理文件名重复
output_path = base_output_file
counter = 1
while output_path.exists():
  counter += 1
  output_path = Path(OUTPUT_DIR) / f"{input_file_name}_manual_skeleton_{counter}.mp4"

if counter > 1:
  print(f"⚠️ 文件名重复，已自动添加序号。新文件名: {output_path.name}")

# 使用 cv2 获取原始视频属性
cap = cv2.VideoCapture(video_path)
if not cap.isOpened():
  raise IOError(f"无法打开视频文件: {video_path}")

width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = cap.get(cv2.CAP_PROP_FPS)

# 初始化视频写入器
video_writer = cv2.VideoWriter(
  str(output_path),
  cv2.VideoWriter_fourcc(*'mp4v'),
  fps,
  (width, height)
)

# --- 4. 运行推理和手动绘图循环 ---

# 运行预测，并通过 'device=DEVICE' 参数明确指定使用 MPS 或 CPU
# 注意：使用 device 参数后，YOLOv8 会自动处理输入图像到设备的移动。
results = model(video_path,
                imgsz=800,
                stream=True,
                conf=0.35,
                device=DEVICE)  # ❗ 明确指定设备 ❗

print("🚀 开始使用 MPS/CPU 进行推理和绘制骨架连线...")

for result in results:
  # result.orig_img 已经在 CPU 上
  frame = result.orig_img.copy()
  
  # 关键点数据通常仍在 MPS 设备上，需要移动到 CPU 才能转换为 NumPy
  if result.keypoints.data is not None and result.keypoints.data.numel() > 0:
    
    for kpts_instance in result.keypoints.data:
      # ❗ 关键步骤：将关键点数据移动到 CPU 才能转换为 NumPy ❗
      keypoints_xyv = kpts_instance.cpu().numpy()
      
      # --- 绘制连线和关键点（保持不变） ---
      CONF_THRESHOLD = 0.1
      
      # 绘制连线
      for start_idx, end_idx in BMX_BODY_SKELETON:
        if keypoints_xyv.shape[0] > max(start_idx, end_idx):
          pt1_x, pt1_y, pt1_v = keypoints_xyv[start_idx]
          pt2_x, pt2_y, pt2_v = keypoints_xyv[end_idx]
          
          if pt1_v > CONF_THRESHOLD and pt2_v > CONF_THRESHOLD:
            pt1 = (int(pt1_x), int(pt1_y))
            pt2 = (int(pt2_x), int(pt2_y))
            cv2.line(frame, pt1, pt2, (0, 255, 0), 3)
            
            # 绘制关键点
      for x, y, v in keypoints_xyv:
        if v > CONF_THRESHOLD:
          center = (int(x), int(y))
          cv2.circle(frame, center, 5, (255, 0, 0), -1)
  
  video_writer.write(frame)

# --- 5. 释放资源 ---
video_writer.release()
cap.release()
print(f"✅ 视频处理完成，已保存至: {output_path.resolve()}")