"""Tests for storage safety, path traversal prevention, download headers, and production fallbacks."""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from fastapi.testclient import TestClient

from src.config import settings
from src.storage.s3 import put_bytes, get_bytes, delete_bytes, promote_quarantined
from src.utils.file_security import (
    get_safe_media_type,
    sanitize_filename,
    build_attachment_headers,
    verify_upload_magic_bytes,
)
from src.api.main import app

client = TestClient(app)


def test_safe_media_type_allowlist():
    assert get_safe_media_type("document.pdf") == "application/pdf"
    assert get_safe_media_type("image.jpg") == "image/jpeg"
    assert get_safe_media_type("image.png") == "image/png"
    assert get_safe_media_type("image.webp") == "image/webp"
    assert get_safe_media_type("notes.txt") == "text/plain"
    assert get_safe_media_type("report.docx") == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert get_safe_media_type("report.xlsx") == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert get_safe_media_type("report.csv") == "text/csv"
    # Unallowed extension defaults safely
    assert get_safe_media_type("script.html") == "application/octet-stream"
    assert get_safe_media_type("executable.exe") == "application/octet-stream"


def test_sanitize_filename():
    assert sanitize_filename("safe.pdf") == "safe.pdf"
    assert sanitize_filename('../../etc/passwd"evil\r\n.txt') == "passwd'evil.txt".replace("'", "") or "passwdevil.txt"
    assert sanitize_filename('test"file\nname.pdf') == "testfilename.pdf"


def test_build_attachment_headers():
    headers = build_attachment_headers('invoice"final\r\n.pdf')
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Content-Security-Policy"] == "sandbox; default-src 'none'"
    assert "attachment" in headers["Content-Disposition"]
    assert 'filename="invoicefinal.pdf"' in headers["Content-Disposition"]
    assert "filename*=UTF-8''invoicefinal.pdf" in headers["Content-Disposition"]


def test_verify_upload_magic_bytes():
    # PDF
    assert verify_upload_magic_bytes(b"%PDF-1.7 sample content", "file.pdf")[0] is True
    ok, err = verify_upload_magic_bytes(b"<html>not a pdf</html>", "file.pdf")
    assert ok is False
    assert "PDF" in err

    # JPEG
    assert verify_upload_magic_bytes(b"\xff\xd8\xff\xe0 sample", "image.jpeg")[0] is True
    ok, err = verify_upload_magic_bytes(b"fake jpeg", "image.jpg")
    assert ok is False

    # PNG
    assert verify_upload_magic_bytes(b"\x89PNG\r\n\x1a\n sample", "image.png")[0] is True
    ok, err = verify_upload_magic_bytes(b"fake png", "image.png")
    assert ok is False

    # WEBP
    assert verify_upload_magic_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image.webp")[0] is True
    ok, err = verify_upload_magic_bytes(b"RIFF\x00\x00\x00\x00JPEGbad", "image.webp")
    assert ok is False

    # DOCX
    assert verify_upload_magic_bytes(b"PK\x03\x04 fake docx archive", "file.docx")[0] is True
    ok, err = verify_upload_magic_bytes(b"plain text fake docx", "file.docx")
    assert ok is False


def test_path_traversal_refusal(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "S3_BUCKET", None)

    with pytest.raises(ValueError, match="Invalid object key|Path traversal denied"):
        get_bytes("../../../etc/passwd")

    with pytest.raises(ValueError, match="Invalid object key|Path traversal denied"):
        delete_bytes("../../../etc/passwd")

    with pytest.raises(ValueError, match="Invalid object key|Path traversal denied"):
        promote_quarantined("../../../etc/passwd", ticket_id="TCK-123", filename="test.pdf")


def test_production_storage_never_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "S3_BUCKET", None)

    # put_bytes must raise
    with pytest.raises(RuntimeError, match="Production S3 upload failed"):
        put_bytes(b"some content", prefix="claims", filename="test.pdf")

    # get_bytes must raise
    with pytest.raises(RuntimeError, match="Production object storage read failed"):
        get_bytes("claims/test.pdf")

    # delete_bytes must raise
    with pytest.raises(RuntimeError, match="Production object deletion failed"):
        delete_bytes("claims/test.pdf")

    # promote_quarantined must raise
    with pytest.raises(RuntimeError, match="Production quarantined object promotion failed"):
        promote_quarantined("quarantine/claims/test.pdf", ticket_id="TCK-1", filename="test.pdf")


