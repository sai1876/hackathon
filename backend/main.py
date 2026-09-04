import logging
import os
from threading import RLock
from fastapi import (
    FastAPI,
    HTTPException
)

from fastapi.middleware.cors import (
    CORSMiddleware
)

from models import (
    RouteRequest,
    IncidentCreate
)

from route_engine import route_engine
from incident_engine import incident_engine
from operations_engine import operations, CorridorCreate, Decision, PositionUpdate, ExerciseCreate, Advance


app = FastAPI(
    title="AegisGrid API",
    version="0.1.0"
)
runtime_lock = RLock()


app.add_middleware(
    CORSMiddleware,

    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if origin.strip()],

    allow_credentials=False,

    allow_methods=["*"],

    allow_headers=["*"]
)


@app.get("/")
def root():

    return {
        "system": "AegisGrid",
        "status": "ONLINE"
    }


@app.get("/health")
def health():

    return {
        "status": "healthy",

        "service":
            "aegisgrid-backend",

        "routing_engine":
            "NetworkX",

        "database":
            "Supabase/PostGIS",

        "road_source":
            "OpenStreetMap"
    }


@app.get("/ready")
def ready():
    import scenario_runtime as shared_runtime
    is_ready = shared_runtime.check_readiness()
    if not is_ready:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "service": "aegisgrid-backend",
                "detail": shared_runtime.failure or "Shared scenario database is loading or unavailable"
            }
        )
    return {
        "status": "ready",
        "service": "aegisgrid-backend",
        "scenario_version": shared_runtime.current["version"] if shared_runtime.current else None,
        "sim_seconds": shared_runtime.current["state"]["seconds"] if shared_runtime.current else None
    }



@app.post("/route")
def calculate_route(
    request: RouteRequest
):

    try:

        with runtime_lock:
            return (
            route_engine
            .calculate_route(
                request
            )
        )

    except RuntimeError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )
    except Exception:
        logging.exception("Route request failed")
        raise HTTPException(status_code=503, detail="Routing data is unavailable. Please retry shortly.")


@app.get("/incidents")
def list_incidents():

    with runtime_lock:
        return incident_engine.list_incidents()


@app.post("/incidents")
def create_incident(
    incident: IncidentCreate
):

    with runtime_lock:
        result = incident_engine.create_incident(incident)
        operations.incident_changed(result, "CREATED")
        return result


@app.delete(
    "/incidents/{incident_id}"
)
def resolve_incident(
    incident_id: str
):

    with runtime_lock:
        result = incident_engine.resolve_incident(incident_id)
        if result:
            operations.incident_changed(result, "RESOLVED")

    if result is None:

        raise HTTPException(
            status_code=404,
            detail="Incident not found"
        )

    return {
        "status": "RESOLVED",
        "incident": result
    }


@app.get("/operations")
def operational_snapshot():
    with runtime_lock:
        return operations.snapshot()


@app.post("/corridors")
def request_corridor(payload: CorridorCreate):
    with runtime_lock:
        return operations.create(payload)


@app.post("/corridors/{identifier}/decision")
def corridor_decision(identifier: str, payload: Decision):
    with runtime_lock:
        return operations.decide(identifier, payload)


@app.post("/corridors/{identifier}/reevaluate")
def reevaluate_corridor(identifier: str, payload: Advance):
    with runtime_lock:
        item = operations.get(identifier, payload.version)
        if item["status"] not in ("PENDING", "APPROVED"):
            raise HTTPException(409, "This corridor is closed")
        operations.compute(item, "Operator requested route review")
        return operations.snapshot()


@app.post("/corridors/{identifier}/position")
def report_position(identifier: str, payload: PositionUpdate):
    with runtime_lock:
        return operations.position(identifier, payload)


@app.post("/simulation/events")
def create_exercise(payload: ExerciseCreate):
    with runtime_lock:
        return operations.exercise(payload)


@app.post("/simulation/corridors/{identifier}/advance")
def advance_exercise(identifier: str, payload: Advance):
    with runtime_lock:
        return operations.advance(identifier, payload)


from electric_engine import router as electric_router
app.include_router(electric_router)


# Rain scenarios change road travel costs. Refresh active corridors independently
# of the electrical clock so a graph fetch cannot stall simulation ticks.
import weather_effects
def refresh_weather_corridors():
    with runtime_lock:
        for item in operations.corridors.values():
            if item["status"] in ("PENDING", "APPROVED"):
                operations.compute(item, "Synthetic polygon rainfall changed road travel costs")
weather_effects.on_change = refresh_weather_corridors

from command_data import router as command_data_router
app.include_router(command_data_router)

from traffic.route_calibration import router as calibration_router
app.include_router(calibration_router)

from metro_engine import router as metro_router
app.include_router(metro_router)

from scenario_runtime import router as scenario_router, start as start_scenario, stop as stop_scenario
app.include_router(scenario_router)
app.router.add_event_handler("startup", start_scenario)
app.router.add_event_handler("shutdown", stop_scenario.set)

from google_weather import router as google_weather_router
app.include_router(google_weather_router)

from google_operations import router as google_operations_router
app.include_router(google_operations_router)

from emergency_api import router as emergency_router, start as start_emergency, stop as stop_emergency
app.include_router(emergency_router)
from metro_operations import router as metro_operations_router
app.include_router(metro_operations_router)
from metro_service_days import router as metro_days_router
app.include_router(metro_days_router)
from signal_operations import router as signals_router
app.include_router(signals_router)
app.router.add_event_handler("startup",start_emergency)
app.router.add_event_handler("shutdown",stop_emergency.set)
