# contingency-respondent-py

:gb: [English README](README.md)

contingency-respondent-dsl の Tier B のパヴロフ型 (レスポンデント) の手続きを、
contingency-py の試行の列に展開し、試行単位の Rescorla–Wagner モデルで走らせ、
その結果を OKL v1 のログに書きます。

- **展開器** — Tier B の AST を試行の列 (段階・CS の集合・US・文脈) にします。
  ネストした Tier A の式は contingency-py (`contingency.respondent`、計算は contingency-rs)
  が展開します。このパッケージは Tier A を自分では展開しません。
- **contingency-py の展開** — `TIER_B` が Tier B の手続きを contingency-py の
  `RespondentRegistry` に登録します。
- **実行器** — 刺激ごとの顕著性を持つ、複合 CS の Rescorla–Wagner です。
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
from contingency_respondent import RescorlaWagner, expand, expand_control, run, write_okl

node = from_dict(expected_ast)          # Tier B の AST（例: conformance の例）
model = RescorlaWagner({"a": 0.3, "x": 0.3}, lambda_by_us={"shock": 1.0})

trace = run(expand(node), model)
v_test = trace.v_at_stage_start("test")  # test 段階の最初の試行に入る時点の連合強度

control = expand_control(node)           # 対照条件。無ければ None
write_okl(trace, "blocking.txt", {"session_name": "blocking"})
```

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
「捨てた変数」としても記録し、モデルは使いません。

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
  そのラベルに漸近値が無いので、US なしの試行として数えます。

## 法則スイート

`tests/laws/test_respondent_phenomena.py` は、Tier B の conformance の例 (`expected_ast`) を全部、展開器と実行器に通し
(全刺激 α = 0.3、β = 1、各 US の λ = 1、AST に回数が無い段階は 20 試行)、現象を V の不等式だけで判定します。
例の置き場は `$RESPONDENT_CONFORMANCE_ROOT`、無ければ `contingency-respondent-dsl/conformance/tier-b` を持つ祖先のディレクトリで、
見つからなければスイートを飛ばします。

- **通過** — R–W で現象の向きが出る。
- **通過・機構は違う** — 素直な拡張 (文脈を要素にする・US ごとに系を分ける) で向きは出るが、その手続きで知られる機構は出ない。
- **期待どおりの不一致** — R–W では現象が出ない。テストは現象を書き、`xfail(strict=True)` にしてある。
- **未対応** — CS 内の時間が要る。`expand` が断る。

| # | 手続き | R–W | V での判定 | 結果 (スイートの値) |
|---|---|---|---|---|
| 1 | HigherOrderConditioning | しない | X→A の後に V_light > 0 | 期待どおりの不一致 (V_light = 0) |
| 2 | SensoryPreconditioning | しない | test で V_light > 0 | 期待どおりの不一致 (V_light = 0) |
| 3 | Counterconditioning | 部分 | V^shock_tone が下がり、V^food_tone > 0 | 通過・機構は違う (0.999 → 0.001、V^food 0.999)。US の系どうしの相互制止は無い |
| 4 | Blocking | する | V_x < 対照 | 通過 (0.000 対 0.500) |
| 5 | Overshadowing | する | V_dim < 単独訓練、V_loud > V_dim (α 0.5 / 0.2) | 通過 (0.286 対 1.000、V_loud 0.714) |
| 6 | Overexpectation | する | AX+ で V_a が下がり、対照は不変 | 通過 (0.999 → 0.500、対照 0.999) |
| 7 | SuperConditioning | する | V_x > 相手が中性刺激の対照 | 通過 (0.969 対 0.500、V_i −0.938) |
| 8 | RetrospectiveRevaluation | しない | 後向きブロッキング (V_x < 対照) と回復 (V_x > 対照) | 期待どおりの不一致 (2 例とも V_x = 対照 = 0.500) |
| 9 | ConditionedInhibition | する | V_i < 0 かつ V_a + V_i → 0 | 通過 (V_a 0.997、V_i −0.996)。記録された A+/AX− のデータ (下) にも弁別が出ている |
| 10 | OccasionSetting | 部分 | FP: V_feature > 0、V_target ≈ 0 | 通過・機構は違う (0.998 / 0.001)。場面設定そのものは要素の和では出ない |
| 11 | InhibitionOfDelay | しない | — | 未対応 |
| 12 | SummationRetardationTest | する | ΣV(E+I) < V_E、5 試行後の V_I < 新奇 CS | 通過 (0.001 対 0.997、0.664 対 0.832) |
| 13 | LatentInhibition | しない | 訓練後の V_tone < 対照 | 期待どおりの不一致 (1.000 = 1.000) |
| 14 | USPreexposure | 部分 | V_tone < 対照 | 通過・機構は違う (0.000 対 0.500)。文脈によるブロッキングだけ |
| 15 | Renewal | 部分 | ΣV (A での test) > ΣV (B での消去の終わり) | 通過・機構は違う (0.750 対 0.000)。文脈 B が制止子になって終わる |
| 16 | Reinstatement | 部分 | ΣV(test) > ΣV (消去の終わり)、別文脈では不変 | 通過・機構は違う (0.760 対 0.000)。文脈の興奮だけ |
| 17 | SpontaneousRecovery | しない | V_tone(test) > 消去の終わり | 期待どおりの不一致 (時間の変数が無い) |
| 18 | LatentExtinction | 部分 | ΣV(test) < 対照 | 通過・機構は違う (0.500 対 1.000)。減るのは文脈の分だけ |
| 19 | PavlovianPREE | しない | 消去後に V(部分) > V(連続) | 期待どおりの不一致 (R–W は逆を出す) |
| 20 | ContextualExtinction | 部分 | ΣV (獲得文脈での test) > 消去の終わり | 通過・機構は違う (0.750 対 0.000) |
| 21 | ReconsolidationInterference | しない | 普通の消去の後は回復し、想起→消去の後は回復しない | 期待どおりの不一致 (どちらも回復しない) |
| 22 | ConditionedTasteAversion | 部分 | 1 試行後に V_taste > 0 | 通過・機構は違う (0.300)。CS–US の遅延は捨てている |
| 23 | StimulusGeneralization | しない | V(750 Hz) > V(500 Hz) > 0 | 期待どおりの不一致 (訓練していない刺激は 0 のまま) |
| 24 | ContextualFearConditioning | 部分 | 1 試行後に V_ctx > 0 | 通過・機構は違う (0.300)。置いてから電撃までの間隔は捨てている |
| 25 | PeakProcedure | しない | — | 未対応 |
| 26 | MediatedConditioning | しない | V^lithium_flavor > 0 | 期待どおりの不一致 (V = 0) |

合計: 通過 6、通過・機構は違う 9、期待どおりの不一致 9、未対応 2 (例のファイルは 26。`RetrospectiveRevaluation` と
`SummationRetardationTest` は例が 2 つずつ)。

9 行目の記録データ: ラットの A+ / AX− 手続きを MED-PC で記録した公開データ (セッション番号の取れる 920 セッション) では、
CS 8 秒あたりの餌皿への進入が、AX− では A+ の 0.73 倍 (セッション 1–5) から 0.44 倍 (6–15)、0.20 倍 (16 以降) に下がり、
A+ は 10 前後のままでした。R–W が予測する弁別 (AX− の ΣV が V_A より小さい) と向きが合います。
このデータには X の加算検査・遅延検査はありません。

## モデル

試行で提示される刺激の集合 *S* に含まれる各刺激 *i* について:

ΔV<sub>i</sub> = α<sub>i</sub> β (λ − Σ<sub>j∈S</sub> V<sub>j</sub>)

- *S* は CS の集合です。展開が文脈を要素として扱う場合は、文脈も加えます。
- US の無い試行は λ = 0 とし、`beta_nonreinforced` (既定は `beta` と同じ) を使います。
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
| 試行 | `phase_enter(label="trial-<k>", name=<文脈>)` … `phase_exit` |
| 試行の各 CS | 試行の始めに `stimulus_on(stimulus=<cs>)`、終わりに `stimulus_off` |
| 試行の US | 試行の終わりの `us_s` 秒 (既定 1 秒) 前に `stimulus_on(stimulus=<us>)`、終わりに `stimulus_off` |

時計は仮想のものです。試行 1 つの幅は `trial_s` 秒 (既定 10 秒) で、AST に ITI があれば
それを足します。CS と US は同じ刺激の事象で書きます。ログに書くのは提示した物で、
モデルの値 (λ・V) は書きません。モデルの上で漸近値を持たない US のラベル (US の欄に
置いた CS のラベル) も、刺激として書きます。

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
