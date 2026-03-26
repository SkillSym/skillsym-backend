from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db, SessionLocal
from app.auth import get_current_user
from app.models.models import User, Usage, Wallet, Transaction, GenerationJob
from app.ai_service import generate_banner_image, generate_audio, generate_marketing_text, upload_to_cloudinary
from app.routers.user import _reset_usage_if_new_month
from app.routers.settings import get_setting

router = APIRouter()

def get_video_cost(db: Session, requested_seconds: int) -> float:
    """Calculate cost based on duration tiers"""
    free_sec = int(get_setting(db, "FREE_VIDEO_SECONDS"))
    if requested_seconds <= free_sec:
        return 0.0
    elif requested_seconds <= 30:
        return float(get_setting(db, "VIDEO_PRICE_30SEC"))
    elif requested_seconds <= 40:
        return float(get_setting(db, "VIDEO_PRICE_40SEC"))
    else:
        return float(get_setting(db, "VIDEO_PRICE_60SEC"))

VIDEO_STYLES = [
    {"id": "corporate", "name": "Corporate"},
    {"id": "fun",       "name": "Fun"},
    {"id": "luxury",    "name": "Luxury"},
    {"id": "social",    "name": "Social Media"},
    {"id": "custom",    "name": "Custom"},
]

class GenerateVideoRequest(BaseModel):
    product_name: str
    description:  str = ""
    cta:          str = "Buy Now"
    style:        str = "corporate"
    aspect_ratio: str = "square"
    language:     str = "en"
    duration_sec: int = 20

@router.get("/styles")
def get_styles():
    return {"styles": VIDEO_STYLES}

@router.post("/generate")
async def generate_video_ad(
    data:       GenerateVideoRequest,
    background: BackgroundTasks,
    user:       User    = Depends(get_current_user),
    db:         Session = Depends(get_db)
):
    free_limit    = int(get_setting(db, "FREE_VIDEO_PER_MONTH"))
    requested_sec = max(10, min(data.duration_sec, 60))

    usage = db.query(Usage).filter(Usage.user_id == user.id).first()
    _reset_usage_if_new_month(db, usage)

    video_free_left = free_limit - (usage.video_seconds // 20)
    cost = get_video_cost(db, requested_sec)

    if video_free_left <= 0:
        cost = max(cost, float(get_setting(db, "VIDEO_PRICE_30SEC")))

    if cost > 0:
        wallet = db.query(Wallet).filter(Wallet.user_id == user.id).first()
        if not wallet or wallet.balance < cost:
            raise HTTPException(402, detail={
                "error":   "Insufficient credits",
                "message": f"This video costs ${cost:.2f}. Your balance: ${wallet.balance:.2f if wallet else 0}",
                "cost":    cost,
                "balance": wallet.balance if wallet else 0,
            })
        wallet.balance -= cost
        db.add(Transaction(
            wallet_id=wallet.id, amount=-cost,
            description=f"Video ad {requested_sec}sec"
        ))
        db.commit()

    job = GenerationJob(
        user_id=user.id, job_type="video", status="pending",
        prompt=f"{data.product_name}: {data.description}",
        style=data.style, language=data.language,
        duration_sec=requested_sec, cost=cost
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background.add_task(_generate_video_background, job.id, data)

    return {
        "status":      "queued",
        "job_id":      job.id,
        "message":     "Video is being generated. Poll /api/video/status/{job_id} for updates.",
        "cost":        cost,
        "eta_seconds": 60 + requested_sec * 2,
    }

@router.get("/status/{job_id}")
def get_video_status(
    job_id: str,
    user:   User    = Depends(get_current_user),
    db:     Session = Depends(get_db)
):
    job = db.query(GenerationJob).filter(
        GenerationJob.id == job_id,
        GenerationJob.user_id == user.id
    ).first()
    if not job:
        raise HTTPException(404, "Job not found")
    return {
        "job_id":     job.id,
        "status":     job.status,
        "video_url":  job.result_url,
        "cost":       job.cost,
        "created_at": job.created_at,
    }

async def _generate_video_background(job_id: str, data: GenerateVideoRequest):
    db = SessionLocal()
    try:
        db.query(GenerationJob).filter(GenerationJob.id == job_id).update({"status": "processing"})
        db.commit()

        script = data.description or await generate_marketing_text(data.product_name, "video ad")

        scene_prompts = [
            f"product showcase {data.product_name} {data.style} style advertisement",
            f"lifestyle advertisement {data.product_name} happy customers",
            f"call to action {data.cta} {data.product_name} {data.style}",
        ]

        image_urls = []
        for prompt_text in scene_prompts:
            img_bytes = await generate_banner_image(data.product_name, prompt_text, data.style, data.aspect_ratio)
            if img_bytes:
                url = await upload_to_cloudinary(img_bytes, "image", f"vframe_{job_id}")
                if url:
                    image_urls.append(url)

        audio_bytes = await generate_audio(script[:200])
        audio_url = None
        if audio_bytes:
            audio_url = await upload_to_cloudinary(audio_bytes, "video", f"vaudio_{job_id}")

        import json
        result = json.dumps({
            "type":    "slideshow",
            "images":  image_urls,
            "audio":   audio_url,
            "script":  script,
            "product": data.product_name,
            "cta":     data.cta,
        })

        result_url = image_urls[0] if image_urls else None

        db.query(GenerationJob).filter(GenerationJob.id == job_id).update({
            "status":     "done",
            "result_url": result_url,
            "prompt":     result,
        })

        job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
        if job:
            usage = db.query(Usage).filter(Usage.user_id == job.user_id).first()
            if usage:
                usage.video_seconds += data.duration_sec
        db.commit()

    except Exception:
        db.query(GenerationJob).filter(GenerationJob.id == job_id).update({"status": "failed"})
        db.commit()
    finally:
        db.close()
