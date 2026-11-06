from time import perf_counter
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.exceptions import AppException, app_exception_handler
from app.modules.auth.router import router as auth_router
from app.modules.vpcs.router import router as vpcs_router
from app.modules.users.router import admin_router, router as users_router


app = FastAPI(
    title="VPC & Security Group Manager",
    description="Backend foundation for cloud network management.",
    version="0.1.0",
)
app.add_exception_handler(AppException, app_exception_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_process_time_header(
    request: Request,
    call_next: Callable[[Request], Response],
) -> Response:
    start = perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time"] = str(perf_counter() - start)
    return response


app.include_router(auth_router)
app.include_router(vpcs_router)
app.include_router(users_router)
app.include_router(admin_router)


@app.get("/")
def get_root() -> dict[str, str]:
    return {
        "api_name": "VPC & Security Group Manager",
        "status": "foundation",
    }


@app.get("/health")
def get_health() -> dict[str, str]:
    return {"status": "ok"}
