"""Translate scenario features into deterministic SUMO movement flows."""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

import pandas as pd
import xml.etree.ElementTree as ET

from .config import ARMS, PipelineConfig
from .network import DESTINATIONS, EDGE_NAME, write_xml


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    demand_vph: float
    imbalance: float

    @property
    def direction(self):
        return 'balanced' if self.imbalance == 0 else ('NS-heavy' if self.imbalance > 0 else 'EW-heavy')

    def rates(self):
        q, d = self.demand_vph, self.imbalance
        return {'N': q * (1 + d) / 4, 'E': q * (1 - d) / 4,
                'S': q * (1 + d) / 4, 'W': q * (1 - d) / 4}


def make_scenarios(config):
    return [Scenario(f's{index:02d}', q, d) for index, (q, d) in enumerate(
        ((q, d) for q in config.demand_vph for d in config.directional_imbalance), 1)]


def scheduled_count(rate, duration):
    # A regular flow requests its first vehicle at begin, and its last before end.
    return max(0, math.ceil(rate * duration / 3600 - 1e-10)) if rate > 0 else 0


def write_demand(config: PipelineConfig, scenario: Scenario, directory: Path):
    directory = Path(directory)
    root = ET.Element('routes')
    ET.SubElement(root, 'vType', id='car', vClass='passenger', carFollowModel='Krauss',
                  accel=str(config.accel_mps2), decel=str(config.decel_mps2), sigma='0',
                  tau=str(config.tau_s), length=str(config.vehicle_length_m),
                  minGap=str(config.min_gap_m), speedFactor='1', speedDev='0',
                  maxSpeed=str(config.speed_mps))
    shares = {'L': config.left_share, 'T': 1 - config.left_share - config.right_share, 'R': config.right_share}
    for arm in ARMS:
        for movement, destination in DESTINATIONS[arm].items():
            ET.SubElement(root, 'route', id=f'{arm}_{movement}',
                          edges=f'{EDGE_NAME[arm]}_in {EDGE_NAME[destination]}_out')
    rows = []
    for cohort, begin, end in [('warmup', 0, config.warmup_s),
                                ('eval', config.warmup_s, config.evaluation_end_s)]:
        for arm, approach_rate in scenario.rates().items():
            for movement, share in shares.items():
                rate = approach_rate * share
                if rate <= 0 or end <= begin:
                    continue
                flow_id = f'{cohort}_{arm}_{movement}'
                ET.SubElement(root, 'flow', id=flow_id, type='car', route=f'{arm}_{movement}',
                              begin=str(begin), end=str(end), vehsPerHour=f'{rate:.12g}',
                              departLane='0', departPos='base', departSpeed='max', arrivalPos='max')
                rows.append({'flow_id': flow_id, 'cohort': cohort, 'approach': arm,
                             'movement': movement, 'rate_vph': rate, 'begin_s': begin, 'end_s': end,
                             'scheduled_vehicles': scheduled_count(rate, end - begin)})
    directory.mkdir(parents=True, exist_ok=True)
    write_xml(root, directory / 'demand.rou.xml')
    frame = pd.DataFrame(rows)
    frame.to_csv(directory / 'flows.csv', index=False)
    eval_flows = frame.loc[frame['cohort'].eq('eval')]
    counts = eval_flows.groupby('approach')['scheduled_vehicles'].sum().reindex(ARMS, fill_value=0)
    total = int(counts.sum())
    realized_d = (counts['N'] + counts['S'] - counts['E'] - counts['W']) / total if total else float('nan')
    return {'scenario_id': scenario.scenario_id, 'demand_vph': scenario.demand_vph,
            'imbalance': scenario.imbalance, 'direction': scenario.direction,
            **{f'q_{arm}_vph': scenario.rates()[arm] for arm in ARMS},
            'scheduled_eval_vehicles': total,
            'effective_demand_vph': total * 3600 / config.evaluation_s,
            'effective_imbalance': realized_d,
            'effective_turning_share': eval_flows.loc[eval_flows['movement'].ne('T'), 'scheduled_vehicles'].sum() / total}
