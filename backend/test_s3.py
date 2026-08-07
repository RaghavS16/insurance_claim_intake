import os
import boto3
from dotenv import load_dotenv
from botocore.exceptions import NoCredentialsError, ClientError

# Load environment variables from .env
load_dotenv()

def test_s3_connection():
    print("Testing S3 Connection...")
    
    access_key = os.getenv('AWS_ACCESS_KEY_ID')
    bucket_name = os.getenv('AWS_S3_BUCKET_NAME')
    
    if not access_key or access_key == 'your_key_here':
        print("[ERROR] AWS_ACCESS_KEY_ID is not set to a real key in your .env file.")
        return
        
    if not bucket_name or bucket_name == 'your_bucket_here':
        print("[ERROR] AWS_S3_BUCKET_NAME is not set to a real bucket in your .env file.")
        return

    try:
        # Initialize client
        s3_client = boto3.client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
        )
        
        # Test 1: Check if we can authenticate by listing buckets (or getting bucket location)
        print(f"Attempting to connect to bucket: {bucket_name}")
        response = s3_client.get_bucket_location(Bucket=bucket_name)
        
        print("[SUCCESS] Successfully connected to AWS and verified bucket access!")
        print(f"Bucket Region: {response.get('LocationConstraint', 'us-east-1')}")
        
    except NoCredentialsError:
        print("[ERROR] Invalid AWS Credentials.")
    except ClientError as e:
        print(f"[ERROR] AWS Client Error: {e}")
    except Exception as e:
        print(f"[ERROR] Unexpected Error: {e}")

if __name__ == "__main__":
    test_s3_connection()
