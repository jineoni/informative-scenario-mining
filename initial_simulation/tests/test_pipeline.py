"""Focused tests for feature translation, censoring, and queue aggregation."""
from dataclasses import replace
import gzip
import tempfile
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

import numpy as np

from initial_simulation.config import PipelineConfig
from initial_simulation.demand import Scenario, make_scenarios, scheduled_count, write_demand
from initial_simulation.evaluation import aggregate_run, read_queues
from initial_simulation.network import build_network


class FeatureTests(unittest.TestCase):
    def test_directional_mapping_and_symmetry(self):
        config = PipelineConfig()
        self.assertEqual(len(make_scenarios(config)), 9)
        for scenario in make_scenarios(config):
            rates = scenario.rates()
            self.assertAlmostEqual(sum(rates.values()), scenario.demand_vph)
            realized = (rates['N'] + rates['S'] - rates['E'] - rates['W']) / sum(rates.values())
            self.assertAlmostEqual(realized, scenario.imbalance)
        self.assertEqual(Scenario('x', 1200, -.5).rates()['E'], 450)
        self.assertEqual(Scenario('x', 1200, .5).rates()['N'], 450)

    def test_flow_rounding_is_reported(self):
        self.assertEqual(scheduled_count(45, 1800), 23)
        self.assertEqual(scheduled_count(360, 1800), 180)
        with tempfile.TemporaryDirectory() as directory:
            row = write_demand(PipelineConfig(), Scenario('x', 1200, .5), Path(directory))
            self.assertEqual(row['scheduled_eval_vehicles'], 604)
            self.assertNotEqual(row['effective_demand_vph'], row['demand_vph'])
            root = ET.parse(Path(directory) / 'demand.rou.xml').getroot()
            self.assertEqual(len(root.findall('route')), 12)
            self.assertEqual(len(root.findall('flow')), 24)

    def test_invalid_features_and_time_grid(self):
        for values in [dict(demand_vph=(0,)), dict(directional_imbalance=(1.1,)),
                       dict(left_share=.8, right_share=.3), dict(step_s=2),
                       dict(evaluation_s=2.5)]:
            with self.assertRaises(ValueError):
                PipelineConfig(**values)


class AggregationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.config = replace(PipelineConfig(), warmup_s=1, evaluation_s=2, drain_s=0)
        xml = '''<fcd-export>
          <timestep time="0"><vehicle id="w" lane="north_in_0" speed="0"/></timestep>
          <timestep time="1"><vehicle id="a" lane="north_in_0" speed="0.099999"/>
            <vehicle id="b" lane="east_in_0" speed="0.1"/>
            <vehicle id="c" lane="south_out_0" speed="0"/></timestep>
          <timestep time="2"><vehicle id="a" lane="north_in_0" speed="0"/>
            <vehicle id="b" lane="east_in_0" speed="0"/></timestep>
          <timestep time="3"><vehicle id="d" lane="west_in_0" speed="0"/></timestep>
        </fcd-export>'''
        with gzip.open(self.directory / 'fcd.xml.gz', 'wt') as handle:
            handle.write(xml)

    def tearDown(self):
        self.temp.cleanup()

    def test_queue_window_threshold_and_units(self):
        frame = read_queues(self.directory / 'fcd.xml.gz', self.config)
        np.testing.assert_array_equal(frame['total'], [1, 2])
        self.assertEqual(frame['total'].mean(), 1.5)
        self.assertEqual(frame['N'].mean(), 1)
        self.assertEqual(frame['E'].mean(), .5)

    def test_incomplete_and_undeparted_do_not_enter_completed_means(self):
        xml = '''<tripinfos>
          <tripinfo id="warmup_N_T.0" depart="0" arrival="10" duration="10" timeLoss="1"/>
          <tripinfo id="eval_N_T.0" depart="1" arrival="41" duration="40" timeLoss="10" departDelay="0"/>
          <tripinfo id="eval_E_T.0" depart="1" arrival="61" duration="60" timeLoss="20" departDelay="0"/>
          <tripinfo id="eval_S_T.0" depart="2" arrival="-1" duration="1" timeLoss="1" departDelay="0" vaporized="end"/>
          <tripinfo id="eval_W_T.0" depart="-1" arrival="-1" duration="-1" timeLoss="-1" vaporized="end"/>
        </tripinfos>'''
        with gzip.open(self.directory / 'tripinfo.xml.gz', 'wt') as handle:
            handle.write(xml)
        (self.directory / 'collisions.xml').write_text('<collisions/>')
        (self.directory / 'sumo.stderr.log').write_text('')
        row = aggregate_run(self.directory, self.config,
                            {'scenario_id': 'x', 'demand_vph': 600, 'imbalance': 0,
                             'direction': 'balanced', 'scheduled_eval_vehicles': 4}, 'fixed')
        self.assertEqual(row['average_delay_s'], 15)
        self.assertEqual(row['average_travel_time_s'], 50)
        self.assertEqual(row['average_queue_vehicles'], 1.5)
        self.assertEqual(row['completion_rate'], .5)
        self.assertEqual(row['unfinished_vehicles'], 1)
        self.assertEqual(row['uninserted_vehicles'], 1)
        self.assertFalse(row['complete_cohort'])
        self.assertTrue(row['valid_run'])
        self.assertEqual(row['removed_vehicles'], 0)


class NetworkTests(unittest.TestCase):
    def test_signal_groups_cover_exactly_one_approach(self):
        with tempfile.TemporaryDirectory() as directory:
            build_network(PipelineConfig(), Path(directory))
            roots = {name: ET.parse(Path(directory) / f'{name}.net.xml').getroot()
                     for name in ['fixed', 'actuated']}
            for name, root in roots.items():
                logic = root.find('tlLogic')
                self.assertEqual(logic.get('type'), 'static' if name == 'fixed' else 'actuated')
                phases = logic.findall('phase')
                self.assertEqual(len(phases), 12)
                for phase in phases:
                    self.assertEqual(len(phase.get('state')), 12)
                    self.assertIn(phase.get('state').count('G'), [0, 3])
                root.remove(logic)
            self.assertEqual(ET.tostring(roots['fixed']), ET.tostring(roots['actuated']))


if __name__ == '__main__':
    unittest.main()
