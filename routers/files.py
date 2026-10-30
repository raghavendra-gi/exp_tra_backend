import os
import uuid

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from deps import get_db, get_current_user
from config import settings
import models
from schemas import FileOut

router = APIRouter()

ALLOWED_TYPES = {"image/png", "image/jpeg", "application/pdf"}
MAX_BYTES = 5 * 1024 * 1024  # 5 MB, same limit as the frontend
EXT_FOR_TYPE = {"image/png": ".png", "image/jpeg": ".jpg", "application/pdf": ".pdf"}


@router.post("/upload", response_model=FileOut)
async def upload_file(
    file: UploadFile = File(...),
    field_key: str = Form(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Uploads a single receipt/photo before the expense itself is submitted -
    mirrors putBlob() into IndexedDB on the frontend. Returns a file id that
    the client attaches into expense.data[field] when it later calls
    POST /api/expenses.
    """
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Only PNG, JPG or PDF files are allowed")

    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds 5 MB limit")

    file_id = "f_" + uuid.uuid4().hex[:16]
    ext = EXT_FOR_TYPE[file.content_type]   # never trust the client-supplied file name for the extension
    disk_path = os.path.join(settings.storage_dir, f"{file_id}{ext}")
    with open(disk_path, "wb") as fh:
        fh.write(content)

    asset = models.FileAsset(
        id=file_id,
        expense_id=None,
        field_key=field_key or None,
        filename=file.filename or file_id,
        content_type=file.content_type,
        size=len(content),
        storage_path=disk_path,
        uploaded_by=current_user.username,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@router.get("/{file_id}")
def download_file(file_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    asset = db.query(models.FileAsset).filter(models.FileAsset.id == file_id).first()
    if not asset or not os.path.exists(asset.storage_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(asset.storage_path, media_type=asset.content_type, filename=asset.filename)


@router.delete("/{file_id}")
def delete_file(file_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    asset = db.query(models.FileAsset).filter(models.FileAsset.id == file_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="File not found")
    if asset.uploaded_by != current_user.username and current_user.role not in ("head", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    try:
        if os.path.exists(asset.storage_path):
            os.remove(asset.storage_path)
    except OSError:
        pass
    db.delete(asset)
    db.commit()
    return {"deleted": True}
