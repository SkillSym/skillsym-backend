from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Dict
from app.database import get_db
from app.auth import get_current_user, require_admin
from app.models.models import Settings, User
from app.models.settings import DEFAULT_SETTINGS

router = APIRouter()

def get_setting(db: Session, key: str) -> str:
    row = db.query(Settings).filter(Settings.key == key).first()
    return row.value if row else DEFAULT_SETTINGS.get(key, "0")

def get_all_settings(db: Session) -> dict:
    rows = db.query(Settings).all()
    result = dict(DEFAULT_SETTINGS)
    for row in rows:
        result[row.key] = row.value
    return result

def set_setting(db: Session, key: str, value: str):
    row = db.query(Settings).filter(Settings.key == key).first()
    if row:
        row.value = value
    else:
        db.add(Settings(key=key, value=value))
    db.commit()

class UpdateSettingsRequest(BaseModel):
    settings: Dict[str, str]

@router.get("/")
def read_settings(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return {"settings": get_all_settings(db)}

@router.post("/")
def update_settings(
    data:  UpdateSettingsRequest,
    db:    Session = Depends(get_db),
    admin: User    = Depends(require_admin)
):
    allowed = set(DEFAULT_SETTINGS.keys())
    updated = []
    for key, value in data.settings.items():
        if key in allowed:
            set_setting(db, key, value)
            updated.append(key)
    return {"success": True, "updated": updated}

@router.post("/reset")
def reset_settings(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    db.query(Settings).delete()
    db.commit()
    return {"success": True, "message": "Reset to defaults"}
