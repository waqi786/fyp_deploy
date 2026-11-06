from __future__ import annotations

import hashlib
import struct

from app.schemas.document import FigureImageAnalysisResponse


class FigureImageAnalysisService:
    def analyze(self, *, filename: str, content_type: str, data: bytes) -> FigureImageAnalysisResponse:
        width, height = _image_dimensions(data, content_type)
        clean_name = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip()
        diagram_type = _diagram_type(clean_name)
        dominant_tone = _dominant_tone(data)
        digest = hashlib.sha256(data).hexdigest()[:16]
        dimensions = f"{width}x{height}" if width and height else "unknown dimensions"
        search_caption = f"{clean_name} {diagram_type} figure {dimensions} {dominant_tone}".strip()
        alt_text = f"Uploaded {diagram_type} figure named {clean_name or filename}, {dimensions}, with {dominant_tone} visual tone."
        confidence = 0.72 if width and height else 0.52
        return FigureImageAnalysisResponse(
            filename=filename,
            content_type=content_type or "application/octet-stream",
            byte_size=len(data),
            width=width,
            height=height,
            perceptual_hash=digest,
            dominant_tone=dominant_tone,
            diagram_type=diagram_type,
            search_caption=search_caption,
            alt_text=alt_text,
            confidence_score=confidence,
        )


def _image_dimensions(data: bytes, content_type: str) -> tuple[int | None, int | None]:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return int(width), int(height)
    if content_type == "image/jpeg" or data.startswith(b"\xff\xd8"):
        return _jpeg_dimensions(data)
    return None, None


def _jpeg_dimensions(data: bytes) -> tuple[int | None, int | None]:
    index = 2
    while index < len(data) - 9:
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        block_length = int.from_bytes(data[index + 2:index + 4], "big")
        if marker in {0xC0, 0xC2} and index + 8 < len(data):
            height = int.from_bytes(data[index + 5:index + 7], "big")
            width = int.from_bytes(data[index + 7:index + 9], "big")
            return width, height
        index += 2 + max(block_length, 1)
    return None, None


def _dominant_tone(data: bytes) -> str:
    if not data:
        return "unknown"
    sample = data[: min(len(data), 4096)]
    mean = sum(sample) / len(sample)
    if mean < 85:
        return "dark"
    if mean > 170:
        return "light"
    return "mixed"


def _diagram_type(name: str) -> str:
    lowered = name.lower()
    if any(token in lowered for token in ("bar", "histogram", "accuracy", "auc", "curve", "trend")):
        return "chart"
    if any(token in lowered for token in ("architecture", "pipeline", "workflow", "diagram")):
        return "diagram"
    if any(token in lowered for token in ("table", "matrix", "grid")):
        return "table-like image"
    return "figure"
