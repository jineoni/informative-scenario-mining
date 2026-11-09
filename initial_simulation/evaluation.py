"""Aggregate vehicle outcomes and time-averaged stopped-vehicle queues."""
from __future__ import annotations

import gzip
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

from .config import ARMS, PipelineConfig


VEHICLE_COLUMNS = ['vehicle_id', 'approach', 'depart_s', 'arrival_s', 'duration_s',
                   'time_loss_s', 'depart_delay_s', 'completed', 'inserted', 'removed']


def open_xml(path):
    path = Path(path)
    return gzip.open(path, 'rb') if path.suffix == '.gz' else path.open('rb')


def read_vehicle_results(path):
    rows = []
    with open_xml(path) as handle:
        for _, element in ET.iterparse(handle, events=('end',)):
            if element.tag != 'tripinfo':
                continue
            vehicle_id = element.get('id', '')
            if vehicle_id.startswith('eval_'):
                depart = float(element.get('depart', '-1'))
                arrival = float(element.get('arrival', '-1'))
                removed = element.get('vaporized', '').lower() not in ('', 'false', '0', 'end')
                rows.append({'vehicle_id': vehicle_id, 'approach': vehicle_id.split('_')[1],
                             'depart_s': depart, 'arrival_s': arrival,
                             'duration_s': float(element.get('duration', 'nan')),
                             'time_loss_s': float(element.get('timeLoss', 'nan')),
                             'depart_delay_s': float(element.get('departDelay', 'nan')),
                             'inserted': depart >= 0,
                             'completed': depart >= 0 and arrival >= 0 and not removed,
                             'removed': removed})
            element.clear()
    frame = pd.DataFrame(rows, columns=VEHICLE_COLUMNS)
    if frame['vehicle_id'].duplicated().any():
        raise RuntimeError('Duplicate evaluation vehicle IDs in TripInfo.')
    return frame


def read_queues(path, config: PipelineConfig):
    lanes = {'north_in_0': 'N', 'east_in_0': 'E', 'south_in_0': 'S', 'west_in_0': 'W'}
    rows = []
    with open_xml(path) as handle:
        iterator = ET.iterparse(handle, events=('start', 'end'))
        _, root = next(iterator)
        for event, element in iterator:
            if event != 'end' or element.tag != 'timestep':
                continue
            time = float(element.get('time'))
            if config.warmup_s <= time < config.evaluation_end_s:
                counts = dict.fromkeys(ARMS, 0)
                for vehicle in element.findall('vehicle'):
                    arm = lanes.get(vehicle.get('lane'))
                    if arm and float(vehicle.get('speed')) < config.halt_speed_mps:
                        counts[arm] += 1
                rows.append({'time_s': time, **counts, 'total': sum(counts.values())})
            root.clear()
    frame = pd.DataFrame(rows, columns=['time_s', *ARMS, 'total'])
    expected = np.arange(config.warmup_s, config.evaluation_end_s, config.step_s)
    if len(frame) != len(expected) or not np.allclose(frame['time_s'], expected):
        raise RuntimeError('FCD output does not contain every evaluation timestep, including empty ones.')
    return frame


def aggregate_run(run_dir, config, scenario, controller):
    run_dir = Path(run_dir)
    vehicles = read_vehicle_results(run_dir / 'tripinfo.xml.gz')
    queues = read_queues(run_dir / 'fcd.xml.gz', config)
    planned = int(scenario['scheduled_eval_vehicles'])
    if len(vehicles) != planned:
        raise RuntimeError(f'Expected {planned} evaluation vehicle records, found {len(vehicles)}. '
                           'Check flow rounding, undeparted output, and removals.')
    completed = vehicles.loc[vehicles['completed']]
    inserted = vehicles.loc[vehicles['inserted']]
    unfinished = vehicles['inserted'] & ~vehicles['completed'] & ~vehicles['removed']
    pending = ~vehicles['inserted']
    with open_xml(run_dir / 'collisions.xml') as handle:
        collisions = sum(element.tag == 'collision' for _, element in ET.iterparse(handle, events=('end',)))
    log = (run_dir / 'sumo.stderr.log').read_text()
    critical_warnings = [line for line in log.splitlines() if any(
        term in line.lower() for term in ('no controlling detector', 'teleporting', 'emergency braking', 'collision'))]
    statistics = ET.parse(run_dir / 'statistics.xml').getroot() if (run_dir / 'statistics.xml').exists() else None
    teleports = int(statistics.find('teleports').get('total', '0')) if statistics is not None else 0
    valid = collisions == 0 and teleports == 0 and not vehicles['removed'].any() and not critical_warnings
    row = {'scenario_id': scenario['scenario_id'], 'controller': controller,
           'demand_vph': scenario['demand_vph'], 'imbalance': scenario['imbalance'],
           'direction': scenario['direction'], 'planned_vehicles': planned,
           'completed_vehicles': len(completed), 'unfinished_vehicles': int(unfinished.sum()),
           'uninserted_vehicles': int(pending.sum()), 'removed_vehicles': int(vehicles['removed'].sum()),
           'completion_rate': len(completed) / planned,
           'average_delay_s': completed['time_loss_s'].mean(),
           'average_travel_time_s': completed['duration_s'].mean(),
           'average_queue_vehicles': queues['total'].mean(),
           **{f'average_queue_{arm}': queues[arm].mean() for arm in ARMS},
           'average_depart_delay_s': inserted['depart_delay_s'].mean(),
           'queue_clear_fraction': queues['total'].eq(0).mean(),
           'queue_first_third': queues.iloc[:max(1, len(queues) // 3)]['total'].mean(),
           'queue_last_third': queues.iloc[-max(1, len(queues) // 3):]['total'].mean(),
           'collisions': collisions, 'teleports': teleports, 'valid_run': valid,
           'complete_cohort': len(completed) == planned,
           'warnings': ' | '.join(critical_warnings),
           'metric_scope': 'completed evaluation vehicles; queues over the fixed evaluation window'}
    vehicles.to_csv(run_dir / 'vehicles.csv', index=False)
    queues.to_csv(run_dir / 'queues.csv', index=False)
    return row
