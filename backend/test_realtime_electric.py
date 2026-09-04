import tempfile
import time
import unittest
from pathlib import Path
import networkx as nx
from shapely.geometry import LineString
from fastapi import HTTPException
from electric_engine import ElectricWorld, ElectricAction
import weather_effects

class RealtimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.world = ElectricWorld(Path(self.temp.name)/'state.sqlite3')
    def tearDown(self):
        weather_effects.publish([])
        self.temp.cleanup()
    def act(self, action, **options):
        return self.world.act(ElectricAction(version=self.world.snapshot()['version'], action=action, operator='Test', note='Synthetic test', **options))
    def step(self, seconds):
        import json
        with self.world.connect() as db:
            state = self.world.read(db)
            self.world.advance_seconds(state, seconds)
            db.execute('UPDATE world SET payload=? WHERE id=1',(json.dumps(state),))
        return self.world.snapshot()
    def test_load_rolls_up_and_protection_requires_sustained_overload(self):
        before=self.world.snapshot()
        after=self.act('LOAD',asset_id='DT-00001',load_percent=200)
        self.assertGreater(after['telemetry']['F-001']['demand_kw'],before['telemetry']['F-001']['demand_kw'])
        self.assertEqual(after['telemetry']['F-002'],before['telemetry']['F-002'])
        self.assertEqual(self.step(9)['trips'],[])
        tripped=self.step(1)
        self.assertIn('DT-00001',tripped['trips'])
        self.assertIn('SIG-001',tripped['off_ids'])
        self.assertNotIn('F-001',tripped['trips'])
        with self.assertRaises(HTTPException): self.act('RESET_PROTECTION',asset_id='DT-00001')
        self.act('LOAD',asset_id='DT-00001',load_percent=100)
        self.assertNotIn('DT-00001',self.act('RESET_PROTECTION',asset_id='DT-00001')['off_ids'])
    def test_clock_advances_once_pauses_and_handles_interruption(self):
        state=self.act('CLOCK',running=True,speed=5)
        now=state['last_tick']+1.1
        self.world.tick(now)
        first=self.world.snapshot()
        self.assertEqual(first['seconds'],5)
        self.world.tick(now)
        self.assertEqual(self.world.snapshot()['seconds'],5)
        self.world.tick(now+30)
        self.assertFalse(self.world.snapshot()['running'])
        self.world.tick(now+40)
        self.assertEqual(self.world.snapshot()['seconds'],5)
        self.assertEqual(self.world.snapshot()['version'],state['version'])
    def test_rain_locality_accumulation_road_delay_and_recovery(self):
        asset=self.world.assets['DT-00001']; x,y=asset['lon'],asset['lat']
        polygon=[[x-.002,y-.002],[x+.002,y-.002],[x+.002,y+.002],[x-.002,y+.002]]
        baseline=self.world.snapshot()
        wet=self.act('RAIN',polygon=polygon,intensity=100)
        self.assertGreater(wet['telemetry']['DT-00001']['demand_kw'],baseline['telemetry']['DT-00001']['demand_kw'])
        outside=next(i for i,a in self.world.assets.items() if a['kind']=='DISTRIBUTION_TRANSFORMER' and abs(a['lon']-x)>.01)
        self.assertEqual(wet['telemetry'][outside],baseline['telemetry'][outside])
        wet=self.step(60)
        self.assertGreater(wet['rain_effects'][0]['water_mm'],0)
        self.assertGreater(wet['rain_effects'][0]['metro_demand_index'],100)
        weather_effects.publish(self.world.weather())
        g=nx.MultiDiGraph()
        g.add_edge(1,2,current_cost=10,geometry=LineString([(x-.001,y),(x+.001,y)]))
        g.add_edge(2,1,current_cost=float('inf'),geometry=LineString([(x-.001,y),(x+.001,y)]))
        g.add_edge(3,4,current_cost=10,geometry=LineString([(x+.1,y),(x+.11,y)]))
        weather_effects.apply(g)
        self.assertGreater(g[1][2][0]['current_cost'],10)
        self.assertEqual(g[2][1][0]['current_cost'],float('inf'))
        self.assertEqual(g[3][4][0]['current_cost'],10)
        rain_id=wet['rain_effects'][0]['id']
        self.act('RAIN_INTENSITY',asset_id=rain_id,intensity=0)
        drained=self.step(60)
        self.assertLess(drained['rain_effects'][0]['water_mm'],wet['rain_effects'][0]['water_mm'])
        self.act('REMOVE_RAIN',asset_id=rain_id)
        self.assertEqual(self.world.snapshot()['telemetry'][outside],baseline['telemetry'][outside])
    def test_invalid_polygons_and_running_manual_step_rejected(self):
        with self.assertRaises(HTTPException): self.act('RAIN',polygon=[[78.4,17.4],[78.5,17.5]])
        self.act('CLOCK',running=True)
        with self.assertRaises(HTTPException): self.act('ADVANCE')

if __name__=='__main__': unittest.main()
