"""Normalize quelware-client objects into serializable models."""

from __future__ import annotations

import enum
from collections import Counter, defaultdict
from collections.abc import Sequence

from quelware_core.entities.instrument import (
    ConfigVariant,
    InstrumentInfo,
    ProfileVariant,
)
from quelware_core.entities.port import PortInfo
from quelware_core.entities.resource import ResourceInfo

from quel3_tool.model import InstrumentSnapshot, PortSnapshot


def enum_name(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, enum.Enum):
        return value.name
    return str(value)


def category_name(value: object) -> str:
    return (enum_name(value) or "UNKNOWN").rsplit(".", maxsplit=1)[-1]


def unit_label(resource_id: str) -> str:
    return resource_id.split(":", maxsplit=1)[0]


def resource_id(resource_info: ResourceInfo) -> str:
    return str(resource_info.id)


def is_visible(resource_info: ResourceInfo, selected_units: Sequence[str]) -> bool:
    return (
        not selected_units or unit_label(resource_id(resource_info)) in selected_units
    )


def count_resources(
    resource_infos: Sequence[ResourceInfo],
) -> dict[str, dict[str, int]]:
    counters: dict[str, Counter[str]] = defaultdict(Counter)
    for info in resource_infos:
        unit = unit_label(resource_id(info))
        category = category_name(info.category)
        counters[unit][category] += 1
    return {
        unit: dict(sorted(counts.items())) for unit, counts in sorted(counters.items())
    }


def port_snapshot(port_info: PortInfo) -> PortSnapshot:
    port_id = str(port_info.id)
    depends_on = tuple(str(item) for item in port_info.depends_on)
    return PortSnapshot(
        id=port_id,
        unit_label=unit_label(port_id),
        role=enum_name(port_info.role),
        depends_on=depends_on,
    )


def instrument_snapshot(
    instrument_info: InstrumentInfo[ProfileVariant, ConfigVariant],
) -> InstrumentSnapshot:
    instrument_id = str(instrument_info.id)
    port_id = str(instrument_info.port_id)
    definition = instrument_info.definition
    config = instrument_info.config
    profile = definition.profile
    alias = string_or_none(definition.alias)
    return InstrumentSnapshot(
        id=instrument_id,
        unit_label=unit_label(instrument_id),
        port_id=port_id,
        alias=alias,
        normalized_alias=normalize_alias(alias, port_id),
        role=enum_name(definition.role),
        mode=enum_name(definition.mode),
        frequency_range_min_hz=float_or_none(profile.frequency_range_min),
        frequency_range_max_hz=float_or_none(profile.frequency_range_max),
        sampling_period_fs=int_or_none(config.sampling_period_fs),
        bitdepth=int_or_none(config.bitdepth),
        timeline_step_samples=int_or_none(config.timeline_step_samples),
        samples_per_tick=int_or_none(config.samples_per_tick),
    )


def normalize_alias(alias: str | None, port_id: str) -> str | None:
    if alias is None:
        return None
    prefix = f"{unit_label(port_id)}:"
    stripped = alias.strip()
    if stripped.startswith(prefix):
        stripped = stripped[len(prefix) :].strip()
    return stripped or None


def string_or_none(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def float_or_none(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) else None
