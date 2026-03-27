from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.models.models import User, Usage, Wallet
from app.auth import hash_password, verify_password, create_token
from datetime import datetime

router = APIRouter()

class SignupRequest(BaseModel):
    email:    str
    password: str
    phone:    str = None

class LoginRequest(BaseModel):
    email:    str
    password: str

def _init_user_data(db: Session, user: User):
    month = datetime.now().strftime("%Y-%m")
    db.add(Usage(user_id=user.id, banners_used=0, audio_used=0,
                 video_seconds=0, month_year=month))
    db.add(Wallet(user_id=user.id, balance=0.0))
    db.commit()

@router.post("/signup")
def signup(data: SignupRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(400, "Email already registered")
    if len(data.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    user = User(
        email=data.email,
        phone=data.phone,
        hashed_password=hash_password(data.password)
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _init_user_data(db, user)
    token = create_token(user.id)
    return {
        "token":    token,
        "user_id":  user.id,
        "email":    user.email,
        "is_admin": user.is_admin,
        "message":  "Account created successfully"
    }

@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(401, "Invalid email or password")
    if user.is_blocked:
        raise HTTPException(403, "Account suspended. Contact support.")
    token = create_token(user.id)
    return {
        "token":    token,
        "user_id":  user.id,
        "email":    user.email,
        "is_admin": user.is_admin
    }
