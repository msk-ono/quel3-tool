# quel3-tool

QuEL-3 の状態確認、instrument の deploy、簡単な fixed-timeline 実行を
`quelware-client` 経由で行う CLI ツールです。

## 基本

```sh
quel3-tool --endpoint HOST:PORT summary
```

`--endpoint` を省略した場合は `localhost:50051` に接続します。
接続待ちの上限は `--timeout` で変更できます。

```sh
quel3-tool --endpoint 192.0.2.10:50051 --timeout 600 summary
```

## 状態を見る

```sh
quel3-tool summary
quel3-tool units
quel3-tool ports --unit <unit-label>
quel3-tool instruments --unit <unit-label>
quel3-tool instruments --port <port-id> --full-ids
```

`--unit` と `--port` は必要な範囲だけを見るための絞り込みです。
複数指定したい場合は同じオプションを繰り返します。

```sh
quel3-tool ports --unit unit-a --unit unit-b
quel3-tool instruments --port unit-a:port-1 --port unit-a:port-2
```

## diagnosis と JSON

port diagnosis を表示するには `diagnosis` を使います。

```sh
quel3-tool diagnosis --unit <unit-label>
quel3-tool diagnosis --port <port-id>
```

JSON snapshot は `json` で出力します。`json` は常に diagnosis も取得します。
保存先を指定しない場合は標準出力に表示します。

```sh
quel3-tool json
quel3-tool json --unit <unit-label> --port <port-id> --output snapshot.json
```

## config から deploy/run する

`examples/config.toml` はサンプル設定です。port ID は placeholder なので、
実行前に自分の環境の resource ID に置き換えてください。

instrument の deploy だけを行う場合:

```sh
quel3-tool deploy examples/config.toml
```

deploy した instrument に waveform/event/capture を設定し、trigger と capture まで
行う場合:

```sh
quel3-tool run examples/config.toml
```

`run` は `[[run_config]]`, `[[waveform]]`, `[[event]]`, `[[capture]]` も読みます。
capture 結果は `run_config.output_dir` に `.npy` 形式で保存します。

## config の最小イメージ

```toml
[[instrument]]
alias = "drive-ge"
port_id = "demo-unit:control-output"
role = "TRANSMITTER"
freq_min_ghz = 4.8
freq_max_ghz = 5.2

[[run_config]]
iterations = 1024
iteration_interval_ns = 100_000
capture_mode = "RAW_WAVEFORM"
output_dir = "output"

[[waveform]]
name = "short-drive"
sampling_period_fs = 400_000
i = [0.0, 0.5, 1.0, 0.5, 0.0]
q = [0.0, 0.0, 0.0, 0.0, 0.0]

[[event]]
alias = "drive-ge"
waveform = "short-drive"
start_offset_samples = 0
gain = 0.8
phase_offset_deg = 0.0
```

より具体的な例は [examples/config.toml](examples/config.toml) を見てください。
