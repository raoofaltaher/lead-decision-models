import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import check_unsloth_pin

FILES = ("decision.py", "_decision_common.py")


def make_folder(root, name, contents):
    folder = root / name
    folder.mkdir()
    for file in FILES:
        (folder / file).write_text(contents[file], encoding="utf-8")
    return folder


def run(installed, reference):
    return check_unsloth_pin.main(
        [
            "--commit",
            "0000000",
            "--installed-dir",
            str(installed),
            "--reference-dir",
            str(reference),
        ]
    )


def test_match_returns_zero(tmp_path, capsys):
    contents = {"decision.py": "a = 1\n", "_decision_common.py": "b = 2\n"}
    installed = make_folder(tmp_path, "installed", contents)
    reference = make_folder(tmp_path, "reference", contents)

    assert run(installed, reference) == 0
    assert capsys.readouterr().out.count("MATCH") == 2


def test_mismatch_is_reported(tmp_path, capsys):
    installed = make_folder(
        tmp_path, "installed", {"decision.py": "a = 1\n", "_decision_common.py": "b = 2\n"}
    )
    reference = make_folder(
        tmp_path, "reference", {"decision.py": "a = 9\n", "_decision_common.py": "b = 2\n"}
    )

    assert run(installed, reference) == 1
    output = capsys.readouterr().out
    assert "DIFF decision.py" in output
    assert "MATCH _decision_common.py" in output


def test_file_sha256_matches_hashlib(tmp_path):
    path = tmp_path / "sample.py"
    path.write_bytes(b"print('decision')\n")

    assert check_unsloth_pin.file_sha256(path) == hashlib.sha256(b"print('decision')\n").hexdigest()
