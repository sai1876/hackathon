import unittest
from unittest.mock import patch
import scenario_runtime as r
import test_shared_scenario as fixtures
class StationTargetTests(unittest.TestCase):
 def stations(self):
  return [dict(id=i,kind='METRO_STATION',name=i,longitude=78.45,latitude=17.42,spec=dict(gtfs_stop_id=i)) for i in ['A','B']]
 def test_targeted_metro_needs_no_polygon_and_affects_only_selected_station(self):
  s=fixtures.Tests().state();s['seconds']=10
  with patch.object(r,'assets',self.stations()):
   r.act(s,r.Command(action='METRO',station_ids=['A'],multiplier=2,request_id='station-target-1'))
   self.assertEqual(s['scenarios'][0]['polygon'],[])
   self.assertEqual(r.station_effects(s)['A']['factor'],2)
   self.assertEqual(r.station_effects(s)['B']['factor'],1)
   with patch('emergency_api.sync'),patch('weather_effects.shared_zones',[]),patch.object(r,'routing_signature',None):
    r.publish(s)
    import weather_effects
    self.assertEqual(weather_effects.shared_zones,[])
   s['seconds']+=3601
   self.assertEqual(r.station_effects(s)['A']['factor'],1)
 def test_missing_or_unknown_station_rejected(self):
  with patch.object(r,'assets',self.stations()):
   for ids in [[],['missing']]:
    with self.assertRaises(ValueError):r.act(fixtures.Tests().state(),r.Command(action='METRO',station_ids=ids,request_id='station-target-2'))
 def test_station_demand_changes_arrivals_not_static_queue_number(self):
  s=fixtures.Tests().state();s['start_seconds']=0
  stations=self.stations();profiles=[dict(kind='passenger_entries_per_15min_weekday',asset_id=i,values=[900]*96) for i in ['A','B']]
  with patch.object(r,'assets',stations),patch.object(r,'profiles',profiles),patch.object(r,'timetable',dict(trips=[],stops={})),patch('metro_engine.active_services',return_value={'WK'}):
   r.act(s,r.Command(action='METRO',station_ids=['A'],multiplier=2,request_id='station-target-3'))
   r.passengers(s,0,10)
   self.assertEqual(s['queues']['A']['arrived'],20)
   self.assertEqual(s['queues']['B']['arrived'],10)
   r.act(s,r.Command(action='REMOVE',target_id=s['scenarios'][0]['id'],request_id='station-target-4'))
   r.passengers(s,10,20)
   self.assertEqual(s['queues']['A']['arrived'],30)
   self.assertEqual(s['queues']['B']['arrived'],20)
if __name__=='__main__':unittest.main()
