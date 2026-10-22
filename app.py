"""
Flask web app for NBS visualizer.
- POST /upload  : upload .nbs file, queue video generation
- GET  /status/<task_id> : check generation progress
- GET  /download/<task_id> : download generated video
- GET  /        : web UI
"""

import os
import sys
import uuid
import threading
import time
from datetime import datetime
from typing import Dict, Optional

from flask import (
    Flask, request, jsonify, send_from_directory,
    render_template, abort,
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nbs_visualizer import render_video
from nbs_visualizer.logger import get_logger

logger = get_logger(__name__)

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(APP_ROOT, "uploads")
OUTPUT_DIR = os.path.join(APP_ROOT, "outputs")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


class TaskManager:
    """渲染任务管理：任务存储、后台执行、文件清理。"""

    FILE_TTL = 86400  # 24 hours

    def __init__(self, upload_dir: str, output_dir: str):
        self._upload_dir = upload_dir
        self._output_dir = output_dir
        self._tasks: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def create(self, task_id: str, filename: str, audio_name: Optional[str],
               use_kimi: bool) -> None:
        with self._lock:
            self._tasks[task_id] = {
                "id": task_id,
                "status": "pending",
                "progress": 0,
                "filename": filename,
                "audio": audio_name,
                "use_kimi": use_kimi,
                "created_at": datetime.now().isoformat(),
            }

    def get(self, task_id: str) -> Optional[dict]:
        with self._lock:
            return self._tasks.get(task_id)

    def count(self) -> int:
        with self._lock:
            return len(self._tasks)

    def start_render(self, task_id: str, nbs_path: str, output_path: str,
                     audio_path: Optional[str] = None,
                     use_kimi: bool = False) -> None:
        def progress(pct, msg=""):
            pct = int(pct * 100) if pct <= 1.0 else int(pct)
            with self._lock:
                if task_id in self._tasks:
                    self._tasks[task_id]["progress"] = pct
                    self._tasks[task_id]["status"] = "rendering"
                    if msg:
                        self._tasks[task_id]["message"] = msg

        def run():
            try:
                with self._lock:
                    self._tasks[task_id]["status"] = "rendering"
                    self._tasks[task_id]["progress"] = 0
                    self._tasks[task_id]["started_at"] = datetime.now().isoformat()

                final_path = render_video(nbs_path, output_path,
                                          audio_file=audio_path,
                                          use_kimi=use_kimi,
                                          progress_callback=progress)

                with self._lock:
                    self._tasks[task_id]["status"] = "done"
                    self._tasks[task_id]["progress"] = 100
                    self._tasks[task_id]["finished_at"] = datetime.now().isoformat()
                    self._tasks[task_id]["output_file"] = os.path.basename(final_path)
                    self._tasks[task_id]["file_size"] = os.path.getsize(final_path)
            except Exception as e:
                import traceback
                err_trace = traceback.format_exc()
                logger.error("Task %s failed:\n%s", task_id, err_trace)
                with self._lock:
                    self._tasks[task_id]["status"] = "error"
                    self._tasks[task_id]["error"] = str(e)
                    self._tasks[task_id]["error_trace"] = err_trace
                    self._tasks[task_id]["finished_at"] = datetime.now().isoformat()
            finally:
                for p in [nbs_path, audio_path]:
                    if p:
                        try:
                            os.remove(p)
                        except OSError as e:
                            logger.warning("Failed to remove temp file %s: %s", p, e)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    def cleanup_old_files(self) -> None:
        now = time.time()
        for d in [self._upload_dir, self._output_dir]:
            for f in os.listdir(d):
                path = os.path.join(d, f)
                if os.path.isfile(path):
                    age = now - os.path.getmtime(path)
                    if age > self.FILE_TTL:
                        try:
                            os.remove(path)
                        except OSError as e:
                            logger.warning("Failed to remove old file %s: %s", path, e)


task_manager = TaskManager(UPLOAD_DIR, OUTPUT_DIR)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400

    if not f.filename.lower().endswith(".nbs"):
        return jsonify({"error": "Only .nbs files are accepted"}), 400

    audio_path = None
    audio_file = request.files.get("audio")
    if audio_file and audio_file.filename:
        audio_ext = os.path.splitext(audio_file.filename)[1].lower()
        if audio_ext not in (".mp3", ".wav", ".ogg", ".m4a"):
            return jsonify({"error": "Audio must be .mp3, .wav, .ogg, or .m4a"}), 400
        audio_filename = f"{uuid.uuid4().hex[:12]}{audio_ext}"
        audio_path = os.path.join(UPLOAD_DIR, audio_filename)
        audio_file.save(audio_path)

    use_kimi = request.form.get('use_kimi', 'true') == 'true'

    task_id = uuid.uuid4().hex[:12]
    nbs_filename = f"{task_id}.nbs"
    nbs_path = os.path.join(UPLOAD_DIR, nbs_filename)

    base_name = os.path.splitext(f.filename)[0]
    safe_base = "".join(c for c in base_name if c.isalnum() or c in (' ', '-', '_', '(', ')', '（', '）')).strip()
    if not safe_base:
        safe_base = task_id
    output_filename = f"{safe_base}.mp4"
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    counter = 2
    while os.path.exists(output_path):
        output_filename = f"{safe_base}_{counter}.mp4"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        counter += 1

    f.save(nbs_path)

    task_manager.create(task_id, f.filename,
                       audio_file.filename if audio_file else None,
                       use_kimi)

    task_manager.start_render(task_id, nbs_path, output_path,
                             audio_path=audio_path, use_kimi=use_kimi)

    return jsonify({"task_id": task_id, "filename": f.filename})


@app.route("/status/<task_id>")
def status(task_id):
    task = task_manager.get(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    return jsonify(task)


@app.route("/download/<task_id>")
def download(task_id):
    task = task_manager.get(task_id)
    if not task:
        abort(404)
    if task["status"] != "done":
        return jsonify({"error": "Video not ready", "status": task["status"]}), 400
    return send_from_directory(OUTPUT_DIR, task["output_file"], as_attachment=True)


@app.route("/preview/<task_id>")
def preview(task_id):
    task = task_manager.get(task_id)
    if not task:
        abort(404)
    if task["status"] != "done":
        return jsonify({"error": "Video not ready", "status": task["status"]}), 400
    return send_from_directory(OUTPUT_DIR, task["output_file"])


@app.route("/health")
def health():
    return jsonify({"status": "ok", "tasks": task_manager.count()})


if __name__ == "__main__":
    import argparse
    import shutil
    parser = argparse.ArgumentParser(description="NBS Visualizer Web Server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int,
                        default=int(os.environ.get("NBS_PORT", 5000)))
    args = parser.parse_args()

    pycache = os.path.join(APP_ROOT, "__pycache__")
    if os.path.isdir(pycache):
        try:
            shutil.rmtree(pycache)
            logger.info("Cleared Python bytecode cache")
        except OSError as e:
            logger.warning("Failed to clear bytecode cache: %s", e)

    task_manager.cleanup_old_files()
    logger.info("=" * 60)
    logger.info("NBS Visualizer Web Server")
    logger.info("Open http://%s:%d in your browser", args.host, args.port)
    logger.info("=" * 60)
    app.run(host=args.host, port=args.port, debug=False, threaded=True)
