.PHONY: all build check export report material-benchmark research-plan wikipedia-plan wikipedia-clean-plan clean

all: check

build:
	python3 scripts/build_db.py

check:
	python3 scripts/import_pubchem_periodic_table.py --check
	python3 scripts/import_nist_isotopes.py --check
	python3 scripts/check_wikipedia_snapshot.py
	python3 scripts/validate_db.py universe.db
	python3 scripts/validate_db.py universe-unverified.db
	python3 -m unittest discover -s tests -v

export: build
	python3 scripts/export_inorganicengineering.py

report: build
	python3 scripts/report.py universe.db

material-benchmark: build
	python3 scripts/describe_material.py --evaluate

research-plan: build
	python3 scripts/research_missing_data.py

wikipedia-plan: build
	python3 scripts/parse_wikipedia_archive.py \
		sources/wikipedia-chemistry-category-snapshot-2026-07-29.zip

wikipedia-clean-plan:
	python3 scripts/clean_wikipedia_candidates.py

clean:
	rm -rf .build
