"""One calculation interface for independent alloy and neutral isotope profiles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

if __package__:
    from .alloy_mechanical_properties import mechanical_properties
    from .atomic_isotope_properties import atomic_properties
else:
    from alloy_mechanical_properties import mechanical_properties
    from atomic_isotope_properties import atomic_properties


def calculate_stats(profile, specification):
    """Dispatch without fitting at query time or writing scientific observations."""
    kind = specification.get("kind")
    if kind == "alloy":
        return mechanical_properties(
            profile,
            specification["composition_mass_fractions"],
            conditions=specification["conditions"],
        )
    if kind == "isotope":
        if profile.get("algorithm") != "atomic-composition-property-profile-1":
            raise ValueError("unsupported atomic property profile")
        approximate = specification.get("approximate_missing", False)
        if type(approximate) is not bool:
            raise ValueError("approximate_missing must be boolean")
        return atomic_properties(
            profile,
            specification["protons"],
            specification["neutrons"],
            specification.get("electrons"),
            state_index=specification.get("state_index", 0),
            approximate_missing=approximate,
        )
    raise ValueError("kind must be alloy or isotope")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() in (args.model.resolve(), args.input.resolve()):
        parser.error("output must differ from input files")
    result = calculate_stats(
        json.loads(args.model.read_text(encoding="utf-8")),
        json.loads(args.input.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
