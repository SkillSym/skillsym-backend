from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid

def gen_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"
    id            = Column(String, primary_key=True, default=gen_uuid)
    email         = Column(String, unique=True, index=True, nullable=False)
    phone         = Column(String, nullable=True)
    hashed_password = Column(String, nullable=False)
    is_active     = Column(Boolean, default=True)
    is_admin      = Column(Boolean, default=False)
    is_blocked    = Column(Boolean, default=False)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())

    usage   = relationship("Usage",       back_populates="user", uselist=False)
    wallet  = relationship("Wallet",      back_populates="user", uselist=False)
    jobs    = relationship("GenerationJob", back_populates="user")

class Usage(Base):
    __tablename__ = "usage"
    id              = Column(String, primary_key=True, default=gen_uuid)
    user_id         = Column(String, ForeignKey("users.id"), unique=True)
    banners_used    = Column(Integer, default=0)
    audio_used      = Column(Integer, default=0)
    video_seconds   = Column(Integer, default=0)
    month_year      = Column(String, default="")   # e.g. "2026-03"
    user            = relationship("User", back_populates="usage")

class Wallet(Base):
    __tablename__ = "wallets"
    id           = Column(String, primary_key=True, default=gen_uuid)
    user_id      = Column(String, ForeignKey("users.id"), unique=True)
    balance      = Column(Float, default=0.0)
    user         = relationship("User", back_populates="wallet")
    transactions = relationship("Transaction", back_populates="wallet")

class Transaction(Base):
    __tablename__ = "transactions"
    id          = Column(String, primary_key=True, default=gen_uuid)
    wallet_id   = Column(String, ForeignKey("wallets.id"))
    amount      = Column(Float, nullable=False)          # positive = credit, negative = debit
    description = Column(String, nullable=False)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    wallet      = relationship("Wallet", back_populates="transactions")

class GenerationJob(Base):
    __tablename__ = "generation_jobs"
    id          = Column(String, primary_key=True, default=gen_uuid)
    user_id     = Column(String, ForeignKey("users.id"))
    job_type    = Column(String)                         # banner / audio / video
    status      = Column(String, default="pending")      # pending/processing/done/failed
    result_url  = Column(String, nullable=True)
    prompt      = Column(Text, nullable=True)
    style       = Column(String, nullable=True)
    language    = Column(String, default="en")
    duration_sec = Column(Integer, default=0)            # for video/audio
    cost        = Column(Float, default=0.0)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())
    user        = relationship("User", back_populates="jobs")
