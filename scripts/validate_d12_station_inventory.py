"""Compare the local D12 I-5 observations with the supplied PeMS I-5N inventory."""

from __future__ import annotations

import gzip
import json
import csv
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed/d12_i5_2026-01_to_2026-09"
INVENTORIES = {
    "N": ROOT / "pems_output_stations_I5N.xlsx",
    "S": ROOT / "southbound_stations.xlsx",
}
OUT = ROOT / "reports/eda/overview/station_inventory_validation.csv"
NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def read_inventory(path: Path) -> list[dict[str, str]]:
    with ZipFile(path) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        targets = {x.attrib["Id"]: x.attrib["Target"] for x in rels}
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            strings = ET.fromstring(z.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in si.findall(".//m:t", NS)) for si in strings]
        sheet = wb.find("m:sheets/m:sheet", NS)
        rel_id = sheet.attrib[f"{{{NS['r']}}}id"]
        target = targets[rel_id].lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        root = ET.fromstring(z.read(target))
        rows = root.findall(".//m:sheetData/m:row", NS)
        matrix = []
        for row in rows:
            values = {}
            for cell in row.findall("m:c", NS):
                col = re.match(r"[A-Z]+", cell.attrib["r"]).group()
                value = cell.find("m:v", NS)
                text = value.text if value is not None else ""
                if cell.attrib.get("t") == "s" and text:
                    text = shared[int(text)]
                elif cell.attrib.get("t") == "inlineStr":
                    text = "".join(t.text or "" for t in cell.findall(".//m:t", NS))
                values[col] = text
            matrix.append(values)
    headers = matrix[0]
    return [
        {headers[col]: row.get(col, "") for col in headers}
        for row in matrix[1:]
    ]


def main() -> None:
    inventories = {direction: [
        r for r in read_inventory(path)
        if r.get("District") == "12" and r.get("Fwy") == f"I5-{direction}"
    ] for direction, path in INVENTORIES.items()}
    observed = {"N": set(), "S": set()}
    for path in sorted(DATA.glob("i5_d12_station_5min_*.csv.gz")):
        with gzip.open(path, "rb") as f:
            next(f, None)  # header
            for line in f:
                fields = line.split(b",", 5)
                if len(fields) > 4:
                    direction = fields[4].decode("ascii")
                    if direction in observed:
                        observed[direction].add(fields[1].decode("ascii"))

    output = []
    for direction in ("N", "S"):
        ids = observed[direction]
        inv = inventories[direction]
        inventory_ids = {r["ID"] for r in inv}
        missing = ids - inventory_ids
        unused = inventory_ids - ids
        for r in inv:
            sid = r["ID"]
            output.append({
                "direction": direction,
                "station_id": sid,
                "in_observations_2026_jan_sep": sid in ids,
                "in_supplied_pems_inventory": True,
                "district": r.get("District", ""),
                "freeway": "5",
                "county": r.get("County", ""),
                "city": r.get("City", ""),
                "postmile_ca": r.get("CA PM", ""),
                "postmile_absolute": r.get("Abs PM", ""),
                "station_name": r.get("Name", ""),
                "station_type": r.get("Type", ""),
                "hov": r.get("HOV", ""),
                "metadata_scope": f"station-level from supplied {direction} inventory",
                "validation": "match" if sid in ids else "inventory_only",
            })
        for sid in sorted(missing):
            output.append({"direction": direction, "station_id": sid,
                           "in_observations_2026_jan_sep": True,
                           "in_supplied_pems_inventory": False,
                           "district": "12", "freeway": "5",
                           "metadata_scope": f"route-level only; station-level {direction} metadata missing",
                           "validation": "observation_only"})
        print(f"{direction} observed={len(ids)} inventory_d12={len(inventory_ids)} "
              f"matched={len(ids & inventory_ids)} observation_only={len(missing)} "
              f"inventory_only={len(unused)}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fields = ["direction", "station_id", "in_observations_2026_jan_sep",
              "in_supplied_pems_inventory", "district", "freeway", "county", "city",
              "postmile_ca", "postmile_absolute", "station_name", "station_type",
              "hov", "metadata_scope", "validation"]
    with OUT.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output)
    print(f"wrote {OUT.relative_to(ROOT)} ({len(output)} rows)")


if __name__ == "__main__":
    main()
