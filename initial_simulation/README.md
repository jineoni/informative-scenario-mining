# Initial SUMO Scenario Pipeline

This folder contains a standalone scenario generation and evaluation pipeline. Run it from the repository root, or call the same functions from `notebooks/04_scenario_pipeline.ipynb`. Markdown, comments, and generated plots use English.

## Folder structure

```text
initial_simulation/
├── README.md                 # Structure, execution, and experiment design
├── configs/default.json      # Feature levels and fixed simulation settings
├── config.py                 # Configuration validation and executable discovery
├── network.py                # Shared geometry and two signal programs
├── demand.py                 # Q and D to directional movement flows
├── runner.py                 # Preparation, execution, caching, and GUI replay
├── evaluation.py             # Vehicle outcomes and queue aggregation
├── plotting.py               # Input, metric, and queue visualizations
├── __init__.py               # Public Python API
├── __main__.py               # Command-line interface
└── tests/test_pipeline.py    # Feature, geometry, and aggregation checks

notebooks/04_scenario_pipeline.ipynb
results/initial_simulation/
├── pilot/                    # Short fixed-time demand review
└── baseline/                 # Full nine-scenario, two-controller experiment
```

Each experiment directory contains:

```text
experiment.json              # Config/code/SUMO signature and input checksums
config.json                  # Exact configuration snapshot
scenarios.csv                # Requested and effective scenario features
network/                     # Nodes, edges, connections, and controller networks
scenarios/s01/
├── demand.rou.xml            # Shared route/flow input for both controllers
└── flows.csv                 # Movement rates, cohorts, and scheduled counts
runs/s01/fixed/               # The actuated controller has a parallel directory
├── run.sumocfg               # Evaluation configuration with output destinations
├── replay.sumocfg            # GUI configuration without evaluation outputs
├── run.json                  # Status, command, metrics, and output checksums
├── tripinfo.xml.gz           # Completed, unfinished, and uninserted vehicles
├── fcd.xml.gz                # Per-step vehicle IDs, lanes, and speeds
├── summary.xml.gz            # Network loading/insertion/completion counts
├── statistics.xml            # Overall statistics, teleports, and safety counts
├── collisions.xml            # Collision events
├── vehicles.csv              # Evaluation-cohort vehicle records
├── queues.csv                # Evaluation-window approach and total queues
└── sumo.*.log                # Captured SUMO output
summary.csv                  # One row per completed simulation run
failures.csv                 # Failed runs, if any
figures/                     # Figures saved by the notebook
```

Generated experiment directories are ignored by Git. The notebook retains tables and figures, and raw results can be regenerated from the configuration.

## How to run

### Environment

Use the existing `scenario-mining` environment. If it does not exist, create it using the repository's `environment.yml`.

```bash
conda env create -f environment.yml  # Only when creating the environment
conda activate scenario-mining
```

Install SUMO separately. `sumo`, `netconvert`, and optionally `sumo-gui` must be available. Discovery checks `SUMO_HOME/bin`, `PATH`, and the standard Eclipse SUMO framework location on macOS. The pipeline runs SUMO as a subprocess and parses its outputs; it does not require a live TraCI connection or a notebook kernel to run simulations.

### Command line

Run these commands from the repository root:

```bash
# Short demand review: all nine scenarios, fixed-time controller only
python -m initial_simulation pilot --output-dir results/initial_simulation/pilot

# Full experiment: nine scenarios and both controllers
python -m initial_simulation run --output-dir results/initial_simulation/baseline

# Read existing results without starting SUMO
python -m initial_simulation summarize --output-dir results/initial_simulation/baseline
```

To inspect inputs before simulating:

```bash
python -m initial_simulation prepare --output-dir results/initial_simulation/baseline
```

A smaller execution can select scenario IDs or controllers:

```bash
python -m initial_simulation run --output-dir results/initial_simulation/subset \
  --scenarios s05 --controllers fixed actuated
```

Change `configs/default.json`, or provide another configuration:

```bash
python -m initial_simulation run --config path/to/experiment.json \
  --output-dir results/initial_simulation/experiment_02
```

Use a new output directory after changing configuration, simulation/evaluation Python code, or SUMO version. A directory's signature prevents mixing different experiments. Repeating the same command reuses successful runs whose inputs and outputs still match their checksums. Failed or incomplete runs are retried. `--rerun` repeats matching completed runs; it does not override a configuration mismatch. `summarize` and `load_results` can read older results after code changes. Plot styling is excluded from the simulation signature, so changing figure appearance does not require new SUMO runs.

### Notebook

Open `notebooks/04_scenario_pipeline.ipynb`, select the `scenario-mining` kernel, and run the cells in order. It calls the same public API, shows the pilot, checks generated inputs, runs or reuses the full experiment, and plots the results.

