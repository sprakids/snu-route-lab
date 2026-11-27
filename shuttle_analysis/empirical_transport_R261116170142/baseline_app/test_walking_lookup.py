"""Visibility lookup acceleration must preserve geometry and blocked endpoints."""
import unittest
from unittest.mock import patch
from routing import WalkingGraph,distance

def network():
    nodes=[{'type':'node','id':i+1,'lat':37.46+(i//10)*.0001,'lon':126.95+(i%10)*.0001} for i in range(40)]
    ways=[{'type':'way','id':100+i,'nodes':[i+1,i+2],'tags':{'highway':'footway'}} for i in range(39)]
    return {'elements':nodes+ways}

class WalkingLookupTests(unittest.TestCase):
    def test_heap_lookup_preserves_sorted_reference_paths(self):
        fast=WalkingGraph(network());reference=WalkingGraph(network())
        def sorted_reference(point):
            choices=sorted(reference.points,key=lambda x:(x[1][0]-point[0])**2+((x[1][1]-point[1])*.794)**2)[:24]
            for n,p in choices:
                d=distance(point,p)
                if d<=30 and not reference.buildings.blocked(point,p):return n,d
        reference.visible_node=sorted_reference
        for start in [(37.46,126.95),(37.46015,126.95045),(37.461,126.951)]:
            for end in [(37.4603,126.9509),(37.4602,126.9502)]:
                self.assertEqual(fast.walk(start,end),reference.walk(start,end))
                self.assertEqual(fast.walk(start,end),reference.walk(start,end))
    def test_repeated_and_disconnected_endpoints_do_not_repeat_visibility_scans(self):
        graph=WalkingGraph(network())
        with patch.object(graph,'visible_node',wraps=graph.visible_node) as lookup:
            for _ in range(20):
                self.assertIsNotNone(graph.endpoint((37.46,126.95)))
                self.assertIsNone(graph.endpoint((37.47,126.96)))
            self.assertEqual(lookup.call_count,2)

if __name__=='__main__':unittest.main()
