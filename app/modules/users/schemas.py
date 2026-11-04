from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator

from app.modules.users.models import UserRole


class UserCreate(BaseModel):
    username: str = Field(
        min_length=3,
        max_length=50,
        description="Username, between 3 and 50 characters.",
    )
    email: EmailStr
    password: SecretStr = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def password_complexity(cls, password: SecretStr) -> SecretStr:
        value = password.get_secret_value()
        if not any(character.isupper() for character in value):
            raise ValueError("Must contain at least one uppercase letter.")
        if not any(character.isdigit() for character in value):
            raise ValueError("Must contain at least one number.")
        if not any(character in "!@#$%^&*()_+-=" for character in value):
            raise ValueError("Must contain at least one special character.")
        return password


class UserRead(BaseModel):
    id: int
    username: str
    email: str
    role: UserRole

    model_config = ConfigDict(from_attributes=True)
