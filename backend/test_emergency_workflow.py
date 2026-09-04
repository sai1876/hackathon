import unittest
from unittest.mock import patch
from copy import deepcopy
import emergency_model as m

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.s=dict(seconds=0,scenarios=[])
        self.events=[]
        self.mock=patch.object(m,'emit',side_effect=lambda s,k,p:self.events.append((k,deepcopy(p))))
        self.mock.start();self.addCleanup(self.mock.stop)
        self.do('REGISTER',vehicle='AMB-1')
    def do(self,action,**p):
        return m.apply(self.s,dict(action=action,actor='Officer',_assets=[],**p))
    def create(self):
        self.do('CREATE',id='trip',vehicle='AMB-1',destination='Hospital',end=dict(lat=17.4,lon=78.42),priority='CRITICAL',route=dict(source='TEST',coordinates=[[78.4,17.4],[78.42,17.4]]))
        return m.world(self.s)['trips']['trip']
    def tick(self,n):
        for _ in range(n):self.s['seconds']+=1;m.tick(self.s,1)
    def test_pending_trip_moves_with_acceleration(self):
        t=self.create();self.tick(1)
        self.assertEqual(t['status'],'PENDING');self.assertAlmostEqual(t['speed_mps'],1.4);self.assertGreater(t['travelled_m'],0)
    def test_rejection_requires_reason_and_normal_motion_continues(self):
        t=self.create()
        with self.assertRaises(ValueError):self.do('REJECT',trip_id='trip',plan_version=1)
        self.do('REJECT',trip_id='trip',plan_version=1,reason='Not eligible');self.tick(3)
        self.assertEqual(t['status'],'REJECTED');self.assertGreater(t['travelled_m'],0)
    def test_blockage_ahead_invalidates_but_behind_does_not(self):
        t=self.create();t['travelled_m']=900;t['position']=m.point_at(t['coordinates'],900)
        self.do('BLOCKAGE',id='behind',lat=17.4,lon=78.401,reason='Road closed behind')
        self.assertEqual(t['plan_version'],1)
        self.do('BLOCKAGE',id='ahead',lat=17.4,lon=78.417,reason='Road closed ahead')
        self.assertEqual(t['plan_version'],2);self.assertEqual(t['movement'],'REPLANNING');self.assertTrue(t['priority_hold'])
    def test_no_route_stops_and_raises_urgent(self):
        t=self.create();self.do('NO_ROUTE',trip_id='trip',plan_version=1);self.tick(5)
        self.assertEqual(t['travelled_m'],0);self.assertTrue(m.world(self.s)['urgent'])
    def test_manual_command_cannot_apply_after_plan_changes(self):
        t=self.create();entry=dict(id='J',distance_m=100,approach=0,position=[78.401,17.4],status='UPCOMING',name='J')
        t['plan']=[entry];t['status']='APPROVED';m.controller(self.s,entry)['manual']=True;m.send(self.s,t,entry)
        command=next(iter(m.world(self.s)['commands'].values()));t['plan_version']=2
        with self.assertRaises(ValueError):self.do('APPLY',target=command['id'])
    def test_verified_green_requires_clearance_and_online(self):
        t=self.create();e=dict(id='J',distance_m=100,approach=0);j=m.controller(self.s,e)
        m.send(self.s,t,e);self.assertFalse(j['verified_green']);self.tick(1)
        self.assertEqual(j['stage'],'PEDESTRIAN_CLEARANCE');self.assertFalse(j['verified_green'])
        self.tick(12);self.assertEqual(j['stage'],'GREEN');self.assertEqual(m.green(self.s,j),[0])
    def test_offline_never_verified(self):
        t=self.create();e=dict(id='J',distance_m=100,approach=0);j=m.controller(self.s,e);j['online']=False
        m.send(self.s,t,e);self.tick(10)
        self.assertFalse(j['verified_green']);self.assertEqual(m.green(self.s,j),[]);self.assertTrue(m.world(self.s)['urgent'])
        self.assertTrue(j['retry_exhausted']);m.send(self.s,t,e);self.assertEqual(j['stage'],'NORMAL')
    def test_arrival_waits_for_recovery(self):
        t=self.create();t['travelled_m']=t['distance_m'];self.tick(1)
        self.assertEqual(t['status'],'RECOVERING');self.tick(1);self.assertEqual(t['status'],'COMPLETED')

class SafetyTests(WorkflowTests):
    def test_releasing_green_has_amber_and_all_red(self):
        t=self.create();j=m.controller(self.s,dict(id='J',approach=0))
        j.update(stage='GREEN',trip_id='trip',verified_green=True,approach=0)
        self.do('STOP',trip_id='trip',plan_version=1)
        self.assertEqual(j['stage'],'AMBER_RECOVERY');self.assertFalse(j['verified_green'])
        self.tick(3);self.assertEqual(j['stage'],'ALL_RED_RECOVERY')
        self.tick(2);self.assertEqual(j['stage'],'RECOVERY')
    def test_late_route_result_cannot_restart_cancelled_trip(self):
        t=self.create();self.do('CANCEL',trip_id='trip',plan_version=1)
        with self.assertRaises(ValueError):self.do('REPLAN',trip_id='trip',plan_version=1,route=dict(source='TEST',coordinates=t['coordinates']))
        self.assertEqual(t['status'],'CANCELLED')
    def test_current_closure_prevents_commit_and_approval(self):
        t=self.create();m.world(self.s).setdefault('blockages',{})['B']=dict(lat=17.4,lon=78.415)
        with self.assertRaises(ValueError):self.do('APPROVE',trip_id='trip',plan_version=1)
        with self.assertRaises(ValueError):self.do('REPLAN',trip_id='trip',plan_version=1,route=dict(source='TEST',coordinates=t['coordinates']))
    def test_critical_timeout_only_one_junction(self):
        t=self.create();t['review_deadline']=0;t['travelled_m']=70;t['speed_mps']=5
        t['plan']=[dict(id='J'+str(i),distance_m=d,approach=0,position=m.point_at(t['coordinates'],d),status='UPCOMING',name='J'+str(i)) for i,d in enumerate([100,900])]
        for e in t['plan']:m.controller(self.s,e).update(queues=[0.]*4,arrivals=[0.]*4)
        self.tick(80)
        self.assertTrue(t['limited_used']);self.assertTrue(t['priority_hold'])
        self.assertIsNone(m.world(self.s)['controllers']['J1']['trip_id'])
    def test_red_and_queue_prevent_crossing(self):
        t=self.create();t['priority']='TRANSFER'
        e=dict(id='J',distance_m=100,approach=0,position=m.point_at(t['coordinates'],100),status='UPCOMING',name='J');t['plan']=[e]
        m.controller(self.s,e).update(online=False,queues=[50.]*4)
        self.tick(50);self.assertLessEqual(t['travelled_m'],95);self.assertEqual(t['speed_mps'],0)
    def test_manual_command_expires_on_stop(self):
        t=self.create();t['status']='APPROVED'
        e=dict(id='J',distance_m=100,approach=0,position=m.point_at(t['coordinates'],100),status='UPCOMING',name='J');t['plan']=[e]
        m.controller(self.s,e)['manual']=True;m.send(self.s,t,e)
        c=next(iter(m.world(self.s)['commands'].values()))
        self.do('STOP',trip_id='trip',plan_version=1)
        self.assertEqual(c['status'],'EXPIRED')
        with self.assertRaises(ValueError):self.do('APPLY',target=c['id'])

if __name__=='__main__':unittest.main()
