import os
import json
import threading
from pathlib import Path
from typing import Optional, Dict, Any


class DocumentCache:
    _lock = threading.Lock()

    @staticmethod
    def get_cache_path(file_path: str) -> Path:
        return Path(file_path).with_suffix(Path(file_path).suffix + ".kairo_cache.json")

    @classmethod
    def get(cls, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached JSON data if it exists and the file's mtime hasn't changed.
        """
        try:
            p = Path(file_path)
            if not p.exists():
                return None

            cache_p = cls.get_cache_path(file_path)
            if not cache_p.exists():
                return None

            with cls._lock:
                # Compare mtimes
                current_mtime = p.stat().st_mtime
                with open(cache_p, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)

                cached_mtime = cached_data.get("mtime", 0.0)
                if abs(current_mtime - cached_mtime) < 1e-4:
                    return cached_data.get("data")
        except Exception:
            pass
        return None

    @classmethod
    def set(cls, file_path: str, data: Dict[str, Any]):
        """
        Store parsed JSON data associated with the file's current mtime.
        """
        try:
            p = Path(file_path)
            if not p.exists():
                return

            cache_p = cls.get_cache_path(file_path)
            current_mtime = p.stat().st_mtime

            cache_payload = {"mtime": current_mtime, "data": data}

            with cls._lock:
                # Write atomically using a temporary file
                temp_cache = cache_p.with_suffix(".tmp")
                with open(temp_cache, "w", encoding="utf-8") as f:
                    json.dump(cache_payload, f, indent=2, ensure_ascii=False)
                os.replace(str(temp_cache), str(cache_p))
        except Exception:
            pass
