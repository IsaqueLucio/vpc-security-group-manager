from typing import Annotated

from fastapi import Depends, Query
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.core.security import decode_access_token
from app.database.session import get_db
from app.modules.users.models import User, UserRole
from app.modules.users.repository import UserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    email = decode_access_token(token)
    if email is None:
        raise AppException(status_code=401, detail="Invalid or expired token")

    user = UserRepository(db).get_by_email(email)
    if user is None:
        raise AppException(status_code=401, detail="User not found")
    return user


def require_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if current_user.role != UserRole.ADMIN:
        raise AppException(status_code=403, detail="The user is not an admin.")
    return current_user


def get_pagination(
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[
        int, Query(ge=1, le=100, description="Limit of records per page")
    ] = 10,
) -> dict[str, int]:
    return {"skip": skip, "limit": limit}
