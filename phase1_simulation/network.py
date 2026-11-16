"""Create the synthetic four-leg road network."""

from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

ARMS = ('N', 'E', 'S', 'W')
ROAD_NAMES = dict(zip(ARMS, ('north', 'east', 'south', 'west')))
MOVEMENTS = ('L', 'T', 'R')
DESTINATIONS = {
    arm: dict(zip(MOVEMENTS, (ARMS[(index + offset) % 4] for offset in (1, 2, 3))))
    for index, arm in enumerate(ARMS)
}


def build_network(config, directory, netconvert='netconvert'):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    length = config['arm_length_m']
    nodes = ET.Element('nodes')
    ET.SubElement(nodes, 'node', id='center', x='0', y='0', type='traffic_light')
    edges = ET.Element('edges')
    connections = ET.Element('connections')
    for arm, (x, y) in zip(ARMS, ((0, length), (length, 0), (0, -length), (-length, 0))):
        road = ROAD_NAMES[arm]
        ET.SubElement(nodes, 'node', id=road, x=str(x), y=str(y), type='priority')
        for edge_id, source, target in [(f'{road}_in', road, 'center'), (f'{road}_out', 'center', road)]:
            ET.SubElement(edges, 'edge', {
                'id': edge_id, 'from': source, 'to': target, 'numLanes': '1',
                'speed': str(config['speed_limit_kmh'] / 3.6),
            })
        for destination in DESTINATIONS[arm].values():
            ET.SubElement(connections, 'connection', {
                'from': f'{road}_in', 'to': f'{ROAD_NAMES[destination]}_out',
                'fromLane': '0', 'toLane': '0',
            })
    for suffix, root in [('nod', nodes), ('edg', edges), ('con', connections)]:
        ET.ElementTree(root).write(directory / f'intersection.{suffix}.xml', encoding='utf-8')
    output = directory / 'intersection.net.xml'
    executable = shutil.which(str(netconvert))
    if executable is None:
        raise FileNotFoundError('Set NETCONVERT to the installed netconvert executable.')
    subprocess.run([
        executable, '--node-files', 'intersection.nod.xml', '--edge-files', 'intersection.edg.xml',
        '--connection-files', 'intersection.con.xml', '--no-turnarounds', 'true',
        '--output-file', output.name,
    ], cwd=directory, check=True, capture_output=True, text=True)
    return output
