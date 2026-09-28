"""
MinIO storage client implementation for the City of Laredo Certificate Management System.

Provides S3-compatible object storage using MinIO.
"""

import os
from typing import Optional

import urllib3
from minio import Minio
from minio.error import S3Error


class MinioStorageClient:
    """MinIO storage client implementing Storage protocol."""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        secure: bool = False,
        bucket_name: str = "documents",
    ):
        """
        Initialize MinIO storage client.

        Args:
            endpoint: MinIO endpoint (defaults to MINIO_ENDPOINT env var)
            access_key: Access key (defaults to MINIO_ACCESS_KEY env var)
            secret_key: Secret key (defaults to MINIO_SECRET_KEY env var)
            secure: Use HTTPS (defaults to MINIO_SECURE env var or False)
            bucket_name: Bucket name for documents
        """
        self.endpoint = endpoint or os.getenv("MINIO_ENDPOINT")
        if not self.endpoint:
            raise RuntimeError("MINIO_ENDPOINT environment variable is required")

        self.access_key = access_key or os.getenv("MINIO_ACCESS_KEY")
        if not self.access_key:
            raise RuntimeError("MINIO_ACCESS_KEY environment variable is required")

        self.secret_key = secret_key or os.getenv("MINIO_SECRET_KEY")
        if not self.secret_key:
            raise RuntimeError("MINIO_SECRET_KEY environment variable is required")
        self.secure = secure or os.getenv("MINIO_SECURE", "false").lower() == "true"
        self.bucket_name = bucket_name

        # Build MinIO client — with mTLS when TLS is enabled
        if self.secure and os.getenv("TLS_ENABLED", "false").lower() == "true":
            ca_cert = os.getenv("TLS_CA_CERT", "/tls/ca.crt")
            client_cert = os.getenv("TLS_CLIENT_CERT", "/tls/client.crt")
            client_key = os.getenv("TLS_CLIENT_KEY", "/tls/client.key")
            http_client = urllib3.PoolManager(
                cert_reqs="CERT_REQUIRED",
                ca_certs=ca_cert,
                cert_file=client_cert,
                key_file=client_key,
            )
            self.client = Minio(
                self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=True,
                http_client=http_client,
            )
        else:
            self.client = Minio(
                self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.secure,
            )

        # Ensure bucket exists
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self) -> None:
        """Ensure the bucket exists, create if it doesn't."""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
        except S3Error as e:
            raise RuntimeError(f"Failed to ensure bucket exists: {e}")

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        """
        Store object with given key.

        Args:
            key: Object key/path
            data: Object data bytes
            content_type: MIME content type
        """
        try:
            from io import BytesIO

            self.client.put_object(
                self.bucket_name,
                key,
                BytesIO(data),
                length=len(data),
                content_type=content_type,
            )
        except S3Error as e:
            raise RuntimeError(f"Failed to put object {key}: {e}")

    async def get(self, key: str) -> bytes:
        """
        Retrieve object by key.

        Args:
            key: Object key/path

        Returns:
            Object data bytes

        Raises:
            FileNotFoundError: If object doesn't exist
        """
        try:
            response = self.client.get_object(self.bucket_name, key)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except S3Error as e:
            if e.code == "NoSuchKey":
                raise FileNotFoundError(f"Object not found: {key}")
            raise RuntimeError(f"Failed to get object {key}: {e}")

    async def delete(self, key: str) -> None:
        """
        Delete object by key.

        Args:
            key: Object key/path
        """
        try:
            self.client.remove_object(self.bucket_name, key)
        except S3Error as e:
            raise RuntimeError(f"Failed to delete object {key}: {e}")

    async def exists(self, key: str) -> bool:
        """
        Check if object exists.

        Args:
            key: Object key/path

        Returns:
            True if object exists, False otherwise
        """
        try:
            self.client.stat_object(self.bucket_name, key)
            return True
        except S3Error as e:
            if e.code == "NoSuchKey":
                return False
            raise RuntimeError(f"Failed to check object existence {key}: {e}")
