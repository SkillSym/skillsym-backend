import os
import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.auth import get_current_user
from app.models.models import User, Wallet, Transaction

router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
YOUR_DOMAIN = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Credit packages
PACKAGES = [
    {"id": "starter",    "credits": 1.00,  "label": "$1 – Starter Pack",    "description": "30 extra banners OR 30 audio ads"},
    {"id": "small",      "credits": 5.00,  "label": "$5 – Small Pack",      "description": "150 banners OR audio ads"},
    {"id": "medium",     "credits": 10.00, "label": "$10 – Medium Pack",     "description": "300 banners OR audio ads + 10 min video"},
    {"id": "large",      "credits": 25.00, "label": "$25 – Large Pack",      "description": "750 banners + 25 min video"},
]

class AddCreditsRequest(BaseModel):
    amount: float   # in USD

class ManualTopupRequest(BaseModel):   # for JazzCash/EasyPaisa (admin confirms)
    user_id: str
    amount:  float
    reference: str

@router.get("/packages")
def get_packages():
    return {"packages": PACKAGES}

@router.post("/create-checkout")
async def create_checkout(
    data: AddCreditsRequest,
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db)
):
    if not stripe.api_key:
        raise HTTPException(503, "Payment not configured yet. Contact support to add credits manually.")
    if data.amount < 1.0:
        raise HTTPException(400, "Minimum top-up is $1")
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": f"SkillSym AI Credits – ${data.amount:.2f}"},
                    "unit_amount": int(data.amount * 100),
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{YOUR_DOMAIN}/dashboard?payment=success&amount={data.amount}",
            cancel_url=f"{YOUR_DOMAIN}/dashboard?payment=cancelled",
            metadata={"user_id": user.id, "amount": str(data.amount)},
        )
        return {"checkout_url": session.url, "session_id": session.id}
    except Exception as e:
        raise HTTPException(500, f"Payment error: {str(e)}")

@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception:
        raise HTTPException(400, "Invalid webhook signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session["metadata"].get("user_id")
        amount  = float(session["metadata"].get("amount", 0))
        if user_id and amount > 0:
            wallet = db.query(Wallet).filter(Wallet.user_id == user_id).first()
            if wallet:
                wallet.balance += amount
                db.add(Transaction(
                    wallet_id=wallet.id, amount=amount,
                    description=f"Credits added via Stripe – ${amount:.2f}"
                ))
                db.commit()
    return {"received": True}

@router.post("/check-credits")
def check_credits(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).first()
    balance = wallet.balance if wallet else 0.0
    return {"balance": round(balance, 2), "has_credits": balance > 0}

# JazzCash / EasyPaisa: Admin manually confirms and adds credits
@router.post("/manual-topup")
def manual_topup(
    data: ManualTopupRequest,
    _admin: User = Depends(get_current_user),  # Checked below
    db: Session  = Depends(get_db)
):
    if not _admin.is_admin:
        raise HTTPException(403, "Admin only")
    wallet = db.query(Wallet).filter(Wallet.user_id == data.user_id).first()
    if not wallet:
        raise HTTPException(404, "User wallet not found")
    wallet.balance += data.amount
    db.add(Transaction(
        wallet_id=wallet.id, amount=data.amount,
        description=f"Manual top-up (ref: {data.reference}) – ${data.amount:.2f}"
    ))
    db.commit()
    return {"success": True, "new_balance": round(wallet.balance, 2)}
