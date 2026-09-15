"""S3 storage adapter for claim evidence and knowledge source documents."""
from __future__ import annotations
import uuid
from pathlib import Path
from typing import BinaryIO
import boto3
from botocore.config import Config
from src.config import settings

def _client():
    if not settings.S3_BUCKET:
        raise RuntimeError("S3_BUCKET is not configured.")
    return boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )

def put_bytes(content: bytes, *, prefix: str, filename: str, content_type: str | None = None) -> dict:
    suffix = Path(filename).suffix.lower()
    key = f"{prefix.rstrip('/')}/{uuid.uuid4().hex}{suffix}"
    extra = {"ContentType": content_type or "application/octet-stream", "ServerSideEncryption": "AES256"}
    _client().put_object(Bucket=settings.S3_BUCKET, Key=key, Body=content, **extra)
    return {"bucket": settings.S3_BUCKET, "key": key, "uri": f"s3://{settings.S3_BUCKET}/{key}"}

def get_bytes(key: str) -> bytes:
    response = _client().get_object(Bucket=settings.S3_BUCKET, Key=key)
    return response["Body"].read()

def presigned_get(key: str, expires: int = 900) -> str:
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_BUCKET, "Key": key},
        ExpiresIn=expires,
    )
