from container_packing import provenance
from container_packing.provenance import source_tree_sha256


def test_source_tree_checksum_changes_with_source(tmp_path):
    source = tmp_path / "src/example.py"
    source.parent.mkdir()
    source.write_text("VALUE = 1\n", encoding="utf-8")
    first = source_tree_sha256(tmp_path)
    source.write_text("VALUE = 2\n", encoding="utf-8")
    second = source_tree_sha256(tmp_path)
    assert len(first) == 64
    assert first != second


def test_runtime_metadata_reuses_snapshot_and_returns_defensive_copy(
    tmp_path, monkeypatch,
):
    provenance.clear_runtime_metadata_cache()
    calls = {"dirty": 0}
    monkeypatch.setattr(provenance, "git_commit", lambda _root: "abc123")

    def dirty(_root):
        calls["dirty"] += 1
        return True

    monkeypatch.setattr(provenance, "git_dirty", dirty)
    monkeypatch.setattr(provenance, "source_tree_sha256", lambda _root: "f" * 64)
    monkeypatch.setattr(provenance, "dependency_versions", lambda: {"pandas": "test"})

    first = provenance.runtime_metadata(tmp_path)
    first["dependency_versions"]["pandas"] = "mutated"
    second = provenance.runtime_metadata(tmp_path)

    assert calls["dirty"] == 1
    assert second["dependency_versions"]["pandas"] == "test"
    provenance.clear_runtime_metadata_cache()
