# respondent-runner

:gb: [English README](README.md)

contingency-respondent-dsl で書いたパヴロフ型（レスポンデント）の手続きを、試行単位の
Rescorla–Wagner モデルで走らせ、その結果を OKL v1 のログに書きます。

- **展開器** — Tier B の AST を試行の列（段階・CS の集合・US・文脈）にします。
- **実行器** — 刺激ごとの顕著性を持つ、複合 CS の Rescorla–Wagner です。
- **OKL 書き出し** — 試行ごとに phase marker を書き、その `cue` に CS の集合を入れます。

## インストール

このパッケージに remote が無いあいだは、兄弟パッケージをローカルのパスで参照します。
このディレクトリで:

```bash
mise exec -- python -m venv .venv
.venv/bin/python -m pip install -e ../../core/contingency-dsl-py -e ../../core/contingency-py \
  -e ../../experiment/experiment-core -e ../../experiment/session-recorder \
  -e ../../core/contingency-respondent-dsl
.venv/bin/python -m pip install -e ".[dev]"
```

`contingency-py` と `contingency-dsl-py` は、`session-recorder` が要る `experiment-core` が
依存しているために入れるだけで、このパッケージは import しません。

## 使い方

```python
from contingency_respondent_dsl import from_dict
from respondent_runner import RescorlaWagner, expand, expand_control, run, write_okl

node = from_dict(expected_ast)          # Tier B の AST（例: conformance の例）
model = RescorlaWagner({"a": 0.3, "x": 0.3}, lambda_by_us={"shock": 1.0})

trace = run(expand(node), model)
v_test = trace.v_at_stage_start("test")  # test 段階の最初の試行に入る時点の連合強度

control = expand_control(node)           # 対照条件。無ければ None
write_okl(trace, "blocking.txt", {"session_name": "blocking"})
```

## 展開の規則

入力は `contingency_respondent_dsl.from_dict` が返すオブジェクトです。Tier B の節点は
dataclass で、ネストした Tier A の式は dict のままです。Core のパーサは使わないので、
手続きの文字列は先に AST にしておく必要があります。

| ネストした Tier A の形 | 試行の雛形 |
|---|---|
| `Pair.<mode>(cs, us)` | CS = `cs`（ラベルか `Compound(elements)`）、US = `us`。`us="nothing"` は US なし |
| `Extinction(cs)` / `Compound(elements)` / `CSOnly(cs)` | US を伴わない CS |
| `USOnly(us)` | CS を伴わない US |
| `Serial(elements=[...])` | 混在提示: 要素の雛形を 1 試行ずつ順に巡回する |
| `Serial(cs_list=[...])` | 未対応（系列複合刺激は CS 内の時間が要る） |

各段階は、その段階の `*_trials` の回数だけ雛形を繰り返します。AST に回数が無ければ
`default_trials`（20）回です。時間の引数（`isi`・`cs_duration` など）は各試行に
「捨てた変数」として記録し、モデルは使いません。

展開する手続き:

| 手続き | 段階 | 対照（`expand_control`） |
|---|---|---|
| `Blocking` | phase1 → phase2 → test | phase1 を省く |
| `Overshadowing` | training → test_a → test_b | `test_b` の要素だけで訓練する |
| `ConditionedInhibition` | training → test | なし |
| `InhibitionOfDelay`・`PeakProcedure` | 未対応: CS 内の反応の分布が要る | — |

`ConditionedInhibition.training` が強化つきの対提示 1 つだけのときは、展開器が
A+ / AI− の混在提示を組み立てます（I は test の式から取ります）。ほかの手続きは
「expansion not implemented」の理由つきで `unsupported` を返します。

## モデル

試行で提示される刺激の集合 *S* に含まれる各刺激 *i* について:

ΔV<sub>i</sub> = α<sub>i</sub> β (λ − Σ<sub>j∈S</sub> V<sub>j</sub>)

- *S* は CS の集合です。展開が文脈を要素として扱う場合は、文脈も加えます。
- US の無い試行は λ = 0 とし、`beta_nonreinforced`（既定は `beta` と同じ）を使います。
- 連合強度は US のラベルごとに別に持ちます。US *u* の試行では *u* の系を
  `lambda_by_us[u]` へ、ほかの系を 0 へ近づけます。`lambda_by_us` に無い US ラベルは
  漸近値を持たず、US の無い試行として数えます。
- *S* に無い刺激は更新しません。

`Trace.v_at_stage_start(stage)` は、その段階の最初の試行に入る時点の連合強度を返します。
`Trace.to_json()` は全試行を書き出します。

## session-analyzer との関係

session-analyzer の `simulate_rescorla_wagner` / `fit_rescorla_wagner` は、記録した
セッションを解析するための単一 CS のモデルです。このパッケージはそれを置き換えず、並べて
置きます。実行器は session-analyzer を import せず、テストで単一 CS の実行が
`simulate_rescorla_wagner` と 1e-12 の範囲で一致することを確かめます。

## OKL の書き方

| 対象 | OKL の記録 |
|---|---|
| 段階 | `phase_enter(label=<段階>, name=<文脈>)` … `phase_exit` |
| 試行 | `phase_enter(label="trial-<k>", name=<文脈>, cue="a+x")` … `phase_exit` |
| 漸近値を持つ US | 試行の終わりに `reinforcer_start(potency=λ)` / `reinforcer_end` |

時計は仮想のものです。試行 1 つの幅は `trial_s` 秒（既定 10 秒）で、AST に ITI があれば
それを足します。OKL の標準の事象には刺激提示を書く欄が無いので、CS の集合は文脈座標の
`cue` で書きます。

## テスト

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check src tests
.venv/bin/mypy src
```

## 参考文献

Rescorla, R. A., & Wagner, A. R. (1972). A theory of Pavlovian conditioning:
Variations in the effectiveness of reinforcement and nonreinforcement. In A. H. Black
& W. F. Prokasy (Eds.), *Classical conditioning II: Current research and theory*
(pp. 64–99). Appleton-Century-Crofts.

## ライセンス

MIT
