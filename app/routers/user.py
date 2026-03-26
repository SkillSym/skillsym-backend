from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user
from app.models.models import User, Usage, Wallet, Transaction
from app.routers.settings import get_setting
from datetime import datetime

router = APIRouter()

def get_limits(db: Session):
    return {
        "FREE_BANNERS_PER_MONTH": int(get_setting(db, "FREE_BANNERS_PER_MONTH")),
        "FREE_AUDIO_PER_MONTH":   int(get_setting(db, "FREE_AUDIO_PER_MONTH")),
        "FREE_VIDEO_PER_MONTH":   int(get_setting(db, "FREE_VIDEO_PER_MONTH")),
        "FREE_AUDIO_SECONDS":     int(get_setting(db, "FREE_AUDIO_SECONDS")),
        "FREE_VIDEO_SECONDS":     int(get_setting(db, "FREE_VIDEO_SECONDS")),
    }

def _reset_usage_if_new_month(db: Session, usage: Usage):
    current_month = datetime.now().strftime("%Y-%m")
    if usage.month_year != current_month:
        usage.banners_used  = 0
        usage.audio_used    = 0
        usage.video_seconds = 0
        usage.month_year    = current_month
        db.commit()

@router.get("/profile")
def get_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {
        "id":         user.id,
        "email":      user.email,
        "phone":      user.phone,
        "is_admin":   user.is_admin,
        "created_at": user.created_at,
    }

@router.get("/usage")
def get_usage(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    usage = db.query(Usage).filter(Usage.user_id == user.id).first()
    if not usage:
        return {}
    _reset_usage_if_new_month(db, usage)
    limits = get_limits(db)
    return {
        "banners_used":        usage.banners_used,
        "banners_free_left":   max(0, limits["FREE_BANNERS_PER_MONTH"] - usage.banners_used),
        "banners_limit":       limits["FREE_BANNERS_PER_MONTH"],
        "audio_used":          usage.audio_used,
        "audio_free_left":     max(0, limits["FREE_AUDIO_PER_MONTH"] - usage.audio_used),
        "audio_limit":         limits["FREE_AUDIO_PER_MONTH"],
        "video_seconds_used":  usage.video_seconds,
        "video_free_left_sec": max(0, limits["FREE_VIDEO_SECONDS"] - usage.video_seconds),
        "video_limit":         limits["FREE_VIDEO_PER_MONTH"],
        "free_audio_seconds":  limits["FREE_AUDIO_SECONDS"],
        "free_video_seconds":  limits["FREE_VIDEO_SECONDS"],
        "month":               usage.month_year,
    }

@router.get("/wallet")
def get_wallet(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).first()
    return {"balance": round(wallet.balance, 2) if wallet else 0.0}

@router.get("/wallet/history")
def wallet_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).first()
    if not wallet:
        return {"transactions": []}
    txs = db.query(Transaction).filter(
        Transaction.wallet_id == wallet.id
    ).order_by(Transaction.created_at.desc()).limit(50).all()
    return {"transactions": [
        {"id": t.id, "amount": t.amount, "description": t.description, "date": t.created_at}
        for t in txs
    ]}
