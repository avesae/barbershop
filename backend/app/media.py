"""Загрузка фото: уменьшаем до разумного размера и сохраняем в webp."""

import io
import secrets
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .config import get_settings

MAX_SIDE = 1600
MAX_BYTES = 10 * 1024 * 1024


class MediaError(Exception):
    pass


def upload_dir() -> Path:
    path = Path(get_settings().upload_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_image(data: bytes) -> str:
    """Сохраняет картинку и возвращает публичный путь вида /uploads/<имя>.webp."""
    if len(data) > MAX_BYTES:
        raise MediaError("Файл больше 10 МБ")
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)  # фото с телефона часто повёрнуто через EXIF
    except (UnidentifiedImageError, OSError):
        raise MediaError("Это не похоже на картинку") from None
    img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    name = f"{secrets.token_hex(8)}.webp"
    img.save(upload_dir() / name, "WEBP", quality=82)
    return f"/uploads/{name}"


def delete_image(public_path: str | None) -> None:
    if public_path and public_path.startswith("/uploads/"):
        (upload_dir() / Path(public_path).name).unlink(missing_ok=True)
