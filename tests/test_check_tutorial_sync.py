import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import check_tutorial_sync

MDX = """---
title: Example
---

Intro.

~~~python
import pandas as pd
print(pd.__version__)
~~~

Text between.

~~~python
total = 1 + 1
~~~

~~~bash
echo not python
~~~
"""


def write_notebook(path, cells):
    notebook = {
        "cells": [{"cell_type": "code", "metadata": {}, "source": source, "outputs": [], "execution_count": None} for source in cells],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.write_text(json.dumps(notebook), encoding="utf-8")


def test_python_blocks_returns_start_lines_and_code(tmp_path):
    mdx = tmp_path / "page.mdx"
    mdx.write_text(MDX, encoding="utf-8")

    blocks = check_tutorial_sync.python_blocks(mdx)

    assert [line for line, _ in blocks] == [7, 14]
    assert blocks[1][1] == "total = 1 + 1"


def test_identical_block_passes(tmp_path):
    mdx = tmp_path / "page.mdx"
    mdx.write_text(MDX, encoding="utf-8")
    notebook = tmp_path / "nb.ipynb"
    write_notebook(notebook, ["import pandas as pd\nprint(pd.__version__)", "total = 1 + 1\n"])

    assert check_tutorial_sync.main(["--mdx", str(mdx), "--notebooks", str(notebook)]) == 0


def test_crlf_and_trailing_space_are_ignored(tmp_path):
    mdx = tmp_path / "page.mdx"
    mdx.write_bytes(MDX.replace("\n", "\r\n").encode("utf-8"))
    notebook = tmp_path / "nb.ipynb"
    write_notebook(notebook, ["import pandas as pd   \nprint(pd.__version__)\n\n", "total = 1 + 1"])

    assert check_tutorial_sync.main(["--mdx", str(mdx), "--notebooks", str(notebook)]) == 0


def test_changed_block_is_reported_with_line_number(tmp_path, capsys):
    mdx = tmp_path / "page.mdx"
    mdx.write_text(MDX, encoding="utf-8")
    notebook = tmp_path / "nb.ipynb"
    write_notebook(notebook, ["import pandas as pd\nprint(pd.__version__)", "total = 1 + 2"])

    assert check_tutorial_sync.main(["--mdx", str(mdx), "--notebooks", str(notebook)]) == 1
    assert f"{mdx}:14" in capsys.readouterr().out


def test_notebook_source_as_list_of_lines_is_read(tmp_path):
    notebook = tmp_path / "nb.ipynb"
    write_notebook(notebook, [["a = 1\n", "b = 2\n"]])

    assert check_tutorial_sync.notebook_cells(notebook) == ["a = 1\nb = 2\n"]
