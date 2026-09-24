from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile

from app.deps import require_admin
from app.schemas import DocumentOut, DocumentVisibility
from app.security import AuthUser
from app.services import document_service

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[DocumentOut])
def list_documents(user: AuthUser = Depends(require_admin)):
    return document_service.list_documents(user.company_id)


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: str, user: AuthUser = Depends(require_admin)):
    return document_service.get_document(user.company_id, document_id)


@router.post("", response_model=DocumentOut)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    visibility: DocumentVisibility = Form("ALL_EMPLOYEES"),
    user: AuthUser = Depends(require_admin),
):
    document = await document_service.create_upload(user.company_id, file, visibility)
    background_tasks.add_task(document_service.process_document, document.id, user.company_id)
    return document


@router.delete("/{document_id}")
def delete_document(document_id: str, user: AuthUser = Depends(require_admin)):
    document_service.delete_document(user.company_id, document_id)
    return {"ok": True}
