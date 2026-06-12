"""Rich terminal rendering for quel3-tool."""

from __future__ import annotations

import re
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from quel3_tool.model import InstrumentSnapshot, PortSnapshot, StateSnapshot

_NATURAL = re.compile(r"(\d+)")
_PORT_NUMBERS = re.compile(r"_p((?:\d+p?)+)")
_RIGHT = {"Ports", "Instruments", "Total", "Min GHz", "Max GHz", "Width MHz"}
_NOWRAP = _RIGHT | {"Severity", "Status", "Unit", "Port", "Role", "Mode"}
_SEVERITY_STYLE = {"ok": "bold green", "warning": "bold yellow", "error": "bold red"}
_GHZ_DECIMALS = 4
_GHZ_WIDTH = 7


def print_summary(console: Console, snapshot: StateSnapshot) -> None:
    console.print(summary_panel(snapshot))
    console.print(resource_counts_table(snapshot))
    console.print(checks_table(snapshot))


def summary_panel(snapshot: StateSnapshot) -> Panel:
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold cyan", no_wrap=True)
    grid.add_column()
    grid.add_row("Endpoint", f"{snapshot.endpoint}:{snapshot.port}")
    grid.add_row("Generated", snapshot.generated_at)
    grid.add_row(
        "Resources",
        (
            f"Units {len(snapshot.units)} | Ports {len(snapshot.ports)} | "
            f"Instruments {len(snapshot.instruments)} | Errors {len(snapshot.errors)}"
        ),
    )
    return Panel(grid, title="QuEL-3 Snapshot", border_style=snapshot_style(snapshot))


def resource_counts_table(snapshot: StateSnapshot) -> Table:
    rows = [
        [unit, counts.get("PORT", 0), counts.get("INSTRUMENT", 0), sum(counts.values())]
        for unit, counts in snapshot.resource_counts_by_unit.items()
    ]
    return table("Resource Counts", ["Unit", "Ports", "Instruments", "Total"], rows)


def units_table(snapshot: StateSnapshot) -> Table:
    return table(
        "Units",
        ["Unit", "Status"],
        [[unit.label, unit.status or "unknown"] for unit in snapshot.units],
    )


def ports_table(snapshot: StateSnapshot) -> Table:
    rows = [
        [
            resource_label(port.id, port.unit_label),
            port.unit_label,
            port.role or "",
            ", ".join(resource_label(dep, port.unit_label) for dep in port.depends_on),
        ]
        for port in sorted_ports(snapshot.ports)
    ]
    return table("Ports", ["Port", "Unit", "Role", "Depends on"], rows)


def instruments_table(snapshot: StateSnapshot, *, full_ids: bool = False) -> Table:
    instruments = sorted_instruments(snapshot.instruments)
    if full_ids:
        headers = [
            "Instrument ID",
            "Unit",
            "Port ID",
            "Alias",
            "Role",
            "Mode",
            "Min GHz",
            "Max GHz",
            "Width MHz",
            "Sampling fs",
        ]
        return table(
            "Instruments",
            headers,
            [instrument_full_row(instrument) for instrument in instruments],
        )

    show_unit = len({instrument.unit_label for instrument in instruments}) > 1
    headers = [
        "Port",
        "Alias",
        "Role",
        "Mode",
        "Min GHz",
        "Max GHz",
        "Width MHz",
        "Sampling fs",
    ]
    if show_unit:
        headers.insert(0, "Unit")
    rows = [instrument_compact_row(i, show_unit=show_unit) for i in instruments]
    return table("Instruments", headers, rows)


def checks_table(snapshot: StateSnapshot) -> Table:
    rows = [
        [check.severity, check.code, check.message, check.detail or ""]
        for check in snapshot.checks
    ]
    return table("Checks", ["Severity", "Code", "Message", "Detail"], rows)


def print_diagnoses(console: Console, snapshot: StateSnapshot) -> None:
    wrote = False
    for diagnosis in snapshot.port_diagnoses:
        console.print(
            Panel(
                Syntax(
                    diagnosis.text.rstrip() or "(empty diagnosis dump)",
                    "yaml",
                    word_wrap=True,
                    background_color="default",
                ),
                title=f"Port {diagnosis.port_id}",
                border_style="cyan",
                box=box.ROUNDED,
            )
        )
        wrote = True

    errors = [
        error for error in snapshot.errors if error.operation == "dump_port_state"
    ]
    if errors:
        console.print(
            table(
                "Diagnosis Errors",
                ["Port", "Error"],
                [[error.resource_id, error.message] for error in errors],
            )
        )
        wrote = True
    if not wrote:
        console.print(Text("(no diagnosis dumps)", style="dim"))


