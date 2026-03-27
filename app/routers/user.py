from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user
from app.models.models import User, Usage, Wallet, Transaction
from app.routers.settings import get_setting
from datetime import datetime

router = APIRouter()

def _reset_usage_if_new_month(db: Session, usage: Usage):
    current_month = datetime.now().strftime("%Y-%m")
    if usage.month_year != current_month:
        usage.banners_used  = 0
        usage.audio_used    = 0
        usage.video_seconds = 0
        usage.month_year    = current_month
        db.commit()

@router.get("/profile")
def get_profile(user: User = Depends(get_current_user)):
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
    free_banners = int(get_setting(db, "FREE_BANNERS_PER_MONTH"))
    free_audio   = int(get_setting(db, "FREE_AUDIO_PER_MONTH"))
    free_vid_sec = int(get_setting(db, "FREE_VIDEO_SECONDS"))
    free_aud_sec = int(get_setting(db, "FREE_AUDIO_SECONDS"))
    return {
        "banners_used":        usage.banners_used,
        "banners_free_left":   max(0, free_banners - usage.banners_used),
        "banners_limit":       free_banners,
        "audio_used":          usage.audio_used,
        "audio_free_left":     max(0, free_audio - usage.audio_used),
        "audio_limit":         free_audio,
        "video_seconds_used":  usage.video_seconds,
        "video_free_left_sec": max(0, free_vid_sec - usage.video_seconds),
        "free_video_seconds":  free_vid_sec,
        "free_audio_seconds":  free_aud_sec,
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
        {"id": t.id, "amount": t.amount,
         "description": t.description, "date": t.created_at}
        for t in txs
    ]}