```python
from initial_simulation import load_config, run_experiment, load_results

config = load_config()
directory = run_experiment(config, output_dir="results/initial_simulation/baseline")
results = load_results(directory)
summary = results["summary"]
```

Change the notebook's experiment directory names when using a different configuration. Existing results can be loaded directly without executing the pilot or simulation cells.

### GUI replay

```bash
# Print the replay command
python -m initial_simulation gui --output-dir results/initial_simulation/baseline \
  --scenario s08 --controller actuated

# Launch it
python -m initial_simulation gui --output-dir results/initial_simulation/baseline \
  --scenario s08 --controller actuated --launch
```

Replay uses the same network, demand, timing, and seed, but writes no evaluation outputs. Opening the GUI does not overwrite the completed experiment's data. The notebook prints these commands and does not launch a GUI automatically.

### Checks

```bash
python -m unittest discover -s initial_simulation/tests -v
```

Tests cover directional feature mapping, finite-window flow rounding, invalid configuration, compatible signal movements, identical controller geometry, the queue window/speed threshold, and completed-versus-censored vehicle aggregation.

## Pipeline design

### Research question and scope

How do total traffic demand and directional imbalance change the performance difference between fixed-time and actuated traffic signals?

This is a small synthetic experiment, not a calibrated reconstruction of an Atlanta intersection. It enumerates the feature grid and compares outcomes. It does not yet optimize scenario selection, tune each controller, or define a general informativeness score. Compass observations are not interpreted as total traffic counts.

The execution stages are:

```text
Read configuration
→ build and validate network/signals
→ translate feature combinations into shared movement flows
→ run controllers
→ aggregate and validate outputs
→ compare scenario-level results
→ replay selected scenarios
```

### Scenario features

Let `q_N`, `q_E`, `q_S`, and `q_W` denote requested approach flow rates in vehicles/hour.

- Total demand: `Q = q_N + q_E + q_S + q_W`.
- Directional imbalance: `D = (q_N + q_S - q_E - q_W) / Q`.
- Mapping: `q_N = q_S = Q(1+D)/4`; `q_E = q_W = Q(1-D)/4`.

| Feature | Default levels | Interpretation |
|---|---|---|
| Total demand Q | 600, 1200, 1800 veh/h | Low, medium, and high candidate demand |
| Directional imbalance D | -0.5, 0, 0.5 | EW-heavy, balanced, NS-heavy |

The resulting nine scenarios are ordered by increasing Q, then increasing D. For Q = 1200 veh/h:

| D | N | E | S | W |
|---:|---:|---:|---:|---:|
| -0.5 | 150 | 450 | 150 | 450 |
| 0 | 300 | 300 | 300 | 300 |
| 0.5 | 450 | 150 | 450 | 150 |

The pipeline creates route-specific `<flow vehsPerHour="...">` definitions, not a native SUMO imbalance parameter. Left, through, and right movements receive 10%, 80%, and 10% of each approach's rate.

A regular SUMO flow requests its first vehicle at `begin` and repeats before `end`. Integer vehicle counts therefore need not equal `rate × duration` exactly. For example, 45 veh/h over 1800 seconds produces 23 requests. `scenarios.csv` reports requested Q/D alongside effective Q/D, turning share, and scheduled evaluation counts. These are input checks, not additional scenario features. Uninserted demand remains part of the evaluation cohort.

### Demand pilot

`pilot` uses the same geometry, signal parameters, feature grid, and fixed-time controller with a 120-second warm-up, 600-second demand window, and 300-second drain.

Review average queue size, queue evolution, completion, and uninserted demand to assess whether candidate levels span lighter and more congested conditions. It does not search for levels that maximize controller differences or silently change the final configuration. The default levels remain synthetic design choices, not empirically estimated Atlanta ranges. The notebook exposes the pilot before the full experiment.

### Fixed conditions

| Setting | Default |
|---|---|
| Geometry | One symmetric four-arm intersection |
| Lanes | One inbound and one outbound lane per arm |
| Outer nodes | 200 m from the intersection center |
| Speed limit | 50 km/h |
| Turning proportions | 10% left, 80% through, 10% right on every approach |
| U-turns and pedestrians | Excluded |
| Vehicle model | Passenger car, Krauss car following |
| Vehicle length / minimum gap | 5 m / 2.5 m |
| Acceleration / deceleration | 2.6 / 4.5 m/s² |
| Time headway | 1 s |
| Driver noise / speed deviation | sigma = 0; speedDev = 0; speedFactor = 1 |
| Departures | Regular movement flows; no randomized demand |
| Insertion | `departPos="base"`, `departLane="0"`, `departSpeed="max"` |
| Arrival | `arrivalPos="max"` on the route's final edge |
| Timestep / seed | 1 s / 0 |
| Automatic jam teleports | Disabled |

