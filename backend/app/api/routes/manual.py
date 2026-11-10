"""Manual documentation: object descriptions, free documents, relationships and attachments."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user, require_admin
from app.api.routes.admin import _read_limited
from app.db.session import get_db
from app.models.manual import ManualAttachment, ManualDescription, ManualDocument
from app.models.system import User
from app.services import manual as svc
from app.services import search as search_service

router = APIRouter(prefix="/manual", tags=["manual"])


def _done(db: Session) -> None:
    db.commit()
    search_service.rebuild(db)
    db.commit()


def _manual_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(404, str(exc).strip("'\""))
    return HTTPException(422, str(exc))


@router.get("/meta")
def meta(_: User = Depends(get_current_user)) -> dict:
    return {"object_types": sorted(svc.OBJECT_TYPES), "document_categories": list(svc.DOCUMENT_CATEGORIES),
            "relations": list(svc.RELATIONS), "attachment_types": sorted(svc.ATTACHMENT_TYPES)}


# ------------------------------------------------------------------ descriptions


class DescriptionIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=50_000)
    location: str | None = Field(default=None, max_length=255)
    responsible: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=50_000)
    tags: list[str] | None = None
    site_id: str | None = Field(default=None, max_length=64)


@router.get("/descriptions")
def list_descriptions(object_type: str | None = None, db: Session = Depends(get_db),
                      _: User = Depends(get_current_user)) -> list[dict]:
    stmt = select(ManualDescription)
    if object_type:
        stmt = stmt.where(ManualDescription.object_type == object_type)
    return [svc.description_dict(m) for m in db.scalars(stmt.order_by(ManualDescription.updated_at.desc())).all()]


@router.put("/descriptions/{object_type}/{object_key:path}")
def put_description(object_type: str, object_key: str, body: DescriptionIn, request: Request,
                    db: Session = Depends(get_db), user: User = Depends(require_admin)) -> dict:
    try:
        m = svc.upsert_description(db, user, object_type, object_key, body.model_dump(exclude={"site_id"}),
                                   body.site_id, client_ip(request))
    except svc.ManualError as exc:
        raise _manual_error(exc) from exc
    _done(db)
    return svc.description_dict(m)


@router.delete("/descriptions/{object_type}/{object_key:path}")
def remove_description(object_type: str, object_key: str, request: Request, db: Session = Depends(get_db),
                       user: User = Depends(require_admin)) -> dict:
    if not svc.delete_description(db, user, object_type, object_key, client_ip(request)):
        raise HTTPException(404, "No description found")
    _done(db)
    return {"ok": True}


# ------------------------------------------------------------------ relationships


class RelationshipIn(BaseModel):
    source_type: str
    source_key: str = Field(max_length=255)
    target_type: str
    target_key: str = Field(max_length=255)
    relation: str = "related"
    description: str | None = Field(default=None, max_length=2000)


@router.get("/relationships")
def get_relationships(object_type: str, object_key: str, db: Session = Depends(get_db),
                      _: User = Depends(get_current_user)) -> list[dict]:
    return svc.relationships_for(db, object_type, object_key)


@router.post("/relationships")
def create_relationship(body: RelationshipIn, request: Request, db: Session = Depends(get_db),
                        user: User = Depends(require_admin)) -> dict:
    try:
        r = svc.add_relationship(db, user, body.model_dump(), client_ip(request))
    except svc.ManualError as exc:
        raise _manual_error(exc) from exc
    _done(db)
    return svc.relationship_dict(r)


@router.delete("/relationships/{rel_id}")
def remove_relationship(rel_id: int, request: Request, db: Session = Depends(get_db),
                        user: User = Depends(require_admin)) -> dict:
    if not svc.delete_relationship(db, user, rel_id, client_ip(request)):
        raise HTTPException(404, "Relationship not found")
    _done(db)
    return {"ok": True}


# ------------------------------------------------------------------ documents


class DocumentIn(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    body: str | None = Field(default=None, max_length=200_000)
    category: str | None = None
    tags: list[str] | None = None
    relationships: list[dict[str, Any]] | None = None


@router.get("/documents")
def list_documents(category: str | None = None, q: str | None = Query(None, max_length=200),
                   db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> list[dict]:
    stmt = select(ManualDocument)
    if category:
        stmt = stmt.where(ManualDocument.category == category)
    if q:
        like = f"%{search_service._escape_like(q.lower())}%"
        stmt = stmt.where(or_(ManualDocument.title.ilike(like, escape="\\"),
                              ManualDocument.body.ilike(like, escape="\\")))
    return [svc.document_dict(d, full=False) for d in
            db.scalars(stmt.order_by(ManualDocument.updated_at.desc())).all()]


@router.post("/documents")
def create_document(body: DocumentIn, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)) -> dict:
    try:
        d = svc.create_document(db, user, body.model_dump(exclude_none=True), client_ip(request))
    except svc.ManualError as exc:
        raise _manual_error(exc) from exc
    _done(db)
    return svc.document_dict(d, db)


@router.get("/documents/{doc_id}")
def get_document(doc_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> dict:
    d = db.get(ManualDocument, doc_id)
    if d is None:
        raise HTTPException(404, "Document not found")
    return svc.document_dict(d, db)


@router.put("/documents/{doc_id}")
def update_document(doc_id: int, body: DocumentIn, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)) -> dict:
    try:
        d = svc.update_document(db, user, doc_id, body.model_dump(exclude_none=True, exclude={"relationships"}),
                                client_ip(request))
    except (svc.ManualError, LookupError) as exc:
        raise _manual_error(exc) from exc
    _done(db)
    return svc.document_dict(d, db)


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)) -> dict:
    if not svc.delete_document(db, user, doc_id, client_ip(request)):
        raise HTTPException(404, "Document not found")
    _done(db)
    return {"ok": True}


# ------------------------------------------------------------------ attachments


@router.post("/documents/{doc_id}/attachments")
async def upload_attachment(doc_id: int, request: Request, file: UploadFile = File(...),
                            db: Session = Depends(get_db), user: User = Depends(require_admin)) -> dict:
    content = await _read_limited(file)
    try:
        a = svc.add_attachment(db, user, doc_id, file.filename or "file", content, client_ip(request))
    except (svc.ManualError, LookupError) as exc:
        raise _manual_error(exc) from exc
    db.commit()
    return svc.attachment_dict(a)


@router.get("/attachments/{att_id}")
def download_attachment(att_id: int, inline: bool = False, db: Session = Depends(get_db),
                        _: User = Depends(get_current_user)) -> FileResponse:
    a = db.get(ManualAttachment, att_id)
    if a is None:
        raise HTTPException(404, "Attachment not found")
    try:
        path = svc.attachment_path(a)
    except (ValueError, OSError) as exc:
        raise HTTPException(404, "Attachment file missing") from exc
    if not path.is_file():
        raise HTTPException(404, "Attachment file missing")
    # Only images and PDFs may be shown inline; everything else is forced to download.
    show_inline = inline and a.content_type in ("image/png", "image/jpeg", "image/gif", "image/webp",
                                                "application/pdf")
    return FileResponse(path, media_type=a.content_type, filename=a.filename,
                        content_disposition_type="inline" if show_inline else "attachment",
                        headers={"X-Content-Type-Options": "nosniff",
                                 "Content-Security-Policy": "default-src 'none'; sandbox"})


@router.delete("/attachments/{att_id}")
def delete_attachment(att_id: int, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(require_admin)) -> dict:
    if not svc.delete_attachment(db, user, att_id, client_ip(request)):
        raise HTTPException(404, "Attachment not found")
    db.commit()
    return {"ok": True}
