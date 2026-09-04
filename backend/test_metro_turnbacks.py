import unittest
from metro_turnbacks import turnback_snapshot


class TurnbackTests(unittest.TestCase):
    def setUp(self):
        self.incoming = dict(id='in', block='vehicle', service='WK', route='RED', headsign='B',
                             times=[['a',100,110,0],['b1',200,220,1]])
        self.outgoing = dict(id='out', block='vehicle', service='WK', route='RED', headsign='A',
                             times=[['b2',400,430,0],['a',500,520,1]])
        self.data = dict(trips=[self.incoming,self.outgoing], stops={
            'a':dict(name='A'), 'b1':dict(name='B',parent='B'), 'b2':dict(name='B',parent='B')})

    def read(self, seconds):
        return turnback_snapshot(self.data, {'WK'}, seconds)['turnbacks']

    def test_same_block_parent_station_and_countdown(self):
        row=self.read(250)[0]
        self.assertEqual(row['remaining_seconds'],150)
        self.assertEqual(row['duration_seconds'],180)
        self.assertEqual(row['next_departure_seconds'],430)
        self.assertEqual(self.read(260)[0]['remaining_seconds'],140)

    def test_platform_dwell_and_terminal_boundaries(self):
        self.assertEqual(self.read(210),[])
        self.assertEqual(self.read(220)[0]['remaining_seconds'],180)
        self.assertEqual(self.read(400),[])

    def test_no_invented_countdown_without_next_trip(self):
        self.data['trips']=[self.incoming]
        self.assertEqual(self.read(250),[])

    def test_different_block_or_terminal_is_not_turnback(self):
        self.outgoing['block']='another'
        self.assertEqual(self.read(250),[])
        self.outgoing['block']='vehicle';self.outgoing['times'][0][0]='a'
        self.assertEqual(self.read(250),[])

    def test_overlap_not_presented_as_turnback(self):
        self.outgoing['times'][0][1]=210
        result=turnback_snapshot(self.data,{'WK'},215)
        self.assertEqual(result['turnbacks'],[])
        self.assertEqual(result['turnback_quality']['overlapping_trip_pairs'],1)

    def test_inactive_service_and_paused_clock(self):
        self.assertEqual(turnback_snapshot(self.data,{'SUN'},250)['turnbacks'],[])
        self.assertEqual(self.read(250),self.read(250))


if __name__=='__main__':unittest.main()
