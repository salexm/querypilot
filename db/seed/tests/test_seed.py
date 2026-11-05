import hashlib
import zipfile
from pathlib import Path

import pytest

import seed


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def write_archive(path: Path, name: str, text: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(name, text)


def test_read_rows_strips_bom_and_renames_columns(tmp_path: Path) -> None:
    path = tmp_path / "data.csv"
    path.write_bytes(b"\xef\xbb\xbfproduct_name_lenght,other\r\n1,2\r\n")

    columns, rows = seed.read_rows(path, {"product_name_lenght": "product_name_length"})

    assert columns == ["product_name_length", "other"]
    assert list(rows) == [["1", "2"]]


def test_read_rows_turns_empty_fields_into_null(tmp_path: Path) -> None:
    path = tmp_path / "data.csv"
    path.write_text("a,b\n1,\n", encoding="utf-8")

    _, rows = seed.read_rows(path, {})

    assert list(rows) == [["1", None]]


def test_read_rows_keeps_line_breaks_inside_quoted_fields(tmp_path: Path) -> None:
    path = tmp_path / "data.csv"
    path.write_bytes(b'id,message\n1,"first\r\nsecond"\n')

    _, rows = seed.read_rows(path, {})

    assert list(rows) == [["1", "first\r\nsecond"]]


def test_hash_mismatches_reports_missing_and_changed_files(tmp_path: Path) -> None:
    (tmp_path / "good.csv").write_text("good", encoding="utf-8")
    (tmp_path / "changed.csv").write_text("changed", encoding="utf-8")
    expected = {
        "good.csv": sha256_text("good"),
        "changed.csv": sha256_text("original"),
        "missing.csv": sha256_text("missing"),
    }

    assert seed.hash_mismatches(tmp_path, expected) == ["changed.csv", "missing.csv"]


def test_ensure_dataset_extracts_a_valid_local_archive(tmp_path: Path) -> None:
    archive = tmp_path / "olist.zip"
    write_archive(archive, "data.csv", "a,b\n")
    data_dir = tmp_path / "data"

    seed.ensure_dataset(
        data_dir, archive, "http://unused.invalid", {"data.csv": sha256_text("a,b\n")}
    )

    assert (data_dir / "data.csv").read_text(encoding="utf-8") == "a,b\n"


def test_ensure_dataset_rejects_changed_source_data(tmp_path: Path) -> None:
    archive = tmp_path / "olist.zip"
    write_archive(archive, "data.csv", "tampered\n")

    with pytest.raises(ValueError, match="Checksum mismatch for data.csv"):
        seed.ensure_dataset(
            tmp_path / "data", archive, "http://unused.invalid", {"data.csv": sha256_text("a,b\n")}
        )


def test_ensure_dataset_skips_download_when_files_are_valid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "data.csv").write_bytes(b"a,b\n")

    def fail_download(url: str, destination: Path) -> None:
        raise AssertionError("should not download")

    monkeypatch.setattr(seed, "download_archive", fail_download)

    seed.ensure_dataset(
        tmp_path,
        tmp_path / "olist.zip",
        "http://unused.invalid",
        {"data.csv": sha256_text("a,b\n")},
    )


def test_expected_rows_include_added_translations() -> None:
    categories = next(spec for spec in seed.TABLES if spec.table == "product_categories")

    assert categories.expected_rows == 73
