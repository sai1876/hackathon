import weather_effects
"""Process-local operational workflow. No signal actuation or live telemetry.

All calls are serialized by main.runtime_lock, including legacy incident writes.
Simulation advances only through explicit server commands, never browser animation.
"""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from models import Coordinate, RouteRequest, IncidentCreate
from route_engine import route_engine
from incident_engine import incident_engine


def now():
    return datetime.now(timezone.utc).isoformat()


class CorridorCreate(RouteRequest):
    ambulance_id: str = Field(min_length=1, max_length=60, pattern=r".*\S.*")
    destination_name: str = Field(min_length=1, max_length=120, pattern=r".*\S.*")
    priority: Literal["CRITICAL", "URGENT", "TRANSFER"] = "URGENT"
    provenance: Literal["OPERATOR_REPORTED", "SYNTHETIC"] = "OPERATOR_REPORTED"
    request_key: str = Field(min_length=8, max_length=80)


class Decision(BaseModel):
    version: int = Field(ge=1)
    decision: Literal["APPROVE", "REJECT", "COMPLETE"]
    operator: str = Field(min_length=1, max_length=80, pattern=r".*\S.*")
    reason: str = Field(min_length=3, max_length=500, pattern=r".*\S.*")


class PositionUpdate(Coordinate):
    version: int = Field(ge=1)


class ExerciseCreate(Coordinate):
    target_edge_id: str | None = Field(default=None, min_length=1, max_length=256)
    incident_type: Literal["ROAD_BLOCKAGE", "ACCIDENT", "WATERLOGGING", "SIGNAL_FAILURE"]


class Advance(BaseModel):
    version: int = Field(ge=1)
    seconds: int = Field(default=15, ge=1, le=60)


