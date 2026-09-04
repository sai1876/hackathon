from pathlib import Path
from uuid import uuid5, NAMESPACE_URL
import json, sys
sys.path.insert(0,r'D:\aegisgrid\backend')
from dotenv import load_dotenv
load_dotenv(r'D:\aegisgrid\backend\.env')
from database import supabase

groups={
'User western group':'Madhapur PS|COD|VR Nagar|Whisper Valley|Khajaguda|TCS X Roads|Cyber Gateway|Cyber Towers|Gachibowli|HCU T Junction|Kothaguda T Junction|Kondapur|Shilpa Park T Junction|Silicon Towers|Khanamet|Malaysian Township|Miyapur X Roads|Kukatpally Cross Road|Jubilee Hills Checkpost|Aramghar X Roads',
'User central group':'Masab Tank|Khaja Mansion Road 1/12|MBNR X Road|Upper Tank Bund|Old Saifabad|Ayodhya|Humayun Nagar|Rethibowli/Nanal Nagar|Tolichowki O.P.|Raidurgam|MJ Market|Taj Island|Nampally Traffic Complex (PCR)|SBH Gunfoundry|Abids GPO|Abids A1 Nampally Chapel Road|Liberty Cross Road|Khairatabad Junction|Basheerbagh X Roads',
'User northern group':'Patny Junction|C.T.O.|Sangeeth X Roads|Bowenpally|Paradise|Begumpet (H.P.S.)|1/10 Junction|Tajmahal Junction',
'User eastern/southern group':'S.R. Nagar|Maithrivanam|Shalimar|Panjagutta|K.C.P.|Taj Krishna|RTC X Roads|Moosarambagh|Uppal X Roads|Tarnaka|Dilsukhnagar|Chaderghat X Roads|Afzalgunj Junction'}
nodes=json.loads(Path(r'D:\aegisgrid-road\data\hyderabad\hyderabad_nodes.geojson').read_text(encoding='utf-8'))['features']
signals={str(n['properties']['osmid']):n for n in nodes if n['properties'].get('highway')=='traffic_signals'}
roads=json.loads(Path(r'D:\aegisgrid-road\data\hyderabad\hyderabad_roads.geojson').read_text(encoding='utf-8'))['features']
names={i:set() for i in signals}
for f in roads:
    p=f['properties']
    for k in ['u','v']:
        i=str(p[k])
        if i in names and isinstance(p.get('name'),str): names[i].add(p['name'])
uid=lambda name:str(uuid5(NAMESPACE_URL,'aegisgrid:'+name))
source=uid('hyderabad-osm-traffic-signals-v1'); user_source=uid('user-junction-list-2026-09-03')
sources=[dict(id=source,source_name='OpenStreetMap Hyderabad traffic signal nodes',source_type='TRAFFIC_SIGNAL_LOCATIONS',provenance='REAL',provider='OpenStreetMap',metadata={'file':'hyderabad_nodes.geojson','filter':'highway=traffic_signals','note':'Mapped asset locations; not live signal telemetry'}),dict(id=user_source,source_name='User supplied Hyderabad signal junction list',source_type='JUNCTION_NAME_REFERENCE',provenance='DERIVED',provider='User supplied',metadata={'note':'Names and groups supplied in chat; coordinates unresolved; groups are not verified jurisdiction boundaries'})]
rows=[]
for i,n in signals.items():
    lon,lat=n['geometry']['coordinates']; road_names=sorted(names[i])
    rows.append(dict(id=uid('osm-signal:'+i),external_id='OSM:signal:'+i,name='Signal near '+ ' / '.join(road_names) if road_names else 'OSM traffic signal '+i,location=f'SRID=4326;POINT({lon} {lat})',junction_type='TRAFFIC_SIGNAL',provenance='REAL',source_id=source,metadata={'osm_node_id':i,'osm_tag':'highway=traffic_signals','road_names':road_names,'location_status':'OSM_MAPPED','signal_state':'UNKNOWN','note':'An OSM signal node may represent one approach, not an entire junction; name is road context, not a confirmed junction-name match'}))
for group,items in groups.items():
    for name in items.split('|'):
        rows.append(dict(id=uid('requested-signal:'+name),external_id='USER:JUNCTION:'+name,name=name,location=None,junction_type='TRAFFIC_SIGNAL_REFERENCE',provenance='DERIVED',source_id=user_source,metadata={'location_status':'NEEDS_COORDINATES','user_group':group,'note':'User-provided junction name; do not place on map until coordinates are verified'}))
Path('signal-import-review.json').write_text(json.dumps({'sources':sources,'junctions':rows},indent=2),encoding='utf-8')
if '--apply' in sys.argv:
    supabase.table('data_sources').upsert(sources,on_conflict='id').execute()
    for start in range(0,len(rows),100): supabase.table('junctions').upsert(rows[start:start+100],on_conflict='id').execute()
    result=supabase.table('junctions').select('id',count='exact').limit(1).execute()
    print('Database junction records:',result.count)
print('Mapped signal nodes:',len(signals),'Unlocated user junction names:',len(rows)-len(signals))
