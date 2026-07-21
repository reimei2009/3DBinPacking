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
