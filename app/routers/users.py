from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import object_session

from ..dependencies import get_current_user
from ..models import User
from ..schemas import MessageResponse, UserResponse, UserUpdate
from ..security import hash_password
from ..utils import AgeRestrictionError, ensure_is_adult


router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.put("/me", response_model=UserResponse)
def update_current_user(
    payload: UserUpdate, current_user: User = Depends(get_current_user)
) -> User:
    db = object_session(current_user)
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to access database session for update",
        )

    if payload.birth_date:
        try:
            ensure_is_adult(payload.birth_date)
        except AgeRestrictionError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        current_user.birth_date = payload.birth_date

    if payload.first_name:
        current_user.first_name = payload.first_name
    if payload.last_name:
        current_user.last_name = payload.last_name
    if payload.region:
        current_user.region = payload.region
    if payload.city:
        current_user.city = payload.city
    if payload.password:
        current_user.hashed_password = hash_password(payload.password)

    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user


@router.delete("/me", response_model=MessageResponse)
def delete_current_user(current_user: User = Depends(get_current_user)) -> MessageResponse:
    db = object_session(current_user)
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to access database session for deletion",
        )

    db.delete(current_user)
    db.commit()
    return MessageResponse(message="Account deleted successfully")
