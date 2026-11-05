from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import AccessTokenPayload, CurrentUser, DbSession
from app.core.config import get_settings
from app.core.rate_limit import auth_rate_limit
from app.schemas.auth import (
    AccountDeleteRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LoginVerifyRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    TwoFactorDisableRequest,
    TwoFactorEnableRequest,
    TwoFactorEnableResponse,
    TwoFactorSetupResponse,
)
from app.schemas.user import UserPublic
from app.services import auth as auth_service
from app.services import two_factor as two_factor_service
from app.services.mail import deliver_password_reset_email
from app.services.users import delete_user_account

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


@router.post("/login", dependencies=[Depends(auth_rate_limit)])
async def login(payload: LoginRequest, db: DbSession):
    user = await auth_service.authenticate_user(db, payload.login, payload.password)
    if getattr(user, "totp_enabled", False):
        challenge_token = two_factor_service.create_challenge_token(user.id)
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"requires_2fa": True, "challenge_token": challenge_token},
        )
    access, refresh = await auth_service.issue_tokens(db, user)
    return TokenResponse(access_token=access, refresh_token=refresh, user=UserPublic.model_validate(user))


@router.post("/login/verify", response_model=TokenResponse, dependencies=[Depends(auth_rate_limit)])
async def login_verify(payload: LoginVerifyRequest, db: DbSession) -> TokenResponse:
    user = await two_factor_service.verify_login_challenge(
        db, payload.challenge_token, payload.code
    )
    access, refresh = await auth_service.issue_tokens(db, user)
    return TokenResponse(access_token=access, refresh_token=refresh, user=UserPublic.model_validate(user))


@router.post("/2fa/setup", response_model=TwoFactorSetupResponse)
async def setup_2fa(current_user: CurrentUser, db: DbSession) -> TwoFactorSetupResponse:
    secret, otpauth_url = await two_factor_service.setup_two_factor(db, current_user)
    return TwoFactorSetupResponse(secret=secret, otpauth_url=otpauth_url)


@router.post("/2fa/enable", response_model=TwoFactorEnableResponse)
async def enable_2fa(
    payload: TwoFactorEnableRequest, current_user: CurrentUser, db: DbSession
) -> TwoFactorEnableResponse:
    recovery_codes = await two_factor_service.enable_two_factor(db, current_user, payload.code)
    return TwoFactorEnableResponse(recovery_codes=recovery_codes)


@router.post("/2fa/disable", status_code=status.HTTP_204_NO_CONTENT)
async def disable_2fa(
    payload: TwoFactorDisableRequest, current_user: CurrentUser, db: DbSession
) -> Response:
    await two_factor_service.disable_two_factor(db, current_user, payload.code, payload.recovery_code)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    payload: AccountDeleteRequest, current_user: CurrentUser, db: DbSession
) -> Response:
    await delete_user_account(db, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: DbSession) -> TokenResponse:
    user, access, refresh_token = await auth_service.refresh_access_token(db, payload.refresh_token)
    return TokenResponse(
        access_token=access, refresh_token=refresh_token, user=UserPublic.model_validate(user)
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: LogoutRequest,
    current_user: CurrentUser,
    token_payload: AccessTokenPayload,
    db: DbSession,
) -> Response:
    await auth_service.revoke_access_jti(token_payload["jti"])
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


@router.get("/sessions", response_model=list[dict])
async def list_sessions(
    current_user: CurrentUser,
    db: DbSession,
    token_payload: AccessTokenPayload,
    current_jti: str | None = Query(default=None, max_length=36),
) -> list[dict]:
    return await auth_service.list_sessions(db, current_user.id, current_jti)


@router.delete("/sessions/{jti}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(jti: str, current_user: CurrentUser, db: DbSession) -> None:
    revoked = await auth_service.revoke_session(db, current_user.id, jti)
    if not revoked:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
