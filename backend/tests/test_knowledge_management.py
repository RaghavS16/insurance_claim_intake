from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from src.api import knowledge_routes


def _user(role="ADJUSTER"):
    return SimpleNamespace(id="user-1", tenant_id="tenant-1", role=role, status="active")


def test_list_documents_is_tenant_scoped(monkeypatch):
    monkeypatch.setattr(knowledge_routes, "require_role", lambda roles: lambda **kwargs: _user())
    doc = SimpleNamespace(
        id="doc-1", source_name="policy.pdf", document_type="policy_wording",
        insurance_type="motor", document_version="v2", jurisdiction="IN",
        metadata_json={"policy_number":"POL-1","publication_status":"published"},
        created_at=datetime(2026,1,1,tzinfo=timezone.utc), source_uri="s3://bucket/key",
        chunks=[1,2],
    )
    db=MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value=[doc]
    out=knowledge_routes.list_documents(_user(),db)
    assert out["items"][0]["id"]=="doc-1"
    assert out["items"][0]["publication_status"]=="published"


def test_update_document_rejects_invalid_publication_status():
    doc=SimpleNamespace(id="doc-1",tenant_id="tenant-1",metadata_json={})
    db=MagicMock()
    db.query.return_value.filter.return_value.first.return_value=doc
    with pytest.raises(HTTPException) as exc:
        knowledge_routes.update_document("doc-1", knowledge_routes.UpdateDocumentRequest(publication_status="bad"), _user(), db)
    assert exc.value.status_code==400


def test_reindex_missing_document_is_404():
    db=MagicMock()
    db.query.return_value.filter.return_value.first.return_value=None
    with pytest.raises(HTTPException) as exc:
        import asyncio
        asyncio.run(knowledge_routes.reindex_document("missing", _user(), db))
    assert exc.value.status_code==404
