"""Image preprocessing shared by encoder backends (no ML deps beyond Pillow/numpy)."""

from pathlib import Path

import numpy as np
from PIL import Image

from library_of_mess.encoders import EmbeddingBackendError

IMAGE_SIZE = 256


def load_image_blob(path: Path, size: int = IMAGE_SIZE) -> np.ndarray:
    """JPEG/PNG thumbnail -> (3, size, size) float32 in [-1, 1]."""
    try:
        rgb = Image.open(path).convert("RGB")
    except OSError as exc:
        raise EmbeddingBackendError(f"unreadable thumbnail: {path}") from exc
    resized = rgb.resize((size, size), Image.Resampling.BILINEAR)
    arr = np.asarray(resized, dtype=np.float32) / 255.0
    arr = (arr - 0.5) / 0.5
    return arr.transpose(2, 0, 1)
