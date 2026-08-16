"""
Utility script to test AWS S3 connection and bucket access.
"""
import os
import boto3
from dotenv import load_dotenv
from botocore.exceptions import NoCredentialsError, ClientError

load_dotenv()


def test_s3_connection():
    print("Testing S3 Connection...")

    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    bucket_name = os.getenv("AWS_S3_BUCKET_NAME")

    if not access_key or access_key.startswith("your_"):
        print("[WARNING] AWS_ACCESS_KEY_ID is not configured with a valid key.")
        return

    if not bucket_name or bucket_name.startswith("your_"):
        print("[WARNING] AWS_S3_BUCKET_NAME is not configured.")
        return

    try:
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=os.getenv("AWS_REGION", "ap-south-1"),
        )
        print(f"Connecting to bucket: {bucket_name}")
        response = s3_client.get_bucket_location(Bucket=bucket_name)
        print("[SUCCESS] Successfully verified AWS S3 bucket access!")
        print(f"Bucket Region: {response.get('LocationConstraint', 'us-east-1')}")
    except NoCredentialsError:
        print("[ERROR] AWS Credentials not found or invalid.")
    except ClientError as e:
        print(f"[ERROR] AWS Client Error: {e}")
    except Exception as e:
        print(f"[ERROR] Unexpected Error: {e}")


if __name__ == "__main__":
    test_s3_connection()
