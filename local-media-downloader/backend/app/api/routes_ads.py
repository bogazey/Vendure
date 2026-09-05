"""Read-only ad placement config for any authenticated user - what AdSlot
needs at render time. Deliberately separate from the /api/admin/ads/*
management surface (routes_admin.py): nothing here is a secret, but only
admins may change it.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.database.commercial_models import User
from app.models.commercial_schemas import AdPlacementOut
from app.services import ad_placement_service

router = APIRouter(prefix="/api/ads", tags=["ads"])


@router.get("/placements", response_model=list[AdPlacementOut])
async def list_ad_placements(
    db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> list[AdPlacementOut]:
    return [
        AdPlacementOut(
            id=p.id, enabled=p.enabled, provider=p.provider, public_slot_id=p.public_slot_id
        )
        for p in ad_placement_service.list_placements(db)
    ]
