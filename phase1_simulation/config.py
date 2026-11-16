"""Load and check the Phase 1 experiment settings."""

import json
from math import isfinite
from pathlib import Path

DEFAULT_CONFIG = Path(__file__).parent / 'configs' / 'default.json'


def load_config(path=DEFAULT_CONFIG):
    config = json.loads(Path(path).read_text())
    for key, minimum, maximum in [
        ('demand_vph', 1, float('inf')),
        ('directional_imbalance', -1, 1),
        ('platooning', 0, 1),
    ]:
        levels = config[key]
        if not levels or len(set(levels)) != len(levels) or not all(
            isfinite(value) and minimum <= value <= maximum for value in levels
        ):
            raise ValueError(f'Invalid levels for {key}.')
    for key, size in [('arrival_profiles', 6), ('turning_profiles', 3)]:
        if not config[key]:
            raise ValueError(f'{key} needs at least one profile.')
        for name, weights in config[key].items():
            if len(weights) != size or any(not isfinite(w) or w < 0 for w in weights) or sum(weights) <= 0:
                raise ValueError(f'{key}.{name} needs {size} nonnegative weights with a positive sum.')
    for key in (
        'bin_s', 'warmup_s', 'drain_s', 'short_gap_s', 'headway_threshold_s',
        'fixed_green_s', 'min_green_s', 'max_green_s', 'yellow_s', 'all_red_s',
    ):
        if type(config[key]) is not int or config[key] <= 0:
            raise ValueError(f'{key} must be a positive integer number of seconds.')
    if config['warmup_s'] >= 6 * config['bin_s']:
        raise ValueError('Warm-up must end before the demand period ends.')
    if config['short_gap_s'] > config['headway_threshold_s']:
        raise ValueError('The short gap must be at or below the headway threshold.')
    if config['min_green_s'] > config['max_green_s']:
        raise ValueError('Minimum green cannot exceed maximum green.')
    for key in ('arm_length_m', 'speed_limit_kmh', 'max_gap_s', 'detector_gap_s', 'halt_speed_mps'):
        if not isfinite(config[key]) or config[key] <= 0:
            raise ValueError(f'{key} must be positive and finite.')
    return config