SUMO trims external lanes around junction geometry, so a 200 m node-to-center distance is not an exact 200 m usable lane. The generated lane lengths are stored in `network/network.json`. All twelve permitted movement connections are checked explicitly.

Movement streams can have coincident departure requests. This regular-flow prototype is not a Poisson-arrival or platoon model. The same input file is shared across controllers. One deterministic run per scenario/controller is used; seed repetition is deferred until explicit stochastic inputs are introduced.

### Controllers

Both controllers use the same N → E → S → W service order, with only one approach green at a time. All three movements from that approach receive unconditional green, avoiding opposing left-turn conflicts and allowing the actuated controller to use its approach detector.

| Setting | Fixed-time | Actuated |
|---|---|---|
| Green | 20 s per approach | 10–40 s |
| Yellow | 3 s | 3 s |
| All-red | 1 s | 1 s |
| Green termination | Fixed duration | SUMO detector-based actuation |
| Maximum detector gap | Not applicable | 3 s |
| Detector distance setting | Not applicable | 2 s at lane maximum speed |

These are initial reference programs, not optimized real-world timings. The two controller `.net.xml` files have identical geometry and connections; only `tlLogic` differs. The program is embedded before signal-controlled connections to avoid duplicate logic IDs. The `.add.xml` files are readable signal definitions, not additionally loaded on top of these network files.

### Timing and spatial measurement boundaries

The full run has a 300-second warm-up, 1800-second evaluation-demand window, and 900-second drain. Flows stop after the demand window. Runs have a common fixed cutoff at 3000 seconds, even if all vehicles finish earlier.

The vehicle evaluation cohort consists of flows whose IDs begin with `eval_`, scheduled during `[300, 2100)`. Warm-up vehicles affect the traffic state but do not enter vehicle-level means. A vehicle scheduled during the evaluation window remains in the cohort even if actual insertion occurs during the drain.

Travel time starts when a vehicle is actually inserted near the beginning of its inbound lane and ends at the end of its outbound lane. It includes approach travel, junction passage, and outbound travel. It does not measure only stop-line crossing time or include pre-insertion waiting. The origin/destination definitions are common to both controllers.

### Three primary performance metrics

| Metric | Definition | Unit and aggregation |
|---|---|---|
| Average delay | SUMO `timeLoss`: accumulated loss from driving below ideal speed | Mean over completed evaluation vehicles, seconds/vehicle |
| Average queue length | Vehicles with speed strictly below 0.1 m/s on the four inbound lanes | Time mean of the summed approach counts, vehicles |
| Average travel time | TripInfo `duration`, actual insertion to arrival | Mean over completed evaluation vehicles, seconds/vehicle |

Delay uses SUMO's `timeLoss` definition, not a separately reconstructed HCM control delay. It includes slow driving as well as stopped time and excludes pre-insertion delay. Queue length is a stopped-vehicle proxy, not a measured contiguous queue in meters.

Queue counts are calculated from full-resolution FCD speed/lane output at every evaluation timestep, including empty timesteps. For a constant timestep, the arithmetic mean equals the time average. Queue snapshots include all vehicles physically present, including remaining warm-up vehicles. Per-approach means and traces are retained. The primary total queue mean is the sum of the four approach means, not their average.

`departDelay`, completion, unfinished vehicles, uninserted vehicles, collisions, teleports, and removals are supporting checks rather than extra primary metrics. SUMO's `vaporized="end"` marks a record written at the cutoff; it is treated as censoring, not as an abnormal removal. Vehicle IDs must reconcile exactly with the scheduled cohort.

The two vehicle means can be biased downward when heavily delayed vehicles have not completed. Plots mark incomplete cohorts with `*`. The difference table withholds delay/travel-time comparisons unless both controllers have valid, complete cohorts; queue differences remain comparable over the common time window. No incomplete vehicle is assigned zero travel time or zero delay.

### Initial scenario analysis

There are 18 full runs: nine feature combinations × two controllers. Compare the three metrics across the feature grid, inspect signed fixed-minus-actuated differences where valid, then examine approach-level queue traces and GUI replay for selected scenarios. EW-heavy and NS-heavy cases are useful symmetry checks, but finite-horizon signal-phase alignment can produce small differences.

These results describe the configured synthetic network. They do not establish general controller superiority or the statistical reliability of an informativeness criterion.

## SUMO references

- [Vehicle, route, and flow definitions](https://sumo.dlr.de/docs/Definition_of_Vehicles%2C_Vehicle_Types%2C_and_Routes.html)
- [Fixed-time and actuated traffic lights](https://sumo.dlr.de/docs/Simulation/Traffic_Lights.html)
- [TripInfo fields and unfinished vehicles](https://sumo.dlr.de/docs/Simulation/Output/TripInfo.html)
- [Floating car data output](https://sumo.dlr.de/docs/Simulation/Output/FCDOutput.html)
