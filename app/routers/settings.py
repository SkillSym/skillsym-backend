from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Dict
from app.database import get_db
from app.auth import get_current_user, require_admin
from app.models.settings import Settings, DEFAULT_SETTINGS
from app.models.models import User

router = APIRouter()

def get_setting(db: Session, key: str) -> str:
    """Get a setting value, return default if not set"""
    row = db.query(Settings).filter(Settings.key == key).first()
    if row:
        return row.value
    return DEFAULT_SETTINGS.get(key, "0")

def get_all_settings(db: Session) -> dict:
    """Get all settings as a dictionary"""
    rows = db.query(Settings).all()
    result = dict(DEFAULT_SETTINGS)  # start with defaults
    for row in rows:
        result[row.key] = row.value
    return result

def set_setting(db: Session, key: str, value: str):
    """Save a setting to database"""
    row = db.query(Settings).filter(Settings.key == key).first()
    if row:
        row.value = value
    else:
        db.add(Settings(key=key, value=value))
    db.commit()

class UpdateSettingsRequest(BaseModel):
    settings: Dict[str, str]

@router.get("/")
def get_settings(
    db:   Session = Depends(get_db),
    user: User    = Depends(get_current_user)
):
    """Anyone logged in can read settings (needed for pricing display)"""
    all_settings = get_all_settings(db)
    return {"settings": all_settings}

@router.post("/")
def update_settings(
    data:  UpdateSettingsRequest,
    db:    Session = Depends(get_db),
    admin: User    = Depends(require_admin)
):
    """Only admin can update settings"""
    allowed_keys = set(DEFAULT_SETTINGS.keys())
    updated = []
    for key, value in data.settings.items():
        if key in allowed_keys:
            set_setting(db, key, value)
            updated.append(key)
    return {
        "success": True,
        "updated": updated,
        "message": f"Updated {len(updated)} settings successfully"
    }

@router.post("/reset")
def reset_settings(
    db:    Session = Depends(get_db),
    admin: User    = Depends(require_admin)
):
    """Reset all settings to default values"""
    db.query(Settings).delete()
    db.commit()
    return {"success": True, "message": "All settings reset to defaults"}
