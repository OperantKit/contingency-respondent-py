# respondent-runner

:jp: [日本語版 README](README.ja.md)

Runs Pavlovian (respondent) procedures written in contingency-respondent-dsl on a
trial-level Rescorla–Wagner model and writes the run as an OKL v1 log.

- **Expander** — turns a Tier B AST into a list of trials (stage, CS set, US, context).
- **Executor** — compound-CS Rescorla–Wagner with per-stimulus salience.
- **OKL writer** — each trial becomes a phase marker whose `cue` is the CS set.

## Install

The sibling packages are referenced by local path while this package has no remote.
From this directory:

```bash
mise exec -- python -m venv .venv
.venv/bin/python -m pip install -e ../../core/contingency-dsl-py -e ../../core/contingency-py \
  -e ../../experiment/experiment-core -e ../../experiment/session-recorder \
  -e ../../core/contingency-respondent-dsl
.venv/bin/python -m pip install -e ".[dev]"
```

`contingency-py` and `contingency-dsl-py` are only needed because `experiment-core`
(required by `session-recorder`) depends on them; this package does not import them.

## Usage

```python
from contingency_respondent_dsl import from_dict
from respondent_runner import RescorlaWagner, expand, expand_control, run, write_okl

node = from_dict(expected_ast)          # a Tier B AST, e.g. a conformance example
model = RescorlaWagner({"a": 0.3, "x": 0.3}, lambda_by_us={"shock": 1.0})

trace = run(expand(node), model)
v_test = trace.v_at_stage_start("test")  # strengths entering the first test trial

control = expand_control(node)           # control condition, or None
write_okl(trace, "blocking.txt", {"session_name": "blocking"})
```

## Expansion rules

The input is the object returned by `contingency_respondent_dsl.from_dict`. Tier B
nodes are dataclasses; nested Tier A expressions stay as dicts. The Core parser is not
used, so procedure text has to be turned into an AST first.

| Nested Tier A form | Trial template |
|---|---|
| `Pair.<mode>(cs, us)` | CS = `cs` (a label or `Compound(elements)`), US = `us`; `us="nothing"` means no US |
| `Extinction(cs)` / `Compound(elements)` / `CSOnly(cs)` | CS without US |
| `USOnly(us)` | US without CS |
| `Serial(elements=[...])` | intermixed presentation: the element templates are cycled one trial at a time |
| `Serial(cs_list=[...])` | unsupported (a serial compound needs time within the CS) |

Each stage repeats its template for the stage's `*_trials` count, or for
`default_trials` (20) when the AST gives none. Timing arguments (`isi`,
`cs_duration`, …) are recorded on each trial as dropped; the model does not use them.

All 26 Tier B procedures are expanded except `InhibitionOfDelay` and `PeakProcedure`,
which need the distribution of responding within the CS and return `unsupported`.
Where the AST is schematic the expander fills in the minimum needed:

- A single reinforced pairing in `ConditionedInhibition.training` (and the one nested in
  `SuperConditioning`) becomes the A+ / AI− intermix, I taken from the test expression.
  `SummationRetardationTest` gets the same E+ / EI− training.
- Procedures that name a context put the context into the summed set
  (`Expansion.context_as_element`): `USPreexposure`, `Renewal`, `Reinstatement`,
  `LatentExtinction`, `ContextualExtinction`, `ContextualFearConditioning`. When the AST
  names no context the expander uses `ctx` (and `ctx_other` / `acq` for controls).
- `PavlovianPREE` places round(p·n) reinforced trials evenly, without randomness.
- A CS label in a US slot (`HigherOrderConditioning`, `SensoryPreconditioning`,
  `MediatedConditioning`) has no asymptote, so it counts as a trial without a US.

## Law suite

`tests/laws/test_respondent_phenomena.py` runs every Tier B conformance fixture
(`expected_ast`) through the expander and the executor (α = 0.3 for every stimulus,
β = 1, λ = 1 for each US, 20 trials where the AST gives no count) and judges the
phenomenon by inequalities on V only. Fixtures are found through
`$RESPONDENT_CONFORMANCE_ROOT`, else an ancestor directory holding
`contingency-respondent-dsl/conformance/tier-b`; the suite is skipped without them.

- **passes** — R–W gives the direction of the phenomenon.
- **passes, mechanism differs** — the direction comes out under a plain extension
  (context as an element, one system per US), but not the mechanism the procedure is
  known for.
- **expected mismatch** — R–W does not give the phenomenon; the test states the
  phenomenon and is `xfail(strict=True)`.
- **unsupported** — needs time within the CS; `expand` refuses.

