"""Hardened private S3 adapter for claim evidence and adjuster-managed knowledge."""
from __future__ import annotations
import uuid
from pathlib import Path
import boto3
from botocore.config import Config
from src.config import settings

def _client():
    if not settings.S3_BUCKET:
        raise RuntimeError("S3_BUCKET is not configured.")
    kwargs={"region_name":settings.AWS_REGION,
            "config":Config(signature_version="s3v4",s3={"addressing_style":"virtual"})}
    if settings.S3_ENDPOINT_URL:
        kwargs["endpoint_url"]=settings.S3_ENDPOINT_URL
    return boto3.client("s3",**kwargs)

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
    extra={"ContentType":content_type or "application/octet-stream",
           "ServerSideEncryption":settings.S3_SERVER_SIDE_ENCRYPTION}
    if metadata: extra["Metadata"]=metadata
    _client().put_object(Bucket=settings.S3_BUCKET,Key=key,Body=content,**extra)
    return {"bucket":settings.S3_BUCKET,"key":key,"uri":f"s3://{settings.S3_BUCKET}/{key}"}

def get_bytes(key:str)->bytes:
    response=_client().get_object(Bucket=settings.S3_BUCKET,Key=_safe_key(key))
    return response["Body"].read()

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
