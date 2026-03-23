from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import asyncio
from app.database import get_db, SessionLocal
from app.auth import get_current_user
from app.models.models import User, Usage, Wallet, Transaction, GenerationJob
from app.ai_service import generate_banner_image, generate_audio, generate_marketing_text, upload_to_cloudinary
from app.routers.user import FREE_VIDEO_SECONDS, _reset_usage_if_new_month

router = APIRouter()

VIDEO_STYLES = [
    {"id": "corporate",   "name": "Corporate",   "description": "Professional business style"},
    {"id": "fun",         "name": "Fun",          "description": "Bright and energetic"},
    {"id": "luxury",      "name": "Luxury",       "description": "Premium and elegant"},
    {"id": "social",      "name": "Social Media", "description": "Optimized for feeds"},
    {"id": "custom",      "name": "Custom",       "description": "Your own style"},
]

class GenerateVideoRequest(BaseModel):
    product_name:  str
    description:   str = ""
    cta:           str = "Buy Now"
    style:         str = "corporate"
    aspect_ratio:  str = "square"
    language:      str = "en"
    duration_sec:  int = 30   # requested duration

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
    usage = db.query(Usage).filter(Usage.user_id == user.id).first()
    _reset_usage_if_new_month(db, usage)

    # Determine cost: first 45 sec free, then $1/min
    requested_sec = max(15, min(data.duration_sec, 300))  # 15s min, 5min max
    free_sec_left = max(0, FREE_VIDEO_SECONDS - usage.video_seconds)
    paid_sec      = max(0, requested_sec - free_sec_left)
    cost = round((paid_sec / 60) * 1.0, 2)  # $1 per minute

    if cost > 0:
        wallet = db.query(Wallet).filter(Wallet.user_id == user.id).first()
        if not wallet or wallet.balance < cost:
            raise HTTPException(402, detail={
                "error": "Insufficient credits",
                "message": f"This video needs ${cost:.2f}. Your balance: ${wallet.balance:.2f}",
                "cost": cost,
                "balance": wallet.balance if wallet else 0,
            })
        wallet.balance -= cost
        db.add(Transaction(
            wallet_id=wallet.id, amount=-cost,
            description=f"Video ad {requested_sec}s ({paid_sec}s paid)"
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

    # Start background generation
    background.add_task(_generate_video_background, job.id, data, cost)

    return {
        "status":   "queued",
        "job_id":   job.id,
        "message":  "Your video is being generated. Poll /api/video/status/{job_id} for progress.",
        "cost":     cost,
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
        "job_id":    job.id,
        "status":    job.status,   # pending / processing / done / failed
        "video_url": job.result_url,
        "cost":      job.cost,
        "created_at": job.created_at,
    }

async def _generate_video_background(job_id: str, data: GenerateVideoRequest, cost: float):
    """
    Background task: generates a slideshow-style video ad.
    Since we don't have a GPU server yet, we create a multi-image slideshow
    with voiceover using only the free HF inference API.
    Full AnimateDiff video can be plugged in later when GPU is available.
    """
    db = SessionLocal()
    try:
        db.query(GenerationJob).filter(GenerationJob.id == job_id).update({"status": "processing"})
        db.commit()

        # Generate script
        script = data.description or await generate_marketing_text(data.product_name, "video ad")

        # Generate 3 scene images (slides for the video)
        scene_prompts = [
            f"product showcase for {data.product_name}, {data.style} style",
            f"lifestyle advertisement {data.product_name}, happy customers",
            f"call to action: {data.cta}, {data.product_name}, {data.style} advertisement",
        ]
        image_urls = []
        for prompt_text in scene_prompts:
            img_bytes = await generate_banner_image(data.product_name, prompt_text, data.style, data.aspect_ratio)
            if img_bytes:
                url = await upload_to_cloudinary(img_bytes, "image", f"video_frame_{job_id}")
                if url:
                    image_urls.append(url)

        # Generate voiceover
        audio_bytes = await generate_audio(script[:200])
        audio_url = None
        if audio_bytes:
            audio_url = await upload_to_cloudinary(audio_bytes, "video", f"video_audio_{job_id}")

        # Store result as JSON describing the video components
        # A real implementation would merge these with FFmpeg on a server
        # This gives users the assets; FFmpeg merge can be done on the client or a cheap VPS
        import json
        result = json.dumps({
            "type": "slideshow",
            "images": image_urls,
            "audio": audio_url,
            "script": script,
            "product": data.product_name,
            "cta": data.cta,
        })

        # Use first image as thumbnail URL for now
        result_url = image_urls[0] if image_urls else None

        db.query(GenerationJob).filter(GenerationJob.id == job_id).update({
            "status": "done",
            "result_url": result_url,
            "prompt": result,
        })

        # Update usage
        job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
        if job:
            usage = db.query(Usage).filter(Usage.user_id == job.user_id).first()  # type: ignore
            if usage:
                usage.video_seconds += data.duration_sec
        db.commit()

    except Exception as e:
        db.query(GenerationJob).filter(GenerationJob.id == job_id).update({"status": "failed"})
        db.commit()
    finally:
        db.close()
