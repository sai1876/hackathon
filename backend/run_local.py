"""Run AegisGrid locally and restore the last captured legacy in-memory view.

The authoritative scenario runtime is already stored in Supabase. This small
compatibility restore only covers older incident/corridor endpoints until they
are migrated to that runtime.
"""
import json,sys
from pathlib import Path
from dotenv import load_dotenv
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
load_dotenv(HERE/'.env')
from main import app,runtime_lock
from operations_engine import operations
from incident_engine import incident_engine
import uvicorn
snapshot=HERE/'data'/'local-runtime-recovery.json'
if snapshot.exists():
 data=json.loads(snapshot.read_text(encoding='utf-8-sig'))
 with runtime_lock:
  operations.corridors={i['id']:i for i in data.get('corridors',[])}
  operations.exercises={i['id']:i for i in data.get('exercises',[])}
  operations.events=data.get('events',[]);operations.revision=data.get('revision',0)
  incident_engine.active_incidents={i['id']:i for i in data.get('incidents',[])}
uvicorn.run(app,host='127.0.0.1',port=8001)
