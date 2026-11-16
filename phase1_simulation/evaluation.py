"""Calculate the common Phase 1 metrics from SUMO output."""

import gzip
from pathlib import Path
from statistics import mean
import xml.etree.ElementTree as ET

from .network import ROAD_NAMES


def evaluate_run(run_dir, vehicles, config):
    directory = Path(run_dir)
    planned = {vehicle['id'] for vehicle in vehicles if vehicle['id'].startswith('eval_')}
    observed = set()
    delays, durations = [], []
    with gzip.open(directory / 'tripinfo.xml.gz', 'rb') as source:
        iterator = ET.iterparse(source, events=('start', 'end'))
        _, root = next(iterator)
        for event, trip in iterator:
            if event != 'end' or trip.tag != 'tripinfo':
                continue
            vehicle_id = trip.get('id')
            if vehicle_id in planned:
                if vehicle_id in observed:
                    raise ValueError(f'Duplicate TripInfo record for {vehicle_id}.')
                observed.add(vehicle_id)
                if float(trip.get('arrival', '-1')) >= 0 and trip.get('vaporized', '') in ('', '0', 'false'):
                    delays.append(float(trip.get('timeLoss')))
                    durations.append(float(trip.get('duration')))
            root.clear()
    if observed != planned:
        raise ValueError(f'TripInfo is missing {len(planned - observed)} scheduled evaluation vehicles.')

    queue_counts = []
    inbound = {f'{road}_in_0' for road in ROAD_NAMES.values()}
    start, end = config['warmup_s'], 6 * config['bin_s']
    with gzip.open(directory / 'fcd.xml.gz', 'rb') as source:
        iterator = ET.iterparse(source, events=('start', 'end'))
        _, root = next(iterator)
        for event, timestep in iterator:
            if event != 'end' or timestep.tag != 'timestep':
                continue
            second = float(timestep.get('time'))
            if start <= second < end:
                if second != start + len(queue_counts):
                    raise ValueError('FCD output has a missing or duplicate evaluation timestep.')
                queue_counts.append(sum(vehicle.get('lane') in inbound
                                        and float(vehicle.get('speed')) < config['halt_speed_mps']
                                        for vehicle in timestep.findall('vehicle')))
            root.clear()
    if len(queue_counts) != end - start:
        raise ValueError('FCD output does not cover the full evaluation window.')
    return {
        'scheduled_vehicles': len(planned),
        'completed_vehicles': len(durations),
        'completion_rate': len(durations) / len(planned) if planned else None,
        'average_delay_s': mean(delays) if delays else None,
        'average_queue_vehicles': mean(queue_counts),
        'average_travel_time_s': mean(durations) if durations else None,
    }
