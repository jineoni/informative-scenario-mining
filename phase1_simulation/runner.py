"""Write a SUMO run configuration and execute it."""

from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET


def run_sumo(network_path, demand_path, config, output_dir, sumo='sumo'):
    directory = Path(output_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    root = ET.Element('configuration')
    for section, options in {
        'input': {'net-file': Path(network_path).resolve(), 'route-files': Path(demand_path).resolve()},
        'time': {'begin': 0, 'end': 6 * config['bin_s'] + config['drain_s'], 'step-length': 1},
        'processing': {'time-to-teleport': -1, 'max-depart-delay': -1},
        'output': {'tripinfo-output': 'tripinfo.xml.gz', 'tripinfo-output.write-unfinished': 'true',
                   'tripinfo-output.write-undeparted': 'true', 'fcd-output': 'fcd.xml.gz',
                   'fcd-output.attributes': 'id,speed,lane'},
    }.items():
        group = ET.SubElement(root, section)
        for key, value in options.items():
            ET.SubElement(group, key, value=str(value))
    ET.indent(root)
    path = directory / 'run.sumocfg'
    ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)
    executable = shutil.which(str(sumo))
    if executable is None:
        raise FileNotFoundError('Set SUMO to the installed sumo executable.')
    with (directory / 'sumo.log').open('w') as log:
        result = subprocess.run([executable, '-c', path.name, '--no-step-log', 'true'],
                                cwd=directory, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'SUMO failed. See {directory / "sumo.log"}')
    return directory
