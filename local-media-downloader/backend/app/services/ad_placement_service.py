"""Ad placement registry and the single ad-eligibility decision.

Two concerns live here on purpose:

1. `is_ad_eligible` - the ONE place that decides whether a signed-in user's
   plan should ever see an ad slot at all (Free: yes, Pro/Creator: no).
   Nothing else should re-derive this from `plan == "free"` checks scattered
   through components/routes - see plan_policy.PlanPolicy.ads_enabled, which
   this simply reads.
2. CRUD over the AdPlacement registry the admin Ads page manages. No secrets
   are ever accepted or stored here (see AdminUpdateAdPlacementRequest).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.commercial_models import AdPlacement
from app.models.commercial_enums import AdminActionType, AdPlacementId, Plan
from app.models.commercial_schemas import AdminUpdateAdPlacementRequest
from app.services.plan_policy import get_policy

# Mirrors the seed data in alembic/versions/3a7c1e9f2b6d_add_ad_placements.py.
# Duplicated deliberately - migrations should stay self-contained rather than
# import service code that can change shape later - but tests build their
# schema via Base.metadata.create_all() (see conftest._commercial_schema),
# which skips migrations entirely, so ensure_default_placements() gives them
# an equivalent seed.
DEFAULT_PLACEMENT_DESCRIPTIONS: dict[AdPlacementId, str] = {
    AdPlacementId.LANDING_DOWNLOADER: "Below the URL input on the marketing landing page downloader.",
    AdPlacementId.DOWNLOAD_RESULT: "Alongside a completed download's result card.",
    AdPlacementId.USER_DASHBOARD: "In the authenticated dashboard, away from download controls.",
    AdPlacementId.DOWNLOAD_HISTORY: "Within the download history / media library list.",
}


def ensure_default_placements(session: Session) -> None:
    """Idempotently seeds the fixed placement rows if missing - real
    deployments get them from the Alembic migration; tests call this after
    Base.metadata.create_all()."""
    existing_ids = {p.id for p in list_placements(session)}
    for placement_id, description in DEFAULT_PLACEMENT_DESCRIPTIONS.items():
        if placement_id.value not in existing_ids:
            session.add(AdPlacement(id=placement_id.value, description=description, enabled=False))
    session.flush()


def is_ad_eligible(plan: Plan) -> bool:
    """Centralized entitlement decision: does this plan ever receive ads?
    Free -> True, Pro/Creator -> False. Never rely on frontend-only state for
    anything server-enforced; this is the server-side source of truth that
    AccountOut.features.ads_enabled is built from."""
    return get_policy(plan).ads_enabled


def list_placements(session: Session) -> list[AdPlacement]:
    return list(session.execute(select(AdPlacement).order_by(AdPlacement.id)).scalars())


def get_placement(session: Session, placement_id: str) -> AdPlacement | None:
    return session.get(AdPlacement, placement_id)


@dataclass
class PlacementUpdateResult:
    placement: AdPlacement
    action: AdminActionType
    changed_fields: dict[str, Any] = field(default_factory=dict)


def update_placement(
    session: Session, placement: AdPlacement, payload: AdminUpdateAdPlacementRequest
) -> PlacementUpdateResult:
    """Applies only the fields the admin actually sent, and reports what
    changed so the caller can write one accurate AdminActionLog entry."""
    changed: dict[str, Any] = {}
    enabled_changed = False

    if payload.enabled is not None and payload.enabled != placement.enabled:
        changed["enabled"] = {"from": placement.enabled, "to": payload.enabled}
        placement.enabled = payload.enabled
        enabled_changed = True
    if payload.provider is not None and payload.provider != placement.provider:
        changed["provider"] = {"from": placement.provider, "to": payload.provider}
        placement.provider = payload.provider
    if payload.public_slot_id is not None and payload.public_slot_id != placement.public_slot_id:
        changed["public_slot_id"] = {"from": placement.public_slot_id, "to": payload.public_slot_id}
        placement.public_slot_id = payload.public_slot_id

    if enabled_changed:
        action = AdminActionType.AD_PLACEMENT_ENABLED if placement.enabled else AdminActionType.AD_PLACEMENT_DISABLED
    else:
        action = AdminActionType.AD_PLACEMENT_UPDATED

    session.flush()
    return PlacementUpdateResult(placement=placement, action=action, changed_fields=changed)
