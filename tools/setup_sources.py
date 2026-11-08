"""Verify reference sources and download missing PDFs from the private GitHub release.

Usage: python -X utf8 tools/setup_sources.py [--check]
Requires Python 3.9+; downloads also require an authenticated GitHub CLI (gh).
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def matches(path, record):
    return (path.is_file()
            and ("size" not in record or path.stat().st_size == record["size"])
            and sha256(path) == record["sha256"])


def prepare(root, check=False):
    wiki = root / "sources" / "zh.wikisource" / "封神演義"
    chapters = json.loads((wiki / "sources.json").read_text(encoding="utf-8"))["chapters"]
    if len(chapters) != 100 or {r["chapter"] for r in chapters} != set(range(1, 101)):
        raise ValueError("Wikisource manifest must contain chapters 001–100")
    bad = [r["file"] for r in chapters if not matches(wiki / r["file"], r)]
    if bad:
        raise ValueError("Wikisource missing or changed; restore from Git: " + ", ".join(bad))
    print("Wikisource: 100/100 verified", flush=True)

    directory = root / "sources" / "najda"
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    records = manifest["files"]
    if len(records) != 20 or {r["file"] for r in records} != {f"vol{n:02}.pdf" for n in range(1, 21)}:
        raise ValueError("PDF manifest must contain vol01.pdf–vol20.pdf")
    pending = [r for r in records if not matches(directory / r["file"], r)]
    print(f"PDFs: {len(records) - len(pending)}/20 verified", flush=True)
    if not pending:
        return 0
    if check:
        print("Missing or changed: " + ", ".join(r["file"] for r in pending))
        return 1
    gh = shutil.which("gh")
    if not gh:
        raise RuntimeError("Install GitHub CLI (https://cli.github.com/), then run: gh auth login")
    for record in pending:
        name = record["file"]
        print(f"Downloading {name} ...", flush=True)
        # Keep the existing file until the replacement has passed both checks.
        with tempfile.TemporaryDirectory(prefix="hong-sin-sources-") as temporary:
            result = subprocess.run(
                [gh, "release", "download", manifest["release"], "--repo", manifest["repository"],
                 "--pattern", name, "--dir", temporary],
                check=False,
            )
            if result.returncode:
                raise RuntimeError(
                    f"Download failed for {name}. Run gh auth login with an account that can access "
                    f"{manifest['repository']}, then retry. Verified files will be skipped."
                )
            downloaded = Path(temporary) / name
            if not matches(downloaded, record):
                raise ValueError(f"Size or SHA-256 mismatch for {name}; existing file preserved")
            staging = directory / (name + ".part")
            try:
                shutil.copyfile(downloaded, staging)
                staging.replace(directory / name)
            finally:
                staging.unlink(missing_ok=True)
        print(f"Verified {name}", flush=True)
    print("Ready: Wikisource 100/100 and PDFs 20/20 verified")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify only; do not download or change files")
    args = parser.parse_args()
    try:
        return prepare(ROOT, args.check)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