class OperationsEngine:
    def __init__(self):
        self.corridors = {}
        self.events = []
        self.exercises = {}
        self.revision = 0

    def event(self, kind, subject, detail, provenance="DERIVED", actor="SYSTEM"):
        self.revision += 1
        self.events.append(dict(id=self.revision, at=now(), kind=kind, subject=subject,
                                detail=detail, provenance=provenance, actor=actor))
        self.events = self.events[-500:]

    def get(self, identifier, version=None):
        item = self.corridors.get(identifier)
        if not item:
            raise HTTPException(404, "Corridor request not found")
        if version is not None and item["version"] != version:
            raise HTTPException(409, "Request changed. Refresh and review the latest route before acting.")
        return item

    def compute(self, item, cause):
        previous = item.get("route")
        try:
            result = deepcopy(route_engine.calculate_route(RouteRequest(
                start=Coordinate(**item["position"]), end=Coordinate(**item["end"]))))
            item["route"] = result
            item["route_error"] = None
            item.setdefault("initial_eta_seconds", result["eta_seconds"])
            item["eta_change_seconds"] = round(result["eta_seconds"] - previous["eta_seconds"], 2) if previous else 0
            changed = previous is None or previous["route"]["geometry"] != result["route"]["geometry"]
            item["route_state"] = "AVAILABLE"
            if changed and item["status"] == "APPROVED":
                item["status"] = "PENDING"
                self.event("REAPPROVAL_REQUIRED", item["id"], "Route changed; movement paused until traffic approves the revised corridor.")
            self.event("ROUTE_EVALUATED", item["id"], f"{cause}: {result['distance_m']} m; {result['eta_seconds']} s modeled travel; change {item['eta_change_seconds']:+g} s from previous evaluation.")
        except Exception as error:
            # Never keep a formerly approved path when revalidation fails.
            item["route"] = None
            item["route_state"] = "UNAVAILABLE"
            item["route_error"] = str(error) if isinstance(error, RuntimeError) else "Routing service unavailable. Retry route review."
            if item["status"] == "APPROVED":
                item["status"] = "PENDING"
            self.event("ROUTE_UNAVAILABLE", item["id"], f"{cause}: {item['route_error']}")
        item["version"] += 1
        item["updated_at"] = now()

    def create(self, payload):
        for item in self.corridors.values():
            if item["request_key"] == payload.request_key:
                if item["request_payload"] != payload.model_dump():
                    raise HTTPException(409, "Request key already used for different input")
                return deepcopy(item)
        identifier = str(uuid4())
        item = dict(id=identifier, **payload.model_dump(), request_payload=payload.model_dump(),
                    status="PENDING", version=1, created_at=now(), updated_at=now(),
                    position=payload.start.model_dump(), position_at=now(),
                    position_provenance=payload.provenance, route=None, decisions=[])
        self.corridors[identifier] = item
        self.event("CORRIDOR_REQUESTED", identifier, f"{payload.ambulance_id} requests {payload.destination_name}; {payload.priority}.", payload.provenance, "AMBULANCE_OPERATOR")
        self.compute(item, "Initial request")
        return deepcopy(item)

    def decide(self, identifier, payload):
        item = self.get(identifier, payload.version)
        expected = "APPROVED" if payload.decision == "COMPLETE" else "PENDING"
        if item["status"] != expected:
            raise HTTPException(409, f"This action requires a {expected} corridor")
        if payload.decision == "APPROVE" and not item.get("route"):
            raise HTTPException(409, "No available route. Re-evaluate before approval.")
        item["status"] = {"APPROVE": "APPROVED", "REJECT": "REJECTED", "COMPLETE": "COMPLETED"}[payload.decision]
        item["decisions"].append(dict(**payload.model_dump(), at=now()))
        item["version"] += 1
        item["updated_at"] = now()
        self.event("CORRIDOR_" + item["status"], identifier, payload.reason, "OPERATOR_REPORTED", payload.operator)
        return deepcopy(item)

    def incident_changed(self, incident, action):
        self.event("INCIDENT_" + action, incident["id"], incident.get("description") or incident["incident_type"], incident["provenance"], "OPERATOR")
        for item in self.corridors.values():
            if item["status"] in ("PENDING", "APPROVED"):
                self.compute(item, f"Incident {incident['id']} {action.lower()}")
        if action == "RESOLVED":
            for exercise in self.exercises.values():
                if exercise["incident_id"] == incident["id"]:
                    exercise["status"] = "RESOLVED"
                    self.event("EXERCISE_RESOLVED", exercise["id"], "Operator resolved the exercise incident; active corridors re-evaluated.", "SYNTHETIC")

    def exercise(self, payload):
        incident = incident_engine.create_incident(IncidentCreate(**payload.model_dump(), severity=3,
            provenance="SYNTHETIC", description="SYNTHETIC backend event exercise; closure model, not a field observation"))
        identifier = str(uuid4())
        self.exercises[identifier] = dict(id=identifier, incident_id=incident["id"], status="AWAITING_ACTION", created_at=now(), provenance="SYNTHETIC")
        self.incident_changed(incident, "CREATED")
        self.event("EXERCISE_AWAITING_ACTION", identifier, "Incident created → active routes evaluated → traffic review required. Resolve the incident to restore road availability.", "SYNTHETIC")
        return deepcopy(self.exercises[identifier])

    def position(self, identifier, payload):
        item = self.get(identifier, payload.version)
        if item["status"] not in ("PENDING", "APPROVED"):
            raise HTTPException(409, "This corridor is closed")
        if item["provenance"] == "SYNTHETIC":
            raise HTTPException(409, "Exercise positions advance with the simulation command")
        item["position"] = dict(lat=payload.lat, lon=payload.lon)
        item["position_at"] = now()
        item["position_provenance"] = "OPERATOR_REPORTED"
        # A reported relocation requires a fresh corridor review.
        if item["status"] == "APPROVED":
            item["status"] = "PENDING"
        self.event("POSITION_REPORTED", identifier, "Operator reported a location; review route from this position.", "OPERATOR_REPORTED", "AMBULANCE_OPERATOR")
        self.compute(item, "Position update")
        return deepcopy(item)

    def advance(self, identifier, payload):
        item = self.get(identifier, payload.version)
        if item["status"] != "APPROVED" or item["provenance"] != "SYNTHETIC" or not item["route"]:
            raise HTTPException(409, "Only approved synthetic corridors can advance")
        route = item["route"]
        coords = route["route"]["geometry"]["coordinates"]
        lengths = [route_engine.haversine(a[1], a[0], b[1], b[0]) for a, b in zip(coords, coords[1:])]
        fraction = min(1, payload.seconds / max(route["eta_seconds"], 0.001))
        remaining = sum(lengths) * fraction
        index, point = 0, coords[-1]
        for index, length in enumerate(lengths):
            if remaining <= length and length > 0:
                t = remaining / length
                point = [coords[index][d] + t * (coords[index + 1][d] - coords[index][d]) for d in (0, 1)]
                break
            remaining -= length
        item["position"] = dict(lon=point[0], lat=point[1])
        item["position_at"] = now()
        item["position_provenance"] = "SYNTHETIC"
        if fraction >= 1:
            item["position"] = dict(lon=coords[-1][0], lat=coords[-1][1])
            item["status"] = "COMPLETED"
            item["route"] = None
            item["route_state"] = "COMPLETED"
        else:
            # Trim the approved geometry; no browser timer or arbitrary straight-line motion.
            route["route"]["geometry"]["coordinates"] = [point] + coords[index + 1:]
            route["eta_seconds"] = round(route["eta_seconds"] * (1 - fraction), 2)
            route["eta_minutes"] = round(route["eta_seconds"] / 60, 2)
            route["distance_m"] = round(route["distance_m"] * (1 - fraction), 2)
            route["distance_km"] = round(route["distance_m"] / 1000, 2)
            route["snapping"]["start"]["requested"] = item["position"]
            route["snapping"]["start"]["snapped"] = item["position"]
            route["snapping"]["start"]["distance_m"] = 0
        item["version"] += 1
        item["updated_at"] = now()
        self.event("EXERCISE_" + ("ARRIVED" if fraction >= 1 else "ADVANCED"), identifier,
                   f"Advanced {payload.seconds} exercise seconds along approved road geometry. Uniform speed derived from free-flow ETA, not GPS.", "SYNTHETIC")
        return deepcopy(item)

    def snapshot(self):
        incidents = deepcopy(incident_engine.list_incidents())
        recommendations = []
        for item in self.corridors.values():
            if item["status"] == "PENDING":
                recommendations.append(dict(id="review-" + item["id"], subject=item["id"], provenance="DERIVED",
                    action="Review corridor" if item.get("route") else "Re-evaluate unavailable route",
                    evidence=f"{item['ambulance_id']}: {item['route_state']}; request version {item['version']}",
                    consequence="Approval permits exercise movement and traffic map visibility. It does not operate signals."))
        for incident in incidents:
            recommendations.append(dict(id="incident-" + incident["id"], subject=incident["id"], provenance="DERIVED",
                action="Review incident; resolve when cleared", evidence=f"{incident['provenance']} / {incident['incident_type']}",
                consequence="Resolution removes its runtime closure and re-evaluates active corridors."))
        return deepcopy(dict(weather_zones=weather_effects.zones + weather_effects.shared_zones, revision=self.revision, server_time=now(), storage="PROCESS_LOCAL",
            corridors=list(self.corridors.values()), incidents=incidents, exercises=list(self.exercises.values()),
            events=self.events, recommendations=recommendations,
            provenance=dict(roads="OpenStreetMap / Supabase imported geometry", routing="NetworkX / free-flow estimates",
                            telemetry="No live traffic, GPS, weather or signal feed", persistence="Runtime state resets on backend restart; use one worker")))


operations = OperationsEngine()
