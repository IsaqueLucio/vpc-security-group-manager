from app.core.exceptions import AppException
from app.modules.users.models import User
from app.modules.users.repository import UserRepository


class UserService:
    def __init__(self, users: UserRepository) -> None:
        self.users = users

    def list_users(self) -> list[User]:
        return self.users.list()

    def delete_user(self, user_id: int, current_admin: User) -> None:
        user = self.users.get_by_id(user_id)
        if user is None:
            raise AppException(status_code=404, detail="User not found.")
        if user.id == current_admin.id:
            raise AppException(
                status_code=409,
                detail="Cannot delete current administrator.",
            )
        self.users.delete(user)
