from pathlib import Path
from ultralytics import YOLO

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def main():
  model = YOLO(str(PROJECT_ROOT / "yolo/pose-model/yolo11x-pose.pt"))

  model.train(
    data=str(PROJECT_ROOT / "yolo/data/MCBMX.v6i.yolov8/data.yaml"),  # 数据集配置文件路径（需先解压 zip）
    epochs=5,                     # 训练轮数
    imgsz=960,                      # 输入图像尺寸
    batch=4,                       # 每个batch的图像数量
    device='mps',                       # 使用哪个GPU，-1为CPU
    save=True,                      # 是否保存checkpoint
  )

if __name__ == '__main__':
  main()