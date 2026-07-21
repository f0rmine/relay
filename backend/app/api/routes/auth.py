from fastapi import APIRouter, BackgroundTasks, Depends, Response, status

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.rate_limit import auth_rate_limit
from app.schemas.auth import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.schemas.user import UserPublic
from app.services import auth as auth_service
from app.services.mail import deliver_password_reset_email

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(auth_rate_limit)],
)
async def register(payload: RegisterRequest, db: DbSession) -> TokenResponse:
    user = await auth_service.register_user(
        db, payload.username, payload.display_name, payload.email, payload.password
    )
    access, refresh = await auth_service.issue_tokens(db, user)
    return TokenResponse(access_token=access, refresh_token=refresh, user=UserPublic.model_validate(user))


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(auth_rate_limit)])
async def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    user = await auth_service.authenticate_user(db, payload.login, payload.password)
    access, refresh = await auth_service.issue_tokens(db, user)
    return TokenResponse(access_token=access, refresh_token=refresh, user=UserPublic.model_validate(user))


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: DbSession) -> TokenResponse:
    user, access, refresh_token = await auth_service.refresh_access_token(db, payload.refresh_token)
    return TokenResponse(
        access_token=access, refresh_token=refresh_token, user=UserPublic.model_validate(user)
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: LogoutRequest, current_user: CurrentUser, db: DbSession) -> Response:
    await auth_service.revoke_refresh_token(db, current_user.id, payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserPublic)
async def me(current_user: CurrentUser) -> UserPublic:
    return UserPublic.model_validate(current_user)


@router.post(
    "/forgot-password", response_model=ForgotPasswordResponse, dependencies=[Depends(auth_rate_limit)]
)
async def forgot_password(
    payload: ForgotPasswordRequest, db: DbSession, background_tasks: BackgroundTasks
) -> ForgotPasswordResponse:
    reset_token = await auth_service.create_password_reset_token(db, payload.email)
    if reset_token is not None:
        background_tasks.add_task(deliver_password_reset_email, str(payload.email), reset_token)
    return ForgotPasswordResponse(
        detail="If the email exists, password reset instructions will be sent.",
        reset_token=reset_token if get_settings().password_reset_token_in_response else None,
    )


@router.post(
    "/reset-password", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(auth_rate_limit)]
)
async def reset_password(payload: ResetPasswordRequest, db: DbSession) -> Response:
    await auth_service.reset_password(db, payload.token, payload.new_password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
