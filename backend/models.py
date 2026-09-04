from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class IncidentType(str, Enum):
    ROAD_BLOCKAGE = "ROAD_BLOCKAGE"
    ACCIDENT = "ACCIDENT"
    WATERLOGGING = "WATERLOGGING"
    SIGNAL_FAILURE = "SIGNAL_FAILURE"


class Coordinate(BaseModel):
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lon: float = Field(ge=-180, le=180, allow_inf_nan=False)


class RouteRequest(BaseModel):
    alternatives: int = Field(default=3, ge=1, le=3)
    start: Coordinate
    end: Coordinate

    search_radius_m: int = Field(
        default=5000,
        ge=1000,
        le=20000
    )


class IncidentCreate(BaseModel):
    incident_type: IncidentType

    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lon: float = Field(ge=-180, le=180, allow_inf_nan=False)

    severity: int = Field(
        default=3,
        ge=1,
        le=5
    )

    target_edge_id: Optional[str] = Field(default=None, min_length=1, max_length=256)
    direction: Optional[str] = None
    lanes_blocked: Optional[int] = None
    description: Optional[str] = None
    provenance: str = Field(default="SYNTHETIC", pattern="^(SYNTHETIC|OPERATOR_REPORTED)$")
