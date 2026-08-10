"""
Application-level exceptions. Services raise these; the API layer maps them
to HTTP responses in one place (see `register_exception_handlers`) so every
module returns errors in the same shape instead of ad hoc HTTPExceptions
scattered across routers.
"""
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class AegisError(Exception):
    """Base class for all domain/application errors."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    default_message: str = "Something went wrong."

    def __init__(self, message: str | None = None):
        self.message = message or self.default_message
        super().__init__(self.message)


class NotFoundError(AegisError):
    status_code = status.HTTP_404_NOT_FOUND
    default_message = "The requested resource was not found."


class ValidationError(AegisError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_message = "The submitted data is invalid."


class AuthenticationError(AegisError):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_message = "Invalid credentials."


class AuthorizationError(AegisError):
    status_code = status.HTTP_403_FORBIDDEN
    default_message = "You don't have permission to do that."


class ConflictError(AegisError):
    status_code = status.HTTP_409_CONFLICT
    default_message = "This resource already exists."


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AegisError)
    async def handle_aegis_error(request: Request, exc: AegisError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"message": exc.message, "type": exc.__class__.__name__}},
        )
