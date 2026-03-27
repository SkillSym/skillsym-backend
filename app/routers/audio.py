from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.auth import get_current_user
from app.models.models import User, Usage, Wallet, Transaction, GenerationJob
from app.ai_service import generate_audio, generate_marketing_text, translate_text, upload_to_cloudinary
from app.routers.user import _reset_usage_if_new_month
from app.routers.settings import get_setting

router = APIRouter()

def calc_audio_cost(db: Session, seconds: int) -> float:
    free_sec = int(get_setting(db, "FREE_AUDIO_SECONDS"))
    if seconds <= free_sec:
        return 0.0
    elif seconds <= 30:
        return float(get_setting(db, "AUDIO_PRICE_30SEC"))
    elif seconds <= 40:
        return float(get_setting(db, "AUDIO_PRICE_40SEC"))
    else:
        return float(get_setting(db, "AUDIO_PRICE_60SEC"))

class GenerateAudioRequest(BaseModel):
    script:       str = ""
    product_name: str = ""
    voice:        str = "female_formal"
    language:     str = "en"
    duration_sec: int = 20

class SuggestScriptRequest(BaseModel):
    product_name: str

@router.get("/voices")
def get_voices():
    return {"voices": [
        {"id": "female_formal",    "name": "Female Formal"},
        {"id": "male_formal",      "name": "Male Formal"},
        {"id": "female_energetic", "name": "Female Energetic"},
        {"id": "male_energetic",   "name": "Male Energetic"},
    ]}

@router.post("/suggest-script")
async def suggest_script(data: SuggestScriptRequest, user: User = Depends(get_current_user)):
    script = await generate_marketing_text(data.product_name, "audio ad")
    return {"suggested_script": script}

@router.post("/generate")
async def generate_audio_ad(
    data: GenerateAudioRequest,
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db)
):
    free_limit    = int(get_setting(db, "FREE_AUDIO_PER_MONTH"))
    requested_sec = max(10, min(data.duration_sec, 60))
    cost          = calc_audio_cost(db, requested_sec)

    usage = db.query(Usage).filter(Usage.user_id == user.id).first()
    _reset_usage_if_new_month(db, usage)

    if usage.audio_used >= free_limit:
        cost = max(cost, float(get_setting(db, "AUDIO_PRICE_30SEC")))

    if cost > 0:
        wallet = db.query(Wallet).filter(Wallet.user_id == user.id).first()
        if not wallet or wallet.balance < cost:
            raise HTTPException(402, detail={
                "error":   "Insufficient credits",
                "message": f"This audio costs ${cost:.2f}. Balance: ${wallet.balance:.2f if wallet else 0}",
                "cost":    cost,
            })
        wallet.balance -= cost
        db.add(Transaction(wallet_id=wallet.id, amount=-cost,
                           description=f"Audio ad {requested_sec}sec"))
        if usage.audio_used >= free_limit:
            usage.audio_used = 0
        db.commit()

    script = data.script
    if not script and data.product_name:
        script = await generate_marketing_text(data.product_name, "audio ad")
    if not script:
        raise HTTPException(400, "Please provide script or product name")

    max_words = int(requested_sec * 2.5)
    words = script.split()
    if len(words) > max_words:
        script = " ".join(words[:max_words])

    if data.language not in ("en", "english"):
        script = await translate_text(script, data.language)

    job = GenerationJob(user_id=user.id, job_type="audio", status="processing",
                        prompt=script, style=data.voice, language=data.language,
                        duration_sec=requested_sec, cost=cost)
    db.add(job)
    db.commit()
    db.refresh(job)

    audio_bytes = await generate_audio(script, data.voice)
    if audio_bytes:
        url = await upload_to_cloudinary(audio_bytes, "video", f"audio_{job.id}")
        db.query(GenerationJob).filter(GenerationJob.id == job.id).update(
            {"status": "done", "result_url": url})
        usage.audio_used += 1
        db.commit()
        return {
            "status":          "done",
            "job_id":          job.id,
            "audio_url":       url,
            "cost":            cost,
            "audio_remaining": max(0, free_limit - usage.audio_used),
        }
    db.query(GenerationJob).filter(GenerationJob.id == job.id).update({"status": "failed"})
    db.commit()
    raise HTTPException(500, "Audio generation failed. Try again.")
