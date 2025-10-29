from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import Session as SessionModel, User


bearer_scheme = HTTPBearer(auto_error=False)


def get_current_session(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> SessionModel:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token = credentials.credentials
    session_obj = db.query(SessionModel).filter(SessionModel.token == token).first()
    if session_obj is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token",
        )

    now = datetime.now(timezone.utc)
    if session_obj.expires_at <= now:
        db.delete(session_obj)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired, please login again",
        )

    return session_obj


def get_current_user(session: SessionModel = Depends(get_current_session)) -> User:
    return session.user
