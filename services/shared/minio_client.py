"""MinIO object storage client utilities."""

from __future__ import annotations

import io

from minio import Minio

from services.shared.config import Settings, get_settings


def get_minio(settings: Settings | None = None) -> Minio:
    """Creates a MinIO client instance from settings."""
    cfg = settings or get_settings()
    return Minio(
        endpoint=cfg.minio_endpoint,
        access_key=cfg.minio_access_key,
        secret_key=cfg.minio_secret_key.get_secret_value(),
        secure=cfg.minio_secure,
    )


def ensure_bucket(client: Minio, bucket_name: str | None = None) -> None:
    """Ensures the target bucket exists in MinIO."""
    target_bucket = bucket_name or get_settings().minio_bucket_raw
    if not client.bucket_exists(target_bucket):
        client.make_bucket(target_bucket)


def raw_key(ticker: str, doc_type: str, fiscal_period: str, doc_hash: str, ext: str = "pdf") -> str:
    """Generates the canonical MinIO storage key per BLUEPRINT §6.1."""
    clean_ext = ext.lstrip(".")
    return f"{ticker}/{doc_type}/{fiscal_period}/{doc_hash}.{clean_ext}"


def pending_key(doc_hash: str, ext: str = "pdf") -> str:
    """Generates a MinIO key for documents awaiting metadata review."""
    clean_ext = ext.lstrip(".")
    return f"pending/{doc_hash}.{clean_ext}"


def put_pdf(client: Minio, key: str, data: bytes, bucket_name: str | None = None) -> None:
    """Uploads binary document bytes to MinIO."""
    target_bucket = bucket_name or get_settings().minio_bucket_raw
    client.put_object(
        bucket_name=target_bucket,
        object_name=key,
        data=io.BytesIO(data),
        length=len(data),
        content_type="application/pdf",
    )


def get_pdf(client: Minio, key: str, bucket_name: str | None = None) -> bytes:
    """Retrieves document binary bytes from MinIO."""
    target_bucket = bucket_name or get_settings().minio_bucket_raw
    response = client.get_object(bucket_name=target_bucket, object_name=key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()
