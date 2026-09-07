import copy
import json
import unittest
from pathlib import Path
from core import compare, graph, prepare, simulate


class CausalTests(unittest.TestCase):
    def setUp(self):
        self.model = {'variables': {
            'x': {'initial': 1, 'equation': 'x'},
            'y': {'initial': 0, 'equation': '2 * x'}}}

    def test_intervention_replaces_equation_and_propagates_next_step(self):
        result = compare(self.model, steps=3, draws=1,
                         interventions={'x': {'value': 5, 'start': 1, 'end': 1}})
        self.assertEqual(result['intervention'][1]['x']['mean'], 5)
        self.assertEqual(result['intervention'][1]['y']['mean'], 2)
        self.assertEqual(result['intervention'][2]['y']['mean'], 10)
        # After release, natural x=x dynamics preserve the changed state.
        self.assertEqual(result['intervention'][2]['x']['mean'], 5)
        self.assertEqual(result['baseline'][2]['y']['mean'], 2)

    def test_temporary_intervention_restores_equation(self):
        self.model['variables']['x']['equation'] = '1'
        result = simulate(self.model, steps=2, draws=1,
                          interventions={'x': {'value': 5, 'start': 1, 'end': 1}})
        self.assertEqual(result[2]['x']['mean'], 1)

    def test_reproducible_and_no_action_matches(self):
        model = json.loads(Path('examples/model.json').read_text())
        result = compare(model)
        self.assertEqual(result, compare(model))
        self.assertEqual(result['baseline'], result['intervention'])

    def test_modifier_and_feedback(self):
        model = json.loads(Path('examples/model.json').read_text())
        edges = graph(model)
        self.assertIn({'from': 'response', 'to': 'state', 'lag': 1}, edges)
        self.assertIn({'from': 'state', 'to': 'response', 'lag': 1}, edges)
        self.assertGreater(compare(model, initial={'modifier': 2})['baseline'][-1]['state']['mean'],
                           compare(model)['baseline'][-1]['state']['mean'])

    def test_rejects_code_and_unknown_names(self):
        for equation in ['__import__("os")', 'x.real', 'unknown + 1', 'x ** 999', 'True']:
            model = copy.deepcopy(self.model)
            model['variables']['y']['equation'] = equation
            with self.assertRaises(ValueError):
                prepare(model)

    def test_bad_requests(self):
        for request in [{'initial': {'typo': 1}}, {'steps': 0}, {'draws': 0},
                        {'interventions': {'x': {'value': 2, 'start': 0, 'end': 2}}}]:
            with self.assertRaises(ValueError):
                simulate(self.model, **request)


if __name__ == '__main__':
    unittest.main()
