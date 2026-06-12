"""Deploy instruments and run fixed-timeline pulses."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from quelware_client.client import create_quelware_client
from quelware_client.core.instrument_driver import (
    create_instrument_driver_fixed_timeline,
)
from quelware_core.entities import directives
from quelware_core.entities.instrument import (
    FixedTimelineProfile,
    InstrumentDefinition,
    InstrumentInfo,
    InstrumentMode,
    InstrumentRole,
)
from quelware_core.entities.result import ResultContainer
from quelware_core.entities.waveform.sampled import IqWaveform, iq_array_from_lists

from quel3_tool._run.config import (
    CaptureConfig,
    EventConfig,
    ExperimentConfig,
    InstrumentConfig,
    RunConfig,
    WaveformConfig,
    load_config,
)


@dataclass(frozen=True, slots=True)
class DeployResult:
    instruments: tuple[InstrumentInfo, ...]


@dataclass(frozen=True, slots=True)
class RunResult:
    instruments: tuple[InstrumentInfo, ...]
    trigger_count: int
    output_files: tuple[Path, ...]


def deploy_from_file(
    config_path: Path,
    *,
    endpoint: str,
    port: int,
    timeout_seconds: float,
) -> DeployResult:
    config = load_config(config_path)
    return asyncio.run(
        asyncio.wait_for(
            deploy_async(config, endpoint=endpoint, port=port),
            timeout=timeout_seconds,
        )
    )


def run_from_file(
    config_path: Path,
    *,
    endpoint: str,
    port: int,
    timeout_seconds: float,
) -> RunResult:
    config = load_config(config_path)
    return asyncio.run(
        asyncio.wait_for(
            run_async(config, endpoint=endpoint, port=port),
            timeout=timeout_seconds,
        )
    )


async def deploy_async(
    config: ExperimentConfig,
    *,
    endpoint: str,
    port: int,
) -> DeployResult:
    async with create_quelware_client(endpoint, port) as client:
        instruments = await deploy_instruments(client, config.instruments)
    return DeployResult(tuple(instruments))


async def run_async(
    config: ExperimentConfig,
    *,
    endpoint: str,
    port: int,
) -> RunResult:
    if config.run_config is None:
        raise ValueError("run command requires [[run_config]]")

    async with create_quelware_client(endpoint, port) as client:
        instruments = await deploy_instruments(client, config.instruments)
        trigger_count, results = await run_pulses(
            client,
            config.run_config,
            instruments,
            config.waveforms,
            config.events,
            config.captures,
        )

    output_files = save_results(config.run_config.output_dir, results)
    return RunResult(tuple(instruments), trigger_count, tuple(output_files))


async def deploy_instruments(
    client,
    instruments: Sequence[InstrumentConfig],
) -> list[InstrumentInfo]:
    deployed: list[InstrumentInfo] = []
    for port_id, configs in group_by_port(instruments).items():
        definitions = [instrument_definition(config) for config in configs]
        async with client.create_session([port_id]) as session:
            deployed.extend(
                await session.deploy_instruments(
                    port_id,
                    definitions=definitions,
                    append=False,
                )
            )
    return deployed


async def run_pulses(
    client,
    run_config: RunConfig,
    instruments: Sequence[InstrumentInfo],
    waveform_configs: Sequence[WaveformConfig],
    event_configs: Sequence[EventConfig],
    capture_configs: Sequence[CaptureConfig],
) -> tuple[int, dict[str, ResultContainer]]:
    waveforms = make_waveforms(waveform_configs)
    instrument_ids = [instrument.id for instrument in instruments]
    capture_aliases = {capture.alias for capture in capture_configs}
    results: dict[str, ResultContainer] = {}

    async with client.create_session(
        instrument_ids,
        ttl_ms=10_000,
        tentative_ttl_ms=5_000,
    ) as session:
        drivers = {
            config_alias(instrument): create_instrument_driver_fixed_timeline(
                session,
                instrument,
            )
            for instrument in instruments
        }
        await asyncio.gather(*(driver.initialize() for driver in drivers.values()))
        await asyncio.gather(
            *(
                apply_instrument_config(
                    drivers[config_alias(instrument)],
                    instrument,
                    run_config,
                    waveforms,
                    event_configs,
                    capture_configs,
                )
                for instrument in instruments
            )
        )
        trigger_count = await session.trigger(instrument_ids)
        for alias in capture_aliases:
            if alias in drivers:
                results[alias] = await drivers[alias].fetch_result()

    return trigger_count, results


async def apply_instrument_config(
    driver,
    instrument: InstrumentInfo,
    run_config: RunConfig,
    waveforms: dict[str, IqWaveform],
    event_configs: Sequence[EventConfig],
    capture_configs: Sequence[CaptureConfig],
) -> bool:
    return await driver.apply(
        directives_for_instrument(
            instrument,
            run_config,
            waveforms,
            event_configs,
            capture_configs,
        )
    )


def instrument_definition(config: InstrumentConfig) -> InstrumentDefinition:
    return InstrumentDefinition(
        alias=config.alias,
        mode=InstrumentMode.FIXED_TIMELINE,
        role=instrument_role(config),
        profile=FixedTimelineProfile(
            frequency_range_min=config.freq_min_ghz * 1e9,
            frequency_range_max=config.freq_max_ghz * 1e9,
        ),
    )


def instrument_role(config: InstrumentConfig) -> InstrumentRole:
    name = config.role.upper().replace("-", "_")
    return InstrumentRole[name]


def group_by_port(
    instruments: Sequence[InstrumentConfig],
) -> dict[str, list[InstrumentConfig]]:
    grouped: dict[str, list[InstrumentConfig]] = {}
    for instrument in instruments:
        grouped.setdefault(instrument.port_id, []).append(instrument)
    return grouped


def make_waveforms(
    waveform_configs: Sequence[WaveformConfig],
) -> dict[str, IqWaveform]:
    waveforms: dict[str, IqWaveform] = {}
    for config in waveform_configs:
        if len(config.i) != len(config.q):
            raise ValueError(f"waveform {config.name!r} has mismatched I/Q lengths")
        waveforms[config.name] = IqWaveform(
            sampling_period_fs=config.sampling_period_fs,
            iq_array=iq_array_from_lists(config.i, config.q),
        )
    return waveforms


def directives_for_instrument(
    instrument: InstrumentInfo,
    run_config: RunConfig,
    waveforms: dict[str, IqWaveform],
    event_configs: Sequence[EventConfig],
    capture_configs: Sequence[CaptureConfig],
) -> list[directives.FixedTimelineDirective]:
    alias = config_alias(instrument)
    waveform_names = list(
        set(event.waveform for event in event_configs if event.alias == alias)
    )
    library = list(waveforms[name] for name in waveform_names)
    events = [
        directives.WaveformEvent(
            waveform_index=waveform_names.index(event.waveform),
            start_offset_samples=event.start_offset_samples,
            gain=event.gain,
            phase_offset_deg=event.phase_offset_deg,
        )
        for event in event_configs
        if event.alias == alias
    ]
    captures = [
        directives.CaptureWindow(
            name=capture.name,
            start_offset_samples=capture.start_offset_samples,
            length_samples=capture.length_samples,
        )
        for capture in capture_configs
        if capture.alias == alias
    ]
    timeline = directives.SetFixedTimeline(
        waveform_library=library,
        events=events,
        capture_windows=captures,
        length=timeline_length(
            instrument,
            run_config,
            waveforms,
            event_configs,
            capture_configs,
        ),
        iterations=run_config.iterations,
    )
    result: list[directives.FixedTimelineDirective] = [
        directives.SetFrequency(hz=center_frequency_hz(instrument)),
        timeline,
    ]
    if captures:
        result.insert(1, directives.SetCaptureMode(mode=capture_mode(run_config)))
    return result


def timeline_length(
    instrument: InstrumentInfo,
    run_config: RunConfig,
    waveforms: dict[str, IqWaveform],
    event_configs: Sequence[EventConfig],
    capture_configs: Sequence[CaptureConfig],
) -> int:
    alias = config_alias(instrument)
    period_fs = instrument.config.sampling_period_fs
    length = max(1, round(run_config.iteration_interval_ns * 1_000_000 / period_fs))
    for event in event_configs:
        if event.alias == alias:
            length = max(
                length,
                event.start_offset_samples + len(waveforms[event.waveform].iq_array),
            )
    for capture in capture_configs:
        if capture.alias == alias:
            length = max(length, capture.start_offset_samples + capture.length_samples)
    step = max(1, instrument.config.timeline_step_samples)
    return math.ceil(length / step) * step


def capture_mode(run_config: RunConfig) -> directives.CaptureMode:
    name = run_config.capture_mode.upper()
    if name == "RAW_WAVEFORM":
        name = "RAW_WAVEFORMS"
    return directives.CaptureMode[name]


def center_frequency_hz(instrument: InstrumentInfo) -> float:
    profile = instrument.definition.profile
    return (profile.frequency_range_min + profile.frequency_range_max) / 2


def config_alias(instrument: InstrumentInfo) -> str:
    return instrument.definition.alias.rsplit(":", 1)[-1]


def save_results(
    output_dir: Path,
    results: dict[str, ResultContainer],
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for alias, result in results.items():
        for window, waveforms in result.iq_waveform_result.items():
            path = output_dir / f"{alias}_{window}_waveforms.npy"
            np.save(path, np.stack([waveform.iq_array for waveform in waveforms]))
            saved.append(path)
        for window, points in result.iq_point_result.items():
            path = output_dir / f"{alias}_{window}_points.npy"
            np.save(path, np.asarray(points, dtype=np.complex128))
            saved.append(path)
        for window, integers in result.integer_result.items():
            path = output_dir / f"{alias}_{window}_integers.npy"
            np.save(path, np.asarray(integers, dtype=np.int64))
            saved.append(path)
    return saved
