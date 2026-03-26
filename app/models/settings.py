from sqlalchemy import Column, String, Float, Integer
from app.database import Base

class Settings(Base):
    __tablename__ = "settings"
    key   = Column(String, primary_key=True)
    value = Column(String, nullable=False)

# Default settings
DEFAULT_SETTINGS = {
    # Free limits per month
    "FREE_BANNERS_PER_MONTH":    "20",
    "FREE_AUDIO_PER_MONTH":      "20",
    "FREE_VIDEO_PER_MONTH":      "20",

    # Free duration limits
    "FREE_AUDIO_SECONDS":        "20",
    "FREE_VIDEO_SECONDS":        "20",

    # Banner pricing
    "BANNER_PRICE_PER_PACK":     "1.00",   # $1 per 20 extra banners
    "BANNER_PACK_SIZE":          "20",      # 20 banners per pack

    # Audio pricing tiers
    "AUDIO_PRICE_30SEC":         "1.00",    # $1 for up to 30 sec
    "AUDIO_PRICE_40SEC":         "2.00",    # $2 for up to 40 sec
    "AUDIO_PRICE_60SEC":         "2.50",    # $2.50 for up to 60 sec

    # Video pricing tiers
    "VIDEO_PRICE_30SEC":         "1.00",    # $1 for up to 30 sec
    "VIDEO_PRICE_40SEC":         "2.00",    # $2 for up to 40 sec
    "VIDEO_PRICE_60SEC":         "2.50",    # $2.50 for up to 60 sec
}
