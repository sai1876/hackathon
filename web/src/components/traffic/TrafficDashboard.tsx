import EmergencyWorkspace from "@/components/emergency/EmergencyWorkspace";
import OperationsWorkspace from "./OperationsWorkspace";
export default function TrafficDashboard(){return <><EmergencyWorkspace role="traffic"/><details><summary>Existing incident and routing workspace</summary><OperationsWorkspace/></details></>;}
