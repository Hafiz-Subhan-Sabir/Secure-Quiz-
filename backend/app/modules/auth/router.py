from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_db
from app.core.security import create_access_token, verify_password
from app.db.models import User
from app.modules.schemas import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == str(body.email).lower()))
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    settings = get_settings()
    token = create_access_token(subject=user.id, role=user.role)  # type: ignore[arg-type]
    return TokenResponse(
        access_token=token,
        role=user.role,  # type: ignore[arg-type]
        expires_in=settings.access_token_expire_minutes * 60,
        full_name=user.full_name,
        email=user.email,
    )
