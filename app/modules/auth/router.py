from fastapi import APIRouter, HTTPException, Response, status

from app.core.database import SessionDep
from app.modules.auth import service
from app.modules.auth.schemas import ErrorResponse, LoginRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])

INVALID_CREDENTIALS = "Invalid email or password"


@router.post(
    "/register",
    status_code=status.HTTP_202_ACCEPTED,
    response_class=Response,
    responses={status.HTTP_202_ACCEPTED: {"description": "Registration accepted"}},
)
async def register(data: RegisterRequest, session: SessionDep) -> Response:
    """Create an account.

    Always 202 with an empty body, whether or not the email is already registered, so the
    response never reveals which emails have an account.
    """
    await service.register(session, data)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post(
    "/login",
    responses={status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse}},
)
async def login(data: LoginRequest, session: SessionDep, response: Response) -> TokenResponse:
    """Exchange email and password for a short-lived access token.

    Unknown email and wrong password return the same 401.
    """
    try:
        token = await service.login(session, data)
    except service.InvalidCredentialsError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_CREDENTIALS,
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    # RFC 6749 5.1: responses carrying tokens must not be cached.
    response.headers["Cache-Control"] = "no-store"
    return TokenResponse(
        access_token=token, expires_in=int(service.ACCESS_TOKEN_TTL.total_seconds())
    )