@pytest.fixture
def storage_test_db(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src.database.models import Base
    from src.database.hardening_models import Base as HardeningBase
    from src.database.session import get_db

    db_file = tmp_path / "storage_test.db"
    db_url = f"sqlite:///{db_file}"
    monkeypatch.setattr(settings, "DATABASE_URL", db_url)

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    HardeningBase.metadata.create_all(bind=engine)

    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield Session
    app.dependency_overrides.pop(get_db, None)


def test_download_route_security_headers_and_content_type(monkeypatch, tmp_path, storage_test_db):
    """Test that stored lying content_type (e.g. text/html for a .txt) is overridden to text/plain attachment."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    monkeypatch.setattr(settings, "ALLOW_INSECURE_TEST_AUTH", True)
    monkeypatch.setattr(settings, "S3_BUCKET", None)
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))

    # Create a local file in UPLOAD_DIR
    target_file = tmp_path / "notes.txt"
    target_file.write_text("Hello claimant notes", encoding="utf-8")

    from src.database.models import Claim, User
    from src.database.hardening_models import ClaimEvidence
    import uuid

    db = storage_test_db()
    try:
        user_id = str(uuid.uuid4())
        tenant_id = "00000000-0000-0000-0000-000000000001"
        from datetime import datetime, timezone
        u = User(
            id=user_id,
            email=f"admin_{user_id}@test.com",
            password_hash="dummy",
            full_name="Admin User",
            role="ADMIN",
            status="active",
            email_verified_at=datetime.now(timezone.utc),
            tenant_id=tenant_id,
        )
        db.add(u)

        c = Claim(
            id=str(uuid.uuid4()),
            ticket_id="TCK-TEST-STORAGE",
            tenant_id=tenant_id,
            claimant_id=user_id,
            status="under_review",
            pipeline_state={"evidence": []},
        )
        db.add(c)

        ev_id = str(uuid.uuid4())
        ev = ClaimEvidence(
            id=ev_id,
            tenant_id=tenant_id,
            claim_id=c.id,
            object_key=str(target_file),
            original_filename="notes.txt",
            content_type="text/html",  # LYING content_type!
            size_bytes=len(target_file.read_bytes()),
            status="uploaded",
        )
        db.add(ev)
        db.commit()

        # Download evidence file
        headers = {"X-User-ID": user_id, "X-Tenant-ID": tenant_id}
        res = client.get(f"/api/v1/adjuster/claims/TCK-TEST-STORAGE/evidence/{ev_id}/download", headers=headers)
        assert res.status_code == 200
        # Check media type is text/plain, NOT text/html!
        assert "text/plain" in res.headers["content-type"]
        assert "text/html" not in res.headers["content-type"]
        # Check Content-Disposition is attachment with sanitized filename
        assert "attachment" in res.headers["content-disposition"]
        assert 'filename="notes.txt"' in res.headers["content-disposition"]
        # Check security headers
        assert res.headers["x-content-type-options"] == "nosniff"
        assert res.headers["content-security-policy"] == "sandbox; default-src 'none'"
    finally:
        db.close()


def test_download_generic_404_on_missing_file(monkeypatch, storage_test_db):
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    monkeypatch.setattr(settings, "ALLOW_INSECURE_TEST_AUTH", True)

    from src.database.models import Claim, User
    import uuid

    db = storage_test_db()
    try:
        user_id = str(uuid.uuid4())
        tenant_id = "00000000-0000-0000-0000-000000000001"
        from datetime import datetime, timezone
        u = User(
            id=user_id,
            email=f"admin_{user_id}@test.com",
            password_hash="dummy",
            full_name="Admin User",
            role="ADMIN",
            status="active",
            email_verified_at=datetime.now(timezone.utc),
            tenant_id=tenant_id,
        )
        db.add(u)

        c = Claim(
            id=str(uuid.uuid4()),
            ticket_id="TCK-MISSING-TEST",
            tenant_id=tenant_id,
            status="under_review",
            pipeline_state={"evidence": []},
        )
        db.add(c)
        db.commit()

        headers = {"X-User-ID": user_id, "X-Tenant-ID": tenant_id}
        res = client.get(f"/api/v1/adjuster/claims/TCK-MISSING-TEST/evidence/{uuid.uuid4()}/download", headers=headers)
        assert res.status_code == 404
        assert res.json() == {"detail": "Evidence item not found"}
    finally:
        db.close()
