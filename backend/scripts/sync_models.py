from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import MODEL_FILENAMES, MODELS_DIR, RESEARCH_MODELS_DIR


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    assert RESEARCH_MODELS_DIR.is_dir(), f"Missing {RESEARCH_MODELS_DIR}"
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    # Safety: we only ever read from research/ and write into backend/models.
    assert not MODELS_DIR.resolve().is_relative_to(RESEARCH_MODELS_DIR.resolve())

    manifest = {
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "source": str(RESEARCH_MODELS_DIR),
        "models": {},
    }
    for model_name, filename in MODEL_FILENAMES.items():
        source = RESEARCH_MODELS_DIR / filename  # final all-data models, not holdout_2026
        assert source.is_file(), f"Missing research artifact: {source}"
        destination = MODELS_DIR / filename
        shutil.copy2(source, destination)
        manifest["models"][model_name] = {
            "file": filename,
            "sha256": sha256(destination),
            "size_bytes": destination.stat().st_size,
        }
        print(f"Synced {model_name}: {filename}")

    manifest_path = MODELS_DIR / "sync_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Wrote {manifest_path}")


if __name__ == "__main__":
    main()
