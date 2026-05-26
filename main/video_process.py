import os
import time
import shutil
import torch
import cv2
import numpy as np
from pathlib import Path
from ultralytics import YOLO

# ================== 路径配置 ==================
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 1. 定义可选模型列表：key -> 模型路径
MODEL_PATHS = {
  "Athlete Body": str(PROJECT_ROOT / "yolo/pose-model/yolo11x-pose.pt"),
  "BMX Handler & Body": str(PROJECT_ROOT / "yolo/pose-model/ours/bmx05-x-100.pt"),
}

# 默认模型 key（前端如果没传，就用这个）
DEFAULT_MODEL_KEY = "BMX Handler & Body"

# 上传文件保存目录
UPLOAD_DIR = str(PROJECT_ROOT / "yolo/data/uploaded-file")

# 推理输出目录
PROCESSED_DIR = str(PROJECT_ROOT / "yolo/data/processed-file")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)


# ================== 自动选择设备 ==================
def select_device() -> str:
  if torch.cuda.is_available():
    print("[INFO] 使用 CUDA GPU: 0")
    return "0"
  if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
    print("[INFO] 使用 Apple MPS GPU")
    # 返回 'mps' 字符串，用于 YOLO 的 device 参数
    return "mps"
  print("[INFO] 使用 CPU")
  return "cpu"


DEVICE = select_device()

# ================== 模型缓存，避免重复加载 ==================
_model_cache: dict[str, YOLO] = {}


def get_model(model_key: str) -> YOLO:
  """
  根据 model_key 返回对应的 YOLO 模型实例，带缓存。
  同时将模型移动到相应的设备上。
  """
  if model_key not in MODEL_PATHS:
    raise ValueError(f"未知模型: {model_key}，可选: {list(MODEL_PATHS.keys())}")
  
  if model_key in _model_cache:
    return _model_cache[model_key]
  
  model_path = MODEL_PATHS[model_key]
  print(f"[INFO] 正在加载模型: {model_key} -> {model_path}")
  model = YOLO(model_path)
  
  # 将模型移动到选定的设备上
  model.to(DEVICE)
  
  _model_cache[model_key] = model
  return model


# ================== 骨架定义（新增）==================
# 关键点顺序: fw(0), b1(1), b2(2), bw(3), b3(4), b4(5)
BMX_BODY_SKELETON = [
  (4, 2), (1, 2), (2, 3), (3, 4), (4, 5), (5, 0), (1, 5)
]
CONF_THRESHOLD = 0.4  # 绘制连线的最小关键点置信度


def get_output_path(base_name: str, output_dir: str) -> Path:
  """
  检查文件名重复，并返回唯一的输出路径 Path 对象。
  """
  output_base_name = f"{base_name}_with_skeleton.mp4"
  output_path = Path(output_dir) / output_base_name
  counter = 1
  
  # 检查文件是否已存在
  while output_path.exists():
    counter += 1
    # 构造新的文件名: base_name_with_skeleton_2.mp4
    output_path = Path(output_dir) / f"{base_name}_with_skeleton_{counter}.mp4"
  
  if counter > 1:
    print(f"⚠️ 文件名重复，已自动添加序号。新文件名: {output_path.name}")
  
  return output_path


# ================== 核心处理函数（修改）==================

def process_video(input_video_path: str, model_key: str | None = None) -> dict:
  """
  视频推理函数，自定义绘制骨架连线并保存视频。
  """
  if not os.path.isfile(input_video_path):
    raise FileNotFoundError(f"找不到视频文件：{input_video_path}")
  
  if model_key is None:
    model_key = DEFAULT_MODEL_KEY
  
  # 拿到对应的模型实例
  model = get_model(model_key)
  
  # 验证文件类型
  ext = os.path.splitext(input_video_path)[1].lower()
  allowed_ext = [".mp4", ".mov", ".avi", ".mkv", ".webm"]
  if ext not in allowed_ext:
    raise ValueError(f"不支持的文件格式: {ext}")
  
  # 1. 文件拷贝和路径准备
  timestamp = time.strftime("%Y%m%d-%H%M%S")
  new_filename = f"{timestamp}{ext}"
  upload_path = os.path.join(UPLOAD_DIR, new_filename)
  shutil.copy(input_video_path, upload_path)
  
  # 2. 输出文件路径
  base_output_name = f"{Path(input_video_path).stem}_{model_key}"
  output_file_path = get_output_path(base_output_name, PROCESSED_DIR)
  
  # 3. 初始化视频读写器
  cap = cv2.VideoCapture(upload_path)
  if not cap.isOpened():
    raise IOError(f"无法读取视频文件：{upload_path}")
  
  width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
  height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
  fps = cap.get(cv2.CAP_PROP_FPS)
  
  video_writer = cv2.VideoWriter(
    str(output_file_path),
    cv2.VideoWriter_fourcc(*'mp4v'),
    fps,
    (width, height)
  )
  
  print(f"[INFO] 开始推理和绘制骨架，设备：{DEVICE}，模型：{model_key}，输入文件：{upload_path}")
  
  # ========= 根据 model_key 配置预测参数 =========
  predict_kwargs = dict(
    save=False,  # 关闭 YOLO 自动保存
    imgsz=640,
    conf=0.5,
    stream=True,
    device=DEVICE,
  )
  # Athlete Body：只检测 class 0（人类）
  if model_key == "Athlete Body":
    predict_kwargs["classes"] = [0]
  
  results = model(upload_path, **predict_kwargs)
  
  for result in results:
    # ------------- 分支一：Athlete Body，用 YOLO 默认可视化 -------------
    if model_key == "Athlete Body":
      # 使用 YOLO 自带的 plot()，包含框 + 关键点
      frame = result.plot()  # 返回的是已经画好 BGR 图像
      video_writer.write(frame)
      continue  # 不执行后面的 BMX 自定义划线逻辑
    
    # ------------- 分支二：BMX Handler & Body，执行自定义划线 -------------
    frame = result.orig_img.copy()
    
    if result.keypoints.data is not None and result.keypoints.data.numel() > 0:
      for kpts_instance in result.keypoints.data:
        keypoints_xyv = kpts_instance.cpu().numpy()
        
        # --- 绘制连线 ---
        for start_idx, end_idx in BMX_BODY_SKELETON:
          if keypoints_xyv.shape[0] > max(start_idx, end_idx):
            pt1_x, pt1_y, pt1_v = keypoints_xyv[start_idx]
            pt2_x, pt2_y, pt2_v = keypoints_xyv[end_idx]
            
            if pt1_v > CONF_THRESHOLD and pt2_v > CONF_THRESHOLD:
              pt1 = (int(pt1_x), int(pt1_y))
              pt2 = (int(pt2_x), int(pt2_y))
              cv2.line(frame, pt1, pt2, (0, 255, 0), 3)
        
        # --- 绘制关键点（点）---
        for x, y, v in keypoints_xyv:
          if v > CONF_THRESHOLD:
            center = (int(x), int(y))
            cv2.circle(frame, center, 5, (255, 0, 0), -1)
    
    video_writer.write(frame)
  
  video_writer.release()
  cap.release()
  print(f"✅ 视频处理完成，已保存至: {output_file_path.resolve()}")
  
  return {
    "status": "success",
    "uploaded_file": new_filename,
    "processed_path": str(output_file_path),
    "upload_path": upload_path,
    "device": DEVICE,
    "model_key": model_key,
  }
