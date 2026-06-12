from pathlib import Path

from quel3_tool._run.config import load_config
from quel3_tool._run.executor import capture_mode, instrument_definition, make_waveforms


def test_load_example_config() -> None:
    config = load_config(Path("examples/config.toml"))

    assert len(config.instruments) == 3
    assert {instrument.alias for instrument in config.instruments} == {
        "drive-ge",
        "drive-ef",
        "readout",
    }
    assert {instrument.port_id for instrument in config.instruments} == {
        "demo-unit:control-output",
        "demo-unit:readout-io",
    }
    assert {instrument.role for instrument in config.instruments} == {
        "TRANSMITTER",
        "TRANSCEIVER",
    }
    assert config.run_config is not None
    assert config.run_config.iterations == 1024
    assert len(config.waveforms) == 2
    sampling_periods = {
        waveform.name: waveform.sampling_period_fs for waveform in config.waveforms
    }
    assert sampling_periods == {
        "short-drive": 400_000,
        "readout-tone": 800_000,
    }
    assert len(config.events) == 3
    assert len(config.captures) == 1


def test_waveform_sampling_period_is_kept_in_iq_waveform() -> None:
    config = load_config(Path("examples/config.toml"))

    waveforms = make_waveforms(config.waveforms)

    assert waveforms["short-drive"].sampling_period_fs == 400_000
    assert waveforms["readout-tone"].sampling_period_fs == 800_000


def test_instrument_definition_uses_frequency_range_hz() -> None:
    config = load_config(Path("examples/config.toml"))
    ge_config = next(
        instrument
        for instrument in config.instruments
        if instrument.alias == "drive-ge"
    )

    definition = instrument_definition(ge_config)

    assert definition.alias == "drive-ge"
    assert definition.role.name == "TRANSMITTER"
    assert definition.profile.frequency_range_min == 4.8e9
    assert definition.profile.frequency_range_max == 5.2e9


def test_capture_mode_accepts_singular_raw_waveform() -> None:
    config = load_config(Path("examples/config.toml"))

    assert config.run_config is not None
    assert capture_mode(config.run_config).name == "RAW_WAVEFORMS"
