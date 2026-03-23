from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from app.database import get_db
from app.auth import require_admin
from app.models.models import User, GenerationJob, Transaction, Wallet

router = APIRouter()

@router.get("/dashboard")
def admin_dashboard(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    total_users   = db.query(func.count(User.id)).scalar()
    total_jobs    = db.query(func.count(GenerationJob.id)).scalar()
    pending_jobs  = db.query(func.count(GenerationJob.id)).filter(GenerationJob.status == "pending").scalar()
    failed_jobs   = db.query(func.count(GenerationJob.id)).filter(GenerationJob.status == "failed").scalar()
    total_revenue = db.query(func.sum(Transaction.amount)).filter(Transaction.amount > 0).scalar() or 0.0
    recent_jobs   = db.query(GenerationJob).order_by(GenerationJob.created_at.desc()).limit(10).all()
    return {
        "stats": {
            "total_users":   total_users,
            "total_jobs":    total_jobs,
            "pending_jobs":  pending_jobs,
            "failed_jobs":   failed_jobs,
            "total_revenue": round(float(total_revenue), 2),
        },
        "recent_jobs": [
            {"id": j.id, "type": j.job_type, "status": j.status, "user_id": j.user_id, "cost": j.cost, "created_at": j.created_at}
            for j in recent_jobs
        ]
    }

@router.get("/users")
def list_users(
    skip: int = 0, limit: int = 50,
    db: Session = Depends(get_db), _: User = Depends(require_admin)
):
    users = db.query(User).offset(skip).limit(limit).all()
    return {"users": [
        {"id": u.id, "email": u.email, "is_blocked": u.is_blocked, "is_admin": u.is_admin, "created_at": u.created_at}
        for u in users
    ]}

class BlockUserRequest(BaseModel):
    user_id: str
    blocked: bool
    reason:  str = ""

@router.post("/users/block")
def block_user(data: BlockUserRequest, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    user = db.query(User).filter(User.id == data.user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    user.is_blocked = data.blocked
    db.commit()
    return {"success": True, "user_id": data.user_id, "blocked": data.blocked}

@router.get("/jobs")
def list_jobs(
    status: str = None, job_type: str = None,
    skip: int = 0, limit: int = 50,
    db: Session = Depends(get_db), _: User = Depends(require_admin)
):
    q = db.query(GenerationJob)
    if status:
        q = q.filter(GenerationJob.status == status)
    if job_type:
        q = q.filter(GenerationJob.job_type == job_type)
    jobs = q.order_by(GenerationJob.created_at.desc()).offset(skip).limit(limit).all()
    return {"jobs": [
        {"id": j.id, "type": j.job_type, "status": j.status, "user_id": j.user_id,
         "cost": j.cost, "result_url": j.result_url, "created_at": j.created_at}
        for j in jobs
    ]}

@router.delete("/jobs/{job_id}")
def remove_flagged_content(job_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    db.delete(job)
    db.commit()
    return {"success": True, "removed": job_id}

@router.get("/revenue")
def revenue_stats(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    txs = db.query(Transaction).filter(Transaction.amount > 0).order_by(Transaction.created_at.desc()).limit(100).all()
    return {"transactions": [
        {"id": t.id, "amount": t.amount, "description": t.description, "date": t.created_at}
        for t in txs
    ]}
