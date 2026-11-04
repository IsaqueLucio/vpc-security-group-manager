import os
from collections.abc import Iterator

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-that-is-at-least-32-characters")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.modules.users.models import User, UserRole


@pytest.fixture
def test_db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = testing_session()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def client(test_db: Session) -> Iterator[TestClient]:
    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def create_test_user(
    db: Session,
    username: str,
    email: str,
    role: UserRole = UserRole.USER,
) -> User:
    user = User(
        username=username,
        email=email,
        hashed_password=hash_password("TestPassword@123"),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_user(test_db: Session) -> User:
    return create_test_user(test_db, "Tester01", "tester01@example.com")


@pytest.fixture
def test_admin(test_db: Session) -> User:
    return create_test_user(
        test_db,
        "AdminTester01",
        "admin-tester@example.com",
        UserRole.ADMIN,
    )


@pytest.fixture
def test_auth_user(test_user: User) -> dict[str, str]:
    token = create_access_token(data={"sub": test_user.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_auth_admin(test_admin: User) -> dict[str, str]:
    token = create_access_token(data={"sub": test_admin.email})
    return {"Authorization": f"Bearer {token}"}
