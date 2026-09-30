from scripts.package_xiaocao_skill import _copy_item


def test_runtime_copy_keeps_native_source_without_generated_build_state(tmp_path):
    source = tmp_path / "native"
    (source / ".build").mkdir(parents=True)
    (source / ".build" / "build.db").write_bytes(b"generated build state")
    (source / ".build" / "executor").write_bytes(b"generated binary")
    (source / ".pytest_cache").mkdir()
    (source / ".pytest_cache" / "cache").write_text("generated test state")
    (source / "Sources").mkdir()
    (source / "Package.swift").write_text("package source")
    (source / "Sources" / "main.swift").write_text("native source")
    destination = tmp_path / "runtime-native"
    _copy_item(source, destination)
    assert (destination / "Package.swift").read_text() == "package source"
    assert (destination / "Sources" / "main.swift").read_text() == "native source"
    assert not (destination / ".build").exists()
    assert not (destination / ".pytest_cache").exists()
