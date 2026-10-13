"""Deterministic offline PubChem factual molecular graph staging import."""

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "sources" / "molecules"
SYMBOLS = (
    [""]
    + "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og".split()
)
LICENSE = "Only uncopyrightable factual chemical identities and numerical graph records; no third-party prose or annotations extracted."


def formula_counts(formula):
    tokens = re.findall(r"([A-Z][a-z]?)([0-9]*)", formula)
    if "".join(a + b for a, b in tokens) != formula:
        raise ValueError("Unsupported formula syntax")
    result = Counter()
    for symbol, count in tokens:
        if symbol not in SYMBOLS or (count and int(count) <= 0):
            raise ValueError("Invalid formula element/count")
        result[symbol] += int(count or 1)
    return result


def extract(compound, reference):
    if compound["id"]["id"]["cid"] != reference["cid"]:
        raise ValueError("CID mismatch")
    native = compound["atoms"]
    aids, elements = native["aid"], native["element"]
    if len(aids) != len(set(aids)) or len(aids) != len(elements):
        raise ValueError("Atom identifiers invalid")
    if any(not isinstance(z, int) or not 1 <= z <= 118 for z in elements):
        raise ValueError("Atomic number invalid")
    sparse = {}
    for key in ("charge", "isotope", "radical"):
        sparse[key] = {}
        for item in native.get(key, []):
            if item["aid"] not in aids or item["aid"] in sparse[key]:
                raise ValueError("Invalid sparse atom annotation")
            sparse[key][item["aid"]] = item["value"]
    atoms = [
        {
            "aid": aid,
            "z": z,
            "charge": sparse["charge"].get(aid, 0),
            "isotope": sparse["isotope"].get(aid),
            "radical": sparse["radical"].get(aid),
        }
        for aid, z in zip(aids, elements)
    ]
    if any(
        a["isotope"] is not None
        and (not isinstance(a["isotope"], int) or a["isotope"] < a["z"])
        for a in atoms
    ):
        raise ValueError("Invalid isotope mass number")
    formula = next(
        p["value"]["sval"]
        for p in compound["props"]
        if p["urn"].get("label") == "Molecular Formula"
    )
    counts = Counter(SYMBOLS[z] for z in elements)
    if counts != formula_counts(formula) or counts != formula_counts(
        reference["formula"]
    ):
        raise ValueError("Formula does not match explicit atom counts")
    charge = compound["charge"]
    if charge != reference["electric_charge"]:
        raise ValueError("Compound charge differs from reference")
    if sum(a["charge"] for a in atoms) != charge:
        raise ValueError("Atom charges do not sum to compound charge")
    bonds = []
    native_bonds = compound.get("bonds", {})
    arrays = [native_bonds.get(k, []) for k in ("aid1", "aid2", "order")]
    if len({len(x) for x in arrays}) != 1:
        raise ValueError("Bond array lengths mismatch")
    seen = set()
    for a, b, order in zip(*arrays):
        pair = tuple(sorted((a, b)))
        if (
            a not in aids
            or b not in aids
            or a == b
            or pair in seen
            or not isinstance(order, int)
            or order <= 0
        ):
            raise ValueError("Invalid bond endpoints/order")
        seen.add(pair)
        bonds.append((a, b, order))
    return {
        "formula": formula,
        "charge": charge,
        "atoms": atoms,
        "bonds": bonds,
        "native_graph": {
            k: compound[k]
            for k in ("atoms", "bonds", "stereo", "charge")
            if k in compound
        },
        "version": sorted(
            {p["urn"]["release"] for p in compound["props"] if "release" in p["urn"]}
        ),
    }


