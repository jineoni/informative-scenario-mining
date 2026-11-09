"""Configuration and SUMO executable discovery for the initial experiment."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import json
import math
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = Path(__file__).parent / 'configs' / 'default.json'
ARMS = ('N', 'E', 'S', 'W')
CONTROLLERS = ('fixed', 'actuated')


@dataclass(frozen=True)
class PipelineConfig:
    demand_vph: tuple[float, ...] = (600, 1200, 1800)
    directional_imbalance: tuple[float, ...] = (-0.5, 0, 0.5)
    arm_length_m: float = 200
    speed_mps: float = 50 / 3.6
    left_share: float = 0.1
    right_share: float = 0.1
    warmup_s: int = 300
    evaluation_s: int = 1800
    drain_s: int = 900
    step_s: float = 1
    fixed_green_s: float = 20
    min_green_s: float = 10
    max_green_s: float = 40
    yellow_s: float = 3
    all_red_s: float = 1
    max_gap_s: float = 3
    detector_gap_s: float = 2
    vehicle_length_m: float = 5
    min_gap_m: float = 2.5
    accel_mps2: float = 2.6
    decel_mps2: float = 4.5
    tau_s: float = 1
    halt_speed_mps: float = 0.1
    seed: int = 0

    def __post_init__(self):
        object.__setattr__(self, 'demand_vph', tuple(self.demand_vph))
        object.__setattr__(self, 'directional_imbalance', tuple(self.directional_imbalance))
        for name in ('demand_vph', 'directional_imbalance'):
            values = getattr(self, name)
            if not values or len(set(values)) != len(values) or not all(math.isfinite(v) for v in values):
                raise ValueError(f'{name} must contain distinct finite levels.')
        if any(q <= 0 for q in self.demand_vph):
            raise ValueError('Demand must be positive.')
        if any(not -1 <= d <= 1 for d in self.directional_imbalance):
            raise ValueError('Directional imbalance must lie in [-1, 1].')
        if not (0 <= self.left_share <= 1 and 0 <= self.right_share <= 1
                and self.left_share + self.right_share <= 1):
            raise ValueError('Turning shares must be nonnegative and sum to at most one.')
        positive = ('arm_length_m', 'speed_mps', 'evaluation_s', 'step_s', 'fixed_green_s',
                    'min_green_s', 'max_green_s', 'yellow_s', 'all_red_s', 'max_gap_s',
                    'detector_gap_s', 'vehicle_length_m', 'min_gap_m', 'accel_mps2',
                    'decel_mps2', 'tau_s', 'halt_speed_mps')
        if any(not math.isfinite(getattr(self, key)) or getattr(self, key) <= 0 for key in positive):
            raise ValueError('Geometry, timing, vehicle, and detection parameters must be positive.')
        if self.warmup_s < 0 or self.drain_s < 0:
            raise ValueError('Warm-up and drain durations must be nonnegative.')
        if self.min_green_s > self.max_green_s:
            raise ValueError('Minimum green must not exceed maximum green.')
        if self.step_s > self.tau_s:
            raise ValueError('Step length must not exceed the car-following time headway.')
        for key in ('warmup_s', 'evaluation_s', 'drain_s'):
            if not math.isclose(getattr(self, key) / self.step_s, round(getattr(self, key) / self.step_s)):
                raise ValueError(f'{key} must be a multiple of step_s.')
        if self.arm_length_m <= 4 * (self.vehicle_length_m + self.min_gap_m):
            raise ValueError('Road segments are too short for this initial experiment.')

    @property
    def evaluation_end_s(self):
        return self.warmup_s + self.evaluation_s

    @property
    def end_s(self):
        return self.evaluation_end_s + self.drain_s

    def to_dict(self):
        return asdict(self)


def load_config(path: str | Path | None = None) -> PipelineConfig:
    raw = json.loads(Path(path or DEFAULT_CONFIG).read_text())
    unknown = set(raw) - {field.name for field in fields(PipelineConfig)}
    if unknown:
        raise ValueError(f'Unknown configuration keys: {sorted(unknown)}')
    return PipelineConfig(**raw)


def find_binary(name: str) -> str:
    candidates = []
    if os.environ.get('SUMO_HOME'):
        candidates.append(Path(os.environ['SUMO_HOME']) / 'bin' / name)
    found = shutil.which(name)
    if found:
        candidates.append(Path(found))
    candidates.append(Path('/Library/Frameworks/EclipseSUMO.framework/Versions/Current/EclipseSUMO/bin') / name)
    for path in candidates:
        if path.is_file() and os.access(path, os.X_OK):
            return str(path.resolve())
    raise FileNotFoundError(f'{name} not found. Add SUMO/bin to PATH or set SUMO_HOME to its installation root.')


def sumo_environment(binary):
    environment = os.environ.copy()
    home = Path(binary).resolve().parent.parent / 'share' / 'sumo'
    if (home / 'data' / 'xsd').is_dir():
        environment['SUMO_HOME'] = str(home)
    return environment
