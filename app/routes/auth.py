"""
Auth Routes - Registrazione, login, profilo utente
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional

from models.database import get_db
from models.user import User
from services.auth_service import AuthService, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


# Schemas
class UserRegister(BaseModel):
    email: EmailStr
    username: str
    password: str
    full_name: Optional[str] = None
    company: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    full_name: Optional[str]
    company: Optional[str]
    is_admin: bool

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    company: Optional[str] = None


# Routes
@router.post("/register", response_model=TokenResponse)
async def register(data: UserRegister, db: Session = Depends(get_db)):
    """Registra un nuovo utente"""
    try:
        user = AuthService.create_user(
            db=db,
            email=data.email,
            username=data.username,
            password=data.password,
            full_name=data.full_name,
            company=data.company
        )
        token = AuthService.create_access_token(user.id, user.email)
        return TokenResponse(
            access_token=token,
            user=UserResponse.model_validate(user)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, db: Session = Depends(get_db)):
    """Login utente"""
    user = AuthService.authenticate_user(db, data.email, data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o password non corretti"
        )
    token = AuthService.create_access_token(user.id, user.email)
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user)
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Ottieni profilo utente corrente"""
    return UserResponse.model_validate(current_user)


@router.put("/me", response_model=UserResponse)
async def update_me(
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Aggiorna profilo utente"""
    if data.full_name is not None:
        current_user.full_name = data.full_name
    if data.company is not None:
        current_user.company = data.company
    db.commit()
    db.refresh(current_user)
    return UserResponse.model_validate(current_user)


@router.post("/change-password")
async def change_password(
    old_password: str,
    new_password: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cambia password"""
    if not AuthService.verify_password(old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password attuale non corretta"
        )
    current_user.hashed_password = AuthService.hash_password(new_password)
    db.commit()
    return {"message": "Password aggiornata con successo"}
