# Validation gates

`python3 scripts/validate_db.py universe.db` validates the checked-in snapshot
without third-party packages. `make check` rebuilds the database first and runs
the validator together with its malformed-database regression suite.

Publication is rejected when any of these boundaries fail:

- SQLite integrity, foreign keys, entity specialization, or dataset/source
  references;
- source redistribution permission;
- exact species formula mass, reaction atom balance, or reaction charge
  balance;
- observation, condition, energy, spectrum, lattice, or cross-section unit
  dimensions;
- individual nuclear probability bounds, compatible branch-group totals, or
  representative isotope abundance totals;
- alias resolution or acyclic, type-preserving entity replacement;
- authored species composition, molecular graph composition/formal charge,
  reaction phase support, material normalization, or acyclic mixture
  composition;
- ordered, contiguous spectral and cross-section points, crystal-site
  occupancy, or condition-range ordering.

All numeric comparisons use `fractions.Fraction`. Unit conversion applies the
schema's exact rational scale, base-10 exponent, and offset; validation does not
round through SQLite `REAL` or Python floating point.

Malformed fixtures in `tests/test_validation.py` cover the mass, charge, atom,
probability, unit, alias, reference, and graph gates independently. New schema
families must add a rejection fixture for every dimensional, conservation,
ordering, probability, or graph invariant they introduce.
