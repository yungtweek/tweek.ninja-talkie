import os
import io
import logging
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from index_worker.settings import Settings

settings = Settings()
logger = logging.getLogger("S3Client")

s3_client = boto3.client(
    "s3",
    endpoint_url=settings.S3_ENDPOINT,
    aws_access_key_id=settings.S3_ACCESS_KEY,
    aws_secret_access_key=settings.S3_SECRET_KEY,
)

def download_file_to_bytes(bucket: str, key: str) -> Optional[bytes]:
    logger.info(f"Downloading {key} from {bucket}")
    """Download an object from S3 and return it as bytes."""
    try:
        buf = io.BytesIO()
        s3_client.download_fileobj(bucket, key, buf)
        buf.seek(0)
        return buf.read()
    except ClientError as e:
        logger.warning(f"Failed to download {key} from {bucket}: {e}")
        return None

# NOTE:
# The following helper functions (upload_bytes, get_presigned_url)
# are not used by index_worker directly.
# They are kept for reference and possible use in other workers
# or in future features (e.g., embedding preview uploads, testing).
def upload_bytes(bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream") -> bool:
    """Upload bytes to S3 as an object."""
    try:
        s3_client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)
        return True
    except ClientError as e:
        logger.warning(f"Failed to upload {key} to {bucket}: {e}")
        return False

def get_presigned_url(bucket: str, key: str, expires_in: int = 3600) -> Optional[str]:
    """Generate a presigned URL for temporary access."""
    try:
        url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )
        return url
    except ClientError as e:
        logger.warning(f"Failed to generate presigned URL for {key}: {e}")
        return None