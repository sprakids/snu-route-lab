"""Mode freedom must not manufacture a new queue problem after every move."""
import copy,unittest
from fixtures import leg
from preferences import Prediction
from test_student_strategy import StudentStrategy

class CurrentPressure(unittest.TestCase):
    def setup(self):
        c,b,p,s,e=StudentStrategy().setup()
        c['review_requires_current_queue_pressure']=True
        p.student_initialize(s);s['student_flexible']=True
        return c,b,p,s,e
    def test_short_new_queue_does_not_authorize_another_physical_change(self):
        c,b,p,s,e=self.setup();p.predict=lambda *a,**k:Prediction(500.,first_wait=100.)
        before=copy.deepcopy(s)
        self.assertFalse(p.student_review_context(s,50.,Prediction(500.,first_wait=100.))[0])
        self.assertFalse(p.maybe_switch(s,50.,'arrival'))
        self.assertTrue(s['student_flexible']);self.assertEqual(s['history'],before['history'])
        self.assertEqual(s['stop_entry'],before['stop_entry']);self.assertEqual(s['full_passes'],before['full_passes'])
    def test_mode_freedom_is_not_locked_again_in_a_short_queue(self):
        c,b,p,s,e=self.setup();p.student_review_context(s,50.,Prediction(500.,first_wait=100.))
        candidate=[{**leg('shuttle-41841'),'test_node':1}]
        self.assertTrue(p.student_mode_allowed(s,candidate,50.))
        self.assertIsNotNone(p.student_filter_stages(s,candidate,False))
        self.assertEqual(s['student_preferred_mode'],'city')
    def test_long_current_expected_wait_still_triggers_review_after_release(self):
        c,b,p,s,e=self.setup();limit=s['student_patience_seconds']
        self.assertTrue(p.student_review_context(s,50.,Prediction(5000.,first_wait=limit))[0])
        self.assertTrue(s['student_flexible'])
    def test_actual_two_denials_and_two_more_departures_still_trigger(self):
        c,b,p,s,e=self.setup();s['student_patience_seconds']=10000.
        p.test_schedule[0]=[(100.,0,0),(200.,1,0),(600.,2,0)]
        s['full_passes']=1
        self.assertFalse(p.student_review_context(s,50.,Prediction(700.,first_wait=550.))[0])
        s['full_passes']=2
        stressed,age,more=p.student_review_context(s,50.,Prediction(700.,first_wait=550.))
        self.assertTrue(stressed);self.assertEqual(more,2)
    def test_new_stop_has_its_own_pressure_without_erasing_journey_experience(self):
        c,b,p,s,e=self.setup();s.update(stop_entry=1000.,completed_wait_seconds=7200.,history=[1,2],visit=3)
        self.assertFalse(p.student_review_context(s,1050.,Prediction(1500.,first_wait=100.))[0])
        self.assertEqual(s['completed_wait_seconds'],7200.);self.assertEqual(s['history'],[1,2])
        self.assertTrue(p.student_review_context(s,1050.+s['student_patience_seconds'],Prediction(5000.,first_wait=1.))[0])
    def test_no_remaining_service_still_triggers_review(self):
        c,b,p,s,e=self.setup()
        self.assertTrue(p.student_review_context(s,50.,None)[0])
        p.test_schedule[0]=[]
        self.assertTrue(p.student_review_context(s,50.,Prediction(500.,first_wait=100.))[0])
    def test_disabled_flag_reproduces_perpetual_released_review(self):
        c,b,p,s,e=self.setup();c['review_requires_current_queue_pressure']=False
        self.assertTrue(p.student_review_context(s,50.,Prediction(500.,first_wait=100.))[0])

if __name__=='__main__':unittest.main()
