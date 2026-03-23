import os
import httpx
import base64
import asyncio
from typing import Optional

HF_TOKEN = os.getenv("HF_TOKEN", "")   # Free from huggingface.co

# Hugging Face Inference API endpoints (all free tier)
HF_BASE        = "https://api-inference.huggingface.co/models"
SDXL_MODEL     = "stabilityai/stable-diffusion-xl-base-1.0"
TTS_MODEL      = "espnet/kan-bayashi_ljspeech_vits"
TEXT_MODEL     = "mistralai/Mistral-7B-Instruct-v0.2"
TRANSLATE_MODEL = "Helsinki-NLP/opus-mt-en-{lang}"

HEADERS = {"Authorization": f"Bearer {HF_TOKEN}"}

async def _hf_post(model: str, payload: dict, timeout: int = 60) -> httpx.Response:
    url = f"{HF_BASE}/{model}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, headers=HEADERS, json=payload)
    return resp

# ─── TEXT / SCRIPT GENERATION ───────────────────────────────────────────────

async def generate_marketing_text(product_name: str, ad_type: str, language: str = "en") -> str:
    prompt = f"""You are a professional marketing copywriter.
Write a compelling {ad_type} ad for: {product_name}
Keep it under 100 words. Be persuasive and clear.
Respond ONLY with the ad copy, nothing else."""
    try:
        resp = await _hf_post(TEXT_MODEL, {
            "inputs": f"<s>[INST] {prompt} [/INST]",
            "parameters": {"max_new_tokens": 150, "temperature": 0.7}
        })
        if resp.status_code == 200:
            data = resp.json()
            text = data[0]["generated_text"] if isinstance(data, list) else str(data)
            # Clean up the [/INST] prefix HF sometimes returns
            if "[/INST]" in text:
                text = text.split("[/INST]")[-1].strip()
            return text
    except Exception:
        pass
    return f"Discover {product_name} — quality you can trust. Get yours today!"

async def translate_text(text: str, target_lang: str) -> str:
    if target_lang in ("en", "english", ""):
        return text
    lang_code = target_lang[:2].lower()
    model = TRANSLATE_MODEL.format(lang=lang_code)
    try:
        resp = await _hf_post(model, {"inputs": text}, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data:
                return data[0].get("translation_text", text)
    except Exception:
        pass
    return text   # fallback: return original

# ─── BANNER IMAGE GENERATION ─────────────────────────────────────────────────

async def generate_banner_image(
    product_name: str,
    slogan: str,
    style: str = "corporate",
    aspect_ratio: str = "square"
) -> Optional[bytes]:
    style_prompts = {
        "corporate": "professional corporate advertisement, clean design, business style",
        "fun":       "colorful fun energetic advertisement, vibrant colors, playful",
        "minimal":   "minimalist elegant advertisement, white space, clean typography",
        "luxury":    "luxury premium advertisement, gold accents, sophisticated elegant",
        "custom":    "creative modern advertisement, eye-catching design",
    }
    sizes = {
        "square":    (1024, 1024),
        "facebook":  (1200, 630),
        "instagram": (1080, 1080),
        "story":     (1080, 1920),
        "youtube":   (1280, 720),
        "tiktok":    (1080, 1920),
    }
    style_desc = style_prompts.get(style.lower(), style_prompts["corporate"])
    w, h = sizes.get(aspect_ratio.lower(), (1024, 1024))
    prompt = (
        f"{style_desc}, product advertisement for {product_name}, "
        f"text overlay '{slogan}', high quality, professional marketing banner, "
        f"sharp text, vivid colors, commercial photography style"
    )
    try:
        resp = await _hf_post(SDXL_MODEL, {
            "inputs": prompt,
            "parameters": {"width": min(w, 1024), "height": min(h, 1024), "num_inference_steps": 25}
        }, timeout=120)
        if resp.status_code == 200:
            return resp.content   # raw image bytes (PNG)
    except Exception:
        pass
    return None

# ─── AUDIO / TTS GENERATION ──────────────────────────────────────────────────

async def generate_audio(script: str, voice: str = "female") -> Optional[bytes]:
    # HF TTS models return audio bytes directly
    try:
        resp = await _hf_post(TTS_MODEL, {"inputs": script[:500]}, timeout=60)
        if resp.status_code == 200:
            return resp.content   # raw audio bytes (wav/flac)
    except Exception:
        pass
    return None

# ─── CLOUDINARY UPLOAD ────────────────────────────────────────────────────────

CLOUDINARY_URL    = os.getenv("CLOUDINARY_URL", "")
CLOUDINARY_PRESET = os.getenv("CLOUDINARY_UPLOAD_PRESET", "skillsym")
CLOUDINARY_NAME   = os.getenv("CLOUDINARY_CLOUD_NAME", "")

async def upload_to_cloudinary(file_bytes: bytes, resource_type: str = "image", filename: str = "ad") -> Optional[str]:
    if not CLOUDINARY_NAME:
        # Fallback: return base64 data URL if no Cloudinary configured
        b64 = base64.b64encode(file_bytes).decode()
        mime = "image/png" if resource_type == "image" else "audio/wav"
        return f"data:{mime};base64,{b64}"
    try:
        b64_data = base64.b64encode(file_bytes).decode()
        upload_url = f"https://api.cloudinary.com/v1_1/{CLOUDINARY_NAME}/{resource_type}/upload"
        payload = {"file": f"data:image/png;base64,{b64_data}", "upload_preset": CLOUDINARY_PRESET}
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(upload_url, data=payload)
        if resp.status_code == 200:
            return resp.json().get("secure_url")
    except Exception:
        pass
    return None
