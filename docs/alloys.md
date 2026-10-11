# Metal alloy reference

`alloys.db` is a separate, reproducible SQLite reference covering iron–carbon,
copper, gold, silver, aluminum, magnesium, titanium, and nickel materials.
The entries are hand-authored with model-assisted primary-source research.
They remain `pending_human_review` under the project's data policy; they are
not promoted into the reviewed `universe.db` tables.

| Family | Grades |
|---|---:|
| Iron–carbon: carbon/alloy/stainless steels and cast irons | 12 |
| Copper | 12 |
| Gold | 3 |
| Silver | 3 |
| Aluminum | 10 |
| Magnesium | 5 |
| Titanium | 5 |
| Nickel | 9 |
| **Total** | **59** |

The first edition contains 383 composition entries and 47 source citations.

The reference records grade identities, producer/standard designations,
composition limits or nominal recipes, applications, qualifications, and
source citations. Producer-specific compositions are identified as such.
Commercially pure metal grades appear alongside alloys where useful for
comparison. An 18-carat gold designation does not specify a unique silver,
copper, or palladium recipe.

No strength, hardness, thermal, or corrosion measurements are asserted.
Those properties require product form, temper, heat treatment, test method,
and operating conditions. Applications are authored orientation notes, not
an engineering suitability certification.

## Rebuild

```sh
python scripts/build_alloy_db.py
python -m unittest tests.test_build_alloy_db
```

Inputs are the three versioned JSON files in `sources/alloys/`. Each source
records its publisher, citation URL, retrieval date, source version where
available, and factual-data redistribution determination. Each composition
row cites its own source. The database metadata stores the input SHA-256
digests; `alloys.db.sha256` records the artifact digest. The builder checks
exact numeric ranges, source references, covered families, foreign keys,
and SQLite integrity before atomically replacing the output.

## Query

```sql
SELECT family, count(*) AS grades FROM alloy GROUP BY family;

SELECT alloy_id, name, designation
FROM alloy WHERE family = 'iron-carbon';

SELECT a.name, c.element, c.role,
       c.min_wt_pct, c.max_wt_pct, c.nominal_wt_pct, s.url, c.note
FROM alloy a JOIN composition_wt_percent c USING (alloy_id)
JOIN source s USING (source_id)
WHERE a.family = 'titanium'
ORDER BY a.name, c.element;
```

`composition` stores exact integer ratios **in mass percent**, not fractions
of one. `composition_wt_percent` provides convenient floating-point values
for display. A missing bound is SQL `NULL`; a maximum-only impurity limit
does not imply an experimentally measured zero lower bound. `balance` means
the remainder, not an independently specified fixed percentage. Combined
analytes such as `Ni+Co` or `Nb+Ta` retain the combined limit; they must not be
treated as a value for either element alone or added to overlapping individual
limits. Additional combined or conditional restrictions appear in notes.

`alloy_source`, `source`, `application`, and `note` preserve the associated
citations and context. Limits from different grades are not interchangeable,
and a composition table does not replace the applicable purchase specification.
