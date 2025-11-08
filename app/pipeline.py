import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from .settings import settings


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{proc.stdout}")


def process_video_job(url: str) -> dict[str, Any]:
    """
    Pipeline (MVP):
    1) Download audio with yt-dlp (ONLY allowed/owned/CC content)
    2) Write minimal artifact manifest
    3) Placeholder for transcription + embeddings
    """
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    job_dir = settings.DATA_DIR / ts
    job_dir.mkdir(parents=True, exist_ok=True)

    # 1) Download audio
    audio_path = job_dir / "audio.m4a"
    # yt-dlp needs ffmpeg installed in PATH
    run([
        "yt-dlp",
        "-f",
        "bestaudio",
        "--extract-audio",
        "--audio-format",
        "m4a",
        "-o",
        str(job_dir / "%(_id)s.%(ext)s"),
        url,
    ])

    # Move best audio file to a known name
    candidates = list(job_dir.glob("*.m4a")) + list(job_dir.glob("*.mp3"))
    if not candidates:
        raise RuntimeError("No audio file downloaded. Ensure you have rights and ffmpeg is installed.")
    shutil.move(str(candidates[0]), audio_path)

    # 2) Minimal manifest
    manifest = {
        "url": url,
        "created_at": ts,
        "artifacts": {
            "audio": str(audio_path),
            # Placeholders to be filled by later stages
            "transcript": None,
            "embeddings": None,
        },
        "notes": "WARNING: Process only owned/licensed/CC content. Respect YouTube ToS.",
    }

    with open(job_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return {"job_dir": str(job_dir), "manifest": manifest}
