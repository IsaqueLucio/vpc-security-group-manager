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
    claims = decode_access_token(token)
    if claims is None:
        raise AppException(status_code=401, detail="Invalid or expired token")
    subject = claims.get("sub")
    role = claims.get("role")
    if not isinstance(subject, str) or not subject.isdigit():
        raise AppException(status_code=401, detail="Invalid token subject")
    if role not in {UserRole.USER.value, UserRole.ADMIN.value}:
        raise AppException(status_code=401, detail="Invalid token role")

    user = UserRepository(db).get_by_id(int(subject))
    if user is None or not user.is_active:
        raise AppException(status_code=401, detail="User is inactive or does not exist")
    return user


def get_resource_owner_id(
    current_user: Annotated[User, Depends(get_current_user)],
) -> int | None:
    if current_user.role == UserRole.ADMIN:
        return None
    return current_user.id


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
