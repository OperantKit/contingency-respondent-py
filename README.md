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

Procedures expanded:

| Procedure | Stages | Control (`expand_control`) |
|---|---|---|
| `Blocking` | phase1 → phase2 → test | phase1 omitted |
| `Overshadowing` | training → test_a → test_b | `test_b` element trained alone |
| `ConditionedInhibition` | training → test | none |
| `InhibitionOfDelay`, `PeakProcedure` | unsupported: they need the distribution of responding within the CS | — |

When `ConditionedInhibition.training` is a single reinforced pairing, the expander
builds the A+ / AI− intermix, taking I from the test expression. Other procedures
return `unsupported` with the reason "expansion not implemented".

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
