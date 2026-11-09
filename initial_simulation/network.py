"""Build one shared network and explicit fixed/actuated traffic light programs."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

from .config import ARMS, CONTROLLERS, PipelineConfig, find_binary, sumo_environment

EDGE_NAME = {'N': 'north', 'E': 'east', 'S': 'south', 'W': 'west'}
DESTINATIONS = {
    'N': {'L': 'E', 'T': 'S', 'R': 'W'},
    'E': {'L': 'S', 'T': 'W', 'R': 'N'},
    'S': {'L': 'W', 'T': 'N', 'R': 'E'},
    'W': {'L': 'N', 'T': 'E', 'R': 'S'},
}


def write_xml(root, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(root, space='  ')
    ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)
    return path


def build_network(config: PipelineConfig, directory: Path):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    length = config.arm_length_m
    coordinates = {'N': (0, length), 'E': (length, 0), 'S': (0, -length), 'W': (-length, 0)}
    nodes, edges, connections = ET.Element('nodes'), ET.Element('edges'), ET.Element('connections')
    ET.SubElement(nodes, 'node', id='center', x='0', y='0', type='traffic_light')
    for arm, (x, y) in coordinates.items():
        name = EDGE_NAME[arm]
        ET.SubElement(nodes, 'node', id=name, x=str(x), y=str(y), type='priority')
        for suffix, origin, target in [('in', name, 'center'), ('out', 'center', name)]:
            ET.SubElement(edges, 'edge', {'id': f'{name}_{suffix}', 'from': origin, 'to': target,
                'numLanes': '1', 'speed': str(config.speed_mps), 'allow': 'passenger'})
        for destination in DESTINATIONS[arm].values():
            ET.SubElement(connections, 'connection', {'from': f'{name}_in',
                'to': f'{EDGE_NAME[destination]}_out', 'fromLane': '0', 'toLane': '0'})
    nodes_file = write_xml(nodes, directory / 'intersection.nod.xml')
    edges_file = write_xml(edges, directory / 'intersection.edg.xml')
    connections_file = write_xml(connections, directory / 'intersection.con.xml')
    network_file = directory / 'intersection.net.xml'
    command = [find_binary('netconvert'), '--node-files', str(nodes_file), '--edge-files', str(edges_file),
               '--connection-files', str(connections_file), '--no-turnarounds', 'true',
               '--output-file', str(network_file)]
    result = subprocess.run(command, capture_output=True, text=True, env=sumo_environment(command[0]))
    (directory / 'netconvert.log').write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f'netconvert failed; see {directory / "netconvert.log"}')
    root = ET.parse(network_file).getroot()
    groups = {arm: [] for arm in ARMS}
    valid_routes = set()
    for connection in root.findall('connection'):
        if connection.get('tl') == 'center':
            arm = next(a for a in ARMS if connection.get('from') == f'{EDGE_NAME[a]}_in')
            groups[arm].append(int(connection.get('linkIndex')))
            valid_routes.add((connection.get('from'), connection.get('to')))
    if any(len(indices) != 3 for indices in groups.values()):
        raise RuntimeError(f'Expected three controlled movements per approach, got {groups}')
    expected = {(f'{EDGE_NAME[a]}_in', f'{EDGE_NAME[d]}_out') for a in ARMS for d in DESTINATIONS[a].values()}
    if valid_routes != expected:
        raise RuntimeError('Generated network does not support exactly the twelve requested movements.')
    link_count = max(i for indices in groups.values() for i in indices) + 1
    if sorted(i for indices in groups.values() for i in indices) != list(range(link_count)):
        raise RuntimeError('Traffic light link indices are not contiguous and unique.')
    phase_rows = []
    for controller in CONTROLLERS:
        additional = ET.Element('additional')
        logic = ET.SubElement(additional, 'tlLogic', id='center', programID='0', offset='0',
                              type='static' if controller == 'fixed' else 'actuated')
        if controller == 'actuated':
            ET.SubElement(logic, 'param', key='max-gap', value=str(config.max_gap_s))
            ET.SubElement(logic, 'param', key='detector-gap', value=str(config.detector_gap_s))
        for arm in ARMS:
            for kind, signal, duration in [('green', 'G', config.fixed_green_s),
                                           ('yellow', 'y', config.yellow_s),
                                           ('all_red', 'r', config.all_red_s)]:
                state = ['r'] * link_count
                for index in groups[arm]:
                    state[index] = signal
                attributes = {'duration': str(duration), 'state': ''.join(state), 'name': f'{arm}_{kind}'}
                if controller == 'actuated' and kind == 'green':
                    attributes.update(minDur=str(config.min_green_s), maxDur=str(config.max_green_s))
                ET.SubElement(logic, 'phase', attributes)
                phase_rows.append({'controller': controller, 'name': attributes['name'], **attributes})
        write_xml(additional, directory / f'{controller}.add.xml')
        controller_root = deepcopy(root)
        old_logics = controller_root.findall('tlLogic')
        logic_index = list(controller_root).index(old_logics[0])
        for old in old_logics:
            controller_root.remove(old)
        controller_root.insert(logic_index, deepcopy(logic))
        write_xml(controller_root, directory / f'{controller}.net.xml')
    metadata = {'incoming_lanes': {a: f'{EDGE_NAME[a]}_in_0' for a in ARMS},
                'controlled_links': groups, 'phases': phase_rows,
                'external_lane_lengths_m': {e.get('id'): float(e.find('lane').get('length'))
                    for e in root.findall('edge') if e.get('function') != 'internal'}}
    (directory / 'network.json').write_text(json.dumps(metadata, indent=2) + '\n')
    return network_file
