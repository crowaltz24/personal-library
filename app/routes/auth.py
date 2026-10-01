from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import create_access_token, hash_password, verify_password
from app.database import get_db
from app.models import User
from app.schemas.auth import AuthRequest, AuthResponse

router = APIRouter(prefix="/auth")


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(data: AuthRequest, db: Session = Depends(get_db)) -> AuthResponse:
    if db.scalar(select(User).where(User.username == data.username)):
        raise HTTPException(status_code=409, detail="Username already exists")
    user = User(username=data.username, password_hash=hash_password(data.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return AuthResponse(access_token=create_access_token(user.id), user_id=user.id)


@router.post("/login", response_model=AuthResponse)
def login(data: AuthRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = db.scalar(select(User).where(User.username == data.username))
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return AuthResponse(access_token=create_access_token(user.id), user_id=user.id)