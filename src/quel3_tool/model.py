"""Small serializable models for QuEL-3 state."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

Severity = Literal["ok", "warning", "error"]
TargetType = Literal["snapshot", "unit", "port", "instrument"]
DEFAULT_TIMEOUT_SECONDS = 300.0


@dataclass(frozen=True, slots=True)
class Quel3RuntimeOptions:
    endpoint: str = "localhost"
    port: int = 50051
    unit_labels: tuple[str, ...] = ()
    instrument_port_ids: tuple[str, ...] = ()
    diagnosis_port_ids: tuple[str, ...] = ()
    include_diagnosis: bool = False
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS


@dataclass(frozen=True, slots=True)
class UnitSnapshot:
    label: str
    status: str | None = None


@dataclass(frozen=True, slots=True)
class PortSnapshot:
    id: str
    unit_label: str
    role: str | None
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class InstrumentSnapshot:
    id: str
    unit_label: str
    port_id: str
    alias: str | None
    normalized_alias: str | None
    role: str | None
    mode: str | None
    frequency_range_min_hz: float | None
    frequency_range_max_hz: float | None
    sampling_period_fs: int | None
    bitdepth: int | None
    timeline_step_samples: int | None
    samples_per_tick: int | None


@dataclass(frozen=True, slots=True)
class ResourceError:
    operation: str
    resource_id: str
    message: str


@dataclass(frozen=True, slots=True)
class PortDiagnosis:
    port_id: str
    unit_label: str
    text: str


@dataclass(frozen=True, slots=True)
class StateCheck:
    severity: Severity
    code: str
    message: str
    detail: str | None = None
    target_type: TargetType | None = None
    target_id: str | None = None


@dataclass(frozen=True, slots=True)
class StateSnapshot:
    generated_at: str
    endpoint: str
    port: int
    selected_unit_labels: tuple[str, ...]
    units: tuple[UnitSnapshot, ...]
    ports: tuple[PortSnapshot, ...]
    instruments: tuple[InstrumentSnapshot, ...]
    resource_counts_by_unit: dict[str, dict[str, int]]
    port_diagnoses: tuple[PortDiagnosis, ...] = ()
    errors: tuple[ResourceError, ...] = ()
    checks: tuple[StateCheck, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
