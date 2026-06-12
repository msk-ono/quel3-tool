"""Command line interface for quel3-tool."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rich.console import Console
from rich.text import Text

from quel3_tool import __version__
from quel3_tool._run.executor import deploy_from_file, run_from_file
from quel3_tool.collect import collect_state_snapshot
from quel3_tool.formatting import (
    has_diagnosis_errors,
    instruments_table,
    ports_table,
    print_diagnoses,
    print_summary,
    units_table,
)
from quel3_tool.model import Quel3RuntimeOptions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="quel3-tool",
        description="Inspect QuEL-3 state through quelware-client.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--endpoint",
        type=parse_endpoint,
        default=("localhost", 50051),
        metavar="HOST:PORT",
        help="quelware endpoint.",
    )
    parser.add_argument("--timeout", type=float, default=300.0, help="Wait timeout.")
    parser.set_defaults(include_diagnosis=False, port_ids=(), unit_labels=())

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("summary", help="Print unit/resource/check summary.")
    subparsers.add_parser("units", help="Print discovered units.")

    ports = subparsers.add_parser("ports", help="Print port resources.")
    ports.add_argument(
        "--unit",
        dest="unit_labels",
        action="append",
        default=[],
        help="Limit the snapshot to one unit label. Repeat for multiple units.",
    )

    instruments = subparsers.add_parser("instruments", help="Print instruments.")
    instruments.add_argument(
        "--unit",
        dest="unit_labels",
        action="append",
        default=[],
        help="Limit the snapshot to one unit label. Repeat for multiple units.",
    )
    instruments.add_argument(
        "--port",
        dest="port_ids",
        action="append",
        default=[],
        help="Limit instruments to one port resource ID. Repeat for multiple ports.",
    )
    instruments.add_argument(
        "--full-ids",
        action="store_true",
        help="Show full instrument and port resource IDs.",
    )

    diagnosis = subparsers.add_parser("diagnosis", help="Print port diagnosis dumps.")
    diagnosis.add_argument(
        "--unit",
        dest="unit_labels",
        action="append",
        default=[],
        help="Limit the snapshot to one unit label. Repeat for multiple units.",
    )
    diagnosis.add_argument(
        "--port",
        dest="port_ids",
        action="append",
        default=[],
        help="Limit diagnoses to one port resource ID. Repeat for multiple ports.",
    )

    json_command = subparsers.add_parser("json", help="Print or write JSON snapshot.")
    json_command.add_argument(
        "--unit",
        dest="unit_labels",
        action="append",
        default=[],
        help="Limit the snapshot to one unit label. Repeat for multiple units.",
    )
    json_command.add_argument(
        "--port",
        dest="port_ids",
        action="append",
        default=[],
        help="Limit diagnoses to one port resource ID. Repeat for multiple ports.",
    )
    json_command.add_argument("--output", type=Path, help="Optional JSON output path.")

    deploy = subparsers.add_parser("deploy", help="Deploy instruments from TOML.")
    deploy.add_argument(
        "config",
        nargs="?",
        type=Path,
        default=Path("examples/config.toml"),
        help="TOML config path.",
    )

    run = subparsers.add_parser("run", help="Deploy, run pulses, and capture.")
    run.add_argument(
        "config",
        nargs="?",
        type=Path,
        default=Path("examples/config.toml"),
        help="TOML config path.",
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    generated_at: str | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    console = Console(highlight=False)
    error_console = Console(stderr=True, highlight=False)
    command = args.command or "summary"

    if command in {"deploy", "run"}:
        try:
            return run_config_command(console, args)
        except Exception as exc:
            error_console.print(Text(f"quel3-tool failed: {exc}", style="bold red"))
            return 1

    try:
        snapshot = collect_state_snapshot(
            options_from_args(args),
            generated_at=generated_at,
        )
    except Exception as exc:
        error_console.print(Text(f"quel3-tool failed: {exc}", style="bold red"))
        return 1

    if command == "summary":
        print_summary(console, snapshot)
    elif command == "units":
        console.print(units_table(snapshot))
    elif command == "ports":
        console.print(ports_table(snapshot))
    elif command == "instruments":
        console.print(instruments_table(snapshot, full_ids=args.full_ids))
    elif command == "json":
        write_json(console, snapshot.to_dict(), args.output)
    elif command == "diagnosis":
        print_diagnoses(console, snapshot)
        return 1 if has_diagnosis_errors(snapshot) else 0
    else:
        parser.error(f"Unsupported command: {command}")
    return 0


def run_config_command(console: Console, args: argparse.Namespace) -> int:
    endpoint, port = args.endpoint
    if args.command == "deploy":
        result = deploy_from_file(
            args.config,
            endpoint=endpoint,
            port=port,
            timeout_seconds=args.timeout,
        )
        console.print(f"Deployed {len(result.instruments)} instruments.")
        return 0

    result = run_from_file(
        args.config,
        endpoint=endpoint,
        port=port,
        timeout_seconds=args.timeout,
    )
    console.print(
        f"Deployed {len(result.instruments)} instruments; "
        f"trigger_count={result.trigger_count}; "
        f"saved {len(result.output_files)} capture files."
    )
    return 0


def options_from_args(args: argparse.Namespace) -> Quel3RuntimeOptions:
    endpoint, port = args.endpoint
    return Quel3RuntimeOptions(
        endpoint=endpoint,
        port=port,
        unit_labels=tuple(args.unit_labels),
        instrument_port_ids=instrument_port_ids(args),
        diagnosis_port_ids=diagnosis_port_ids(args),
        include_diagnosis=include_diagnosis(args),
        timeout_seconds=args.timeout,
    )


def include_diagnosis(args: argparse.Namespace) -> bool:
    return args.command in {"diagnosis", "json"}


def instrument_port_ids(args: argparse.Namespace) -> tuple[str, ...]:
    if args.command != "instruments":
        return ()
    return tuple(args.port_ids)


def diagnosis_port_ids(args: argparse.Namespace) -> tuple[str, ...]:
    if args.command not in {"diagnosis", "json"}:
        return ()
    return tuple(args.port_ids)


def parse_endpoint(value: str) -> tuple[str, int]:
    host, separator, port_text = value.rpartition(":")
    if not separator or not host or not port_text:
        raise argparse.ArgumentTypeError("endpoint must be HOST:PORT")
    try:
        port = int(port_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("endpoint port must be an integer") from exc
    return host, port


def write_json(
    console: Console,
    payload: dict[str, object],
    output: Path | None,
) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if output is None:
        console.print_json(json=text)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text + "\n", encoding="utf-8")
    console.print(Text(f"Wrote {output}", style="bold green"))


if __name__ == "__main__":
    raise SystemExit(main())
