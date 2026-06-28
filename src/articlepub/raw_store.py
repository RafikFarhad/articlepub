from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class RawArtifact:
    path: str
    label: str
    content_type: str
    metadata: dict[str, Any] = field(default_factory=dict)


class RawStore:
    def __init__(self, output_dir: Path, enabled: bool) -> None:
        self.output_dir = output_dir
        self.raw_dir = output_dir / ".raw"
        self.enabled = enabled
        self._counter = 0
        self._artifacts: list[RawArtifact] = []

        if self.raw_dir.exists():
            shutil.rmtree(self.raw_dir)
        if self.enabled:
            self.raw_dir.mkdir(parents=True, exist_ok=True)
            self._write_manifest()

    def write_text(
        self,
        label: str,
        extension: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        content_type: str = "text/plain",
    ) -> Path | None:
        if not self.enabled:
            return None
        path = self._next_path(label, extension)
        path.write_text(content, encoding="utf-8")
        self._add_artifact(path, label, content_type, metadata)
        return path

    def write_json(self, label: str, content: Any, metadata: dict[str, Any] | None = None) -> Path | None:
        if not self.enabled:
            return None
        path = self._next_path(label, "json")
        path.write_text(json.dumps(content, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        self._add_artifact(path, label, "application/json", metadata)
        return path

    def _next_path(self, label: str, extension: str) -> Path:
        self._counter += 1
        suffix = extension.lstrip(".")
        return self.raw_dir / f"{self._counter:03d}-{_slug(label)}.{suffix}"

    def _add_artifact(
        self,
        path: Path,
        label: str,
        content_type: str,
        metadata: dict[str, Any] | None,
    ) -> None:
        self._artifacts.append(
            RawArtifact(
                path=path.name,
                label=label,
                content_type=content_type,
                metadata=metadata or {},
            )
        )
        self._write_manifest()

    def _write_manifest(self) -> None:
        manifest = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "artifacts": [asdict(artifact) for artifact in self._artifacts],
        }
        (self.raw_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )


def _slug(value: str) -> str:
    out = []
    for char in value.lower():
        if char.isalnum():
            out.append(char)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-") or "artifact"
