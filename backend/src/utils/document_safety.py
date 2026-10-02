"""Defensive limits for untrusted document parsing and OCR workloads."""
from __future__ import annotations
import io
import os
import zipfile
from pypdf import PdfReader
from PIL import Image
from src.config import settings

ZIP_EXTENSIONS = {".docx", ".xlsx", ".pptx", ".zip"}

def enforce_document_limits(content: bytes, filename: str) -> None:
    if len(content) > settings.KNOWLEDGE_MAX_UPLOAD_BYTES:
        raise ValueError("Document exceeds the configured upload size limit.")
    ext = os.path.splitext(filename or "")[1].lower()
    if ext in {".jpg", ".jpeg", ".png", ".webp"}:
        try:
            with Image.open(io.BytesIO(content)) as image:
                if int(image.width) * int(image.height) > settings.MAX_IMAGE_PIXELS:
                    raise ValueError("Image dimensions exceed the configured safety limit.")
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Image payload is not safely readable.") from exc
    if ext == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(content), strict=False)
            if len(reader.pages) > settings.MAX_PDF_PAGES:
                raise ValueError(
                    f"PDF exceeds the configured maximum of {settings.MAX_PDF_PAGES} pages."
                )
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("PDF payload is not safely readable.") from exc
    if ext in ZIP_EXTENSIONS:
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                total = 0
                for info in archive.infolist():
                    total += int(info.file_size or 0)
                    if total > settings.MAX_ARCHIVE_EXPANDED_BYTES:
                        raise ValueError("Compressed document expands beyond the configured safety limit.")
                    if info.file_size > max(1, len(content)) * 1000:
                        raise ValueError("Compressed document has an unsafe expansion ratio.")
        except ValueError:
            raise
        except zipfile.BadZipFile:
            if ext != ".zip":
                return
            raise ValueError("Compressed document is corrupt.")

def enforce_extracted_text_limit(text: str, filename: str) -> str:
    value = str(text or "")
    if len(value) > settings.MAX_EXTRACTED_TEXT_CHARS:
        raise ValueError(
            f"Extracted text from '{filename}' exceeds the configured safety limit."
        )
    return value
