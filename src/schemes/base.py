from sqlalchemy import create_engine,Column,Integer,String,Float,MetaData,Table,ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker,relationship
from config import get_settings

settings = get_settings()
engine = create_engine(settings.DATABASE_URL)

Base = declarative_base()