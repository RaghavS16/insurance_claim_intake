"""Hardened private S3 adapter for claim evidence and adjuster-managed knowledge."""
from __future__ import annotations
from typing import Any
import uuid
from pathlib import Path
import boto3
from botocore.config import Config
from src.config import settings

import logging

logger = logging.getLogger(__name__)

def _client():
    if not settings.S3_BUCKET:
        raise RuntimeError("S3_BUCKET is not configured.")
    kwargs: dict[str, Any] = {
        "region_name": settings.AWS_REGION,
        "config": Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    }
    if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
        if settings.AWS_SESSION_TOKEN:
            kwargs["aws_session_token"] = settings.AWS_SESSION_TOKEN
    if settings.S3_ENDPOINT_URL:
        kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
    return boto3.client("s3", **kwargs)

def _safe_key(key:str)->str:
    clean=key.strip().lstrip("/")
    if not clean or ".." in clean.split("/"):
        raise ValueError("Invalid object key.")
    return clean

def put_bytes(content:bytes,*,prefix:str,filename:str,content_type:str|None=None,metadata:dict[str,str]|None=None)->dict:
    if len(content)>settings.MAX_EVIDENCE_UPLOAD_BYTES and prefix.rstrip("/") == settings.S3_EVIDENCE_PREFIX:
        raise ValueError("Evidence file exceeds configured size limit.")
    suffix=Path(filename).suffix.lower()
    key=f"{prefix.rstrip('/')}/{uuid.uuid4().hex}{suffix}"
    try:
        if not settings.S3_BUCKET:
            raise RuntimeError("S3_BUCKET is not configured.")
        extra: dict[str, Any] = {"ContentType": content_type or "application/octet-stream",
                                 "ServerSideEncryption": settings.S3_SERVER_SIDE_ENCRYPTION}
        if metadata: extra["Metadata"]=metadata
        _client().put_object(Bucket=settings.S3_BUCKET,Key=key,Body=content,**extra)
        logger.info("Successfully uploaded object to S3: s3://%s/%s", settings.S3_BUCKET, key)
        return {"bucket":settings.S3_BUCKET,"key":key,"uri":f"s3://{settings.S3_BUCKET}/{key}"}
    except Exception as exc:
        logger.warning("S3 upload to bucket '%s' failed (%s: %s). Falling back to local disk storage.", settings.S3_BUCKET, type(exc).__name__, exc)
        if settings.ENVIRONMENT in ("production", "staging") and settings.REQUIRE_S3_IN_PRODUCTION:
            raise RuntimeError(f"Production S3 upload failed: {exc}") from exc
        # Graceful local fallback for development
        local_dir = Path("uploads") / prefix.rstrip("/")
        local_dir.mkdir(parents=True, exist_ok=True)
        local_path = (local_dir / f"{uuid.uuid4().hex}{suffix}").resolve()
        local_path.write_bytes(content)
        return {"bucket":"local","key":str(local_path),"uri":local_path.as_uri()}

def get_bytes(key:str)->bytes:
    try:
        response=_client().get_object(Bucket=settings.S3_BUCKET,Key=_safe_key(key))
        return response["Body"].read()
    except Exception:
        # Fallback to local file read
        p = Path(key)
        if p.exists() and p.is_file():
            return p.read_bytes()
        raise

def presigned_get(key:str,expires:int|None=None)->str:
    ttl=expires if expires is not None else settings.S3_PRESIGNED_URL_EXPIRE_SECONDS
    ttl=max(60,min(ttl,3600))
    return _client().generate_presigned_url("get_object",Params={"Bucket":settings.S3_BUCKET,"Key":_safe_key(key)},ExpiresIn=ttl)

def presigned_put(*,prefix:str,filename:str,content_type:str="application/octet-stream",expires:int|None=None)->dict:
    ttl=expires if expires is not None else settings.S3_PRESIGNED_URL_EXPIRE_SECONDS
    ttl=max(60,min(ttl,3600))
    suffix=Path(filename).suffix.lower()
    key=f"{prefix.rstrip('/')}/{uuid.uuid4().hex}{suffix}"
    url=_client().generate_presigned_url("put_object",Params={
        "Bucket":settings.S3_BUCKET,"Key":key,"ContentType":content_type,
        "ServerSideEncryption":settings.S3_SERVER_SIDE_ENCRYPTION},ExpiresIn=ttl)
    return {"bucket":settings.S3_BUCKET,"key":key,"url":url,"expires_in":ttl}
