from sqlalchemy import Column, Integer, String,ForeignKey, DateTime
from sqlalchemy.orm import relationship
from config import get_settings
from .base import Base
import datetime

class Orgs(Base):
    __tablename__ = "orgs"

    id = Column(Integer, primary_key=True, index=True)
    org_name = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("auth.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    user = relationship("Auth", back_populates="user_orgs")


