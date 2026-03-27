from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.auth import get_current_user
from app.models.models import User, Usage, Wallet, Transaction, GenerationJob
from app.ai_service import generate_banner_image, generate_marketing_text, translate_text, upload_to_cloudinary
from app.routers.user import _reset_usage_if_new_month
from app.routers.settings import get_setting

router = APIRouter()

class GenerateBannerRequest(BaseModel):
    product_name: str
    slogan:       str = ""
    style:        str = "corporate"
    aspect_ratio: str = "square"
    language:     str = "en"

class SuggestTextRequest(BaseModel):
    product_name: str
    ad_type:      str = "banner"

@router.get("/templates")
def get_templates():
    return {
        "templates": [
            {"id": "corporate", "name": "Corporate"},
            {"id": "fun",       "name": "Fun"},
            {"id": "minimal",   "name": "Minimal"},
            {"id": "luxury",    "name": "Luxury"},
            {"id": "custom",    "name": "Custom"},
        ],
        "aspect_ratios": [
            {"id": "square",    "name": "Square",    "size": "1024x1024"},
            {"id": "facebook",  "name": "Facebook",  "size": "1200x630"},
            {"id": "instagram", "name": "Instagram", "size": "1080x1080"},
            {"id": "youtube",   "name": "YouTube",   "size": "1280x720"},
            {"id": "tiktok",    "name": "TikTok",    "size": "1080x1920"},
        ]
    }

@router.post("/suggest-text")
async def suggest_text(data: SuggestTextRequest, user: User = Depends(get_current_user)):
    text = await generate_marketing_text(data.product_name, data.ad_type)
    return {"suggested_text": text}

@router.post("/generate")
async def generate_banner(
    data: GenerateBannerRequest,
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db)
):
    free_limit = int(get_setting(db, "FREE_BANNERS_PER_MONTH"))
    pack_price = float(get_setting(db, "BANNER_PRICE_PER_PACK"))
    pack_size  = int(get_setting(db, "BANNER_PACK_SIZE"))

    usage = db.query(Usage).filter(Usage.user_id == user.id).first()
    _reset_usage_if_new_month(db, usage)

    cost = 0.0
    if usage.banners_used >= free_limit:
        wallet = db.query(Wallet).filter(Wallet.user_id == user.id).first()
        if not wallet or wallet.balance < pack_price:
            raise HTTPException(402, detail={
                "error":   "Free limit reached",
                "message": f"You used your {free_limit} free banners. Add ${pack_price} for {pack_size} more.",
            })
        wallet.balance -= pack_price
        cost = pack_price
        db.add(Transaction(wallet_id=wallet.id, amount=-pack_price,
                           description=f"{pack_size} extra banners pack"))
        usage.banners_used = 0
        db.commit()

    job = GenerationJob(user_id=user.id, job_type="banner", status="processing",
                        prompt=data.product_name, style=data.style,
                        language=data.language, cost=cost)
    db.add(job)
    db.commit()
    db.refresh(job)

    slogan = data.slogan or await generate_marketing_text(data.product_name, "banner")
    if data.language not in ("en", "english"):
        slogan = await translate_text(slogan, data.language)

    img_bytes = await generate_banner_image(data.product_name, slogan, data.style, data.aspect_ratio)

    if img_bytes:
        url = await upload_to_cloudinary(img_bytes, "image", f"banner_{job.id}")
        db.query(GenerationJob).filter(GenerationJob.id == job.id).update(
            {"status": "done", "result_url": url})
        usage.banners_used += 1
        db.commit()
        return {
            "status":            "done",
            "job_id":            job.id,
            "image_url":         url,
            "cost":              cost,
            "banners_remaining": max(0, free_limit - usage.banners_used),
        }
    db.query(GenerationJob).filter(GenerationJob.id == job.id).update({"status": "failed"})
    db.commit()
    raise HTTPException(500, "Generation failed. Please try again.")