def table(title: str, headers: list[str], rows: list[list[Any]]) -> Table:
    result = Table(
        title=title,
        box=box.ROUNDED,
        header_style="bold cyan",
        border_style="bright_black",
        row_styles=("", "dim"),
    )
    for header in headers:
        result.add_column(
            header,
            justify="right" if header in _RIGHT else "left",
            no_wrap=header in _NOWRAP,
            overflow="fold",
        )
    if not rows:
        result.add_row(
            Text(f"No {title.lower()}", style="dim"),
            *[""] * (len(headers) - 1),
        )
        return result
    for row in rows:
        result.add_row(
            *(cell(value, header) for header, value in zip(headers, row, strict=True))
        )
    return result


def cell(value: Any, header: str) -> Text:
    text = str(value)
    if header == "Severity":
        return severity_text(text)
    if header == "Status":
        return status_text(text)
    if not text:
        return Text("-", style="dim")
    if header in _RIGHT:
        return Text(text, style="cyan")
    return Text(text)


def severity_text(severity: str) -> Text:
    return Text(severity.upper(), style=_SEVERITY_STYLE.get(severity.lower(), "bold"))


def status_text(status: str) -> Text:
    upper = status.upper()
    if upper == "ACTIVE":
        return Text(status, style="bold green")
    if upper == "UNKNOWN":
        return Text(status, style="dim")
    return Text(status, style="bold yellow")


def snapshot_style(snapshot: StateSnapshot) -> str:
    severities = {check.severity for check in snapshot.checks}
    if "error" in severities:
        return "red"
    if "warning" in severities:
        return "yellow"
    return "green"


def instrument_compact_row(
    instrument: InstrumentSnapshot,
    *,
    show_unit: bool,
) -> list[Any]:
    row: list[Any] = [
        resource_label(instrument.port_id, instrument.unit_label),
        instrument_alias(instrument),
        instrument.role or "",
        instrument.mode or "",
        *frequency_bounds(instrument),
        frequency_width_mhz(instrument),
        instrument.sampling_period_fs or "",
    ]
    if show_unit:
        row.insert(0, instrument.unit_label)
    return row


def instrument_full_row(instrument: InstrumentSnapshot) -> list[Any]:
    return [
        instrument.id,
        instrument.unit_label,
        instrument.port_id,
        instrument_alias(instrument),
        instrument.role or "",
        instrument.mode or "",
        *frequency_bounds(instrument),
        frequency_width_mhz(instrument),
        instrument.sampling_period_fs or "",
    ]


def frequency_bounds(instrument: InstrumentSnapshot) -> tuple[str, str]:
    lower = instrument.frequency_range_min_hz
    upper = instrument.frequency_range_max_hz
    if lower is None or upper is None:
        return "", ""
    return frequency_ghz(lower), frequency_ghz(upper)


def frequency_ghz(value: float) -> str:
    return f"{value / 1.0e9:{_GHZ_WIDTH}.{_GHZ_DECIMALS}f}"


def frequency_width_mhz(instrument: InstrumentSnapshot) -> str:
    lower = instrument.frequency_range_min_hz
    upper = instrument.frequency_range_max_hz
    if lower is None or upper is None:
        return ""
    return f"{abs(upper - lower) / 1.0e6:.0f}"


def sorted_ports(ports: tuple[PortSnapshot, ...]) -> tuple[PortSnapshot, ...]:
    return tuple(
        sorted(
            ports,
            key=lambda port: (natural_key(port.unit_label), port_key(port.id)),
        )
    )


def sorted_instruments(
    instruments: tuple[InstrumentSnapshot, ...],
) -> tuple[InstrumentSnapshot, ...]:
    return tuple(
        sorted(
            instruments,
            key=lambda item: (
                natural_key(item.unit_label),
                port_key(item.port_id),
                instrument_alias(item) == "",
                natural_key(instrument_alias(item)),
                natural_key(item.id),
            ),
        )
    )


def port_key(port_id: str) -> tuple[tuple[int, ...], tuple[tuple[int, int | str], ...]]:
    suffix = resource_suffix(port_id)
    match = _PORT_NUMBERS.search(suffix)
    numbers = (
        tuple(int(value) for value in re.findall(r"\d+", match.group(1)))
        if match
        else ()
    )
    return numbers, natural_key(suffix)


def natural_key(value: str) -> tuple[tuple[int, int | str], ...]:
    parts = []
    for part in _NATURAL.split(value.casefold()):
        if part:
            parts.append((1, int(part)) if part.isdecimal() else (0, part))
    return tuple(parts)


def instrument_alias(instrument: InstrumentSnapshot) -> str:
    return instrument.normalized_alias or instrument.alias or ""


def resource_suffix(resource_id: str) -> str:
    return resource_id.split(":", maxsplit=1)[-1]


def resource_label(resource_id: str, unit: str) -> str:
    if resource_id.startswith(f"{unit}:"):
        return resource_suffix(resource_id)
    return resource_id


def has_diagnosis_errors(snapshot: StateSnapshot) -> bool:
    return any(error.operation == "dump_port_state" for error in snapshot.errors)
