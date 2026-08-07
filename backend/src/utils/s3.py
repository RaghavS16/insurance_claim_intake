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

def upload_to_s3(file_obj, filename: str) -> str:
    """
    Uploads a file object to S3 and returns the public URL.
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
        
        # Generate the URL
        region = s3_client.meta.region_name
        
        # If region is not available from meta, fallback to standard aws url format
        if region:
            url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{filename}"
        else:
            url = f"https://{bucket_name}.s3.amazonaws.com/{filename}"
            
        return url

    except NoCredentialsError:
        raise Exception("AWS credentials not found. Please check your .env file.")
