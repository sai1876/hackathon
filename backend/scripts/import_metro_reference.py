from pathlib import Path
import sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from database import supabase
lines=[('RED','#ee5868','Miyapur|JNTU College|KPHB Colony|Kukatpally|Dr. B. R. Ambedkar Balanagar|Moosapet|Bharat Nagar|Erragadda|ESI Hospital|S. R. Nagar|Ameerpet|Punjagutta|Irrum Manzil|Khairatabad|Lakdi-ka-pul|Assembly|Nampally|Gandhi Bhavan|Osmania Medical College|MG Bus Station|Malakpet|New Market|Musarambagh|Dilsukhnagar|Chaitanyapuri|Victoria Memorial|L. B. Nagar'),('BLUE','#36b6ef','Nagole|Uppal|Stadium|NGRI|Habsiguda|Tarnaka|Mettuguda|Secunderabad East|Parade Ground|Paradise|Rasoolpura|Prakash Nagar|Begumpet|Ameerpet|Madhura Nagar|Yusufguda|Road No. 5 Jubilee Hills|Jubilee Hills Check Post|Peddamma Gudi|Madhapur|Durgam Cheruvu|HITEC City|Raidurg'),('GREEN','#36ca8e','JBS Parade Ground|Secunderabad West|Gandhi Hospital|Musheerabad|RTC X Roads|Chikkadpally|Narayanaguda|Sultan Bazar|MG Bus Station')]
network=[dict(id=id,color=color,stations=names.split('|')) for id,color,names in lines]

from uuid import uuid5,NAMESPACE_URL
source_id=str(uuid5(NAMESPACE_URL,'aegisgrid:metro-pdf-reference-v1'))
run_id=str(uuid5(NAMESPACE_URL,'aegisgrid:metro-reference-exercise-v1'))
supabase.table('data_sources').upsert(dict(id=source_id,source_name='Hyderabad Metro PDF network reference',source_type='METRO_SCHEMATIC',provenance='REAL',provider='User supplied HMRRouteMap_new.pdf',metadata={'network':network,'note':'Station sequence from reference PDF; no live train feed or geographic coordinates'})).execute()
if not supabase.table('simulation_runs').select('id').eq('id',run_id).execute().data:
 supabase.table('simulation_runs').insert(dict(id=run_id,name='Metro reference-map exercise',scenario_type='METRO_SYNTHETIC',status='PAUSED',configuration={'version':0,'source':'HMRRouteMap_new.pdf (user supplied)','network':network,'state':{'running':False,'speed':1,'sim_seconds':0,'last_clock':time.time()}})).execute()
print('Imported',len(network),'lines;',len(set(s for l in network for s in l['stations'])),'distinct named stations. Simulation paused.')
