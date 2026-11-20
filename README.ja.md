# contingency-respondent-py

:gb: [English README](README.md)

contingency-respondent-dsl の Tier B のパヴロフ型 (レスポンデント) の手続きを、
contingency-py の試行の列に展開し、その試行を OKL v1 のログに書きます。

- **展開器** — Tier B の AST を試行の列 (段階・CS の集合・US・文脈) にします。
  ネストした Tier A の式は contingency-py (`contingency.respondent`、計算は contingency-rs)
  が展開します。このパッケージは Tier A を自分では展開しません。
- **contingency-py の展開** — `TIER_B` が Tier B の手続きを contingency-py の
  `RespondentRegistry` に登録します。
- **OKL 書き出し** — 試行ごとに phase marker を書き、CS と US を `stimulus_on` / `stimulus_off`
  の事象で書きます。

## インストール

このパッケージに remote が無いあいだは、兄弟パッケージをローカルのパスで参照します。
このディレクトリで:

```bash
mise exec -- python -m venv .venv
.venv/bin/python -m pip install -e ../../core/contingency-dsl-py \
  -e ../../core/contingency-py -e ../../core/contingency-respondent-dsl \
  -e ../../experiment/session-recorder
.venv/bin/python -m pip install -e ".[dev]"
```

実行時の依存は contingency-py (Tier A を展開する拡張モジュール `contingency_core` を含む)・
contingency-respondent-dsl・session-recorder です。`experiment-core` は要りません。

## 使い方

```python
from contingency_respondent_dsl import from_dict
from contingency_respondent import expand, expand_control, write_okl

node = from_dict(expected_ast)          # Tier B の AST (例: conformance の例)
expansion = expand(node)                # 全段階の試行を順に
control = expand_control(node)          # 対照条件。無ければ None

write_okl(expansion, "blocking.txt", {"session_name": "blocking"})
```

