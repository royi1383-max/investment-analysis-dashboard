"""
Shared JSON disk persistence — atomic writes + numpy-safe encoding.

Used by: alerts (.alerts.json), weekly picks (.wp_cache.json / .wp_history.json),
paper portfolios (.paper_portfolios.json), watchlist (.watchlist.json).

Atomic write (tmp file + os.replace) prevents corruption if the app is
interrupted mid-write or two Streamlit reruns race.
"""
import os
import json
import numpy as np
from pathlib import Path
from typing import Any


class NumpyEncoder(json.JSONEncoder):
    """Converts numpy scalars/arrays → Python natives so they round-trip.
    Anything else non-serializable (dates, Timestamps) falls back to str."""
    def default(self, obj: Any) -> Any:
        if isinstance(obj, np.integer):  return int(obj)
        if isinstance(obj, np.floating): return float(obj)
        if isinstance(obj, np.bool_):    return bool(obj)
        if isinstance(obj, np.ndarray):  return obj.tolist()
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)


def load_json(path: Path | str, default: Any = None) -> Any:
    """Read JSON file; returns `default` on any failure."""
    try:
        p = Path(path)
        if not p.exists():
            return default
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path | str, data: Any, indent: int | None = 2) -> bool:
    """Atomic JSON write. Returns True on success."""
    try:
        p = Path(path)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=indent, cls=NumpyEncoder),
            encoding="utf-8",
        )
        os.replace(tmp, p)
        return True
    except Exception:
        return False
