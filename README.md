# Casuar — tiny causal core

> Don't encode concepts into semantics if they can be derived from causal structure, interaction, or time.

Three Postgres tables + a Python runner. No server, ORM, agent framework, or medical ontology.

## Run now

Python 3.12, no dependencies for the local demo:

```sh
python run.py
python -m unittest discover -s tests -v
```

The synthetic example compares baseline against `do(input=2)` during steps 1–6,
with a co-factor interaction, delayed effects, feedback, and uncertain parameters.
Output includes mean/SD trajectories, final mean differences, derived temporal edges,
model hash, runner version, and the complete request. Values are arbitrary, not health estimates.

## Model contract

Equations define `X[t] = f(parents[t-1], parameters, u[t])`. All updates are simultaneous.
Variable references derive the graph; multiplication expresses co-factor interactions.
Feedback runs across time, so no same-step cyclic solver is needed. One-step lags only
in v0; represent longer memory with explicit state variables. `time_unit` is descriptive;
the caller must choose consistent equations and step size.

Parameters have Gaussian `mean`/`sd` and are drawn once per trajectory. Disturbances
are independent Gaussian draws per variable per step. These assumptions are explicit,
not evidence that the model is true. Baseline and intervention share seeded draws.
Output SD describes simulated spread, not clinical confidence or a confidence interval.

Interventions replace the target equation at inclusive steps `start..end` (starting at 1).
Effects on children arrive next step. After release the equation resumes; the state does
not reset. `initial` supplies exact state overrides at t=0, not Bayesian conditioning.

Equations support only numeric literals, known names, `+ - * /`, and unary signs.
`u` is the variable's disturbance. There is no Python `eval`/`exec`, function call,
attribute access, import, filesystem, or network operation in the expression interpreter.
This is a small arithmetic subset, not an arbitrary-code sandbox.

## Database

Recommended: existing Supabase Postgres, private `casuar_do` schema. Any ordinary
Postgres also works. No graph database is needed: definitions/equations live in JSONB.

- `models`: versioned definitions, assumptions, evidence references.
- `observations`: timestamped person/variable/value/unit/source/uncertainty records.
- `runs`: exact model snapshot and full result/request for reproducibility.

```sh
# Set DATABASE_URL securely to your Postgres connection string; never commit it.
python -m pip install -r requirements.txt
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f schema.sql
python run.py --db
```

Apply `schema.sql` once to an unused schema. Use a private backend database connection
with access to the schema; RLS is enabled with no public policies. No frontend/API
access is configured. Supabase connection details: https://supabase.com/docs/guides/database/connecting-to-postgres

`--db` inserts a new model version or loads its existing matching definition, computes,
and persists a run atomically. Different content requires a new version. Run snapshots
preserve exact inputs even if an administrator later edits the model row. Do not edit
published definitions; increment the version. Record the runtime/Python version when
reproducing across environments; seeded randomness is intended for the same runtime.

Observations are stored but deliberately not auto-selected or converted into initial
conditions yet. Supply explicit `initial` values after aligning time and units. Measurement
uncertainty is stored, not propagated in v0. No real patient data belongs in this repository.

## Scope

This is dynamic structural causal model simulation under supplied assumptions.
It does **not** implement Pearl's symbolic do-calculus rules, causal identification,
causal discovery, fitting, posterior inference, patient counterfactual inference, or
intervention recommendations. A graph alone cannot supply numerical causal effects.

Next proof: encode one evidence-backed mechanism, inspect its assumptions, and compare
its predicted trajectories with observations before adding any orchestration.
