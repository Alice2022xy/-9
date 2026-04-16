from __future__ import annotations

from pathlib import Path
from fastapi import UploadFile, HTTPException


def validate_suffix(filename: str, allowed: set[str], error_message: str) -> str:
    suffix = (Path(filename).suffix or "").lower()
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail=error_message)
    return suffix


def save_upload_with_limit(
    upload: UploadFile,
    dest: Path,
    max_bytes: int,
    too_large_message: str,
    chunk_size: int = 1024 * 1024,  # 1MB
) -> str:
    """
    Streaming 保存上传文件，并限制最大字节数：
    - 不依赖 upload.file 是否支持 seek/tell（部署更稳）
    - 超过 max_bytes 立即中止并删除目标文件，避免磁盘残留
    - too_large_message 用于返回更精确的提示文案
    """
    dest.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    try:
        with dest.open("wb") as f:
            while True:
                chunk = upload.file.read(chunk_size)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(status_code=400, detail=too_large_message)
                f.write(chunk)
    except HTTPException:
        try:
            if dest.exists():
                dest.unlink()
        except Exception:
            pass
        raise
    except Exception:
        try:
            if dest.exists():
                dest.unlink()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="文件保存失败，请重试")

    return str(dest)