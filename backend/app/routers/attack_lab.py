"""Attack Simulation Lab API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..security import get_current_user
from ..services import attack_lab

router = APIRouter(prefix="/api/attack-lab", tags=["attack-lab"])


@router.get("/scenarios")
def scenarios(
    platform: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=100),
    user: str = Depends(get_current_user),
):
    items = attack_lab.list_scenarios(platform, q)
    return {"items": items, "total": len(items)}


@router.get("/scenarios/{scenario_id}")
def scenario(scenario_id: str, user: str = Depends(get_current_user)):
    item = attack_lab.get_scenario(scenario_id)
    if item is None:
        raise HTTPException(404, "Attack scenario not found")
    return item


@router.post("/scenarios/{scenario_id}/simulate")
def simulate(scenario_id: str, user: str = Depends(get_current_user)):
    result = attack_lab.simulate(scenario_id)
    if result is None:
        raise HTTPException(404, "Attack scenario not found")
    return result
