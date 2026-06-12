# quel3-tool

QuEL-3 の状態を `quelware-client` 経由で扱うための CLI ツールです。

## 使い方

```sh
quel3-tool --endpoint HOST:PORT summary
```

`--endpoint` を省略すると `localhost:50051` に接続します。

主なコマンド:

```sh
quel3-tool units
quel3-tool ports --unit <unit>
quel3-tool instruments --unit <unit>
quel3-tool diagnosis --unit <unit>
quel3-tool json --output snapshot.json
```
