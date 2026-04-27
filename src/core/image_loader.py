"""Load SEM images (TIFF/PNG/JPEG/BMP) and convert to uint8 grayscale."""

from __future__ import annotations
from pathlib import Path
import cv2
import numpy as np

SUPPORTED_EXTENSIONS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp"}


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def load_grayscale(path: str | Path) -> np.ndarray:
    """Return uint8 grayscale image array.

    Handles 8-bit and 16-bit TIFF; RGB images are converted to grayscale.
    Raises ValueError if the file cannot be read.
    """
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"Cannot read image: {path}")

    if img.ndim == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    if img.dtype == np.uint16:
        img = (img / 256).astype(np.uint8)
    elif img.dtype != np.uint8:
        img = img.astype(np.float32)
        img = ((img - img.min()) / ((img.max() - img.min()) + 1e-9) * 255).astype(np.uint8)

    return img


def scan_folder(folder: str | Path, recursive: bool = True) -> list[Path]:
    """Return sorted list of supported image paths inside *folder*."""
    folder = Path(folder)
    if recursive:
        paths = [p for p in folder.rglob("*") if p.is_file() and is_supported(p)]
    else:
        paths = [p for p in folder.iterdir() if p.is_file() and is_supported(p)]
    return sorted(paths)
