from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user
from app.models.models import User, Usage, Wallet, Transaction
from datetime import datetime

router = APIRouter()

FREE_BANNERS_PER_MONTH = 30
FREE_AUDIO_PER_MONTH   = 30
FREE_VIDEO_SECONDS     = 45

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
    return {
        "banners_used":      usage.banners_used,
        "banners_free_left": max(0, FREE_BANNERS_PER_MONTH - usage.banners_used),
        "audio_used":        usage.audio_used,
        "audio_free_left":   max(0, FREE_AUDIO_PER_MONTH - usage.audio_used),
        "video_seconds_used": usage.video_seconds,
        "video_free_left_sec": max(0, FREE_VIDEO_SECONDS - usage.video_seconds),
        "month": usage.month_year,
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
