import unittest
from metro_engine import point_at,train_position,advance,active_services
class MetroTests(unittest.TestCase):
 def setUp(self):
  self.data={'shapes':{'r':[[78,17,0],[78.01,17,100],[78.01,17.01,200]]},'stops':{'a':{'name':'A'},'b':{'name':'B'}},'calendar':[dict(service_id='WK',monday='1',tuesday='1',wednesday='1',thursday='1',friday='1',saturday='0',sunday='0',start_date='20260902',end_date='20300101')]}
  self.trip=dict(id='t',block='b',route='RED',shape='r',headsign='B',times=[['a',28800,28830,0],['b',28930,28950,200]])
 def test_scheduled_departure_and_arrival(self):
  self.assertEqual(train_position(self.trip,28810,self.data)['status'],'DWELLING')
  moving=train_position(self.trip,28880,self.data);self.assertEqual(moving['status'],'IN_TRANSIT');self.assertEqual(moving['position'],[78.01,17])
  self.assertEqual(train_position(self.trip,28935,self.data)['status'],'DWELLING')
  self.assertIsNone(train_position(self.trip,28950,self.data))
 def test_shape_follows_bend_not_straight_station_line(self):
  self.assertEqual(point_at(self.data['shapes']['r'],100),[78.01,17])
 def test_pause_speed_restart_anchor(self):
  state=dict(running=True,speed=5,sim_seconds=28800,last_clock=100)
  self.assertEqual(advance(state,110)['sim_seconds'],28850)
  state['running']=False;self.assertEqual(advance(state,110)['sim_seconds'],28800)
 def test_calendar(self):
  self.assertEqual(active_services(self.data,'2026-09-03'),{'WK'});self.assertEqual(active_services(self.data,'2026-09-06'),set())
