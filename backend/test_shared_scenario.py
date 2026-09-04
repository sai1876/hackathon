import unittest
from copy import deepcopy
from unittest.mock import patch
import networkx as nx
from shapely.geometry import LineString
import scenario_runtime as r
import weather_effects as w
class Tests(unittest.TestCase):
 def state(self):return dict(seconds=0,running=True,speed=1,last_wall=0,start_seconds=18000,service_date='2026-09-03',scenarios=[],events=[],outbox=[],requests=[],recommendations=[],assumptions=dict(block_depth_mm=150,drainage_dispatch_multiplier=2,pumping_max_load_fraction=.15))
 def rain(self):return dict(id='rain',kind='RAIN',polygon=[[78.4,17.4],[78.5,17.4],[78.5,17.5],[78.4,17.4]],start=0,end=3600,intensity=180,multiplier=1,water_mm=149.9,drainage=20,blocked=False,event_id=None)
 def test_water_pause(self):
  s=self.state();s['scenarios']=[self.rain()]
  with patch.object(r,'timetable',None):r.advance(s,5)
  self.assertAlmostEqual(s['scenarios'][0]['water_mm'],149.9+160*5/3600);self.assertTrue(s['scenarios'][0]['blocked'])
  old=deepcopy(s);s['running']=False;r.advance(s,10);self.assertEqual(s['seconds'],old['seconds']);self.assertEqual(s['scenarios'],old['scenarios'])
 def test_end_drains(self):
  s=self.state();z=self.rain();z.update(end=2,water_mm=20);s['scenarios']=[z]
  with patch.object(r,'timetable',None):r.advance(s,5)
  self.assertAlmostEqual(z['water_mm'],20+(180*2-20*5)/3600)
 def test_idempotency(self):
  s=self.state();z=self.rain();s['scenarios']=[z];s['recommendations']=[dict(id='rec',status='PENDING',scenario_id='rain')]
  c=r.Command(action='APPROVE',target_id='rec',request_id='test-approval');r.act(s,c);n=len(s['events']);r.act(s,c)
  self.assertTrue(z['drainage_approved']);self.assertEqual(n,len(s['events']))
 def test_blocked_edge(self):
  g=nx.MultiDiGraph();g.add_edge(1,2,geometry=LineString([(78.41,17.405),(78.45,17.405)]),current_cost=10)
  with patch.object(w,'zones',[]),patch.object(w,'shared_zones',[dict(id='x',polygon=self.rain()['polygon'],factor=2,blocked=True)]):w.apply(g)
  self.assertTrue(g[1][2][0]['blocked']);self.assertEqual(g[1][2][0]['current_cost'],float('inf'))
 def test_crossing_polygon(self):
  with self.assertRaises(ValueError):r.validate_polygon([[78.4,17.4],[78.5,17.5],[78.4,17.5],[78.5,17.4]])
 def test_passenger_conservation(self):
  s=self.state();s['start_seconds']=0
  trip=dict(id='T',block='B1',service='WK',times=[['A',0,5,0],['B',8,10,1]])
  feed=dict(stops={x:dict(parent='',name=x) for x in ['A','B']},trips=[trip])
  assets=[dict(id=x,kind='METRO_STATION',longitude=78.4,latitude=17.4,spec=dict(gtfs_stop_id=x)) for x in ['A','B']]+[dict(kind='METRO_TRAIN',spec=dict(block_id='B1',capacity_passengers=2))]
  profiles=[dict(kind='passenger_entries_per_15min_weekday',asset_id=x,values=[900]*96) for x in ['A','B']]
  with patch.object(r,'timetable',feed),patch.object(r,'assets',assets),patch.object(r,'profiles',profiles),patch('metro_engine.active_services',return_value={'WK'}):r.passengers(s,0,10)
  for q in s['queues'].values():self.assertEqual(q['waiting'],q['arrived']-q['boarded'])
  self.assertEqual(s['queues']['A']['boarded'],2);self.assertEqual(s['queues']['B']['alighted'],2);self.assertEqual(sum(t['passengers'] for t in s['trains'].values()),0)
if __name__=='__main__':unittest.main()


class PortalRegressionTests(unittest.TestCase):
 def test_start_service_uses_timetable(self):
  s=Tests().state();s['running']=False
  feed={'trips':[{'service':'WK','times':[['A',21600,21620,0]]}]}
  with patch.object(r,'timetable',feed),patch('metro_engine.active_services',return_value={'WK'}):
   r.act(s,r.Command(action='SERVICE_START',request_id='service-test'))
  self.assertEqual(s['start_seconds'],21600);self.assertTrue(s['running'])
 def test_service_start_never_rewinds_run(self):
  s=Tests().state();s['seconds']=60
  with self.assertRaises(ValueError):r.act(s,r.Command(action='SERVICE_START',request_id='service-test'))
 def test_electric_layer_uses_parent_relationships(self):
  assets=[dict(id='S',kind='SUBSTATION',name='Sub',parent_id=None,longitude=78.4,latitude=17.4,zone_id='Z',spec={'capacity_kva':100}),dict(id='T',kind='DISTRIBUTION_TRANSFORMER',name='Transformer',parent_id='S',longitude=78.41,latitude=17.41,zone_id='Z',spec={'capacity_kva':10})]
  with patch.object(r,'assets',assets),patch.object(r,'snapshot',return_value={}):result=r.electric_network()
  self.assertEqual(len(result['features']),3)
  self.assertEqual(result['features'][-1]['geometry']['coordinates'],[[78.4,17.4],[78.41,17.41]])


class ClockControlTests(unittest.TestCase):
 def test_advance_time_processes_rain_then_pauses(self):
  s=Tests().state();s['scenarios']=[Tests().rain()]
  with patch.object(r,'timetable',None):r.act(s,r.Command(action='SET_TIME',seconds=18600,request_id='clock-forward'))
  self.assertEqual(s['seconds'],600);self.assertFalse(s['running']);self.assertGreater(s['scenarios'][0]['water_mm'],149.9)
 def test_rewind_rejected(self):
  s=Tests().state();s['seconds']=600
  with self.assertRaises(ValueError):r.act(s,r.Command(action='SET_TIME',seconds=18000,request_id='clock-backward'))
