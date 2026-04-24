"""Domain-level exceptions and their HTTP projections.

We raise these from services; a small translation layer in `app.py` turns
each into a JSON body of the shape `{error, detail, request_id}`.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base for exceptions the API layer knows how to translate."""

    status_code: int = 400
    error_code: str = "domain_error"

    def __init__(self, detail: str = "") -> None:
        super().__init__(detail or self.error_code)
        self.detail = detail or self.error_code


class NotFoundError(DomainError):
    status_code = 404
    error_code = "not_found"


class ConflictError(DomainError):
    status_code = 409
    error_code = "conflict"


class InvalidStateError(DomainError):
    status_code = 409
    error_code = "invalid_state"


class UndoWindowExpiredError(DomainError):
    status_code = 409
    error_code = "undo_window_expired"


class PinNotSetError(DomainError):
    status_code = 400
    error_code = "pin_not_set"


class PinAlreadySetError(DomainError):
    status_code = 400
    error_code = "pin_already_set"


class PinInvalidError(DomainError):
    status_code = 401
    error_code = "pin_invalid"


class AuthRequiredError(DomainError):
    status_code = 401
    error_code = "auth_required"


class ForbiddenError(DomainError):
    status_code = 403
    error_code = "forbidden"
