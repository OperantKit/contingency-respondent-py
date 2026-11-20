# contingency-respondent-py

:jp: [日本語版 README](README.ja.md)

Expands the Tier B Pavlovian (respondent) procedures of contingency-respondent-dsl
into trial lists for contingency-py and writes the trials as an OKL v1 log.

- **Expander** — turns a Tier B AST into a list of trials (stage, CS set, US, context).
  Nested Tier A expressions are expanded by contingency-py (`contingency.respondent`,
  computed by contingency-rs); this package does not expand Tier A itself.
- **contingency-py expansion** — `TIER_B` registers the Tier B procedures in a
  contingency-py `RespondentRegistry`.
- **OKL writer** — each trial becomes a phase marker; CS and US are written as
  `stimulus_on` / `stimulus_off` events.

## Install

The sibling packages are referenced by local path while this package has no remote.
From this directory:

```bash
mise exec -- python -m venv .venv
.venv/bin/python -m pip install -e ../../core/contingency-dsl-py \
  -e ../../core/contingency-py -e ../../core/contingency-respondent-dsl \
  -e ../../experiment/session-recorder
.venv/bin/python -m pip install -e ".[dev]"
```

The runtime dependencies are contingency-py (with its `contingency_core` extension
module, which expands Tier A), contingency-respondent-dsl and session-recorder.
`experiment-core` is not needed.

## Usage

```python
from contingency_respondent_dsl import from_dict
from contingency_respondent import expand, expand_control, write_okl

node = from_dict(expected_ast)          # a Tier B AST, e.g. a conformance example
expansion = expand(node)                # trials of every stage, in order
control = expand_control(node)          # control condition, or None

write_okl(expansion, "blocking.txt", {"session_name": "blocking"})
```

To run a model on the trials, see [Running a model](#running-a-model).

## Expansion rules

The input is the object returned by `contingency_respondent_dsl.from_dict`. Tier B
nodes are dataclasses; nested Tier A expressions stay as dicts in the shape
contingency-py reads (for example `Compound` takes `cs_list`). The Core parser is not
used, so procedure text has to be turned into an AST first.

Each nested Tier A expression is expanded by contingency-py into one trial, and that
trial is the template the stage repeats. Its CS set, US, order and times are kept on
every trial of the stage.

| Nested form | Trial template |
|---|---|
| `Pair<Mode>(cs, us, …)` (e.g. `PairForwardDelay`; `Pair.ForwardDelay` is read too) | the contingency-py trial; `us="nothing"` means no US |
| `Extinction(cs)` / `Compound(cs_list)` / `CSOnly(cs)` / `USOnly(us)` | the contingency-py trial |
| `Serial(elements=[...])` (not a Tier A form; read by this package) | intermixed presentation: the element templates are cycled one trial at a time |
| `Serial(cs_list=[...])`, `Contingency`, `TrulyRandom`, `ExplicitlyUnpaired`, `ITI`, `Differential` | unsupported (no single repeated trial template) |

Each stage repeats its template for the stage's `*_trials` count, or for
`default_trials` (20) when the AST gives none. Timing arguments (`isi`,
`cs_duration`, …) are also recorded on each trial as dropped; a trial-level model does
not use them.

## Registering in contingency-py

contingency-py expands Tier A itself and leaves Tier B to expansions registered per
program. `TIER_B` is the expansion for the procedures here; `registry()` builds a
`RespondentRegistry` holding it (pass further expansions as arguments).

```python
from contingency_respondent import registry

trials = registry().expand(expected_ast, {"trials": 20})
# [{"stage": "phase1", "cs": ["a"], "us": "shock", "context": None,
#   "order": None, "time": {...}, "iti_s": None}, ...]
```

Nested expressions go back through the same registry. Options:

| Option | Meaning |
|---|---|
| `trials` (required) | trials of every stage whose count the AST does not give; no default is chosen (`RespondentUnresolvedError`) |
| `control` (default `false`) | expand the control condition instead of the procedure |
| `seed`, `labels` | passed to every nested Tier A expansion |

A procedure that does not reduce to a trial list (see below) raises
`RespondentSpecError` with the reason. The trial list is the same as
`to_trial_dicts(expand(node, default_trials=trials))`.

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
  `MediatedConditioning`) stays on the trial as its US label. A model that gives that
  label no asymptote treats the trial as one without a US.

## Running a model

This package expands procedures; it has no learning model. session-analyzer's
`simulate_compound_rescorla_wagner` runs the compound-CS Rescorla–Wagner model on the
trials (the context is summed in when the expansion says so):

```python
from session_analyzer.analytics import (
    CompoundRescorlaWagner, CompoundTrial, simulate_compound_rescorla_wagner,
)

cae = expansion.context_as_element
trials = [CompoundTrial(t.elements(cae), t.us, t.stage) for t in expansion.trials]
trace = simulate_compound_rescorla_wagner(
    trials, CompoundRescorlaWagner({}, lambda_by_us={"shock": 1.0})
)
v_test = trace.v_at_stage_start("test")  # strengths entering the first test trial
```

The law suite that runs all 26 Tier B conformance examples this way, and the table of
which phenomena the Rescorla–Wagner model predicts, are in contingency-bench
(`tests/test_respondent_laws.py`, extra `respondent`).

## OKL layout

| What | OKL record |
|---|---|
| stage | `phase_enter(label=<stage>, name=<context>)` … `phase_exit` |
| trial | `phase_enter(label="trial-<k>", name=<context>)` … `phase_exit` |
| each CS of the trial | `stimulus_on(stimulus=<cs>)` at the trial start, `stimulus_off` at the trial end |
| US of the trial | `stimulus_on(stimulus=<us>)` `us_s` seconds (default 1 s) before the trial end, `stimulus_off` at the trial end |

The clock is virtual: each trial is `trial_s` seconds wide (default 10 s), plus the
ITI when the AST gives one. CS and US use the same stimulus events; the log records
what was presented. A CS label in a US slot is written as a stimulus too.

## Stimulus sequence on a real-time clock

`contingency_respondent.timeline.stimulus_timeline` returns the stimulus onsets and offsets
of a respondent program from its time values (unlike the trial-level OKL writer
above, which uses a fixed trial width). It handles `Pair.ForwardDelay` and `USOnly`
with an optional `@iti(distribution=fixed, mean=...)`. The session starts with an
ITI, the ITI runs from the last offset of a trial, and the US lasts the
`presentation_s` value given by the caller (neither the DSL nor the model carries it).

It is the respondent side of the same-experiment fixtures in contingency-dsl
(`conformance/equivalence/`): `tests/test_equivalence.py` runs each fixture's
`respondent` program with each input response sequence and compares the result
with the fixture's expected stimulus sequence. Set `CONTINGENCY_DSL_CONFORMANCE`
to the `conformance` directory of a contingency-dsl checkout; by default the
sibling checkout is used, and the test is skipped when neither is present.

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
