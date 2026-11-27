import unittest
from aggregate_half_hour import aggregate,BINS


def row(arrival,minutes,weight=1,outcome='boarded'):
    return [0,arrival,arrival+minutes*60,weight,-1,outcome=='unserved',1,outcome]


class HalfHourTests(unittest.TestCase):
    def test_boundary_belongs_to_the_next_half_hour(self):
        data=aggregate([row(43199.999,1),row(43200,2),row(44999.999,3),row(45000,4)],1)['0']
        self.assertEqual(data['41400']['served_weight'],1)
        self.assertEqual(data['43200']['served_weight'],2)
        self.assertEqual(data['43200']['mean_wait_min'],2.5)
        self.assertEqual(data['45000']['mean_wait_min'],4)

    def test_weighted_mean_and_quantile_use_passenger_weights(self):
        data=aggregate([row(43300,1,9),row(45100,10,1)],1)['0']
        a,b=data['43200'],data['45000']
        self.assertEqual((a['mean_wait_min'],b['mean_wait_min']),(1,10))
        self.assertEqual((a['p90_wait_min'],b['p90_wait_min']),(1,10))
        mixed=aggregate([row(43300,1,9),row(43400,10,1)],1)['0']['43200']
        self.assertEqual(mixed['p90_wait_min'],1)
        self.assertEqual((a['served_weight']*a['mean_wait_min']+b['served_weight']*b['mean_wait_min'])/10,1.9)

    def test_partial_window_and_unserved_sentinel_are_censored(self):
        data=aggregate([row(40799,1),row(40800,1),row(83100,5+1/60,2,'unserved'),row(83400,0)],1)['0']
        self.assertEqual(len(BINS),25)
        self.assertEqual(data['39600']['arrival_weight'],1)
        self.assertEqual(data['82800']['arrival_weight'],2)
        self.assertEqual(data['82800']['mean_queue_exposure_min'],5)
        self.assertIsNone(data['82800']['mean_wait_min'])

    def test_switchers_are_separate_from_boarded_waits(self):
        data=aggregate([row(43300,2,3),row(43300,10,2,'switched')],1)['0']['43200']
        self.assertEqual(data['arrival_weight'],5)
        self.assertEqual(data['mean_wait_min'],2)
        self.assertEqual(data['switched_weight'],2)
        self.assertAlmostEqual(data['mean_queue_exposure_min'],5.2)


if __name__=='__main__':unittest.main()
