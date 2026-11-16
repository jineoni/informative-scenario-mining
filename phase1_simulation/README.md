# Phase 1 SUMO Scenario Pipeline

Generate an hourly vehicle schedule, run the same demand under fixed-time and actuated control, and compare the results in [notebook 06](../notebooks/phase1/06_phase1_scenario_pipeline.ipynb). The package defines its own functions and uses SUMO and netconvert executables. Notebook 05 records the Compass IoT analysis that informed the candidate profiles.

## Structure

| File | Role |
|---|---|
| `configs/default.json` | Feature levels, road network, vehicle behavior, signal settings, and timing |
| `config.py` | Read and validate the experiment settings |
| `network.py` | Build the shared four-leg road network with netconvert |
| `controller.py` | Write a fixed-time or actuated signal program into the network |
| `demand.py` | Convert a scenario to vehicle routes and scheduled departures |
| `runner.py` | Write the SUMO run configuration and invoke SUMO |
| `evaluation.py` | Read SUMO outputs and calculate the evaluation metrics |
| `tests/test_pipeline.py` | Check vehicle allocation, headway scheduling, and evaluation rules |
| `__init__.py` | Expose the functions called by the notebook |

## Run the notebook

1. Open notebook 06 in the `scenario-mining` environment. Install SUMO separately and set `SUMO` and `NETCONVERT` in the first code cell if the executables are outside your PATH.
2. Run the setup and scenario cells. Choose a `SCENARIO_ID` from the candidate table. The notebook starts with a single example.
3. Run the demand cell and review the counts and scheduled platooning for each approach and bin. Run the controller comparison cell to simulate both controllers with that same schedule.

4. Run the full experiment section to simulate all schedulable scenarios with both controllers. It saves one row per run to `results/phase1_simulation/full_experiment/metrics.csv`.
5. Run the comparison section to view the scatter plots for mean delay, queue length, and travel time and the scenario heatmaps for each platooning target. All three scatter plots use the same scenarios with complete evaluation cohorts under both controllers. Within those scenarios, mean queue still counts all stopped vehicles on inbound lanes during the common evaluation window. The heatmaps distinguish infeasible schedules from incomplete simulated cohorts.

Each selected scenario writes to `results/phase1_simulation/<scenario_id>/`. The shared `demand.rou.xml` contains individual vehicles, and `network/` contains the common geometry and the two signal networks. The controller subdirectories hold `run.sumocfg`, `tripinfo.xml.gz`, `fcd.xml.gz`, and `sumo.log`. Running the same scenario again replaces its generated outputs.

## Scenario design

The default grid has **675 candidates** from 3 demand levels × 3 directional splits × 5 hourly profiles × 5 turning profiles × 3 platooning targets. The selected hourly and turning profiles apply to every approach in a scenario.

- **Total and directional demand.** `Q` sets the number of scheduled vehicles in the one-hour demand period. The north and south approaches each receive one quarter of the total times `1 + D`; the east and west approaches each receive one quarter times `1 - D`.
- **Routes and time bins.** Split each approach total by left, through, and right shares, then split each movement across the six 10-minute bins. Allocate whole vehicles by largest remainder at each step to preserve the parent total. JSON profiles are represented as weights, so six equal weights define uniform demand.
- **Platooning.** An approach-bin with `n` vehicles has `n - 1` headways. Round the target number of short headways to the nearest integer and spread 2 s gaps evenly through the sequence. When there are long gaps, distribute the remaining time among them as evenly as possible. At the 1 s simulation step, a long gap is at least 4 s. A bin with fewer than two vehicles has no measured headway share. A schedule that cannot fit its assigned vehicles and gaps within the bin raises an error identifying the approach and bin. The notebook reports the scheduled share alongside the target. Actual insertion times can shift when entry space is unavailable.
- **SUMO input.** Each `<vehicle>` names a route and an integer scheduled departure time. Vehicles are written in departure order and both controllers read the same file.

## Common simulation settings

| Setting | Default |
|---|---|
| Road network | Synthetic four-leg intersection, one inbound and one outbound lane per leg, 200 m from center to each network boundary, 50 km/h speed limit |
| Vehicles | Passenger cars, identical Krauss parameters, 1 s simulation step |
| Fixed-time signal | 20 s green per approach |
| Actuated signal | 10–40 s green per approach, 3 s maximum detector gap |
| Signal sequence | N → E → S → W, with 3 s yellow and 1 s all-red |
| Demand and cutoff | Departures scheduled during 0–60 min. The first 5 min serve as warm-up. No new departures are scheduled during the 60–75 min drain. |

## Evaluation

Vehicles scheduled during **5–60 min** form the evaluation cohort, regardless of their actual insertion time. Delay is the mean SUMO `timeLoss` and travel time is the mean time from insertion to arrival, both over vehicles that finish by the cutoff. Interpret these means alongside completion rate, which divides completed trips by scheduled evaluation vehicles. The mean queue is the time average of the total number of vehicles below 0.1 m/s on the four inbound lanes during **5–60 min**, including any warm-up vehicles still present.

## Tests

Run from the repository root in the project environment.

```bash
python -m unittest discover -s phase1_simulation/tests -v
```
