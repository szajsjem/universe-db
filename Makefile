.PHONY: all build check report clean

all: check

build:
	python3 scripts/build_db.py

check: build
	python3 scripts/import_pubchem_periodic_table.py --check
	python3 scripts/import_nist_isotopes.py --check
	python3 scripts/validate_db.py universe.db
	python3 -m unittest discover -s tests -v

report: build
	python3 scripts/report.py universe.db

clean:
	rm -rf .build