| # | Procedure | R–W | Judgement on V | Result (values from the suite) |
|---|---|---|---|---|
| 1 | HigherOrderConditioning | no | V_light > 0 after X→A | expected mismatch (V_light = 0) |
| 2 | SensoryPreconditioning | no | V_light > 0 at test | expected mismatch (V_light = 0) |
| 3 | Counterconditioning | partial | V^shock_tone falls, V^food_tone > 0 | passes, mechanism differs (0.999 → 0.001; V^food 0.999). No reciprocal inhibition between US systems |
| 4 | Blocking | predicts | V_x < control | passes (0.000 vs 0.500) |
| 5 | Overshadowing | predicts | V_dim < trained alone; V_loud > V_dim (α 0.5 / 0.2) | passes (0.286 vs 1.000; V_loud 0.714) |
| 6 | Overexpectation | predicts | V_a falls in AX+; control unchanged | passes (0.999 → 0.500; control 0.999) |
| 7 | SuperConditioning | predicts | V_x > control whose partner is a neutral stimulus | passes (0.969 vs 0.500; V_i −0.938) |
| 8 | RetrospectiveRevaluation | no | backward blocking (V_x < control) and recovery (V_x > control) | expected mismatch (V_x = control = 0.500 in both) |
| 9 | ConditionedInhibition | predicts | V_i < 0 and V_a + V_i → 0 | passes (V_a 0.997, V_i −0.996). Recorded A+/AX− data (below) show the discrimination |
| 10 | OccasionSetting | partial | FP: V_feature > 0, V_target ≈ 0 | passes, mechanism differs (0.998 / 0.001). Occasion setting itself is not elemental |
| 11 | InhibitionOfDelay | no | — | unsupported |
| 12 | SummationRetardationTest | predicts | ΣV(E+I) < V_E; V_I after 5 trials < novel CS | passes (0.001 vs 0.997; 0.664 vs 0.832) |
| 13 | LatentInhibition | no | V_tone < control after training | expected mismatch (1.000 = 1.000) |
| 14 | USPreexposure | partial | V_tone < control | passes, mechanism differs (0.000 vs 0.500). Context blocking only |
| 15 | Renewal | partial | ΣV(test in A) > ΣV(end of extinction in B) | passes, mechanism differs (0.750 vs 0.000). Context B ends inhibitory |
| 16 | Reinstatement | partial | ΣV(test) > ΣV(end of extinction); other context unchanged | passes, mechanism differs (0.760 vs 0.000). Context excitation only |
| 17 | SpontaneousRecovery | no | V_tone(test) > end of extinction | expected mismatch (no time variable) |
| 18 | LatentExtinction | partial | ΣV(test) < control | passes, mechanism differs (0.500 vs 1.000). Only the context's share is lost |
| 19 | PavlovianPREE | no | V(partial) > V(continuous) after extinction | expected mismatch (R–W gives the reverse) |
| 20 | ContextualExtinction | partial | ΣV(test in acquisition context) > end of extinction | passes, mechanism differs (0.750 vs 0.000) |
| 21 | ReconsolidationInterference | no | recovery after plain extinction, none after retrieval–extinction | expected mismatch (no recovery in either) |
| 22 | ConditionedTasteAversion | partial | V_taste > 0 after 1 trial | passes, mechanism differs (0.300). CS–US delay is dropped |
| 23 | StimulusGeneralization | no | V(750 Hz) > V(500 Hz) > 0 | expected mismatch (untrained stimuli stay 0) |
| 24 | ContextualFearConditioning | partial | V_ctx > 0 after 1 trial | passes, mechanism differs (0.300). Placement-to-shock interval is dropped |
| 25 | PeakProcedure | no | — | unsupported |
| 26 | MediatedConditioning | no | V^lithium_flavor > 0 | expected mismatch (V = 0) |

Totals: 6 pass, 9 pass with a differing mechanism, 9 expected mismatches, 2 unsupported
(one fixture file per procedure; `RetrospectiveRevaluation` and `SummationRetardationTest` have two
examples each).

Recorded data for row 9: in a public MED-PC dataset of an A+ / AX− procedure in rats
(920 sessions with a session number), head entries per 8-s CS interval in AX− fell from
0.73 of those in A+ (sessions 1–5) to 0.44 (6–15) and 0.20 (16 and later), while A+
stayed near 10. That is the discrimination R–W predicts (ΣV of AX− below V_A); the
data have no summation or retardation test of X.

## Model

For every stimulus *i* in the trial's presented set *S*:

ΔV<sub>i</sub> = α<sub>i</sub> β (λ − Σ<sub>j∈S</sub> V<sub>j</sub>)

- *S* is the CS set, plus the context when the expansion marks the context as an element.
- A trial without a US uses λ = 0 and `beta_nonreinforced` (default: `beta`).
- Associative strength is kept per US label. A trial with US *u* drives the *u* system
  toward `lambda_by_us[u]` and the others toward 0. A US label absent from
  `lambda_by_us` carries no asymptote and counts as a trial without a US.
- Stimuli not in *S* are not updated.

`Trace.v_at_stage_start(stage)` returns the strengths entering the first trial of a
stage; `Trace.to_json()` dumps every trial.

## Relation to session-analyzer

session-analyzer's `simulate_rescorla_wagner` / `fit_rescorla_wagner` are a single-CS
model used to analyse recorded sessions. This package sits beside it rather than
replacing it: the executor does not import session-analyzer, and the test suite checks
that a single-CS run matches `simulate_rescorla_wagner` to 1e-12.

## OKL layout

| What | OKL record |
|---|---|
| stage | `phase_enter(label=<stage>, name=<context>)` … `phase_exit` |
| trial | `phase_enter(label="trial-<k>", name=<context>, cue="a+x")` … `phase_exit` |
| US with an asymptote | `reinforcer_start(potency=λ)` / `reinforcer_end` at the end of the trial |

The clock is virtual: each trial is `trial_s` seconds wide (default 10 s), plus the
ITI when the AST gives one. The OKL canonical events have no field for stimulus
presentation, so the CS set is carried by the `cue` context coordinate.

## Tests

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check src tests
.venv/bin/mypy src
```

## References

Rescorla, R. A., & Wagner, A. R. (1972). A theory of Pavlovian conditioning:
Variations in the effectiveness of reinforcement and nonreinforcement. In A. H. Black
& W. F. Prokasy (Eds.), *Classical conditioning II: Current research and theory*
(pp. 64–99). Appleton-Century-Crofts.

## License

MIT