def build(output, source_dir=SOURCE_DIR):
    source_dir, output = Path(source_dir), Path(output)
    manifest = json.loads((source_dir / "manifest.json").read_text())
    records = []
    for ref in manifest["records"]:
        raw = (source_dir / ref["file"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != ref["sha256"]:
            raise ValueError("Source SHA256 mismatch: " + ref["file"])
        doc = json.loads(raw)
        if len(doc["PC_Compounds"]) != 1:
            raise ValueError("Expected one compound")
        records.append((ref, extract(doc["PC_Compounds"][0], ref)))
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + ".tmp")
    temp.unlink(missing_ok=True)
    with closing(sqlite3.connect(temp)) as db, db:
        db.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE unverified_molecular_source(source_id TEXT PRIMARY KEY,url TEXT NOT NULL,retrieved_at TEXT NOT NULL,version_json TEXT NOT NULL,response_sha256 TEXT NOT NULL,license TEXT NOT NULL,provenance_class TEXT NOT NULL);
        CREATE TABLE unverified_molecular_molecule(molecule_id TEXT PRIMARY KEY,source_id TEXT NOT NULL REFERENCES unverified_molecular_source,name TEXT NOT NULL,cid INTEGER NOT NULL,formula TEXT NOT NULL,electric_charge INTEGER NOT NULL,core_entity_id TEXT,core_mapping_status TEXT,review_status TEXT NOT NULL,native_graph_json TEXT NOT NULL);
        CREATE TABLE unverified_molecular_atom(molecule_id TEXT NOT NULL REFERENCES unverified_molecular_molecule,atom_id INTEGER NOT NULL,atomic_number INTEGER NOT NULL,isotope_mass_number INTEGER,formal_charge INTEGER NOT NULL,radical_native INTEGER,PRIMARY KEY(molecule_id,atom_id));
        CREATE TABLE unverified_molecular_bond(molecule_id TEXT NOT NULL,atom_id_1 INTEGER NOT NULL,atom_id_2 INTEGER NOT NULL,order_native INTEGER NOT NULL,FOREIGN KEY(molecule_id,atom_id_1) REFERENCES unverified_molecular_atom,FOREIGN KEY(molecule_id,atom_id_2) REFERENCES unverified_molecular_atom,PRIMARY KEY(molecule_id,atom_id_1,atom_id_2));
        CREATE TABLE unverified_molecular_gap(molecule_id TEXT NOT NULL REFERENCES unverified_molecular_molecule,field TEXT NOT NULL,reason TEXT NOT NULL);
        CREATE TABLE unverified_molecular_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        """)
        for ref, rec in records:
            mid = ref["id"]
            db.execute(
                "INSERT INTO unverified_molecular_source VALUES(?,?,?,?,?,?,?)",
                (
                    mid,
                    f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{ref['cid']}/JSON?record_type=2d",
                    manifest["retrieved_at"],
                    json.dumps(rec["version"]),
                    ref["sha256"],
                    LICENSE,
                    "curated",
                ),
            )
            db.execute(
                "INSERT INTO unverified_molecular_molecule VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    mid,
                    mid,
                    ref["name"],
                    ref["cid"],
                    rec["formula"],
                    rec["charge"],
                    ref.get("core_entity_id"),
                    ref.get("core_mapping_status"),
                    "pending_human_review",
                    json.dumps(
                        rec["native_graph"], sort_keys=True, separators=(",", ":")
                    ),
                ),
            )
            db.executemany(
                "INSERT INTO unverified_molecular_atom VALUES(?,?,?,?,?,?)",
                [
                    (mid, a["aid"], a["z"], a["isotope"], a["charge"], a["radical"])
                    for a in rec["atoms"]
                ],
            )
            db.executemany(
                "INSERT INTO unverified_molecular_bond VALUES(?,?,?,?)",
                [(mid, *b) for b in rec["bonds"]],
            )
            db.execute(
                "INSERT INTO unverified_molecular_gap VALUES(?,?,?)",
                (
                    mid,
                    "experimental_geometry",
                    "2D depiction coordinates omitted; no measured geometry imported",
                ),
            )
        db.executemany(
            "INSERT INTO unverified_molecular_metadata VALUES(?,?)",
            [
                ("schema_version", "1"),
                ("transformation", "scripts/build_molecular_evidence.py"),
                ("status", "unverified source-backed factual graph identities"),
            ],
        )
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Foreign key failure")
    db.close()
    temp.replace(output)
    output.with_suffix(output.suffix + ".sha256").write_text(
        hashlib.sha256(output.read_bytes()).hexdigest() + "  " + output.name + "\n"
    )
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "molecules.db")
    args = parser.parse_args()
    print(build(args.output))
