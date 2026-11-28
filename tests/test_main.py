#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

import pytest

from py3createtorrent import main


def test_main_summary_output(sample_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main([str(sample_file), "--output", str(tmp_path)])
    captured = capsys.readouterr()

    expected_outputs = [
        "Successfully created torrent:",
        "Name:",
        "Protocol:",
        "Size:",
        "Pieces:",
        "Comment:",
        "Private:",
        "Creation date:",
        "DHT bootstrap nodes:",
        "Webseeds:",
        "Primary tracker:",
        "Backup trackers:",
    ]
    for expected in expected_outputs:
        assert expected in captured.out, f"CLI stdout is missing '{expected}'"


def test_main_exits_on_missing_target(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.dat"
    with pytest.raises(SystemExit) as exc_info:
        main([str(missing), "--output", str(tmp_path)])
    assert exc_info.value.code == 1
