from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.auth import get_current_user
from app.models.models import User, Usage, Wallet, Transaction, GenerationJob
from app.ai_service import generate_banner_image, generate_marketing_text, translate_text, upload_to_cloudinary
from app.routers.user import FREE_BANNERS_PER_MONTH, _reset_usage_if_new_month
from datetime import datetime

router = APIRouter()

BANNER_TEMPLATES = [
    {"id": "corporate", "name": "Corporate",  "description": "Professional business look"},
    {"id": "fun",       "name": "Fun",         "description": "Colorful and energetic"},
    {"id": "minimal",   "name": "Minimal",     "description": "Clean and elegant"},
    {"id": "luxury",    "name": "Luxury",      "description": "Premium gold accents"},
    {"id": "custom",    "name": "Custom",      "description": "Your own style"},
]

ASPECT_RATIOS = [
    {"id": "facebook",  "name": "Facebook",    "size": "1200×630"},
    {"id": "instagram", "name": "Instagram",   "size": "1080×1080"},
    {"id": "youtube",   "name": "YouTube",     "size": "1280×720"},
    {"id": "tiktok",    "name": "TikTok",      "size": "1080×1920"},
    {"id": "square",    "name": "Square",      "size": "1024×1024"},
]

class GenerateBannerRequest(BaseModel):
    product_name: str
    slogan:       str = ""
    description:  str = ""
    style:        str = "corporate"
    aspect_ratio: str = "square"
    language:     str = "en"

class SuggestTextRequest(BaseModel):
    product_name: str
    ad_type:      str = "banner"

@router.get("/templates")
def get_templates():
    return {"templates": BANNER_TEMPLATES, "aspect_ratios": ASPECT_RATIOS}

@router.post("/suggest-text")
async def suggest_text(data: SuggestTextRequest, user: User = Depends(get_current_user)):
    text = await generate_marketing_text(data.product_name, data.ad_type)
    return {"suggested_text": text}

@router.post("/generate")
async def generate_banner(
    data:       GenerateBannerRequest,
    background: BackgroundTasks,
    user:       User    = Depends(get_current_user),
    db:         Session = Depends(get_db)
):
    # 1. Check / reset usage
    usage = db.query(Usage).filter(Usage.user_id == user.id).first()
    _reset_usage_if_new_month(db, usage)

    banners_free_left = FREE_BANNERS_PER_MONTH - usage.banners_used
    cost = 0.0

    # 2. Charge wallet if over free limit (every 30 = $1)
    if banners_free_left <= 0:
        wallet = db.query(Wallet).filter(Wallet.user_id == user.id).first()
        if not wallet or wallet.balance < 1.0:
            raise HTTPException(402, detail={
                "error": "Free limit reached",
                "message": "You've used your 30 free banners this month. Add $1 to generate 30 more.",
                "banners_used": usage.banners_used,
            })
        # Deduct $1 and reset paid counter in groups of 30
        wallet.balance -= 1.0
        cost = 1.0
        tx = Transaction(wallet_id=wallet.id, amount=-1.0, description="30 extra banner ads pack")
        db.add(tx)
        # Reset counter for next 30
        usage.banners_used = 0
        db.commit()

    # 3. Create job record
    job = GenerationJob(
        user_id=user.id, job_type="banner", status="processing",
        prompt=f"{data.product_name}: {data.slogan}",
        style=data.style, language=data.language, cost=cost
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    job_id = job.id

    # 4. Translate slogan if needed
    slogan = data.slogan or await generate_marketing_text(data.product_name, "banner", data.language)
    if data.language not in ("en", "english"):
        slogan = await translate_text(slogan, data.language)

    # 5. Generate image
    img_bytes = await generate_banner_image(data.product_name, slogan, data.style, data.aspect_ratio)

    if img_bytes:
        url = await upload_to_cloudinary(img_bytes, "image", f"banner_{job_id}")
        db.query(GenerationJob).filter(GenerationJob.id == job_id).update(
            {"status": "done", "result_url": url}
        )
        usage.banners_used += 1
        db.commit()
        return {
            "status": "done",
            "job_id": job_id,
            "image_url": url,
            "cost": cost,
            "banners_remaining": max(0, FREE_BANNERS_PER_MONTH - usage.banners_used),
        }
    else:
        db.query(GenerationJob).filter(GenerationJob.id == job_id).update({"status": "failed"})
        db.commit()
        raise HTTPException(500, "AI generation failed. Please try again in a moment.")
