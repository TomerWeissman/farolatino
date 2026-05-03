"""GET /api/skills — list of available @-skills for the autocomplete."""
from __future__ import annotations

from fastapi import APIRouter

from api.schemas import SkillSummary
from core.skill_registry import list_skills

router = APIRouter()


@router.get("/skills", response_model=list[SkillSummary])
def get_skills() -> list[SkillSummary]:
    return [
        SkillSummary(
            slug=s.slug,
            name=s.name or s.slug,
            description=s.description or "",
        )
        for s in list_skills()
    ]
