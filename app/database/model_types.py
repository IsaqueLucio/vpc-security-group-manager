from sqlalchemy import Enum as SQLEnum
from sqlalchemy import text

from app.domain.enums import ResourceStatus

RESOURCE_STATUS = SQLEnum(ResourceStatus, name="resource_status", native_enum=True)
ACTIVE_ROW = text("status != 'DELETED'")
