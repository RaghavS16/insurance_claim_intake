import os
import boto3
from botocore.exceptions import NoCredentialsError

def get_s3_client():
    # FIX 5: Pass region_name so meta.region_name is never None.
    # Without this, the URL falls back to the deprecated path-style format
    # (https://s3.amazonaws.com/{bucket}/{key}) instead of the virtual-hosted
    # style (https://{bucket}.s3.{region}.amazonaws.com/{key}).
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    return boto3.client(
        's3',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=region,  # may still be None if env not set; boto3 will use ~/.aws config
    )

def upload_to_s3(file_obj, filename: str, expires_in: int = 3600) -> str:
    """
    Uploads a file object to S3 and returns a secure presigned URL (or public URL if configured).
    """
    s3_client = get_s3_client()
    bucket_name = os.getenv('AWS_S3_BUCKET_NAME')
    
    if not bucket_name:
        raise ValueError("AWS_S3_BUCKET_NAME is not set in environment variables.")
        
    try:
        # Upload the file stream to the bucket
        s3_client.upload_fileobj(
            file_obj, 
            bucket_name, 
            filename
        )
        
        # S-1 Security Fix: Default to secure presigned URLs unless public URLs are explicitly requested.
        use_public = os.getenv("AWS_S3_PUBLIC_URLS", "false").lower() == "true"
        if not use_public:
            return generate_presigned_url(filename, expires_in=expires_in)

        # Generate standard public URL fallback
        region = s3_client.meta.region_name
        if region:
            url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{filename}"
        else:
            url = f"https://{bucket_name}.s3.amazonaws.com/{filename}"
            
        return url

    except NoCredentialsError:
        raise Exception("AWS credentials not found. Please check your .env file.")

def generate_presigned_url(filename: str, expires_in: int = 3600) -> str:
    """
    Generates a secure temporary presigned URL for downloading/viewing a file from S3.
    """
    s3_client = get_s3_client()
    bucket_name = os.getenv('AWS_S3_BUCKET_NAME')
    if not bucket_name:
        raise ValueError("AWS_S3_BUCKET_NAME is not set in environment variables.")
    return s3_client.generate_presigned_url(
        'get_object',
        Params={'Bucket': bucket_name, 'Key': filename},
        ExpiresIn=expires_in
    )

