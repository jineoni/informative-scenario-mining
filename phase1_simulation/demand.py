"""Convert one scenario to scheduled vehicles in a SUMO demand file."""

from math import floor
from pathlib import Path
import xml.etree.ElementTree as ET

from .network import ARMS, DESTINATIONS, MOVEMENTS, ROAD_NAMES


def allocate(total, weights):
    """Preserve the parent count using largest remainders."""
    exact = [total * weight / sum(weights) for weight in weights]
    counts = [floor(value) for value in exact]
    priority = sorted(range(len(counts)), key=lambda i: exact[i] - counts[i], reverse=True)
    for index in priority[:total - sum(counts)]:
        counts[index] += 1
    return counts


def schedule_departures(count, start, bin_s, target, short_gap, threshold):
    """Spread a rounded number of short gaps across the available gap positions."""
    if count < 2:
        return [start + bin_s // 2] if count else []
    gaps = count - 1
    short_count = floor(target * gaps + .5)
    long_count = gaps - short_count
    long_min = threshold + 1
    span = bin_s - 1
    if short_count * short_gap + long_count * long_min > span:
        raise ValueError(f'{count} vehicles cannot fit in {bin_s} s at target B={target:g} '
                         f'with {short_gap} s short gaps and long gaps above {threshold} s.')
    long_gap, extra = divmod(span - short_count * short_gap, max(1, long_count))
    times = [start]
    long_index = 0
    for index in range(gaps):
        short_before = (index * short_count + gaps // 2) // gaps
        short_after = ((index + 1) * short_count + gaps // 2) // gaps
        if short_after > short_before:
            gap = short_gap
        else:
            gap = long_gap + ((long_index + 1) * extra // long_count - long_index * extra // long_count)
            long_index += 1
        times.append(times[-1] + gap)
    return times


def write_demand(config, scenario, path):
    """Write individual vehicle departures and return the schedule and bin summaries."""
    bin_s = config['bin_s']
    total = round(scenario['Q'] * (6 * bin_s) / 3600)
    d = scenario['D']
    approach_counts = allocate(total, [1 + d, 1 - d, 1 + d, 1 - d])
    arrival_weights = config['arrival_profiles'][scenario['arrival_profile']]
    turning_weights = config['turning_profiles'][scenario['turning_profile']]
    target = scenario['B']
    root = ET.Element('routes')
    ET.SubElement(root, 'vType', id='car', vClass='passenger', carFollowModel='Krauss',
                  **{key: str(value) for key, value in config['vehicle'].items()})
    vehicles, bins = [], []
    for arm, count in zip(ARMS, approach_counts):
        for movement, destination in DESTINATIONS[arm].items():
            ET.SubElement(root, 'route', id=f'{arm}_{movement}',
                          edges=f'{ROAD_NAMES[arm]}_in {ROAD_NAMES[destination]}_out')
        counts_by_route = [allocate(n, arrival_weights) for n in allocate(count, turning_weights)]
        for index, counts in enumerate(zip(*counts_by_route)):
            start = index * bin_s
            try:
                times = schedule_departures(sum(counts), start, bin_s, target,
                                            config['short_gap_s'], config['headway_threshold_s'])
            except ValueError as error:
                raise ValueError(f'Approach {arm}, bin {index + 1}: {error}') from error
            # Interleave routes in proportion to their counts to avoid movement blocks.
            routes = sorted(((i + .5) / n, movement)
                            for movement, n in zip(MOVEMENTS, counts) for i in range(n))
            vehicles.extend({'depart': second, 'route': f'{arm}_{movement}'}
                            for second, (_, movement) in zip(times, routes))
            short = sum(b - a <= config['headway_threshold_s'] for a, b in zip(times, times[1:]))
            bins.append({'approach': arm, 'bin': index + 1, **dict(zip(MOVEMENTS, counts)),
                         'vehicles': len(times), 'target_B': target,
                         'scheduled_B': short / (len(times) - 1) if len(times) > 1 else None})

    vehicles.sort(key=lambda vehicle: vehicle['depart'])
    for index, vehicle in enumerate(vehicles):
        cohort = 'eval' if vehicle['depart'] >= config['warmup_s'] else 'warmup'
        vehicle['id'] = f'{cohort}_{index:05d}'
        ET.SubElement(root, 'vehicle', id=vehicle['id'], type='car', route=vehicle['route'],
                      depart=str(vehicle['depart']), departLane='0', departPos='base',
                      departSpeed='max', arrivalPos='max')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(root)
    ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)
    return vehicles, bins
