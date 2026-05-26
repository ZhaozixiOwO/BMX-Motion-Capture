from flask import Flask, request, jsonify
from ultralytics import YOLO
import os, time, shutil

app = Flask(__name__)

# ===== 路径配置 =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
YOLO_DIR = os.path.join(BASE_DIR, "yolo-files")
MODEL_PATH = os.path.join(YOLO_DIR, "pose-model", "bmx03-100.pt")
UPLOAD_DIR = os.path.join(YOLO_DIR, "uploaded-file")
PROCESSED_DIR = os.path.join(YOLO_DIR, "processed-file")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

# ===== 一行加载模型 =====
model = YOLO(MODEL_PATH)

@app.route("/process", methods=["POST"])
def process_file():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "没有检测到文件"}), 400

    # 验证文件类型
    ext = os.path.splitext(file.filename)[1].lower()
    allowed_ext = [".mp4", ".mov", ".avi", ".mkv", ".webm"]
    if ext not in allowed_ext:
        return jsonify({"error": f"不支持的文件格式: {ext}"}), 400

    # 生成时间戳命名
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    new_filename = f"{timestamp}{ext}"
    upload_path = os.path.join(UPLOAD_DIR, new_filename)

    # 保存文件副本到 uploaded-file
    temp_path = os.path.join(BASE_DIR, new_filename)
    file.save(temp_path)
    shutil.copy(temp_path, upload_path)
    os.remove(temp_path)  # 删除临时文件

    # 执行推理
    model(
        upload_path,
        save=True,
        imgsz=960,
        conf=0.5,
        project=PROCESSED_DIR,
        name=timestamp
    )

    # 输出路径
    processed_path = os.path.join(PROCESSED_DIR, timestamp)

    return jsonify({
        "status": "success",
        "uploaded_file": new_filename,
        "processed_path": processed_path
    })

if __name__ == "__main__":
    # 注意：生产部署时建议用 run.py 启动
    app.run(host="0.0.0.0", port=5000, debug=True)