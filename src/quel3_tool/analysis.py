"""Derived checks for collected QuEL-3 state."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from quel3_tool.model import (
    InstrumentSnapshot,
    PortSnapshot,
    ResourceError,
    StateCheck,
    StateSnapshot,
    TargetType,
)


def evaluate(snapshot: StateSnapshot) -> tuple[StateCheck, ...]:
    checks = [
        StateCheck("ok", "OK", "Snapshot collection completed.", target_type="snapshot")
    ]
    if not snapshot.units:
        checks.append(
            StateCheck(
                "error",
                "NO_UNITS",
                "No QuEL-3 units discovered.",
                target_type="snapshot",
            )
        )

    discovered = {unit.label for unit in snapshot.units}
    missing = sorted(set(snapshot.selected_unit_labels) - discovered)
    if missing:
        checks.append(
            StateCheck(
                "error",
                "UNIT_NOT_FOUND",
                "Selected unit labels were not discovered.",
                ", ".join(missing),
                target_type="snapshot",
            )
        )

    checks.extend(
        StateCheck(
            "warning",
            "UNIT_STATUS",
            f"Unit {unit.label} is not ACTIVE.",
            unit.status,
            target_type="unit",
            target_id=unit.label,
        )
        for unit in snapshot.units
        if unit.status is not None and unit.status != "ACTIVE"
    )
    if not snapshot.ports:
        checks.append(StateCheck("warning", "NO_PORTS", "No port resources found."))
    if not snapshot.instruments:
        checks.append(
            StateCheck("warning", "NO_INSTRUMENTS", "No instrument resources found.")
        )

    checks.extend(fetch_error_checks(snapshot.errors))
    checks.extend(port_dependency_checks(snapshot.ports))
    checks.extend(instrument_checks(snapshot.instruments, snapshot.ports))
    return tuple(checks)


def fetch_error_checks(errors: Sequence[ResourceError]) -> list[StateCheck]:
    return [
        StateCheck(
            "error",
            "RESOURCE_FETCH_ERROR",
            f"{error.operation} failed for {error.resource_id}.",
            error.message,
            target_type=target_type(error.operation),
            target_id=error.resource_id,
        )
        for error in errors
    ]


def port_dependency_checks(ports: Sequence[PortSnapshot]) -> list[StateCheck]:
    checks: list[StateCheck] = []
    port_ids = {port.id for port in ports}
    for port in ports:
        missing = [
            resource_id
            for resource_id in port.depends_on
            if resource_id not in port_ids
        ]
        if missing:
            checks.append(
                StateCheck(
                    "warning",
                    "UNKNOWN_PORT_DEPENDENCY",
                    f"Port {port.id} references resources not listed as ports.",
                    ", ".join(missing),
                    target_type="port",
                    target_id=port.id,
                )
            )
    return checks


def instrument_checks(
    instruments: Sequence[InstrumentSnapshot],
    ports: Sequence[PortSnapshot],
) -> list[StateCheck]:
    checks: list[StateCheck] = []
    port_ids = {port.id for port in ports}
    checks.extend(duplicate_alias_checks(instruments))
    for instrument in instruments:
        if instrument.port_id not in port_ids:
            checks.append(
                StateCheck(
                    "error",
                    "ORPHAN_INSTRUMENT",
                    f"Instrument {instrument.id} points to an unknown port.",
                    instrument.port_id,
                    target_type="instrument",
                    target_id=instrument.id,
                )
            )
        if not instrument.alias:
            checks.append(
                StateCheck(
                    "warning",
                    "EMPTY_INSTRUMENT_ALIAS",
                    f"Instrument {instrument.id} has no alias.",
                    target_type="instrument",
                    target_id=instrument.id,
                )
            )
        checks.extend(frequency_checks(instrument))
    return checks


def duplicate_alias_checks(
    instruments: Sequence[InstrumentSnapshot],
) -> list[StateCheck]:
    counts = Counter(instrument.alias for instrument in instruments if instrument.alias)
    return [
        StateCheck(
            "warning",
            "DUPLICATE_INSTRUMENT_ALIAS",
            f"Instrument alias {alias} appears {count} times.",
            target_type="snapshot",
        )
        for alias, count in sorted(counts.items())
        if count > 1
    ]


def frequency_checks(instrument: InstrumentSnapshot) -> list[StateCheck]:
    lower = instrument.frequency_range_min_hz
    upper = instrument.frequency_range_max_hz
    if lower is None or upper is None:
        return [
            StateCheck(
                "warning",
                "MISSING_FREQUENCY_RANGE",
                f"Instrument {instrument.id} has no complete frequency range.",
                target_type="instrument",
                target_id=instrument.id,
            )
        ]
    if lower >= upper:
        return [
            StateCheck(
                "error",
                "INVALID_FREQUENCY_RANGE",
                f"Instrument {instrument.id} has an invalid frequency range.",
                f"{lower} >= {upper}",
                target_type="instrument",
                target_id=instrument.id,
            )
        ]
    return []


def target_type(operation: str) -> TargetType:
    targets: dict[str, TargetType] = {
        "get_port_info": "port",
        "get_instrument_info": "instrument",
        "dump_port_state": "port",
    }
    return targets.get(operation, "snapshot")
