#!/usr/bin/env python3
from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

import pytest

from py3createtorrent import TorrentSpec, create_torrent


def test_comment(sample_file: Path, tmp_path: Path) -> None:
    spec = TorrentSpec(target=sample_file, output=tmp_path, comment="my_comment")
    _, metainfo, _ = create_torrent(spec)
    assert metainfo.get("comment") == "my_comment"


def test_created_by_disabled(sample_file: Path, tmp_path: Path) -> None:
    spec = TorrentSpec(target=sample_file, output=tmp_path, created_by=False)
    _, metainfo, _ = create_torrent(spec)
    assert "created by" not in metainfo


def test_custom_name(sample_file: Path, tmp_path: Path) -> None:
    spec = TorrentSpec(target=sample_file, output=tmp_path, name="custom_release")
    output_path, metainfo, _ = create_torrent(spec)
    assert metainfo["info"]["name"] == "custom_release"
    assert output_path.name == "custom_release.torrent"

    invalid_spec = TorrentSpec(target=sample_file, output=tmp_path, name="bad/name")
    with pytest.raises(ValueError, match="Invalid name"):
        create_torrent(invalid_spec)


def test_date(sample_file: Path, tmp_path: Path) -> None:
    spec = TorrentSpec(target=sample_file, output=tmp_path, date=1337)
    _, metainfo, _ = create_torrent(spec)
    assert metainfo.get("creation date") == 1337


def test_date_disabled(sample_file: Path, tmp_path: Path) -> None:
    spec = TorrentSpec(target=sample_file, output=tmp_path, date=-2)
    _, metainfo, _ = create_torrent(spec)
    assert "creation date" not in metainfo


def test_date_invalid(sample_file: Path, tmp_path: Path) -> None:
    spec = TorrentSpec(target=sample_file, output=tmp_path, date=-3)
    with pytest.raises(ValueError, match="Invalid date"):
        create_torrent(spec)


def test_node(sample_file: Path, tmp_path: Path) -> None:
    spec = TorrentSpec(target=sample_file, output=tmp_path, nodes=["host,1337"])
    _, metainfo, _ = create_torrent(spec)
    assert metainfo.get("nodes") == [["host", 1337]]


@pytest.mark.parametrize(
    ("private", "nodes", "expectation"),
    [
        pytest.param(True, ["host,123"], pytest.raises(ValueError, match="private torrent"), id="private_with_nodes"),
        pytest.param(False, ["invalid_node_spec"], pytest.raises(ValueError, match="Invalid format"), id="bad_format"),
        pytest.param(False, ["host,abc"], pytest.raises(ValueError, match="Invalid port number"), id="non_numeric"),
        pytest.param(False, ["host,0"], pytest.raises(ValueError, match="Port number out of range"), id="port_low"),
        pytest.param(
            False, ["host,65536"], pytest.raises(ValueError, match="Port number out of range"), id="port_high"
        ),
    ],
)
def test_nodes_invalid(
    sample_file: Path,
    tmp_path: Path,
    private: bool,
    nodes: list[str],
    expectation: AbstractContextManager[Any],
) -> None:
    spec = TorrentSpec(target=sample_file, private=private, nodes=nodes, output=tmp_path)
    with expectation:
        create_torrent(spec)


@pytest.mark.parametrize("piece_length", [15, 17, -1])
def test_piece_length_invalid(sample_file: Path, tmp_path: Path, piece_length: int) -> None:
    spec = TorrentSpec(target=sample_file, output=tmp_path, piece_length=piece_length)
    with pytest.raises(ValueError, match="Piece length"):
        create_torrent(spec)


def test_private(sample_file: Path, tmp_path: Path) -> None:
    spec = TorrentSpec(target=sample_file, output=tmp_path, private=True)
    _, metainfo, _ = create_torrent(spec)
    assert metainfo["info"].get("private") == 1


def test_source(sample_file: Path, tmp_path: Path) -> None:
    spec = TorrentSpec(target=sample_file, output=tmp_path, source="my_source")
    _, metainfo, _ = create_torrent(spec)
    assert metainfo["info"].get("source") == "my_source"

    invalid_spec = TorrentSpec(target=sample_file, output=tmp_path, source="%")
    with pytest.raises(ValueError, match="Invalid source"):
        create_torrent(invalid_spec)


def test_target_does_not_exist(testdata_dir: Path, tmp_path: Path) -> None:
    spec = TorrentSpec(testdata_dir / "non_existent_folder", output=tmp_path)
    with pytest.raises(FileNotFoundError):
        create_torrent(spec)


def test_target_empty(empty_folder: Path, tmp_path: Path) -> None:
    spec = TorrentSpec(empty_folder, output=tmp_path)
    with pytest.raises(ValueError, match="Cannot create torrent for 0-byte data"):
        create_torrent(spec)
