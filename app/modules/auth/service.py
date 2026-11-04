from app.core.exceptions import AppException
from app.core.security import create_access_token, hash_password, verify_password
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import UserCreate


class AuthService:
    def __init__(self, users: UserRepository) -> None:
        self.users = users

    def register(self, user_data: UserCreate) -> User:
        if self.users.get_by_email(user_data.email):
            raise AppException(status_code=409, detail="The email is already registered.")
        if self.users.get_by_username(user_data.username):
            raise AppException(
                status_code=409,
                detail="The username is already registered.",
            )

        user = User(
            username=user_data.username,
            email=user_data.email,
            hashed_password=hash_password(user_data.password.get_secret_value()),
        )
        return self.users.create(user)

    def login(self, email: str, password: str) -> str:
        user = self.users.get_by_email(email)
        if user is None or not verify_password(password, user.hashed_password):
            raise AppException(
                status_code=401,
                detail="Incorrect username or password.",
            )
        return create_access_token(data={"sub": user.email})
