#!/usr/bin/env python3
from __future__ import annotations

import logging
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

import pytest

from py3createtorrent import ProtocolVersion, TorrentSpec, create_torrent


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


def _included_rel_paths(metainfo: dict[str, Any]) -> set[str]:
    # Extract POSIX-style relative paths from v1 metainfo['info']['files']
    return {"/".join(entry["path"]) for entry in metainfo["info"]["files"]}


def test_exclude_explicit_paths(exclude_test_folder: Path, tmp_path: Path) -> None:
    spec = TorrentSpec(
        target=exclude_test_folder,
        output=tmp_path,
        protocol=ProtocolVersion.V1,
        exclude=[
            exclude_test_folder / "ignore_me.tmp",
            exclude_test_folder / "sub",
        ],
    )
    _, metainfo, _ = create_torrent(spec)
    assert _included_rel_paths(metainfo) == {"keep.txt", "README.MD"}


def test_exclude_target_itself_raises(exclude_test_folder: Path, tmp_path: Path) -> None:
    spec = TorrentSpec(
        target=exclude_test_folder,
        output=tmp_path,
        exclude=[exclude_test_folder],
    )
    with pytest.raises(ValueError, match="Cannot exclude the target directory itself"):
        create_torrent(spec)


def test_exclude_non_existent_path_logs_warning(
    exclude_test_folder: Path,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    missing_path = exclude_test_folder / "does_not_exist.txt"
    spec = TorrentSpec(
        target=exclude_test_folder,
        output=tmp_path,
        exclude=[missing_path],
    )

    with caplog.at_level(logging.WARNING):
        create_torrent(spec)

    assert "excluding a path that does not exist" in caplog.text


def test_exclude_on_single_file_target_logs_warning(
    sample_file: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    spec = TorrentSpec(
        target=sample_file, output=tmp_path, exclude=[sample_file.parent / "any_exclude_not_matchin_target.txt"]
    )

    with caplog.at_level(logging.WARNING):
        create_torrent(spec)

    assert "not possible when creating a torrent for a single file" in caplog.text


def test_exclude_pattern_case_sensitive(exclude_test_folder: Path, tmp_path: Path) -> None:
    spec = TorrentSpec(
        target=exclude_test_folder,
        output=tmp_path,
        protocol=ProtocolVersion.V1,
        # Lowercase '.md$' must NOT match 'README.MD'
        exclude_pattern=[r"\.tmp$", r"^sub/", r"\.md$"],
    )
    _, metainfo, _ = create_torrent(spec)
    assert _included_rel_paths(metainfo) == {"keep.txt", "README.MD"}


def test_exclude_pattern_case_insensitive(exclude_test_folder: Path, tmp_path: Path) -> None:
    spec = TorrentSpec(
        target=exclude_test_folder,
        output=tmp_path,
        protocol=ProtocolVersion.V1,
        exclude_pattern_ci=[r"\.md$", r"\.log$"],
    )
    _, metainfo, _ = create_torrent(spec)
    assert _included_rel_paths(metainfo) == {"keep.txt", "ignore_me.tmp", "sub/data.bin"}


@pytest.mark.parametrize(
    ("kwargs", "error_match"),
    [
        ({"exclude_pattern": ["[invalid"]}, "Invalid regular expression"),
        ({"exclude_pattern_ci": ["[invalid"]}, "Invalid case-insensitive regular expression"),
    ],
)
def test_exclude_pattern_invalid_regex(
    exclude_test_folder: Path,
    tmp_path: Path,
    kwargs: dict[str, list[str]],
    error_match: str,
) -> None:
    spec = TorrentSpec(target=exclude_test_folder, output=tmp_path, **kwargs)
    with pytest.raises(ValueError, match=error_match):
        create_torrent(spec)


def test_exclude_all_files_raises(exclude_test_folder: Path, tmp_path: Path) -> None:
    spec = TorrentSpec(
        target=exclude_test_folder,
        output=tmp_path,
        exclude_pattern=[r".*"],
    )
    with pytest.raises(ValueError, match="Cannot create torrent for 0-byte data"):
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


def test_output_file(sample_file: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "explicit_output_path.torrent"
    assert not output_path.is_file()
    spec = TorrentSpec(target=sample_file, output=output_path)
    create_torrent(spec)
    assert output_path.is_file()


def test_output_default_cwd(
    sample_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Switch working directory to tmp_path so the default output does not pollute the repo
    monkeypatch.chdir(tmp_path)
    expected_torrent_location = tmp_path / f"{sample_file.name}.torrent"
    assert not expected_torrent_location.is_file()

    spec = TorrentSpec(target=sample_file, output=None)
    create_torrent(spec)

    assert expected_torrent_location.is_file()


def test_output_directory(sample_file: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "existing_output_directory"
    output_path.mkdir()
    assert output_path.is_dir()
    expected_torrent_location = output_path / f"{sample_file.name}.torrent"
    assert not expected_torrent_location.is_file()
    spec = TorrentSpec(target=sample_file, output=output_path)
    create_torrent(spec)
    assert expected_torrent_location.is_file()


def test_output_missing_parent_dir(sample_file: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "missing_parent" / "custom.torrent"
    spec = TorrentSpec(target=sample_file, output=output_path)
    with pytest.raises(FileNotFoundError, match="Output directory does not exist"):
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


def test_threads(sample_file: Path, tmp_path: Path) -> None:
    spec = TorrentSpec(target=sample_file, output=tmp_path, threads=0)
    with pytest.raises(ValueError, match="Thread count"):
        create_torrent(spec)
