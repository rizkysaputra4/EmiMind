"""Unit tests for MinIO key generation format."""

from __future__ import annotations

from services.shared.minio_client import raw_key


def test_raw_key_format() -> None:
    key = raw_key(
        ticker="BMRI",
        doc_type="FS_QUARTERLY",
        fiscal_period="2024Q4",
        doc_hash="a1b2c3d4e5",
        ext="pdf",
    )
    assert key == "BMRI/FS_QUARTERLY/2024Q4/a1b2c3d4e5.pdf"


def test_raw_key_xbrl_format() -> None:
    key = raw_key(
        ticker="ADRO",
        doc_type="FS_ANNUAL",
        fiscal_period="2023FY",
        doc_hash="f6e5d4c3b2",
        ext=".xbrl.xml",
    )
    assert key == "ADRO/FS_ANNUAL/2023FY/f6e5d4c3b2.xbrl.xml"
