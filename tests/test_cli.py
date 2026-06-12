import pytest

from quel3_tool.cli import build_parser, include_diagnosis, options_from_args


def test_parser_defaults_to_summary_options() -> None:
    args = build_parser().parse_args([])

    assert args.command is None
    assert args.endpoint == ("localhost", 50051)
    assert args.unit_labels == ()
    assert args.timeout == 300.0
    assert not include_diagnosis(args)


def test_endpoint_argument_sets_runtime_host_and_port() -> None:
    args = build_parser().parse_args(["--endpoint", "example.com:12345"])

    options = options_from_args(args)

    assert options.endpoint == "example.com"
    assert options.port == 12345


def test_global_unit_argument_is_not_supported() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--unit", "unit-1", "summary"])


def test_ports_command_accepts_unit_argument() -> None:
    args = build_parser().parse_args(["ports", "--unit", "unit-1", "--unit", "unit-2"])

    assert args.command == "ports"
    assert args.unit_labels == ["unit-1", "unit-2"]


def test_instruments_command_accepts_unit_argument() -> None:
    args = build_parser().parse_args(
        ["instruments", "--unit", "unit-1", "--port", "port-1"],
    )
    options = options_from_args(args)

    assert args.command == "instruments"
    assert args.unit_labels == ["unit-1"]
    assert options.instrument_port_ids == ("port-1",)


def test_diagnosis_command_includes_diagnosis() -> None:
    args = build_parser().parse_args(
        ["diagnosis", "--unit", "unit-1", "--port", "port-1"],
    )
    options = options_from_args(args)

    assert args.command == "diagnosis"
    assert args.port_ids == ["port-1"]
    assert args.unit_labels == ["unit-1"]
    assert include_diagnosis(args)
    assert options.diagnosis_port_ids == ("port-1",)


def test_json_command_always_includes_diagnosis() -> None:
    args = build_parser().parse_args(
        ["json", "--unit", "unit-1", "--port", "port-1"],
    )
    options = options_from_args(args)

    assert args.command == "json"
    assert args.unit_labels == ["unit-1"]
    assert include_diagnosis(args)
    assert options.unit_labels == ("unit-1",)
    assert options.diagnosis_port_ids == ("port-1",)


def test_json_command_does_not_accept_include_diagnosis() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["json", "--include-diagnosis"])


def test_deploy_command_accepts_config_path() -> None:
    args = build_parser().parse_args(["deploy", "examples/config.toml"])

    assert args.command == "deploy"
    assert str(args.config) == "examples/config.toml"


def test_run_command_defaults_to_example_config() -> None:
    args = build_parser().parse_args(["run"])

    assert args.command == "run"
    assert str(args.config) == "examples/config.toml"
