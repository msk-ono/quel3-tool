"""TOML configuration for deploy/run commands."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


@dataclass(frozen=True, slots=True)
class InstrumentConfig:
    alias: str
    port_id: str
    role: str
    freq_min_ghz: float
    freq_max_ghz: float


@dataclass(frozen=True, slots=True)
class RunConfig:
    iterations: int
    iteration_interval_ns: int
    capture_mode: str
    output_dir: Path


@dataclass(frozen=True, slots=True)
class WaveformConfig:
    name: str
    sampling_period_fs: int
    i: tuple[float, ...]
    q: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class EventConfig:
    alias: str
    waveform: str
    start_offset_samples: int
    gain: float
    phase_offset_deg: float


@dataclass(frozen=True, slots=True)
class CaptureConfig:
    alias: str
    name: str
    start_offset_samples: int
    length_samples: int


@dataclass(frozen=True, slots=True)
class ExperimentConfig:
    instruments: tuple[InstrumentConfig, ...]
    run_config: RunConfig | None
    waveforms: tuple[WaveformConfig, ...]
    events: tuple[EventConfig, ...]
    captures: tuple[CaptureConfig, ...]


def load_config(path: Path) -> ExperimentConfig:
    with path.open("rb") as file:
        data = tomllib.load(file)

    run_configs = data.get("run_config", [])
    if len(run_configs) > 1:
        raise ValueError("config must contain at most one [[run_config]] table")

    return ExperimentConfig(
        instruments=tuple(
            InstrumentConfig(
                alias=str(item["alias"]),
                port_id=str(item["port_id"]),
                role=str(item["role"]),
                freq_min_ghz=float(item["freq_min_ghz"]),
                freq_max_ghz=float(item["freq_max_ghz"]),
            )
            for item in list_of_tables(data, "instrument")
        ),
        run_config=parse_run_config(run_configs[0]) if run_configs else None,
        waveforms=tuple(
            WaveformConfig(
                name=str(item["name"]),
                sampling_period_fs=int(item["sampling_period_fs"]),
                i=tuple(float(value) for value in item["i"]),
                q=tuple(float(value) for value in item["q"]),
            )
            for item in list_of_tables(data, "waveform")
        ),
        events=tuple(
            EventConfig(
                alias=str(item["alias"]),
                waveform=str(item["waveform"]),
                start_offset_samples=int(item["start_offset_samples"]),
                gain=float(item["gain"]),
                phase_offset_deg=float(item["phase_offset_deg"]),
            )
            for item in list_of_tables(data, "event")
        ),
        captures=tuple(
            CaptureConfig(
                alias=str(item["alias"]),
                name=str(item["name"]),
                start_offset_samples=int(item["start_offset_samples"]),
                length_samples=int(item["length_samples"]),
            )
            for item in list_of_tables(data, "capture")
        ),
    )


def parse_run_config(item: dict[str, Any]) -> RunConfig:
    return RunConfig(
        iterations=int(item["iterations"]),
        iteration_interval_ns=int(item["iteration_interval_ns"]),
        capture_mode=str(item["capture_mode"]),
        output_dir=Path(str(item["output_dir"])),
    )


def list_of_tables(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{key} must be an array of TOML tables")
    return value
