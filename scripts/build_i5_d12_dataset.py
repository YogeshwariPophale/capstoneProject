#!/usr/bin/env python3
"""Filter daily PeMS D12 5-minute text exports to I-5, preserving all columns.

Inputs are left untouched. Parallel workers write daily gzip members, which are
assembled in date order into monthly gzip CSVs with a manifest. Stdlib only.
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import shutil
import tempfile
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

BASE_COLUMNS = [
    "timestamp", "station_id", "district", "freeway", "direction", "lane_type",
    "station_length", "samples", "percent_observed", "total_flow",
    "avg_occupancy", "avg_speed",
]
LANE_COLUMNS = [f"lane_{n}_{field}" for n in range(1, 11)
                for field in ("samples", "flow", "avg_occupancy", "avg_speed")]
COLUMNS = BASE_COLUMNS + LANE_COLUMNS
DATE_RE = re.compile(r"_(\d{4})_(\d{2})_(\d{2})\.txt$")


def process_one(task: tuple[str, str, int, int]) -> dict:
    src_name, temp_name, district, freeway = task
    src_path, temp_path = Path(src_name), Path(temp_name)
    counts = Counter()
    by_direction, by_lane_type, by_station = Counter(), Counter(), Counter()
    malformed = []
    with src_path.open("rb") as src, gzip.open(temp_path, "wb", compresslevel=1) as dst:
        for line_no, line in enumerate(src, 1):
            counts["input_rows"] += 1
            fields = line.rstrip(b"\r\n").split(b",")
            if len(fields) != len(COLUMNS):
                counts["malformed_rows"] += 1
                if len(malformed) < 10:
                    malformed.append({"line": line_no, "field_count": len(fields)})
                continue
            if fields[2].strip() != str(district).encode("ascii") or fields[3].strip() != str(freeway).encode("ascii"):
                continue
            direction = fields[4].strip().upper()
            if direction not in {b"N", b"S"}:
                continue
            dst.write(b",".join(fields) + b"\n")
            counts["i5_rows"] += 1
            by_direction[direction.decode("ascii")] += 1
            by_lane_type[fields[5].strip().decode("ascii", errors="replace")] += 1
            by_station[fields[1].strip().decode("ascii", errors="replace")] += 1
    return {"file": src_path.name, "bytes": src_path.stat().st_size, "counts": dict(counts),
            "by_direction": dict(by_direction), "by_lane_type": dict(by_lane_type),
            "by_station": dict(by_station), "malformed_examples": malformed,
            "temp_file": str(temp_path)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--district", type=int, default=12)
    ap.add_argument("--freeway", type=int, default=5)
    ap.add_argument("--start", default="2026-01-01")
    ap.add_argument("--end", default="2026-09-30")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    files = []
    for path in sorted(args.input.glob("*.txt")):
        match = DATE_RE.search(path.name)
        if match:
            day = date(*(int(v) for v in match.groups()))
            if start <= day <= end:
                files.append((day, path))
    if not files:
        raise SystemExit(f"No dated .txt inputs found in {args.input}")
    args.output.mkdir(parents=True, exist_ok=True)
    # A repeat run replaces only the monthly files generated for this requested window.
    for month in sorted({day.strftime("%Y-%m") for day, _ in files}):
        stale = args.output / f"i5_d{args.district:02d}_station_5min_{month}.csv.gz"
        if stale.exists():
            stale.unlink()
    all_results = []
    with tempfile.TemporaryDirectory(prefix="i5_d12_work_", dir=args.output) as temp_root:
        temp_root = Path(temp_root)
        tasks = [(str(path), str(temp_root / f"{day.isoformat()}.gz"), args.district, args.freeway)
                 for day, path in files]
        with ProcessPoolExecutor(max_workers=max(1, args.workers)) as executor:
            futures = {executor.submit(process_one, task): task for task in tasks}
            completed = 0
            for future in as_completed(futures):
                result = future.result()
                all_results.append(result)
                completed += 1
                print(f"processed {completed}/{len(files)} {result['file']} "
                      f"input={result['counts'].get('input_rows', 0)} "
                      f"I5={result['counts'].get('i5_rows', 0)}", flush=True)
        results_by_name = {r["file"]: r for r in all_results}
        for day, source_path in files:
            result = results_by_name[source_path.name]
            month = day.strftime("%Y-%m")
            out_path = args.output / f"i5_d{args.district:02d}_station_5min_{month}.csv.gz"
            if not out_path.exists():
                with gzip.open(out_path, "wb", compresslevel=1) as out:
                    out.write((",".join(COLUMNS) + "\n").encode("ascii"))
            with out_path.open("ab") as out, Path(result["temp_file"]).open("rb") as member:
                shutil.copyfileobj(member, out, length=1024 * 1024)
    # The temp folder is removed after monthly gzip members have been assembled.
    by_day, by_month, by_direction, by_lane_type, by_station = {}, Counter(), Counter(), Counter(), Counter()
    totals = Counter()
    malformed_examples = []
    source_records = []
    for day, path in files:
        result = results_by_name[path.name]
        counts = result["counts"]
        by_day[day.isoformat()] = counts
        totals.update(counts)
        by_month[day.strftime("%Y-%m")] += counts.get("i5_rows", 0)
        by_direction.update(result["by_direction"])
        by_lane_type.update(result["by_lane_type"])
        by_station.update(result["by_station"])
        for sample in result["malformed_examples"]:
            if len(malformed_examples) < 100:
                malformed_examples.append({"file": path.name, **sample})
        source_records.append({"file": path.name, "date": day.isoformat(), "bytes": result["bytes"],
                               "rows": counts.get("input_rows", 0), "i5_rows": counts.get("i5_rows", 0)})
    expected_days, present = [], {day for day, _ in files}
    current = start
    while current <= end:
        expected_days.append(current)
        current += timedelta(days=1)
    output_files = [{"file": p.name, "bytes": p.stat().st_size} for p in sorted(args.output.glob("*.csv.gz"))]
    manifest = {
        "dataset": "Caltrans PeMS Station 5-Minute, filtered to I-5 District 12",
        "created_local_date": date.today().isoformat(),
        "scope": {"district": args.district, "freeway": args.freeway, "directions": ["N", "S"],
                  "start": start.isoformat(), "end": end.isoformat(), "lane_types": "all retained"},
        "filter": f"district == {args.district} AND freeway == {args.freeway} AND direction in {{N,S}}; all lane types retained",
        "schema": {"field_count": len(COLUMNS), "columns": COLUMNS, "header_added": True,
                   "input_has_header": False, "delimiter": ","},
        "source": {"input_directory": str(args.input), "files_found": len(files), "files": source_records,
                   "days_expected": len(expected_days), "days_present": len(present),
                   "missing_dates": [d.isoformat() for d in expected_days if d not in present]},
        "counts": {"input_rows": totals["input_rows"], "i5_rows": totals["i5_rows"],
                   "malformed_rows": totals["malformed_rows"], "by_day": by_day,
                   "i5_rows_by_month": dict(sorted(by_month.items())),
                   "i5_rows_by_direction": dict(sorted(by_direction.items())),
                   "i5_rows_by_lane_type": dict(sorted(by_lane_type.items())),
                   "unique_station_ids": len(by_station), "i5_rows_by_station": dict(sorted(by_station.items()))},
        "malformed_examples_capped_at_100": malformed_examples,
        "outputs": output_files,
        "processing_notes": ["Source files were not modified.", "Output is gzip-compressed CSV, not Excel.",
                             "All 52 fields are retained; header names identify ten lane groups.",
                             "Monthly files contain concatenated valid gzip members in date order.",
                             "Missing dates reflect the provided folder only and are not proof that PeMS lacks those dates."],
    }
    manifest_path = args.output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"DONE files={len(files)} input_rows={totals['input_rows']} I5_rows={totals['i5_rows']} "
          f"malformed={totals['malformed_rows']} stations={len(by_station)} manifest={manifest_path}", flush=True)


if __name__ == "__main__":
    main()
