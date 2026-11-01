import argparse
import hashlib
import tempfile
import urllib.request
from pathlib import Path

FILES = ("decision.py", "_decision_common.py")
RAW_URL = "https://raw.githubusercontent.com/unslothai/unsloth/{commit}/unsloth/models/{file}"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def installed_models_dir() -> Path:
    import importlib.util

    spec = importlib.util.find_spec("unsloth")
    if spec is None or not spec.submodule_search_locations:
        raise SystemExit("unsloth is not installed in this environment")
    return Path(next(iter(spec.submodule_search_locations))) / "models"


def download_reference(commit: str, folder: Path) -> Path:
    for file in FILES:
        with urllib.request.urlopen(RAW_URL.format(commit=commit, file=file), timeout=60) as response:
            (folder / file).write_bytes(response.read())
    return folder


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare the installed Unsloth decision code with a commit.")
    parser.add_argument("--commit", required=True)
    parser.add_argument("--installed-dir", type=Path)
    parser.add_argument("--reference-dir", type=Path)
    args = parser.parse_args(argv)

    installed = args.installed_dir or installed_models_dir()
    with tempfile.TemporaryDirectory() as scratch:
        reference = args.reference_dir or download_reference(args.commit, Path(scratch))
        mismatches = 0
        for file in FILES:
            if file_sha256(installed / file) == file_sha256(reference / file):
                print(f"MATCH {file}")
            else:
                print(f"DIFF {file}")
                mismatches += 1
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
