from io import BytesIO
from hashlib import sha256

import pytest
import yaml

from container_packing.data.external_sources import download_pinned_source
from container_packing.data.mpv_workflow import (
    COMPILER_REQUIRED, build_mpv_capture_adapter, download_mpv_bundle,
)


class _Response(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def test_pinned_download_writes_only_after_checksum_matches(tmp_path) -> None:
    payload = b"pinned academic generator"
    destination = tmp_path / "external" / "test3dbpp.c"
    digest = download_pinned_source(
        url="https://example.test/test3dbpp.c",
        expected_sha256=sha256(payload).hexdigest(),
        destination=destination,
        opener=lambda *args, **kwargs: _Response(payload),
    )
    assert digest == sha256(payload).hexdigest()
    assert destination.read_bytes() == payload


def test_pinned_download_rejects_checksum_mismatch_without_publishing(tmp_path) -> None:
    destination = tmp_path / "test3dbpp.c"
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        download_pinned_source(
            url="https://example.test/test3dbpp.c",
            expected_sha256="0" * 64,
            destination=destination,
            opener=lambda *args, **kwargs: _Response(b"wrong"),
        )
    assert not destination.exists()


def test_pinned_download_rejects_insecure_url(tmp_path) -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        download_pinned_source(
            url="http://example.test/test3dbpp.c",
            expected_sha256="0" * 64,
            destination=tmp_path / "test3dbpp.c",
        )


def test_mpv_bundle_download_is_atomic_and_refuses_checksum_mismatch(tmp_path) -> None:
    payloads = {
        "test3dbpp.c": b"generator source", "3dbpp.c": b"solver source",
        "readme.3dbpp": b"readme source",
    }
    lock = tmp_path / "mpv_source_lock.yaml"
    lock.write_text(yaml.safe_dump({
        "schema_version": "1.0", "bundle_id": "mpv-official-source-v1",
        "checksum_policy": "TOFU", "artifacts": [
            {"role": "generator_source", "filename": "test3dbpp.c",
             "canonical_url": "https://hjemmesider.diku.dk/~pisinger/new3dbpp/test3dbpp.c",
             "sha256": sha256(payloads["test3dbpp.c"]).hexdigest()},
            {"role": "solver_source", "filename": "3dbpp.c",
             "canonical_url": "https://hjemmesider.diku.dk/~pisinger/new3dbpp/3dbpp.c",
             "sha256": sha256(payloads["3dbpp.c"]).hexdigest()},
            {"role": "compilation_readme", "filename": "readme.3dbpp",
             "canonical_url": "https://hjemmesider.diku.dk/~pisinger/new3dbpp/readme.3dbpp",
             "sha256": sha256(payloads["readme.3dbpp"]).hexdigest()},
        ],
    }, sort_keys=False), encoding="utf-8")

    def opener(url, **_kwargs):
        return _Response(payloads[url.rsplit("/", 1)[-1]])

    destination = download_mpv_bundle(lock, destination_root=tmp_path / "external", opener=opener)
    assert {path.name for path in destination.iterdir()} >= set(payloads)
    assert download_mpv_bundle(lock, destination_root=tmp_path / "external", opener=opener) == destination

    lock_payload = yaml.safe_load(lock.read_text(encoding="utf-8"))
    lock_payload["artifacts"][1]["sha256"] = sha256(b"tampered").hexdigest()
    lock.write_text(yaml.safe_dump(lock_payload, sort_keys=False), encoding="utf-8")
    with pytest.raises(FileExistsError, match="Refusing to replace"):
        download_mpv_bundle(lock, destination_root=tmp_path / "external", opener=opener)


def test_mpv_build_reports_missing_compiler_before_creating_build(tmp_path, monkeypatch) -> None:
    import container_packing.data.mpv_workflow as workflow

    monkeypatch.setattr(workflow, "find_c_compiler", lambda: None)
    with pytest.raises(RuntimeError, match=COMPILER_REQUIRED):
        build_mpv_capture_adapter(
            source_dir=tmp_path / "sources", adapter_path=tmp_path / "adapter.c",
            build_root=tmp_path / "builds",
        )
    assert not (tmp_path / "builds").exists()
