from pathlib import Path

import pytest

from container_packing import reporting


def test_atomic_write_retries_transient_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "manifest.json"
    original_replace = Path.replace
    attempts = 0

    def flaky_replace(source: Path, destination: Path) -> Path:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("temporary Windows sharing violation")
        return original_replace(source, destination)

    monkeypatch.setattr(Path, "replace", flaky_replace)
    monkeypatch.setattr(reporting.time, "sleep", lambda _seconds: None)

    reporting.write_text(target, '{"status": "VALID"}')

    assert attempts == 3
    assert target.read_text(encoding="utf-8") == '{"status": "VALID"}'
    assert not target.with_suffix(".json.tmp").exists()


def test_atomic_write_preserves_complete_temporary_file_after_retry_exhaustion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "manifest.json"
    monkeypatch.setattr(
        Path, "replace",
        lambda _source, _destination: (_ for _ in ()).throw(PermissionError("locked")),
    )
    monkeypatch.setattr(reporting.time, "sleep", lambda _seconds: None)

    with pytest.raises(reporting.AtomicPublishError, match="after 5 attempts"):
        reporting.write_text(target, '{"status": "VALID"}')

    temporary = target.with_suffix(".json.tmp")
    assert not target.exists()
    assert temporary.read_text(encoding="utf-8") == '{"status": "VALID"}'


def test_atomic_write_does_not_retry_non_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "manifest.json"
    attempts = 0

    def invalid_replace(_source: Path, _destination: Path) -> Path:
        nonlocal attempts
        attempts += 1
        raise FileNotFoundError("invalid destination")

    monkeypatch.setattr(Path, "replace", invalid_replace)

    with pytest.raises(FileNotFoundError, match="invalid destination"):
        reporting.write_text(target, "payload")

    assert attempts == 1
    assert target.with_suffix(".json.tmp").exists()
