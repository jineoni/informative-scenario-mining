"""Small plotting helpers shared by the notebook and standalone analysis."""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from .config import ARMS, CONTROLLERS

METRICS = {
    'average_delay_s': ('Average delay', 'SUMO timeLoss (s/vehicle)'),
    'average_queue_vehicles': ('Average queue length', 'Stopped vehicles (total)'),
    'average_travel_time_s': ('Average travel time', 'Travel time (s/vehicle)'),
}


def plot_demand(scenarios):
    fig, ax = plt.subplots(figsize=(9, 3.8), constrained_layout=True)
    x = np.arange(len(scenarios))
    for index, arm in enumerate(ARMS):
        ax.bar(x + (index - 1.5) * .19, scenarios[f'q_{arm}_vph'], width=.19, label=arm)
    ax.set(xticks=x, xticklabels=scenarios['scenario_id'], xlabel='Scenario',
           ylabel='Requested flow (vehicles/hour)', title='Directional demand generated from Q and D')
    ax.legend(title='Approach', ncol=4, fontsize=8)
    ax.grid(axis='y', alpha=.2)
    return fig


def plot_metric_comparison(summary, metric):
    title, unit = METRICS[metric]
    demand = sorted(summary['demand_vph'].unique())
    imbalance = sorted(summary['imbalance'].unique())
    finite = summary.loc[summary['valid_run'], metric].dropna()
    upper = max(1., float(finite.max())) if len(finite) else 1.
    fig, axes = plt.subplots(1, 2, figsize=(9, 4))
    fig.subplots_adjust(left=.10, right=.83, bottom=.17, top=.76, wspace=.36)
    image = None
    for ax, controller in zip(axes, CONTROLLERS):
        frame = summary.loc[summary['controller'].eq(controller)]
        values = np.full((len(demand), len(imbalance)), np.nan)
        annotations = {}
        for row in frame.itertuples(index=False):
            i, j = demand.index(row.demand_vph), imbalance.index(row.imbalance)
            value = getattr(row, metric)
            if row.valid_run:
                values[i, j] = value
            suffix = '*' if not row.complete_cohort else ''
            annotations[(i, j)] = f'{value:.1f}{suffix}' if row.valid_run else 'invalid'
        image = ax.imshow(np.ma.masked_invalid(values), cmap='YlOrRd', vmin=0, vmax=upper, aspect='auto')
        for (i, j), text in annotations.items():
            value = values[i, j]
            ax.text(j, i, text, ha='center', va='center',
                    color='white' if np.isfinite(value) and value > upper * .65 else 'black', fontsize=10)
        ax.set(xticks=range(len(imbalance)), xticklabels=[f'{v:g}' for v in imbalance],
               yticks=range(len(demand)), yticklabels=[f'{v:g}' for v in demand],
               xlabel='Directional imbalance D', ylabel='Requested demand Q (veh/h)', title=controller.capitalize())
    colorbar_ax = fig.add_axes([.88, .22, .025, .49])
    fig.colorbar(image, cax=colorbar_ax, label=unit)
    fig.suptitle(title + '\n* Evaluation cohort not fully completed at the cutoff', fontsize=12)
    return fig


def plot_queues(queues, scenario_id, warmup_s=300):
    subset = queues.loc[queues['scenario_id'].eq(scenario_id)]
    if subset.empty:
        raise ValueError(f'No queue results for {scenario_id}')
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8), sharex=True, sharey=True, constrained_layout=True)
    for ax, controller in zip(axes, CONTROLLERS):
        frame = subset.loc[subset['controller'].eq(controller)]
        if frame.empty:
            ax.text(.5, .5, 'Controller not run', transform=ax.transAxes, ha='center')
        else:
            for arm in ARMS:
                ax.plot((frame['time_s'] - warmup_s) / 60, frame[arm], lw=.8, label=arm)
        ax.set(title=controller.capitalize(), xlabel='Minutes into evaluation', ylabel='Stopped vehicles')
        ax.grid(alpha=.2)
    axes[0].legend(ncol=4, fontsize=8, title='Approach')
    fig.suptitle(f'{scenario_id}: directional queues at every simulation step', fontsize=12)
    return fig


def controller_differences(summary):
    rows = []
    for scenario_id, frame in summary.groupby('scenario_id', sort=True):
        records = {row['controller']: row for row in frame.to_dict('records')}
        if not all(controller in records for controller in CONTROLLERS):
            continue
        fixed, actuated = records['fixed'], records['actuated']
        comparable = all(row['valid_run'] and row['complete_cohort'] for row in records.values())
        row = {'scenario_id': scenario_id, 'demand_vph': fixed['demand_vph'], 'imbalance': fixed['imbalance'],
               'complete_valid_pair': comparable,
               'fixed_completion_rate': fixed['completion_rate'],
               'actuated_completion_rate': actuated['completion_rate']}
        for metric in METRICS:
            allowed = comparable if metric != 'average_queue_vehicles' else all(r['valid_run'] for r in records.values())
            row[f'fixed_minus_actuated_{metric}'] = fixed[metric] - actuated[metric] if allowed else np.nan
        rows.append(row)
    return pd.DataFrame(rows)
