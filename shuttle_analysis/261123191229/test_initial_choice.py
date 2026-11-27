"""Guard the V11 input contract and the direction of R's weather/distance effect."""
import math
import unittest
from candidate import HERE, apply_choice, eligible, load, load_v11, target_probabilities

class InitialChoiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_v11()
        cls.catalog = load(HERE/'walk_catalog.json')

    def apply(self, day, rate):
        source = self.bundle['prepared']
        plans = list(source['plans'][day])
        common = {**source['common'], 'paths':list(source['common']['paths'])}
        prepared = {**source, 'plans':{day:plans}, 'common':common}
        bundle = {**self.bundle, 'prepared':prepared}
        changed, stats = apply_choice(bundle, self.catalog, day, rate)
        for old, new in zip(source['plans'][day], plans):
            if old[0] in changed:
                self.assertTrue(eligible(old,bundle))
                self.assertEqual(new[:5],old[:5])
                self.assertFalse(new[6])
                path = common['paths'][new[5][0]]
                self.assertEqual(path[0], common['paths'][old[5][0]][0])
                self.assertEqual(path[-1], common['destinations']['daehak'])
            else:
                self.assertIs(old,new)
        return changed,stats

    def test_weather_nested_and_zero_reproduces_v11_plans(self):
        for day in self.bundle['prepared']['plans']:
            zero,_ = self.apply(day,0)
            rain,_ = self.apply(day,.45)
            dry,stats = self.apply(day,.50)
            upper,_ = self.apply(day,.55)
            self.assertFalse(zero)
            self.assertTrue(set(rain)<set(dry)<set(upper))
            self.assertAlmostEqual(stats['converted_mass'],sum(v[0] for v in dry.values()))

    def test_distance_and_expected_rate(self):
        weights = {100:1,450:2,500:2,1200:3,2200:5}
        probs = target_probabilities(weights,.5)
        self.assertEqual(probs[100],probs[500])
        self.assertGreater(probs[500],probs[1200])
        self.assertGreater(probs[1200],probs[2200])
        self.assertTrue(math.isclose(sum(mass*probs[d] for d,mass in weights.items())/sum(weights.values()),.5))

if __name__ == '__main__':
    unittest.main()

