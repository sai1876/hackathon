"""Regression tests for physical-road closures and explicit route targeting."""
import unittest
from unittest.mock import patch
from copy import deepcopy
import networkx as nx
from shapely.geometry import LineString
from fastapi.testclient import TestClient
from main import app
from graph_manager import graph_manager
from incident_engine import incident_engine
from operations_engine import operations
from route_engine import route_engine

class BlockageTests(unittest.TestCase):
    def setUp(self):
        self.g=nx.MultiDiGraph()
        self.points={'a':(78.48,17.38),'b':(78.49,17.38),'c':(78.50,17.38),'d':(78.49,17.39)}
        for n,(x,y) in self.points.items(): self.g.add_node(n,x=x,y=y)
        for u,v,cost in [('a','b',10),('b','c',10),('a','d',25),('d','c',25)]:
            self.edge(u,v,cost); self.edge(v,u,cost)
        self.saved_incidents=incident_engine.active_incidents
        self.saved_ops=deepcopy(operations.__dict__)
        incident_engine.active_incidents={}; operations.__init__()
        self.client=TestClient(app)
        self.mock=patch.object(graph_manager,'get_graph',side_effect=lambda *a:self.g.copy()); self.mock.start()
    def tearDown(self):
        self.mock.stop(); incident_engine.active_incidents=self.saved_incidents
        operations.__dict__.clear(); operations.__dict__.update(self.saved_ops)
    def edge(self,u,v,cost=10,key=0,coords=None):
        self.g.add_edge(u,v,key=key,external_id=f'{u}-{v}-{key}',geometry=LineString(coords or [self.points[u],self.points[v]]),length_m=100,base_travel_time_sec=cost,current_cost=cost)
    def create(self,lon,lat=17.38,**extra):
        r=self.client.post('/incidents',json=dict(incident_type='ROAD_BLOCKAGE',lat=lat,lon=lon,**extra))
        self.assertEqual(r.status_code,200,r.text); return r.json()
    def route(self,start='a',end='c'):
        return self.client.post('/route',json={name:{'lon':self.points[n][0],'lat':self.points[n][1]} for name,n in [('start',start),('end',end)]})
    def test_two_blockages_force_detour_in_both_directions_and_restore(self):
        a=self.create(78.485); b=self.create(78.495)
        for start,end in [('a','c'),('c','a')]:
            r=self.route(start,end); self.assertEqual(r.status_code,200,r.text)
            data=r.json(); self.assertEqual(data['eta_seconds'],58 if start=='a' else 55)
            closed={edge for i in data['incidents'] for edge in i['affected_edges']}
            self.assertEqual(closed,{'a-b-0','b-a-0','b-c-0','c-b-0'})
            self.assertFalse(closed & {e['external_id'] for e in data['route_edges']})
            self.assertEqual(len(data['route_segments']['features']),2)
        self.client.delete('/incidents/'+a['id']); self.assertEqual(self.route().json()['eta_seconds'],58)
        self.client.delete('/incidents/'+b['id']); self.assertEqual(self.route().json()['eta_seconds'],20)
        self.assertEqual(self.g['a']['b'][0]['current_cost'],10)
    def test_duplicates_closed_but_parallel_geometry_remains_usable(self):
        self.edge('a','b',key=1)
        self.edge('a','b',cost=15,key=2,coords=[self.points['a'],(78.485,17.3804),self.points['b']])
        self.create(78.485); r=self.route().json()
        self.assertIn('a-b-2',{e['external_id'] for e in r['route_edges']})
        closed=set(r['incidents'][0]['affected_edges'])
        self.assertIn('a-b-1',closed); self.assertNotIn('a-b-2',closed)
    def test_selected_route_edge_wins_over_nearer_side_street(self):
        self.points['x']=(78.485,17.38005); self.points['y']=(78.487,17.38005)
        for n in ['x','y']: self.g.add_node(n,x=self.points[n][0],y=self.points[n][1])
        self.edge('x','y')
        i=self.create(78.486,17.38005,target_edge_id='a-b-0')
        r=self.route().json()
        matched=next(x for x in r['incidents'] if x['id']==i['id'])
        self.assertEqual(set(matched['affected_edges']),{'a-b-0','b-a-0'})
        self.assertEqual(matched['match_source'],'SELECTED_ROUTE_EDGE')
        self.assertEqual(r['eta_seconds'],58)
    def test_pinned_match_does_not_jump_to_other_road_in_different_bbox(self):
        self.create(78.485); self.route()
        self.g.remove_edge('a','b',0); self.g.remove_edge('b','a',0)
        updated=route_engine.apply_incidents(self.g.copy())
        self.assertEqual(incident_engine.list_incidents()[0]['affected_edges'],[])
        self.assertTrue(all(d['current_cost']!=float('inf') for *_,d in updated.edges(data=True)))
    def test_reverse_closure_cannot_be_bypassed_by_endpoint_splitting(self):
        self.create(78.485)
        r=self.client.post('/route',json={'start':{'lat':17.38,'lon':78.487},'end':{'lat':17.38,'lon':78.483}})
        self.assertEqual(r.status_code,400)
    def test_resolving_one_of_overlapping_incidents_does_not_reopen_road(self):
        a=self.create(78.485); self.create(78.485)
        self.client.delete('/incidents/'+a['id']); self.assertEqual(self.route().json()['eta_seconds'],58)

if __name__=='__main__': unittest.main()
