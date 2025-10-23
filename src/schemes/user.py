from sqlalchemy import create_engine, Column, Integer, String, Float, MetaData, Table, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from config import get_settings
from .base import Base
import datetime

class Auth(Base):
    __tablename__ = "auth"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    organizations = Column(JSON, default=list)  
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    user_orgs = relationship("Orgs", back_populates="user", cascade="all, delete-orphan")
