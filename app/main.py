from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, user, banner, audio, video, payment, admin, settings
from app.database import engine, Base

# Create all database tables automatically
Base.metadata.create_all(bind=engine)

app = FastAPI(title="SkillSym AI API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,     prefix="/api/auth",     tags=["Auth"])
app.include_router(user.router,     prefix="/api/user",     tags=["User"])
app.include_router(banner.router,   prefix="/api/banner",   tags=["Banner"])
app.include_router(audio.router,    prefix="/api/audio",    tags=["Audio"])
app.include_router(video.router,    prefix="/api/video",    tags=["Video"])
app.include_router(payment.router,  prefix="/api/payment",  tags=["Payment"])
app.include_router(admin.router,    prefix="/api/admin",    tags=["Admin"])
app.include_router(settings.router, prefix="/api/settings", tags=["Settings"])

@app.get("/")
def root():
    return {"message": "SkillSym AI API is running", "version": "1.0.0"}

@app.get("/health")
def health():
    return {"status": "ok"}
