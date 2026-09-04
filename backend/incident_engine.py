from datetime import datetime, timezone
from uuid import uuid4


class IncidentEngine:

    def __init__(self):
        self.active_incidents = {}

    def create_incident(self, incident):

        incident_id = str(uuid4())

        data = {
            "id": incident_id,

            "incident_type":
                incident.incident_type.value,

            "lat": incident.lat,
            "lon": incident.lon,

            "severity": incident.severity,

            "target_edge_id": incident.target_edge_id,
            "direction": incident.direction,

            "lanes_blocked":
                incident.lanes_blocked,

            "description":
                incident.description,

            "status": "ACTIVE",
            "provenance": incident.provenance,

            "created_at":
                datetime.now(
                    timezone.utc
                ).isoformat(),

            "affected_edges": []
        }

        self.active_incidents[
            incident_id
        ] = data

        return data

    def list_incidents(self):

        return list(
            self.active_incidents.values()
        )

    def resolve_incident(
        self,
        incident_id
    ):

        incident = (
            self.active_incidents
            .get(incident_id)
        )

        if not incident:
            return None

        incident["status"] = "RESOLVED"

        incident["resolved_at"] = (
            datetime.now(
                timezone.utc
            ).isoformat()
        )

        self.active_incidents.pop(
            incident_id
        )

        return incident


incident_engine = IncidentEngine()
