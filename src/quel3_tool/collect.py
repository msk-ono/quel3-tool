"""Read QuEL-3 state from quelware-client."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from quelware_client.client import create_quelware_client
from quelware_client.core import QuelwareClient
from quelware_core.entities.resource import ResourceCategory, ResourceId, ResourceInfo

from quel3_tool.analysis import evaluate
from quel3_tool.model import (
    InstrumentSnapshot,
    PortDiagnosis,
    PortSnapshot,
    Quel3RuntimeOptions,
    ResourceError,
    StateSnapshot,
    UnitSnapshot,
)
from quel3_tool.parsing import (
    count_resources,
    instrument_snapshot,
    is_visible,
    port_snapshot,
    unit_label,
)


async def collect_state_snapshot_async(
    options: Quel3RuntimeOptions | None = None,
    *,
    generated_at: str | None = None,
) -> StateSnapshot:
    options = Quel3RuntimeOptions() if options is None else options
    timestamp = generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")

    async with create_quelware_client(options.endpoint, options.port) as client:
        discovered = tuple(str(label) for label in await call(client.list_unit_labels))
        selected = tuple(options.unit_labels)
        visible_units = tuple(
            label for label in discovered if not selected or label in selected
        )
        units, unit_errors = collect_units(visible_units)

        all_resources = list(await call(client.list_resource_infos))
        resources = [info for info in all_resources if is_visible(info, selected)]
        ports, port_errors = await collect_ports(client, resources)
        instruments, instrument_errors = await collect_instruments(client, resources)
        instruments = filter_instruments_by_port(
            instruments,
            options.instrument_port_ids,
        )
        diagnoses, diagnosis_errors = await collect_port_diagnoses(
            client,
            ports,
            options.diagnosis_port_ids,
            enabled=options.include_diagnosis,
        )

    errors = (*unit_errors, *port_errors, *instrument_errors, *diagnosis_errors)
    snapshot = StateSnapshot(
        generated_at=timestamp,
        endpoint=options.endpoint,
        port=options.port,
        selected_unit_labels=selected,
        units=tuple(units),
        ports=tuple(ports),
        instruments=tuple(instruments),
        resource_counts_by_unit=count_resources(resources),
        port_diagnoses=tuple(diagnoses),
        errors=tuple(errors),
    )
    return replace(snapshot, checks=evaluate(snapshot))


def collect_state_snapshot(
    options: Quel3RuntimeOptions | None = None,
    *,
    generated_at: str | None = None,
) -> StateSnapshot:
    options = Quel3RuntimeOptions() if options is None else options
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            asyncio.wait_for(
                collect_state_snapshot_async(
                    options,
                    generated_at=generated_at,
                ),
                timeout=options.timeout_seconds,
            )
        )
    raise RuntimeError("Use collect_state_snapshot_async inside a running event loop.")


def collect_units(
    unit_labels: Sequence[str],
) -> tuple[list[UnitSnapshot], tuple[ResourceError, ...]]:
    return [UnitSnapshot(label) for label in unit_labels], ()


async def collect_ports(
    client: QuelwareClient,
    resource_infos: Sequence[ResourceInfo],
) -> tuple[list[PortSnapshot], tuple[ResourceError, ...]]:
    ids = [info.id for info in resource_infos if info.category is ResourceCategory.PORT]
    results = await asyncio.gather(
        *(call(client.get_port_info, resource_id) for resource_id in ids),
        return_exceptions=True,
    )
    ports: list[PortSnapshot] = []
    errors: list[ResourceError] = []
    for requested_id, result in zip(ids, results, strict=True):
        requested_id_text = str(requested_id)
        if isinstance(result, BaseException):
            errors.append(
                ResourceError("get_port_info", requested_id_text, str(result))
            )
            ports.append(
                PortSnapshot(requested_id_text, unit_label(requested_id_text), None)
            )
        else:
            ports.append(port_snapshot(result))
    return ports, tuple(errors)


def filter_instruments_by_port(
    instruments: Sequence[InstrumentSnapshot],
    port_ids: Sequence[str],
) -> list[InstrumentSnapshot]:
    if not port_ids:
        return list(instruments)
    selected = set(port_ids)
    return [instrument for instrument in instruments if instrument.port_id in selected]


async def collect_instruments(
    client: QuelwareClient,
    resource_infos: Sequence[ResourceInfo],
) -> tuple[list[InstrumentSnapshot], tuple[ResourceError, ...]]:
    ids = [
        info.id
        for info in resource_infos
        if info.category is ResourceCategory.INSTRUMENT
    ]
    results = await asyncio.gather(
        *(call(client.get_instrument_info, resource_id) for resource_id in ids),
        return_exceptions=True,
    )
    instruments: list[InstrumentSnapshot] = []
    errors: list[ResourceError] = []
    for requested_id, result in zip(ids, results, strict=True):
        requested_id_text = str(requested_id)
        if isinstance(result, BaseException):
            errors.append(
                ResourceError("get_instrument_info", requested_id_text, str(result))
            )
        else:
            instruments.append(instrument_snapshot(result))
    return instruments, tuple(errors)


async def collect_port_diagnoses(
    client: QuelwareClient,
    ports: Sequence[PortSnapshot],
    requested_port_ids: Sequence[str],
    *,
    enabled: bool,
) -> tuple[list[PortDiagnosis], tuple[ResourceError, ...]]:
    if not enabled:
        return [], ()

    port_ids = tuple(ResourceId(port_id) for port_id in requested_port_ids) or tuple(
        ResourceId(port.id) for port in ports
    )
    results = await asyncio.gather(
        *(call(client.dump_port_state, port_id) for port_id in port_ids),
        return_exceptions=True,
    )
    diagnoses: list[PortDiagnosis] = []
    errors: list[ResourceError] = []
    for port_id, result in zip(port_ids, results, strict=True):
        port_id_text = str(port_id)
        if isinstance(result, BaseException):
            errors.append(ResourceError("dump_port_state", port_id_text, str(result)))
        else:
            diagnoses.append(
                PortDiagnosis(port_id_text, unit_label(port_id_text), str(result))
            )
    return diagnoses, tuple(errors)


async def call(method: Callable[..., Any], *args: Any) -> Any:
    result = method(*args)
    if inspect.isawaitable(result):
        return await result
    return result
