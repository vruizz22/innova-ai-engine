from __future__ import annotations

from pydantic import BaseModel, Field


class IrtItemParams(BaseModel):
    item_id: str
    a: float = Field(
        default=1.0,
        ge=0.1,
        le=3.0,
        description="Discrimination parameter")
    b: float = Field(
        default=0.0,
        ge=-3.0,
        le=3.0,
        description="Difficulty parameter")
    calibrated: bool = False
