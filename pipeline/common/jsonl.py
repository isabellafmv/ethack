"""Append-only JSONL. The source of truth.

One file per puller per run, timestamped, never edited in place. The database
is a derived artifact that can always be thrown away and rebuilt from these
files; these files cannot be rebuilt from anything.

Why append-only: at hour 18 someone will ask "did that number change, or did
we always have it wrong". With an append-only log, that is answerable.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .paths import OBSERVATIONS
from .schema import Observation, SCHEMA_VERSION, SchemaError, validate


def run_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


class ObservationWriter:
    """Validates at write time. A bad record never reaches disk.

        with ObservationWriter("S09") as w:
            w.write(obs)
            w.write(obs2, source_text=filing_text)   # quote checked mechanically
    """

    def __init__(self, source: str, run: str | None = None, base=None):
        self.source = source
        self.run = run or run_stamp()
        self.dir = (base or OBSERVATIONS) / source
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / f"{self.run}.jsonl"
        self._fh = None
        self.counts: dict[str, int] = {}
        self.rejected: list[tuple[str, str, str]] = []

    def __enter__(self) -> "ObservationWriter":
        self._fh = self.path.open("a", encoding="utf-8")
        return self

    def __exit__(self, *exc) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None

    def write(self, obs: Observation, *, source_text: str | None = None) -> Observation | None:
        if obs.source != self.source:
            raise SchemaError(
                f"writer for {self.source} got a record claiming source={obs.source}. "
                f"A source package writes only its own records."
            )
        try:
            obs = validate(obs, source_text=source_text)
        except SchemaError as e:
            # Rejected records are reported, never silently dropped: silent
            # partial failure is failure mode #1 in the plan doc.
            self.rejected.append((obs.ticker, obs.field, str(e)))
            return None

        payload = json.loads(obs.to_json())
        payload["schema_version"] = SCHEMA_VERSION
        payload["run"] = self.run
        self._fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        self.counts[obs.status.value] = self.counts.get(obs.status.value, 0) + 1
        return obs

    def summary(self) -> str:
        wrote = sum(self.counts.values())
        bits = ", ".join(f"{k}={v}" for k, v in sorted(self.counts.items()))
        line = f"[{self.source}] wrote {wrote} records to {self.path.name} ({bits or 'none'})"
        if self.rejected:
            line += f"\n  REJECTED {len(self.rejected)}:"
            for t, f, err in self.rejected[:5]:
                line += f"\n    {t}/{f}: {err}"
            if len(self.rejected) > 5:
                line += f"\n    ... and {len(self.rejected) - 5} more"
        return line


def read_jsonl(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path.name}:{n} is not valid JSON: {e}") from e


def all_runs(source: str | None = None, base=None) -> list[Path]:
    """Every JSONL file, oldest first. Later runs win on key collision."""
    root = (base or OBSERVATIONS)
    root = root / source if source else root
    if not root.exists():
        return []
    files = sorted(root.rglob("*.jsonl"))
    if base is None:
        # TEST-prefixed runs are fixtures. They may live in a temp log (where
        # the test suite puts them) but must never reach the real database.
        files = [p for p in files if not p.name.startswith("TEST")]
    return files
