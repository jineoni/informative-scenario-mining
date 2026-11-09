"""Prepare, execute, cache, and inspect an isolated SUMO experiment."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

import pandas as pd

from .config import CONTROLLERS, ROOT, PipelineConfig, find_binary, load_config, sumo_environment
from .demand import make_scenarios, write_demand
from .evaluation import aggregate_run
from .network import build_network, write_xml


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _signature(config):
    simulation_modules = {'config.py', 'network.py', 'demand.py', 'runner.py', 'evaluation.py'}
    sources = {p.name: _digest(p) for p in Path(__file__).parent.glob('*.py') if p.name in simulation_modules}
    version = subprocess.run([find_binary('sumo'), '--version'], capture_output=True, text=True, check=True).stdout.splitlines()[0]
    payload = {'config': config.to_dict(), 'sources': sources, 'sumo_version': version}
    signature = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return signature, version


def prepare_experiment(config=None, output_dir=None):
    config = config or load_config()
    if output_dir is None:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        output_dir = ROOT / 'results' / 'initial_simulation' / stamp
    directory = Path(output_dir).resolve()
    signature, version = _signature(config)
    manifest_path = directory / 'experiment.json'
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text())
        if old['signature'] != signature:
            raise ValueError('This output directory belongs to a different configuration, code version, or SUMO version. '
                             'Choose a new output directory.')
        for relative, digest in old['input_hashes'].items():
            if not (directory / relative).exists() or _digest(directory / relative) != digest:
                raise ValueError(f'Prepared input changed: {relative}. Choose a new output directory.')
        return directory
    if directory.exists() and any(directory.iterdir()):
        raise ValueError('Output directory is nonempty and has no experiment manifest. Choose a new directory.')
    directory.mkdir(parents=True, exist_ok=True)
    build_network(config, directory / 'network')
    rows = [write_demand(config, scenario, directory / 'scenarios' / scenario.scenario_id)
            for scenario in make_scenarios(config)]
    pd.DataFrame(rows).to_csv(directory / 'scenarios.csv', index=False)
    (directory / 'config.json').write_text(json.dumps(config.to_dict(), indent=2) + '\n')
    files = [p for sub in ('network', 'scenarios') for p in (directory / sub).rglob('*.xml')]
    files += list((directory / 'scenarios').rglob('flows.csv')) + [directory / 'scenarios.csv', directory / 'config.json']
    manifest = {'signature': signature, 'sumo_version': version, 'config': config.to_dict(),
                'created_utc': datetime.now(timezone.utc).isoformat(),
                'input_hashes': {str(p.relative_to(directory)): _digest(p) for p in files},
                'feature_scope': 'synthetic demand levels; not calibrated from Compass observations'}
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    return directory


def write_run_config(directory, scenario_id, controller, config):
    run_dir = directory / 'runs' / scenario_id / controller
    run_dir.mkdir(parents=True, exist_ok=True)
    root = ET.Element('configuration')
    inputs = ET.SubElement(root, 'input')
    ET.SubElement(inputs, 'net-file', value=str(directory / 'network' / f'{controller}.net.xml'))
    ET.SubElement(inputs, 'route-files', value=str(directory / 'scenarios' / scenario_id / 'demand.rou.xml'))
    time = ET.SubElement(root, 'time')
    for key, value in [('begin', 0), ('end', config.end_s), ('step-length', config.step_s)]:
        ET.SubElement(time, key, value=str(value))
    processing = ET.SubElement(root, 'processing')
    for key, value in [('time-to-teleport', -1), ('max-depart-delay', -1), ('collision.check-junctions', 'true')]:
        ET.SubElement(processing, key, value=str(value))
    random = ET.SubElement(root, 'random_number')
    ET.SubElement(random, 'seed', value=str(config.seed))
    replay_path = write_xml(root, run_dir / 'replay.sumocfg')
    output = ET.SubElement(root, 'output')
    outputs = [('tripinfo-output', 'tripinfo.xml.gz'), ('fcd-output', 'fcd.xml.gz'),
               ('summary-output', 'summary.xml.gz'), ('statistic-output', 'statistics.xml'),
               ('collision-output', 'collisions.xml')]
    for key, filename in outputs:
        ET.SubElement(output, key, value=str(run_dir / filename))
    for key, value in [('tripinfo-output.write-unfinished', 'true'),
                       ('tripinfo-output.write-undeparted', 'true'),
                       ('fcd-output.attributes', 'id,speed,lane'), ('precision', '6')]:
        ET.SubElement(output, key, value=value)
    return write_xml(root, run_dir / 'run.sumocfg'), replay_path


def run_experiment(config=None, output_dir=None, controllers=CONTROLLERS, scenario_ids=None, rerun=False):
    config = config or load_config()
    if not controllers or set(controllers) - set(CONTROLLERS):
        raise ValueError(f'Controllers must be selected from {CONTROLLERS}.')
    directory = prepare_experiment(config, output_dir)
    scenarios = pd.read_csv(directory / 'scenarios.csv')
    if scenario_ids is not None:
        missing = set(scenario_ids) - set(scenarios['scenario_id'])
        if missing:
            raise ValueError(f'Unknown scenarios: {sorted(missing)}')
        scenarios = scenarios.loc[scenarios['scenario_id'].isin(scenario_ids)]
    failures = []
    for scenario in scenarios.to_dict('records'):
        for controller in controllers:
            run_dir = directory / 'runs' / scenario['scenario_id'] / controller
            record = run_dir / 'run.json'
            if record.exists() and not rerun:
                previous = json.loads(record.read_text())
                hashes = previous.get('output_hashes', {})
                if previous.get('status') == 'complete' and hashes and all(
                        (run_dir / file).is_file() and _digest(run_dir / file) == digest for file, digest in hashes.items()):
                    print(f"Cached {scenario['scenario_id']} / {controller}", flush=True)
                    continue
            print(f"Running {scenario['scenario_id']} / {controller}: Q={scenario['demand_vph']:g}, D={scenario['imbalance']:g}", flush=True)
            configuration, _ = write_run_config(directory, scenario['scenario_id'], controller, config)
            command = [find_binary('sumo'), '-c', str(configuration), '--no-step-log', 'true', '--duration-log.disable', 'true']
            record.write_text(json.dumps({'status': 'running', 'command': command}, indent=2) + '\n')
            try:
                result = subprocess.run(command, capture_output=True, text=True, env=sumo_environment(command[0]))
                (run_dir / 'sumo.stdout.log').write_text(result.stdout)
                (run_dir / 'sumo.stderr.log').write_text(result.stderr)
                if result.returncode:
                    raise RuntimeError(f'SUMO exited with status {result.returncode}: {result.stderr[-1500:]}')
                row = aggregate_run(run_dir, config, scenario, controller)
                files = ['run.sumocfg', 'replay.sumocfg', 'vehicles.csv', 'queues.csv', 'tripinfo.xml.gz',
                         'fcd.xml.gz', 'summary.xml.gz', 'statistics.xml', 'collisions.xml',
                         'sumo.stdout.log', 'sumo.stderr.log']
                record.write_text(json.dumps({'status': 'complete', 'command': command, 'metrics': row,
                                              'output_hashes': {p: _digest(run_dir / p) for p in files}}, indent=2) + '\n')
            except Exception as error:
                failures.append({'scenario_id': scenario['scenario_id'], 'controller': controller, 'error': str(error)})
                record.write_text(json.dumps({'status': 'failed', 'error': str(error), 'command': command}, indent=2) + '\n')
    rows = []
    for record in sorted((directory / 'runs').glob('*/*/run.json')):
        data = json.loads(record.read_text())
        if data.get('status') == 'complete':
            rows.append(data['metrics'])
    pd.DataFrame(rows).to_csv(directory / 'summary.csv', index=False)
    pd.DataFrame(failures, columns=['scenario_id', 'controller', 'error']).to_csv(directory / 'failures.csv', index=False)
    if failures:
        raise RuntimeError(f'{len(failures)} run(s) failed. See {directory / "failures.csv"}')
    return directory


def run_pilot(config=None, output_dir=None):
    config = config or load_config()
    pilot = replace(config, warmup_s=120, evaluation_s=600, drain_s=300)
    return run_experiment(pilot, output_dir, controllers=('fixed',))


def load_results(directory):
    directory = Path(directory).resolve()
    summary = pd.read_csv(directory / 'summary.csv')
    scenarios = pd.read_csv(directory / 'scenarios.csv')
    queues = []
    for row in summary.itertuples(index=False):
        frame = pd.read_csv(directory / 'runs' / row.scenario_id / row.controller / 'queues.csv')
        frame['scenario_id'], frame['controller'] = row.scenario_id, row.controller
        queues.append(frame)
    return {'directory': directory, 'scenarios': scenarios, 'summary': summary,
            'queues': pd.concat(queues, ignore_index=True) if queues else pd.DataFrame()}


def gui_command(directory, scenario_id, controller):
    if controller not in CONTROLLERS:
        raise ValueError(f'Unknown controller: {controller}')
    path = Path(directory).resolve() / 'runs' / scenario_id / controller / 'replay.sumocfg'
    if not path.is_file():
        raise FileNotFoundError(f'Run this scenario/controller first: {path}')
    return [find_binary('sumo-gui'), '-c', str(path), '--start']
