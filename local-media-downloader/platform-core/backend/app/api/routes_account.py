"""Self-service account endpoints beyond the core auth/session surface in
`routes_auth.py` - account closure (mission-brief Phase 39)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.database.models import AccountClosureRequest, User
from app.services import account_closure_service

router = APIRouter(prefix="/api/v1/account", tags=["account"])


def _closure_out(request: AccountClosureRequest) -> dict:
    return {
        "id": request.id, "status": request.status, "reason": request.reason,
        "requested_at": request.requested_at.isoformat(),
        "confirmed_at": request.confirmed_at.isoformat() if request.confirmed_at else None,
        "closed_at": request.closed_at.isoformat() if request.closed_at else None,
        "canceled_at": request.canceled_at.isoformat() if request.canceled_at else None,
    }


@router.get("/closure")
async def closure_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict | None:
    request = account_closure_service.get_status(db, user.id)
    return _closure_out(request) if request else None


@router.post("/closure")
async def request_closure(payload: dict | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    request = account_closure_service.request_closure(db, user, (payload or {}).get("reason"))
    return _closure_out(request)


@router.post("/closure/{request_id}/confirm")
async def confirm_closure(request_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    request = account_closure_service.confirm_closure(db, user, request_id)
    return _closure_out(request)


@router.post("/closure/{request_id}/cancel")
async def cancel_closure(request_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    request = account_closure_service.cancel_closure(db, user, request_id)
    return _closure_out(request)
