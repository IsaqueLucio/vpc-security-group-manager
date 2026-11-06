from math import ceil

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppException


def set_local_lock_timeout(db: Session) -> None:
    db.execute(
        text("SELECT set_config('lock_timeout', :timeout, true)"),
        {"timeout": f"{settings.database_lock_timeout_ms}ms"},
    )


def app_exception_for_database_error(exc: DBAPIError) -> AppException | None:
    sqlstate = getattr(exc.orig, "sqlstate", None)
    if sqlstate == "55P03":
        retry_after = max(1, ceil(settings.database_lock_timeout_ms / 1000))
        return AppException(
            status_code=503,
            detail="O recurso está ocupado; tente novamente.",
            headers={"Retry-After": str(retry_after)},
        )
    if sqlstate == "23P01":
        return AppException(
            status_code=409,
            detail="O CIDR se sobrepõe a outro recurso ativo.",
        )
    if sqlstate == "23505":
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint in {
            "uq_vpcs_owner_name_active",
            "uq_subnets_vpc_name_active",
            "uq_ip_allocations_subnet_ip_active",
            "uq_internet_gateways_vpc_active",
        }:
            detail = (
                "O IP já está alocado nesta subnet."
                if constraint == "uq_ip_allocations_subnet_ip_active"
                else "A VPC já possui um Internet Gateway ativo."
                if constraint == "uq_internet_gateways_vpc_active"
                else "Já existe um recurso ativo com esse nome."
            )
            return AppException(
                status_code=409,
                detail=detail,
            )
    return None
