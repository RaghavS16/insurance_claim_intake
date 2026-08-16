"""
S3 Storage Utility functions for document persistence and presigned URL generation.
"""
import os
import boto3
from botocore.exceptions import NoCredentialsError


def get_s3_client():
    """Create and return a configured boto3 S3 client."""
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    return boto3.client(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=region,
    )


def upload_to_s3(file_obj, filename: str, expires_in: int = 3600) -> str:
    """
    Upload a file stream to configured S3 bucket and return presigned URL (or public URL).
    """
    s3_client = get_s3_client()
    bucket_name = os.getenv("AWS_S3_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("AWS_S3_BUCKET_NAME is not set in environment variables.")

    try:
        s3_client.upload_fileobj(file_obj, bucket_name, filename)

        use_public = os.getenv("AWS_S3_PUBLIC_URLS", "false").lower() == "true"
        if not use_public:
            return generate_presigned_url(filename, expires_in=expires_in)

        region = s3_client.meta.region_name
        if region:
            return f"https://{bucket_name}.s3.{region}.amazonaws.com/{filename}"
        return f"https://{bucket_name}.s3.amazonaws.com/{filename}"

    except NoCredentialsError:
        raise Exception("AWS credentials not found. Please check your .env configuration.")


def generate_presigned_url(filename: str, expires_in: int = 3600) -> str:
    """
    Generate a secure temporary presigned GET URL for an S3 object key.
    """
    s3_client = get_s3_client()
    bucket_name = os.getenv("AWS_S3_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("AWS_S3_BUCKET_NAME is not set in environment variables.")

    return s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket_name, "Key": filename},
        ExpiresIn=expires_in,
    )
