"""Command-line entry point; notebooks use the same public functions."""
import argparse
import shlex
import subprocess

from . import gui_command, load_config, load_results, prepare_experiment, run_experiment, run_pilot


def main():
    parser = argparse.ArgumentParser(description='Generate and evaluate initial SUMO scenarios.')
    parser.add_argument('action', choices=['prepare', 'pilot', 'run', 'summarize', 'gui'])
    parser.add_argument('--config', help='JSON configuration; defaults to the bundled experiment.')
    parser.add_argument('--output-dir', required=True, help='Experiment directory; use separate pilot/full directories.')
    parser.add_argument('--controllers', nargs='+', choices=['fixed', 'actuated'], default=['fixed', 'actuated'])
    parser.add_argument('--scenarios', nargs='+', help='Optional scenario IDs, such as s01 s02.')
    parser.add_argument('--rerun', action='store_true', help='Repeat completed runs using the same prepared inputs.')
    parser.add_argument('--scenario', help='Scenario ID for GUI replay.')
    parser.add_argument('--controller', choices=['fixed', 'actuated'], default='fixed')
    parser.add_argument('--launch', action='store_true', help='Launch the GUI instead of printing its command.')
    args = parser.parse_args()
    if args.action == 'summarize':
        columns = ['scenario_id', 'demand_vph', 'imbalance', 'controller', 'average_delay_s',
                   'average_queue_vehicles', 'average_travel_time_s', 'completion_rate', 'valid_run']
        print(load_results(args.output_dir)['summary'][columns].round(3).to_string(index=False))
    elif args.action == 'gui':
        if not args.scenario:
            parser.error('--scenario is required for gui')
        command = gui_command(args.output_dir, args.scenario, args.controller)
        if args.launch:
            subprocess.Popen(command)
        else:
            print(shlex.join(command))
    else:
        config = load_config(args.config)
        if args.action == 'prepare':
            directory = prepare_experiment(config, args.output_dir)
        elif args.action == 'pilot':
            directory = run_pilot(config, args.output_dir)
        else:
            directory = run_experiment(config, args.output_dir, args.controllers, args.scenarios, args.rerun)
        print(directory)


if __name__ == '__main__':
    main()
