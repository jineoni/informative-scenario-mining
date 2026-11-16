"""Check the scenario input and common evaluation rules."""

import gzip
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import xml.etree.ElementTree as ET

from phase1_simulation import evaluate_run, load_config, write_demand
from phase1_simulation.demand import allocate, schedule_departures


class DemandTests(unittest.TestCase):
    def test_rounding_keeps_total(self):
        self.assertEqual(allocate(7, [1, 1, 1]), [3, 2, 2])

    def test_headways_and_bin_boundary(self):
        times = schedule_departures(12, 600, 600, .8, 2, 3)
        gaps = [b - a for a, b in zip(times, times[1:])]
        self.assertEqual(len(times), 12)
        self.assertEqual(sum(gap == 2 for gap in gaps), 9)
        self.assertTrue(all(gap == 2 or gap > 3 for gap in gaps))
        self.assertTrue(all(600 <= second < 1200 for second in times))

    def test_infeasible_headways_are_reported(self):
        with self.assertRaisesRegex(ValueError, 'cannot fit'):
            schedule_departures(338, 0, 600, .8, 2, 3)

    def test_scenario_vehicle_allocation_and_evaluation_cohort(self):
        config = load_config()
        scenario = {'Q': 1200, 'D': .5, 'arrival_profile': 'sustained_peak',
                    'turning_profile': 'balanced_turns', 'B': .8}
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'demand.rou.xml'
            vehicles, bins = write_demand(config, scenario, path)
            records = ET.parse(path).getroot().findall('vehicle')
        self.assertEqual(len(records), 1200)
        north_first = next(row for row in bins if row['approach'] == 'N' and row['bin'] == 1)
        self.assertEqual([north_first[key] for key in ('L', 'T', 'R')], [36, 108, 36])
        self.assertEqual([v['depart'] for v in vehicles], sorted(v['depart'] for v in vehicles))
        self.assertTrue(all(v['depart'] < 3600 for v in vehicles))
        self.assertTrue(any(v['depart'] < 300 for v in vehicles))
        for vehicle in vehicles:
            self.assertEqual(vehicle['id'].startswith('eval_'), 300 <= vehicle['depart'] < 3600)


class EvaluationTests(unittest.TestCase):
    def test_completed_vehicle_means_and_common_queue_window(self):
        config = {**load_config(), 'bin_s': 1, 'warmup_s': 4}
        vehicles = [{'id': key} for key in ('warmup_0', 'eval_1', 'eval_2')]
        with TemporaryDirectory() as directory:
            path = Path(directory)
            with gzip.open(path / 'tripinfo.xml.gz', 'wt') as output:
                output.write('<tripinfos><tripinfo id="warmup_0" arrival="5" duration="3" timeLoss="0"/>'
                             '<tripinfo id="eval_1" arrival="8" duration="4" timeLoss="2"/>'
                             '<tripinfo id="eval_2" arrival="-1" duration="7" timeLoss="7" vaporized="end"/>'
                             '</tripinfos>')
            with gzip.open(path / 'fcd.xml.gz', 'wt') as output:
                output.write('<fcd-export><timestep time="4"><vehicle lane="north_in_0" speed="0"/>'
                             '<vehicle lane="east_out_0" speed="0"/></timestep>'
                             '<timestep time="5"/></fcd-export>')
            metrics = evaluate_run(path, vehicles, config)
        self.assertEqual(metrics['completion_rate'], .5)
        self.assertEqual(metrics['average_delay_s'], 2)
        self.assertEqual(metrics['average_travel_time_s'], 4)
        self.assertEqual(metrics['average_queue_vehicles'], .5)