試行の上でモデルを走らせるときは [モデルを走らせる](#モデルを走らせる) を見てください。

## 展開の規則

入力は `contingency_respondent_dsl.from_dict` が返すオブジェクトです。Tier B の節点は
dataclass で、ネストした Tier A の式は contingency-py が読む形の dict のままです
(例: `Compound` は `cs_list` を取る)。Core のパーサは使わないので、手続きの文字列は
先に AST にしておく必要があります。

ネストした Tier A の式は contingency-py が 1 試行に展開し、その試行が段階で繰り返す雛形に
なります。CS の集合・US・順序・時刻は、段階のどの試行にもそのまま残ります。

| ネストした形 | 試行の雛形 |
|---|---|
| `Pair<Mode>(cs, us, …)` (例: `PairForwardDelay`。`Pair.ForwardDelay` も読む) | contingency-py の試行。`us="nothing"` は US なし |
| `Extinction(cs)` / `Compound(cs_list)` / `CSOnly(cs)` / `USOnly(us)` | contingency-py の試行 |
| `Serial(elements=[...])` (Tier A の形ではない。このパッケージが読む) | 混在提示: 要素の雛形を 1 試行ずつ順に巡回する |
| `Serial(cs_list=[...])`・`Contingency`・`TrulyRandom`・`ExplicitlyUnpaired`・`ITI`・`Differential` | 未対応 (1 つの雛形の繰り返しにならない) |

各段階は、その段階の `*_trials` の回数だけ雛形を繰り返します。AST に回数が無ければ
`default_trials` (20) 回です。時間の引数 (`isi`・`cs_duration` など) は各試行に
「捨てた変数」としても記録し、試行単位のモデルは使いません。

## contingency-py への登録

contingency-py は Tier A を自分で展開し、Tier B はプログラムごとに登録した展開に任せます。
`TIER_B` はこのパッケージの手続きの展開で、`registry()` はそれを持つ `RespondentRegistry`
を作ります (ほかの展開は引数で渡す)。

```python
from contingency_respondent import registry

trials = registry().expand(expected_ast, {"trials": 20})
# [{"stage": "phase1", "cs": ["a"], "us": "shock", "context": None,
#   "order": None, "time": {...}, "iti_s": None}, ...]
```

ネストした式は同じ登録表を通って展開されます。設定:

| 設定 | 意味 |
|---|---|
| `trials` (必須) | AST が回数を決めていない段階の試行数。既定値では埋めない (`RespondentUnresolvedError`) |
| `control` (既定 `false`) | 手続きの代わりに対照条件を展開する |
| `seed`・`labels` | ネストした Tier A の展開にそのまま渡す |

試行の列にならない手続き (下を参照) は理由つきの `RespondentSpecError` になります。
試行の列は `to_trial_dicts(expand(node, default_trials=trials))` と同じです。

Tier B の 26 手続きのうち、`InhibitionOfDelay` と `PeakProcedure` を除く 24 手続きを展開します。
この 2 つは CS 内の反応の分布が要るので `unsupported` を返します。
AST が略式のときは、展開器が最小限を補います:

- `ConditionedInhibition.training` (と `SuperConditioning` に入れ子になったもの) が強化つきの対提示 1 つだけなら、
  A+ / AI− の混在提示を組み立てます (I は test の式から取ります)。`SummationRetardationTest` にも同じ E+ / EI− の訓練を付けます。
- 文脈を名指す手続きでは、文脈を足し合わせる集合に入れます (`Expansion.context_as_element`):
  `USPreexposure`・`Renewal`・`Reinstatement`・`LatentExtinction`・`ContextualExtinction`・`ContextualFearConditioning`。
  AST に文脈名が無いときは `ctx` (対照には `ctx_other` / `acq`) を使います。
- `PavlovianPREE` は、round(p·n) 回の強化試行を乱数を使わず等間隔に置きます。
- US の欄に CS のラベルが入る手続き (`HigherOrderConditioning`・`SensoryPreconditioning`・`MediatedConditioning`) では、
  そのラベルを試行の US のラベルとして残します。そのラベルに漸近値を与えないモデルでは、US なしの試行になります。

## モデルを走らせる

このパッケージは手続きを展開するだけで、学習のモデルを持ちません。試行の上で複合 CS の
Rescorla–Wagner モデルを走らせるのは session-analyzer の `simulate_compound_rescorla_wagner` です
(展開が文脈を要素にするときは、文脈も和に入れます):

```python
from session_analyzer.analytics import (
    CompoundRescorlaWagner, CompoundTrial, simulate_compound_rescorla_wagner,
)

cae = expansion.context_as_element
trials = [CompoundTrial(t.elements(cae), t.us, t.stage) for t in expansion.trials]
trace = simulate_compound_rescorla_wagner(
    trials, CompoundRescorlaWagner({}, lambda_by_us={"shock": 1.0})
)
v_test = trace.v_at_stage_start("test")  # test 段階の最初の試行に入る時点の連合強度
```

この形で Tier B の conformance の例 26 個を全部走らせる法則スイートと、どの現象を
Rescorla–Wagner モデルが予測するかの表は、contingency-bench にあります
(`tests/test_respondent_laws.py`、extra は `respondent`)。

## OKL の書き方

| 対象 | OKL の記録 |
|---|---|
| 段階 | `phase_enter(label=<段階>, name=<文脈>)` … `phase_exit` |
| 試行 | `phase_enter(label="trial-<k>", name=<文脈>)` … `phase_exit` |
| 試行の各 CS | 試行の始めに `stimulus_on(stimulus=<cs>)`、終わりに `stimulus_off` |
| 試行の US | 試行の終わりの `us_s` 秒 (既定 1 秒) 前に `stimulus_on(stimulus=<us>)`、終わりに `stimulus_off` |

時計は仮想のものです。試行 1 つの幅は `trial_s` 秒 (既定 10 秒) で、AST に ITI があれば
それを足します。CS と US は同じ刺激の事象で書きます。ログに書くのは提示した物です。
US の欄に置いた CS のラベルも、刺激として書きます。

## 実時間の時計での刺激の列

`contingency_respondent.timeline.stimulus_timeline` は、レスポンデントの式の時間の値から、
刺激の on と off の列を返します (上の OKL の書き手は試行の幅を固定で使いますが、
こちらは式の値を使います)。扱うのは `Pair.ForwardDelay` と `USOnly` で、
`@iti(distribution=fixed, mean=...)` を付けられます。セッションは ITI から始まり、
ITI は試行の最後の off から数えます。US の持続は呼び出し側が渡す `presentation_s`
の値です (DSL にもモデルにもこの値はありません)。

これは contingency-dsl の「同じ実験」の fixture (`conformance/equivalence/`) の
レスポンデントの側です。`tests/test_equivalence.py` が各 fixture の `respondent` の式を
入力の反応の列ごとに回し、fixture の期待の刺激の列と比べます。
`CONTINGENCY_DSL_CONFORMANCE` に contingency-dsl の `conformance` ディレクトリを
指定します。指定しなければ隣の checkout を使い、どちらも無ければテストを飛ばします。

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
