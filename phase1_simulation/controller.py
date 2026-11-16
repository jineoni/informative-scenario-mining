"""Write fixed-time and actuated signal programs on the same network."""

from pathlib import Path
import xml.etree.ElementTree as ET

from .network import ARMS, ROAD_NAMES

CONTROLLERS = ('fixed', 'actuated')


def write_controller(network_path, config, controller):
    if controller not in CONTROLLERS:
        raise ValueError(f'Unknown controller: {controller}')
    network_path = Path(network_path)
    tree = ET.parse(network_path)
    root = tree.getroot()
    links = [
        (connection.get('from'), int(connection.get('linkIndex')))
        for connection in root.findall('connection') if connection.get('tl') == 'center'
    ]
    groups = {
        arm: [index for edge, index in links if edge == f'{ROAD_NAMES[arm]}_in']
        for arm in ARMS
    }
    if any(len(indices) != 3 for indices in groups.values()) or sorted(
        index for _, index in links
    ) != list(range(12)):
        raise ValueError('Expected three controlled movements per approach.')

    existing = root.find("tlLogic[@id='center']")
    position = list(root).index(existing)
    root.remove(existing)
    program = ET.Element('tlLogic', id='center', programID='0', offset='0',
                         type='static' if controller == 'fixed' else 'actuated')
    if controller == 'actuated':
        for parameter in ('max-gap', 'detector-gap'):
            key = parameter.replace('-', '_') + '_s'
            ET.SubElement(program, 'param', key=parameter, value=str(config[key]))
    for arm in ARMS:
        for signal, seconds in [
            ('G', config['fixed_green_s']), ('y', config['yellow_s']), ('r', config['all_red_s'])
        ]:
            state = ['r'] * 12
            for index in groups[arm]:
                state[index] = signal
            phase = ET.SubElement(program, 'phase', duration=str(seconds), state=''.join(state))
            if controller == 'actuated' and signal == 'G':
                phase.set('minDur', str(config['min_green_s']))
                phase.set('maxDur', str(config['max_green_s']))
    root.insert(position, program)
    output = network_path.with_name(f'{controller}.net.xml')
    tree.write(output, encoding='utf-8', xml_declaration=True)
    return output
