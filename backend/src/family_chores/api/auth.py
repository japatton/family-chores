"""Parent-PIN + JWT auth endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from family_chores.api.deps import (
    get_jwt_secret,
    get_remote_user,
    get_session,
    get_ws_manager,
    maybe_parent,
    require_parent,
)
from family_chores.api.errors import (
    PinAlreadySetError,
    PinInvalidError,
    PinNotSetError,
)
from family_chores.api.events import EVT_PIN_CLEARED, EVT_PIN_SET, WSManager
from family_chores.api.schemas import (
    ClearPinRequest,
    SetPinRequest,
    TokenResponse,
    VerifyPinRequest,
    WhoAmI,
)
from family_chores.db.models import ActivityLog
from family_chores.security import (
    ParentClaim,
    clear_pin_hash,
    get_pin_hash,
    hash_pin,
    mint_parent_token,
    set_pin_hash,
    verify_pin,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/whoami", response_model=WhoAmI)
async def whoami(
    user: str = Depends(get_remote_user),
    claim: ParentClaim | None = Depends(maybe_parent),
    session: AsyncSession = Depends(get_session),
) -> WhoAmI:
    pin_hash = await get_pin_hash(session)
    return WhoAmI(
        user=user,
        parent_pin_set=pin_hash is not None,
        parent_mode_active=claim is not None,
    )


@router.post("/pin/set", response_model=WhoAmI, status_code=200)
async def set_pin(
    body: SetPinRequest,
    user: str = Depends(get_remote_user),
    session: AsyncSession = Depends(get_session),
    ws: WSManager = Depends(get_ws_manager),
) -> WhoAmI:
    current_hash = await get_pin_hash(session)

    # If a PIN is already set, the caller must prove they know the current one.
    if current_hash is not None:
        if not body.current_pin:
            raise PinAlreadySetError("current_pin required to rotate PIN")
        if not verify_pin(body.current_pin, current_hash):
            raise PinInvalidError("current PIN incorrect")

    await set_pin_hash(session, hash_pin(body.pin))
    session.add(ActivityLog(actor=user, action="pin_set", payload={}))
    await session.commit()
    await ws.broadcast({"type": EVT_PIN_SET})
    return WhoAmI(user=user, parent_pin_set=True, parent_mode_active=False)


@router.post("/pin/verify", response_model=TokenResponse)
async def verify(
    body: VerifyPinRequest,
    user: str = Depends(get_remote_user),
    session: AsyncSession = Depends(get_session),
    secret: str = Depends(get_jwt_secret),
) -> TokenResponse:
    pin_hash = await get_pin_hash(session)
    if pin_hash is None:
        raise PinNotSetError("no PIN is set; call /api/auth/pin/set first")
    if not verify_pin(body.pin, pin_hash):
        raise PinInvalidError("incorrect PIN")
    token, exp = mint_parent_token(secret, user)
    return TokenResponse(token=token, expires_at=exp)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    claim: ParentClaim = Depends(require_parent),
    secret: str = Depends(get_jwt_secret),
) -> TokenResponse:
    """Extend an already-valid parent session.

    The frontend calls this on user activity to achieve the spec's
    5-min-of-inactivity semantic on top of short absolute JWTs.
    """
    token, exp = mint_parent_token(secret, claim.user)
    return TokenResponse(token=token, expires_at=exp)


@router.post("/pin/clear", response_model=WhoAmI)
async def clear_pin(
    body: ClearPinRequest,
    user: str = Depends(get_remote_user),
    session: AsyncSession = Depends(get_session),
    ws: WSManager = Depends(get_ws_manager),
) -> WhoAmI:
    pin_hash = await get_pin_hash(session)
    if pin_hash is None:
        raise PinNotSetError("no PIN is set")
    if not verify_pin(body.pin, pin_hash):
        raise PinInvalidError("incorrect PIN")
    await clear_pin_hash(session)
    session.add(ActivityLog(actor=user, action="pin_cleared", payload={}))
    await session.commit()
    await ws.broadcast({"type": EVT_PIN_CLEARED})
    return WhoAmI(user=user, parent_pin_set=False, parent_mode_active=False)
