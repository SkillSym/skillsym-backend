import os
import httpx
import base64
from typing import Optional

HF_TOKEN = os.getenv("HF_TOKEN", "")
HF_BASE  = "https://api-inference.huggingface.co/models"
SDXL_MODEL  = "stabilityai/stable-diffusion-xl-base-1.0"
TTS_MODEL   = "espnet/kan-bayashi_ljspeech_vits"
TEXT_MODEL  = "mistralai/Mistral-7B-Instruct-v0.2"
HEADERS = {"Authorization": f"Bearer {HF_TOKEN}"}

CLOUDINARY_NAME   = os.getenv("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_PRESET = os.getenv("CLOUDINARY_UPLOAD_PRESET", "skillsym")

async def _hf_post(model: str, payload: dict, timeout: int = 120) -> httpx.Response:
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.post(f"{HF_BASE}/{model}", headers=HEADERS, json=payload)

async def generate_marketing_text(product_name: str, ad_type: str, language: str = "en") -> str:
    prompt = f"Write a short compelling {ad_type} for: {product_name}. Under 80 words. Only the ad copy."
    try:
        resp = await _hf_post(TEXT_MODEL, {
            "inputs": f"<s>[INST] {prompt} [/INST]",
            "parameters": {"max_new_tokens": 120, "temperature": 0.7}
        })
        if resp.status_code == 200:
            data = resp.json()
            text = data[0]["generated_text"] if isinstance(data, list) else str(data)
            if "[/INST]" in text:
                text = text.split("[/INST]")[-1].strip()
            return text
    except Exception:
        pass
    return f"Discover {product_name} — quality you can trust. Get yours today!"

async def translate_text(text: str, target_lang: str) -> str:
    if target_lang in ("en", "english", ""):
        return text
    model = f"Helsinki-NLP/opus-mt-en-{target_lang[:2].lower()}"
    try:
        resp = await _hf_post(model, {"inputs": text}, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data:
                return data[0].get("translation_text", text)
    except Exception:
        pass
    return text

async def generate_banner_image(product_name: str, slogan: str,
                                 style: str = "corporate",
                                 aspect_ratio: str = "square") -> Optional[bytes]:
    style_map = {
        "corporate": "professional corporate advertisement, clean business design",
        "fun":       "colorful fun energetic advertisement, vibrant playful",
        "minimal":   "minimalist elegant advertisement, white space, clean",
        "luxury":    "luxury premium advertisement, gold accents, sophisticated",
        "custom":    "creative modern advertisement, eye-catching",
    }
    prompt = (
        f"{style_map.get(style, style_map['corporate'])}, "
        f"product advertisement for {product_name}, text '{slogan}', "
        f"high quality commercial photography, sharp vivid colors"
    )
    try:
        resp = await _hf_post(SDXL_MODEL, {
            "inputs": prompt,
            "parameters": {"num_inference_steps": 20}
        })
        if resp.status_code == 200:
            return resp.content
    except Exception:
        pass
    return None

async def generate_audio(script: str, voice: str = "female_formal") -> Optional[bytes]:
    try:
        resp = await _hf_post(TTS_MODEL, {"inputs": script[:500]})
        if resp.status_code == 200:
            return resp.content
    except Exception:
        pass
    return None

async def upload_to_cloudinary(file_bytes: bytes, resource_type: str = "image",
                                filename: str = "ad") -> Optional[str]:
    if not CLOUDINARY_NAME:
        b64 = base64.b64encode(file_bytes).decode()
        mime = "image/png" if resource_type == "image" else "audio/wav"
        return f"data:{mime};base64,{b64}"
    try:
        b64_data = base64.b64encode(file_bytes).decode()
        upload_url = f"https://api.cloudinary.com/v1_1/{CLOUDINARY_NAME}/{resource_type}/upload"
        payload = {
            "file": f"data:image/png;base64,{b64_data}",
            "upload_preset": CLOUDINARY_PRESET
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(upload_url, data=payload)
        if resp.status_code == 200:
            return resp.json().get("secure_url")
    except Exception:
        pass
    return None
