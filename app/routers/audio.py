from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.auth import get_current_user
from app.models.models import User, Usage, Wallet, Transaction, GenerationJob
from app.ai_service import generate_audio, generate_marketing_text, translate_text, upload_to_cloudinary
from app.routers.user import FREE_AUDIO_PER_MONTH, _reset_usage_if_new_month

router = APIRouter()

FREE_MAX_SECONDS = 45

VOICES = [
    {"id": "female_formal",    "name": "Female – Formal"},
    {"id": "male_formal",      "name": "Male – Formal"},
    {"id": "female_energetic", "name": "Female – Energetic"},
    {"id": "male_energetic",   "name": "Male – Energetic"},
    {"id": "female_fun",       "name": "Female – Fun"},
]

class GenerateAudioRequest(BaseModel):
    script:       str = ""
    product_name: str = ""
    voice:        str = "female_formal"
    language:     str = "en"
    background_music: bool = False

class SuggestScriptRequest(BaseModel):
    product_name: str
    tone: str = "professional"

@router.get("/voices")
def get_voices():
    return {"voices": VOICES}

@router.post("/suggest-script")
async def suggest_script(data: SuggestScriptRequest, user: User = Depends(get_current_user)):
    script = await generate_marketing_text(data.product_name, f"audio ad with {data.tone} tone")
    return {"suggested_script": script}

@router.post("/generate")
async def generate_audio_ad(
    data: GenerateAudioRequest,
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db)
):
    usage = db.query(Usage).filter(Usage.user_id == user.id).first()
    _reset_usage_if_new_month(db, usage)

    audio_free_left = FREE_AUDIO_PER_MONTH - usage.audio_used
    cost = 0.0

    if audio_free_left <= 0:
        wallet = db.query(Wallet).filter(Wallet.user_id == user.id).first()
        if not wallet or wallet.balance < 1.0:
            raise HTTPException(402, detail={
                "error": "Free limit reached",
                "message": "30 free audio ads used. Add $1 for 30 more.",
                "audio_used": usage.audio_used,
            })
        wallet.balance -= 1.0
        cost = 1.0
        db.add(Transaction(wallet_id=wallet.id, amount=-1.0, description="30 extra audio ads pack"))
        usage.audio_used = 0
        db.commit()

    # Prepare script
    script = data.script
    if not script and data.product_name:
        script = await generate_marketing_text(data.product_name, "audio ad")
    if not script:
        raise HTTPException(400, "Please provide a script or product name")

    # Keep free version under 45 sec (roughly 150 words)
    words = script.split()
    if cost == 0.0 and len(words) > 110:   # ~110 words ≈ 45 sec at normal pace
        script = " ".join(words[:110])

    if data.language not in ("en", "english"):
        script = await translate_text(script, data.language)

    job = GenerationJob(
        user_id=user.id, job_type="audio", status="processing",
        prompt=script, style=data.voice, language=data.language, cost=cost
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    audio_bytes = await generate_audio(script, data.voice)

    if audio_bytes:
        url = await upload_to_cloudinary(audio_bytes, "video", f"audio_{job.id}")  # Cloudinary uses 'video' for audio
        db.query(GenerationJob).filter(GenerationJob.id == job.id).update(
            {"status": "done", "result_url": url}
        )
        usage.audio_used += 1
        db.commit()
        return {
            "status":       "done",
            "job_id":       job.id,
            "audio_url":    url,
            "cost":         cost,
            "audio_remaining": max(0, FREE_AUDIO_PER_MONTH - usage.audio_used),
        }
    else:
        db.query(GenerationJob).filter(GenerationJob.id == job.id).update({"status": "failed"})
        db.commit()
        raise HTTPException(500, "Audio generation failed. Please try again.")
