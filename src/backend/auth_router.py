from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select
from datetime import datetime, timedelta
from typing import Optional
import os
import sys

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, project_root)

from src.schemes.user import Auth
from src.schemes.base import Base
from config import get_settings

# Create async engine
settings = get_settings()
db_url = settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql+asyncpg://")
async_engine = create_async_engine(db_url, echo=False)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

# Define a router with a /auth prefix
router = APIRouter(prefix="/auth", tags=["Authentication"])

SECRET_KEY = "secretkeyforjwt"  #a secret string used to sign JWTS, in production securely stored
ALGORITHM = "HS256"      #specify JWT signing algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = 30     #Sets the token expiration time to 30 minutes.

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme
#defines an OAuth2 pass flow where the token is obtained from the /auth/login endpoint
#fastapi uses this to extarct the JWT token from the Authorization header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# Pydantic models
#User registration model
class UserCreate(BaseModel):
    username: str
    password: str

#user response
class User(BaseModel):
    id: int
    username: str
    created_at: datetime

    class Config:
        from_attributes = True #Allows Pydantic to convert SQLAlchemy objects to Pydantic models.

#represent the JWT response
class Token(BaseModel):
    access_token: str
    token_type: str

# Dependency for async SQLAlchemy session
async def get_async_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

# Password hashing and verification
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# JWT token creation
def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Get current user dependency
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_async_db)
    ) -> Auth:

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")

        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    result = await db.execute(select(Auth).filter(Auth.username == username))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    return user

# Routes
@router.post("/register", response_model=User)
async def register(user: UserCreate, db: AsyncSession = Depends(get_async_db)):
    """Register a new user"""
    hashed_password = hash_password(user.password)
    
    result = await db.execute(select(Auth).filter(Auth.username == user.username))
    db_user = result.scalar_one_or_none()
    
    if db_user:
        raise HTTPException(
            status_code=400,
            detail="Username already used"
        )

    new_user = Auth(username=user.username, 
                    password_hash=hashed_password)
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return new_user

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(),
                db: AsyncSession = Depends(get_async_db)):
    """Login and get access token"""

    result = await db.execute(select(Auth).filter(Auth.username == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, 
            "token_type": "bearer"}

@router.get("/me", response_model=User)
async def read_users_me(current_user: Auth = Depends(get_current_user)):
    """Get current user information"""
    return current_user
