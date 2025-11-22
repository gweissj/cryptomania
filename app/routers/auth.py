from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, object_session

from ..database import get_db
from ..models import Session as SessionModel, User
from ..schemas import AuthTokenResponse, MessageResponse, UserCreate, UserLogin, UserResponse
from ..security import compute_session_expiry, generate_session_token, hash_password, verify_password
from ..utils import AgeRestrictionError, ensure_is_adult
from ..dependencies import get_current_session


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="User with this email already exists"
        )

    try:
        ensure_is_adult(payload.birth_date)
    except AgeRestrictionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    new_user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
        birth_date=payload.birth_date,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.post("/login", response_model=AuthTokenResponse)
def login_user(payload: UserLogin, db: Session = Depends(get_db)) -> AuthTokenResponse:
    user = db.query(User).filter(User.email == payload.email).first()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password"
        )

    session_token = generate_session_token()
    session_entry = SessionModel(user_id=user.id, token=session_token, expires_at=compute_session_expiry())
    db.add(session_entry)
    db.commit()

    return AuthTokenResponse(access_token=session_token)


@router.post("/logout", response_model=MessageResponse)
def logout_user(session_entry: SessionModel = Depends(get_current_session)) -> MessageResponse:
    db = object_session(session_entry)
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to access database session for logout",
        )

    db.delete(session_entry)
    db.commit()
    return MessageResponse(message="Logged out successfully")
