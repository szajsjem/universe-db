#!/usr/bin/env python3
"""Describe an unreviewed material by analogy with reviewed database materials.

This is deliberately a small, inspectable baseline rather than a generative
model.  It fits inverse-document-frequency weights on material compositions,
uses a weighted k-nearest-neighbour search, and abstains outside its learned
domain.  Its output is model evidence, never a reviewed database observation.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT / "universe.db"
ALGORITHM_ID = "material-composition-knn"
ALGORITHM_VERSION = "1.0.0"
SCHEMA_VERSION = 1
COMPONENT_WEIGHT = 0.65
ELEMENT_WEIGHT = 0.35
DEFAULT_NEIGHBORS = 3


class DescriptorError(ValueError):
    """Raised when a material specification cannot be represented safely."""


@dataclass(frozen=True)
class Component:
    key: str
    label: str
    formula: str
    elements: dict[str, int]
    amount: Fraction | None
    basis: str
    role: str | None = None
    resolved_species_id: str | None = None


@dataclass(frozen=True)
class MaterialExample:
    material_id: str
    name: str
    material_kind: str
    components: tuple[Component, ...]


@dataclass(frozen=True)
class Features:
    components: dict[str, float]
    elements: dict[str, float]


@dataclass(frozen=True)
class Neighbor:
    example: MaterialExample
    similarity: float
    component_similarity: float
    element_similarity: float


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise DescriptorError(f"database does not exist: {path}")
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def fraction_json(value: Fraction | None) -> dict[str, int] | None:
    if value is None:
        return None
    return {"numerator": value.numerator, "denominator": value.denominator}


def rounded(value: float) -> float:
    return round(value, 6)


class FormulaParser:
    """Parse neutral formulas with nested parentheses/brackets and hydrates."""

    def __init__(self, element_symbols: Iterable[str]):
        self.element_symbols = set(element_symbols)

    def parse(self, formula: str) -> dict[str, int]:
        compact = re.sub(r"\s+", "", formula)
        if not compact:
            raise DescriptorError("component formula cannot be empty")
        if "+" in compact or "-" in compact or "^" in compact:
            raise DescriptorError(
                f"unresolved charged formula {formula!r}; use a reviewed species ID"
            )
        total: Counter[str] = Counter()
        for raw_segment in re.split(r"[.\u00b7]", compact):
            if not raw_segment:
                raise DescriptorError(f"invalid hydrate formula {formula!r}")
            match = re.match(r"^(\d+)(?=[A-Z(\[])", raw_segment)
            multiplier = int(match.group(1)) if match else 1
            segment = raw_segment[match.end() :] if match else raw_segment
            counts, position = self._sequence(segment, 0, None, formula)
            if position != len(segment):
                raise DescriptorError(f"cannot parse formula {formula!r}")
            for symbol, count in counts.items():
                total[symbol] += multiplier * count
        if not total:
            raise DescriptorError(f"formula {formula!r} contains no elements")
        return dict(sorted(total.items()))

    def _sequence(
        self,
        value: str,
        position: int,
        closing: str | None,
        original: str,
    ) -> tuple[Counter[str], int]:
        counts: Counter[str] = Counter()
        pairs = {"(": ")", "[": "]"}
        while position < len(value):
            character = value[position]
            if closing and character == closing:
                return counts, position + 1
            if character in ")]":
                raise DescriptorError(f"unmatched bracket in formula {original!r}")
            if character in pairs:
                nested, position = self._sequence(
                    value, position + 1, pairs[character], original
                )
                if not nested:
                    raise DescriptorError(f"empty group in formula {original!r}")
                multiplier, position = self._number(value, position)
                for symbol, count in nested.items():
                    counts[symbol] += count * multiplier
                continue
            match = re.match(r"[A-Z][a-z]?", value[position:])
            if not match:
                raise DescriptorError(
                    f"unexpected token at position {position + 1} "
                    f"in formula {original!r}"
                )
            symbol = match.group(0)
            if symbol not in self.element_symbols:
                raise DescriptorError(
                    f"unknown element symbol {symbol!r} in {original!r}"
                )
            position += len(symbol)
            multiplier, position = self._number(value, position)
            counts[symbol] += multiplier
        if closing:
            raise DescriptorError(f"unclosed bracket in formula {original!r}")
        return counts, position

    @staticmethod
    def _number(value: str, position: int) -> tuple[int, int]:
        match = re.match(r"\d+", value[position:])
        if not match:
            return 1, position
        number = int(match.group(0))
        if number <= 0:
            raise DescriptorError("formula subscripts must be positive")
        return number, position + len(match.group(0))


def canonical_composition(elements: dict[str, int]) -> str:
    divisor = 0
    for count in elements.values():
        divisor = math.gcd(divisor, count)
    return ":".join(
        f"{symbol}{count // divisor}" for symbol, count in sorted(elements.items())
    )


class MaterialModel:
    def __init__(self, database: Path, examples: list[MaterialExample]):
        if not examples:
            raise DescriptorError("database has no reviewed material examples")
        self.database = database
        self.database_sha256 = sha256_file(database)
        self.examples = examples
        self.component_idf = self._idf(
            features.components for features in map(self.features, examples)
        )
        self.element_idf = self._idf(
            features.elements for features in map(self.features, examples)
        )
        self.in_domain_threshold = self._fit_domain_threshold()

    @classmethod
    def load(cls, database: Path) -> MaterialModel:
        connection = connect_readonly(database)
        try:
            examples: list[MaterialExample] = []
            rows = connection.execute(
                """
                SELECT m.entity_id, e.name, m.material_kind
                FROM material AS m
                JOIN entity AS e ON e.entity_id = m.entity_id
                WHERE e.lifecycle_state = 'active'
                ORDER BY m.entity_id
                """
            ).fetchall()
            for row in rows:
                component_rows = connection.execute(
                    """
                    SELECT mc.species_id, component.name, cs.formula,
                           mc.amount_numerator, mc.amount_denominator,
                           mc.basis, mc.role
                    FROM material_component AS mc
                    JOIN chemical_species AS cs ON cs.entity_id = mc.species_id
                    JOIN entity AS component ON component.entity_id = mc.species_id
                    WHERE mc.material_id = ?
                    ORDER BY mc.species_id
                    """,
                    (row["entity_id"],),
                ).fetchall()
                components = []
                for component_row in component_rows:
                    element_rows = connection.execute(
                        """
                        SELECT element.symbol, se.atom_count
                        FROM species_element AS se
                        JOIN element ON element.entity_id = se.element_id
                        WHERE se.species_id = ?
                        ORDER BY element.atomic_number
                        """,
                        (component_row["species_id"],),
                    ).fetchall()
                    elements = {
                        item["symbol"]: item["atom_count"] for item in element_rows
                    }
                    amount = None
                    if component_row["amount_numerator"] is not None:
                        amount = Fraction(
                            component_row["amount_numerator"],
                            component_row["amount_denominator"],
                        )
                    components.append(
                        Component(
                            key=f"species:{component_row['species_id']}",
                            label=component_row["name"],
                            formula=component_row["formula"],
                            elements=elements,
                            amount=amount,
                            basis=component_row["basis"],
                            role=component_row["role"],
                            resolved_species_id=component_row["species_id"],
                        )
                    )
                if components:
                    examples.append(
                        MaterialExample(
                            material_id=row["entity_id"],
                            name=row["name"],
                            material_kind=row["material_kind"],
                            components=tuple(components),
                        )
                    )
            return cls(database, examples)
        finally:
            connection.close()

    @staticmethod
    def _idf(documents: Iterable[dict[str, float]]) -> dict[str, float]:
        documents = list(documents)
        frequency: Counter[str] = Counter()
        for document in documents:
            frequency.update(key for key, value in document.items() if value > 0)
        size = len(documents)
        return {
            key: math.log((size + 1) / (count + 1)) + 1
            for key, count in frequency.items()
        }

    @staticmethod
    def features(example: MaterialExample) -> Features:
        amounts = [component.amount for component in example.components]
        if all(amount is not None for amount in amounts):
            present_amounts = [amount for amount in amounts if amount is not None]
            total = sum(present_amounts, Fraction())
            weights = [float(amount / total) for amount in present_amounts]
        else:
            weights = [1.0 / len(example.components)] * len(example.components)

        component_features: defaultdict[str, float] = defaultdict(float)
        element_features: defaultdict[str, float] = defaultdict(float)
        for component, weight in zip(example.components, weights, strict=True):
            component_features[component.key] += weight
            atom_total = sum(component.elements.values())
            if atom_total:
                for symbol, count in component.elements.items():
                    element_features[symbol] += weight * count / atom_total
        return Features(dict(component_features), dict(element_features))

    @staticmethod
    def _weighted_jaccard(
        left: dict[str, float],
        right: dict[str, float],
        idf: dict[str, float],
        default_idf: float,
    ) -> float:
        keys = set(left) | set(right)
        denominator = sum(
            max(left.get(key, 0.0), right.get(key, 0.0))
            * idf.get(key, default_idf)
            for key in keys
        )
        if denominator == 0:
            return 0.0
        numerator = sum(
            min(left.get(key, 0.0), right.get(key, 0.0))
            * idf.get(key, default_idf)
            for key in keys
        )
        return numerator / denominator

    @staticmethod
    def _cosine(
        left: dict[str, float],
        right: dict[str, float],
        idf: dict[str, float],
        default_idf: float,
    ) -> float:
        keys = set(left) | set(right)
        weighted_left = {
            key: left.get(key, 0.0) * idf.get(key, default_idf) for key in keys
        }
        weighted_right = {
            key: right.get(key, 0.0) * idf.get(key, default_idf) for key in keys
        }
        left_norm = math.sqrt(sum(value * value for value in weighted_left.values()))
        right_norm = math.sqrt(sum(value * value for value in weighted_right.values()))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return sum(
            weighted_left[key] * weighted_right[key] for key in keys
        ) / (left_norm * right_norm)

    def similarity(self, left: Features, right: Features) -> tuple[float, float, float]:
        default_idf = math.log((len(self.examples) + 1) / 1) + 1
        component = self._weighted_jaccard(
            left.components, right.components, self.component_idf, default_idf
        )
        element = self._cosine(
            left.elements, right.elements, self.element_idf, default_idf
        )
        combined = COMPONENT_WEIGHT * component + ELEMENT_WEIGHT * element
        return combined, component, element

    def neighbors(
        self,
        query: MaterialExample,
        count: int = DEFAULT_NEIGHBORS,
        exclude_material_id: str | None = None,
    ) -> list[Neighbor]:
        query_features = self.features(query)
        neighbors = []
        for example in self.examples:
            if example.material_id == exclude_material_id:
                continue
            combined, component, element = self.similarity(
                query_features, self.features(example)
            )
            neighbors.append(Neighbor(example, combined, component, element))
        neighbors.sort(key=lambda item: (-item.similarity, item.example.material_id))
        return neighbors[:count]

    def _fit_domain_threshold(self) -> float:
        nearest_scores = []
        for example in self.examples:
            neighbors = self.neighbors(example, 1, example.material_id)
            if neighbors:
                nearest_scores.append(neighbors[0].similarity)
        if not nearest_scores:
            return 0.5
        nearest_scores.sort()
        lower_decile = nearest_scores[max(0, math.ceil(len(nearest_scores) * 0.1) - 1)]
        return max(0.2, min(0.8, lower_decile))

    def describe(
        self,
        query: MaterialExample,
        neighbor_count: int = DEFAULT_NEIGHBORS,
    ) -> dict:
        neighbors = self.neighbors(query, neighbor_count)
        best_similarity = neighbors[0].similarity if neighbors else 0.0
        near_threshold = self.in_domain_threshold / 2
        if best_similarity >= self.in_domain_threshold:
            applicability = "in_domain"
        elif best_similarity >= near_threshold:
            applicability = "near_domain"
        else:
            applicability = "out_of_domain"

        votes: defaultdict[str, float] = defaultdict(float)
        for neighbor in neighbors:
            votes[neighbor.example.material_kind] += neighbor.similarity
        vote_total = sum(votes.values())
        ranked_votes = sorted(votes.items(), key=lambda item: (-item[1], item[0]))
        prediction = (
            ranked_votes[0][0]
            if ranked_votes and applicability == "in_domain"
            else None
        )
        support = ranked_votes[0][1] / vote_total if prediction and vote_total else 0.0

        feature_values = self.features(query)
        element_profile = sorted(
            feature_values.elements.items(), key=lambda item: (-item[1], item[0])
        )
        known_count = sum(
            component.resolved_species_id is not None for component in query.components
        )
        component_text = ", ".join(
            f"{component.label} ({component.formula})" for component in query.components
        )
        if prediction:
            inference_text = (
                f"Composition-based analogy suggests the material kind {prediction!r}; "
                f"the closest reviewed material is {neighbors[0].example.name!r}."
            )
        else:
            inference_text = (
                "The composition is outside the model's reviewed support, so material "
                "kind inference was withheld."
            )

        return {
            "schema_version": SCHEMA_VERSION,
            "result_kind": "unreviewed_material_model_output",
            "input": {
                "name": query.name,
                "basis": query.components[0].basis,
                "components": [
                    {
                        "label": component.label,
                        "formula": component.formula,
                        "amount": fraction_json(component.amount),
                        "resolved_species_id": component.resolved_species_id,
                    }
                    for component in query.components
                ],
            },
            "description": (
                f"{query.name} is an unreviewed material specified as "
                f"{component_text}. "
                f"{inference_text} This is an analogy, not a reviewed identity or a "
                "physical-property claim."
            ),
            "composition_profile": {
                "normalized_element_embedding": [
                    {"element": symbol, "fraction": rounded(value)}
                    for symbol, value in element_profile
                ],
                "resolved_component_count": known_count,
                "component_count": len(query.components),
                "fallback": (
                    "equal component weights"
                    if query.components[0].basis == "unspecified"
                    else (
                        "declared component fractions; each component's atom counts "
                        "normalized"
                    )
                ),
            },
            "inference": {
                "applicability": applicability,
                "predicted_material_kind": prediction,
                "kind_vote_support": rounded(support) if prediction else None,
                "closest_similarity": rounded(best_similarity),
                "in_domain_threshold": rounded(self.in_domain_threshold),
                "neighbors": [
                    {
                        "material_id": neighbor.example.material_id,
                        "name": neighbor.example.name,
                        "material_kind": neighbor.example.material_kind,
                        "similarity": rounded(neighbor.similarity),
                        "component_similarity": rounded(neighbor.component_similarity),
                        "element_similarity": rounded(neighbor.element_similarity),
                    }
                    for neighbor in neighbors
                ],
            },
            "model": self.model_card(neighbor_count),
            "limitations": [
                "The training corpus is small and strongly dominated by ores.",
                (
                    "Similarity does not establish identity, safety, performance, "
                    "or suitability."
                ),
                (
                    "No unobserved physical, chemical, mechanical, or process "
                    "property is predicted."
                ),
                (
                    "Unspecified database compositions are equally weighted as an "
                    "explicit fallback."
                ),
            ],
        }

    def model_card(self, neighbor_count: int | None = None) -> dict:
        kinds = Counter(example.material_kind for example in self.examples)
        return {
            "algorithm_id": ALGORITHM_ID,
            "algorithm_version": ALGORITHM_VERSION,
            "database_sha256": self.database_sha256,
            "training_material_count": len(self.examples),
            "training_kind_counts": dict(sorted(kinds.items())),
            "data_dependencies": [
                "entity",
                "material",
                "material_component",
                "chemical_species",
                "species_element",
                "element",
            ],
            "configuration": {
                "neighbors": neighbor_count,
                "reviewed_component_weight": COMPONENT_WEIGHT,
                "elemental_composition_weight": ELEMENT_WEIGHT,
                "in_domain_similarity_threshold": rounded(
                    self.in_domain_threshold
                ),
            },
            "random_seed": None,
            "deterministic": True,
            "precision": "Python binary64; reported scores rounded to 6 decimals",
            "validity_domain": (
                "Compositions expressible using element symbols present in the "
                "database; kind inference requires similarity to reviewed material "
                "compositions."
            ),
            "fallback_policy": "abstain below the learned similarity threshold",
        }

    def evaluate(self, neighbor_count: int = DEFAULT_NEIGHBORS) -> dict:
        exact_correct = 0
        holdout_correct = 0
        holdout_predictions = 0
        holdout_rows = []
        label_totals: Counter[str] = Counter()
        label_correct: Counter[str] = Counter()
        for example in self.examples:
            exact = self.neighbors(example, 1)
            if exact and exact[0].example.material_id == example.material_id:
                exact_correct += 1
            training_examples = [
                candidate
                for candidate in self.examples
                if candidate.material_id != example.material_id
            ]
            fold_model = MaterialModel(self.database, training_examples)
            neighbors = fold_model.neighbors(example, neighbor_count)
            votes: defaultdict[str, float] = defaultdict(float)
            for neighbor in neighbors:
                votes[neighbor.example.material_kind] += neighbor.similarity
            candidate_prediction = (
                sorted(votes.items(), key=lambda item: (-item[1], item[0]))[0][0]
                if votes and sum(votes.values()) > 0
                else None
            )
            closest_similarity = neighbors[0].similarity if neighbors else 0.0
            prediction = (
                candidate_prediction
                if closest_similarity >= fold_model.in_domain_threshold
                else None
            )
            correct = prediction == example.material_kind
            label_totals[example.material_kind] += 1
            if prediction is not None:
                holdout_predictions += 1
            if correct:
                holdout_correct += 1
                label_correct[example.material_kind] += 1
            holdout_rows.append(
                {
                    "material_id": example.material_id,
                    "expected_kind": example.material_kind,
                    "predicted_kind": prediction,
                    "correct": correct,
                    "closest_similarity": rounded(closest_similarity),
                    "in_domain_threshold": rounded(
                        fold_model.in_domain_threshold
                    ),
                    "closest_material_id": (
                        neighbors[0].example.material_id if neighbors else None
                    ),
                }
            )
        per_kind_recall = {
            label: label_correct[label] / count
            for label, count in sorted(label_totals.items())
        }
        macro_recall = sum(per_kind_recall.values()) / len(per_kind_recall)
        majority_count = max(label_totals.values())
        return {
            "schema_version": SCHEMA_VERSION,
            "benchmark_id": "material-composition-knn-leave-one-out-v1",
            "model": self.model_card(neighbor_count),
            "method": {
                "split": "leave-one-material-out",
                "neighbors": neighbor_count,
                "leakage_control": (
                    "the query material is excluded before IDF fitting and "
                    "neighbor search"
                ),
            },
            "sanity_check": {
                "name": "exact training-composition retrieval",
                "correct": exact_correct,
                "total": len(self.examples),
                "accuracy": rounded(exact_correct / len(self.examples)),
                "interpretation": (
                    "pipeline integrity only; not generalization evidence"
                ),
            },
            "holdout": {
                "correct": holdout_correct,
                "total": len(self.examples),
                "accuracy": rounded(holdout_correct / len(self.examples)),
                "macro_recall": rounded(macro_recall),
                "abstained": len(self.examples) - holdout_predictions,
                "coverage": rounded(holdout_predictions / len(self.examples)),
                "selective_accuracy": (
                    rounded(holdout_correct / holdout_predictions)
                    if holdout_predictions
                    else None
                ),
                "per_kind_recall": {
                    label: rounded(value) for label, value in per_kind_recall.items()
                },
                "majority_class_baseline_accuracy": rounded(
                    majority_count / len(self.examples)
                ),
                "rows": holdout_rows,
            },
            "conclusion": (
                "This benchmark verifies deterministic fitting and retrieval. Rare "
                "material kinds remain unvalidated until the reviewed database "
                "contains multiple independent examples per kind."
            ),
        }


def load_query(
    database: Path,
    name: str,
    specifications: list[str],
    basis: str,
) -> MaterialExample:
    if not specifications:
        raise DescriptorError("at least one --component is required")
    connection = connect_readonly(database)
    try:
        symbols = [row[0] for row in connection.execute("SELECT symbol FROM element")]
        parser = FormulaParser(symbols)
        species_rows = connection.execute(
            """
            SELECT cs.entity_id, entity.name, cs.formula
            FROM chemical_species AS cs
            JOIN entity ON entity.entity_id = cs.entity_id
            WHERE entity.lifecycle_state = 'active'
            ORDER BY cs.entity_id
            """
        ).fetchall()
        lookup: defaultdict[str, list[sqlite3.Row]] = defaultdict(list)
        for row in species_rows:
            for value in (row["entity_id"], row["name"], row["formula"]):
                lookup[value.casefold()].append(row)

        components = []
        amount_presence = []
        seen_component_keys: set[str] = set()
        for specification in specifications:
            token, separator, amount_text = specification.rpartition("=")
            if not separator:
                token = specification
                amount = None
            else:
                if not token or not amount_text:
                    raise DescriptorError(
                        f"invalid component specification {specification!r}"
                    )
                try:
                    amount = Fraction(amount_text)
                except (ValueError, ZeroDivisionError) as exception:
                    raise DescriptorError(
                        f"invalid exact fraction {amount_text!r}"
                    ) from exception
                if amount <= 0:
                    raise DescriptorError("component amounts must be positive")
            token = token.strip()
            matches = lookup.get(token.casefold(), [])
            unique_ids = {row["entity_id"] for row in matches}
            if len(unique_ids) > 1:
                raise DescriptorError(
                    f"component {token!r} is ambiguous; use a chem: species ID"
                )
            if matches:
                row = matches[0]
                element_rows = connection.execute(
                    """
                    SELECT element.symbol, se.atom_count
                    FROM species_element AS se
                    JOIN element ON element.entity_id = se.element_id
                    WHERE se.species_id = ?
                    ORDER BY element.atomic_number
                    """,
                    (row["entity_id"],),
                ).fetchall()
                elements = {item["symbol"]: item["atom_count"] for item in element_rows}
                if not elements:
                    raise DescriptorError(
                        f"reviewed species {row['entity_id']} has no elemental "
                        "composition"
                    )
                component = Component(
                    key=f"species:{row['entity_id']}",
                    label=row["name"],
                    formula=row["formula"],
                    elements=elements,
                    amount=amount,
                    basis=basis,
                    resolved_species_id=row["entity_id"],
                )
            else:
                elements = parser.parse(token)
                component = Component(
                    key=f"composition:{canonical_composition(elements)}",
                    label=token,
                    formula=token,
                    elements=elements,
                    amount=amount,
                    basis=basis,
                )
            if component.key in seen_component_keys:
                raise DescriptorError(f"duplicate component {token!r}")
            seen_component_keys.add(component.key)
            amount_presence.append(amount is not None)
            components.append(component)

        if any(amount_presence) != all(amount_presence):
            raise DescriptorError(
                "either every component or no component must have an amount"
            )
        if basis == "unspecified" and any(amount_presence):
            raise DescriptorError(
                "choose a quantitative --basis when component amounts are set"
            )
        if basis != "unspecified" and not all(amount_presence):
            raise DescriptorError(
                f"--basis {basis} requires an amount for every component"
            )
        return MaterialExample("query:unreviewed", name, "unknown", tuple(components))
    finally:
        connection.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Describe an unreviewed material from reviewed database analogies."
    )
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--name", default="unreviewed material")
    parser.add_argument(
        "--component",
        action="append",
        default=[],
        metavar="SPEC[=AMOUNT]",
        help="repeatable species ID/name/formula with optional exact fraction",
    )
    parser.add_argument(
        "--basis",
        choices=("unspecified", "mole_fraction", "mass_fraction", "volume_fraction"),
        default="unspecified",
    )
    parser.add_argument("--neighbors", type=int, default=DEFAULT_NEIGHBORS)
    parser.add_argument(
        "--evaluate",
        action="store_true",
        help="run the database-derived leave-one-out benchmark instead",
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    if arguments.neighbors <= 0:
        raise SystemExit("--neighbors must be positive")
    try:
        model = MaterialModel.load(arguments.database)
        if arguments.evaluate:
            result = model.evaluate(arguments.neighbors)
        else:
            query = load_query(
                arguments.database,
                arguments.name,
                arguments.component,
                arguments.basis,
            )
            result = model.describe(query, arguments.neighbors)
    except (DescriptorError, OSError, sqlite3.Error) as exception:
        raise SystemExit(f"error: {exception}") from exception
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
