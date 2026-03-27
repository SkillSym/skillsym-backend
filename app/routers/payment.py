import os
import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.auth import get_current_user, require_admin
from app.models.models import User, Wallet, Transaction

router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
YOUR_DOMAIN = os.getenv("FRONTEND_URL", "http://localhost:3000")

class AddCreditsRequest(BaseModel):
    amount: float

class ManualTopupRequest(BaseModel):
    user_id:   str
    amount:    float
    reference: str

@router.post("/create-checkout")
async def create_checkout(
    data: AddCreditsRequest,
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db)
):
    if not stripe.api_key or stripe.api_key == "skip_for_now":
        raise HTTPException(503,
            "Online payment not configured yet. "
            "Please use JazzCash/EasyPaisa and contact support."
        )
    if data.amount < 1.0:
        raise HTTPException(400, "Minimum top-up is $1")
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": f"SkillSym AI Credits ${data.amount:.2f}"},
                    "unit_amount": int(data.amount * 100),
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{YOUR_DOMAIN}?payment=success&amount={data.amount}",
            cancel_url=f"{YOUR_DOMAIN}?payment=cancelled",
            metadata={"user_id": user.id, "amount": str(data.amount)},
        )
        return {"checkout_url": session.url}
    except Exception as e:
        raise HTTPException(500, f"Payment error: {str(e)}")

@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig, STRIPE_WEBHOOK_SECRET
        )
    except Exception:
        raise HTTPException(400, "Invalid webhook")

    if event["type"] == "checkout.session.completed":
        s = event["data"]["object"]
        user_id = s["metadata"].get("user_id")
        amount  = float(s["metadata"].get("amount", 0))
        if user_id and amount > 0:
            wallet = db.query(Wallet).filter(Wallet.user_id == user_id).first()
            if wallet:
                wallet.balance += amount
                db.add(Transaction(
                    wallet_id=wallet.id, amount=amount,
                    description=f"Credits added via Stripe ${amount:.2f}"
                ))
                db.commit()
    return {"received": True}

@router.post("/check-credits")
def check_credits(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).first()
    balance = wallet.balance if wallet else 0.0
    return {"balance": round(balance, 2), "has_credits": balance > 0}

@router.post("/manual-topup")
def manual_topup(
    data:   ManualTopupRequest,
    admin:  User    = Depends(require_admin),
    db:     Session = Depends(get_db)
):
    wallet = db.query(Wallet).filter(Wallet.user_id == data.user_id).first()
    if not wallet:
        raise HTTPException(404, "User wallet not found")
    wallet.balance += data.amount
    db.add(Transaction(
        wallet_id=wallet.id, amount=data.amount,
        description=f"Manual top-up ref:{data.reference} ${data.amount:.2f}"
    ))
    db.commit()
    return {"success": True, "new_balance": round(wallet.balance, 2)}
