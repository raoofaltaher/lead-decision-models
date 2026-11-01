import argparse
import json
import re
from pathlib import Path

OPENING = re.compile(r"^(~~~|```)\s*python\s*$")


def normalize(code: str) -> str:
    lines = [line.rstrip() for line in code.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def python_blocks(mdx: Path) -> list[tuple[int, str]]:
    lines = Path(mdx).read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    blocks, current, start, fence = [], None, 0, ""
    for number, line in enumerate(lines, 1):
        if current is None:
            match = OPENING.match(line.strip())
            if match:
                current, start, fence = [], number, match.group(1)
        elif line.strip() == fence:
            blocks.append((start, "\n".join(current)))
            current = None
        else:
            current.append(line)
    return blocks


def notebook_cells(notebook: Path) -> list[str]:
    data = json.loads(Path(notebook).read_text(encoding="utf-8"))
    cells = []
    for cell in data.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        source = cell.get("source", "")
        cells.append("".join(source) if isinstance(source, list) else source)
    return cells


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check that every tutorial Python block equals a notebook cell.")
    parser.add_argument("--mdx", nargs="+", required=True, type=Path)
    parser.add_argument("--notebooks", nargs="+", required=True, type=Path)
    args = parser.parse_args(argv)

    cells = {normalize(cell) for notebook in args.notebooks for cell in notebook_cells(notebook)}
    missing = [
        f"{mdx}:{line}"
        for mdx in args.mdx
        for line, code in python_blocks(mdx)
        if normalize(code) not in cells
    ]
    for location in missing:
        print(f"NO MATCHING CELL {location}")
    print(f"{len(missing)} unmatched block(s)")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
