import json

import pytest

from xiaocao.kol.netdisk_opencli_templates import (
    netdisk_opencli_template_names,
    render_netdisk_opencli_template,
)


EXPECTED_PATH = "/课程/自己的课/小草/20260804 大师班专场-compressed.mp4"


def _render(name: str) -> str:
    return render_netdisk_opencli_template(name, expected_path=EXPECTED_PATH)


def test_netdisk_opencli_template_registry_renders_all_commands():
    assert netdisk_opencli_template_names() == (
        "prepare_ai_note",
        "probe_ai_note",
        "probe_transcript",
        "submit_ai_note",
    )
    for name in netdisk_opencli_template_names():
        source = _render(name)
        assert f"baidu-netdisk/{name.replace('_', '-')}" in source
        assert "__EXPECTED_PATH__" not in source


def test_netdisk_opencli_template_parameters_are_exact_and_json_escaped():
    hostile_path = EXPECTED_PATH + "'; window.pwned = true; //"
    source = render_netdisk_opencli_template(
        "probe_ai_note",
        expected_path=hostile_path,
    )

    assert json.dumps(hostile_path, ensure_ascii=False) in source
    assert "const expectedPath = '/课程" not in source

    with pytest.raises(ValueError, match="missing=.*expected_path"):
        render_netdisk_opencli_template("probe_ai_note")
    with pytest.raises(ValueError, match="unknown=.*extra"):
        render_netdisk_opencli_template(
            "probe_ai_note",
            expected_path=EXPECTED_PATH,
            extra=True,
        )
    with pytest.raises(ValueError, match="unknown Netdisk OpenCLI template"):
        render_netdisk_opencli_template(
            "unknown",
            expected_path=EXPECTED_PATH,
        )


def test_only_submit_template_can_dispatch_the_generation_click():
    submit = _render("submit_ai_note")
    assert "buttonMatches[0].click()" in submit
    assert "genNoteByTpl" not in submit

    for name in ("probe_transcript", "probe_ai_note"):
        source = _render(name)
        assert ".click()" not in source
        assert "previewTemplate" not in source
        assert "genNoteByTpl" not in source

    prepare = _render("prepare_ai_note")
    assert "buttonMatches[0].click()" not in prepare
    assert "click_dispatched: false" in prepare


def test_submit_click_is_terminal_after_selected_template_precondition():
    source = _render("submit_ai_note")

    selected_check = source.index("const templateSelected")
    fail_closed_check = source.index("!templateSelected")
    generation_click = source.index("buttonMatches[0].click()")
    dispatched_receipt = source.index("confirmed_state: 'dispatched'")

    assert selected_check < fail_closed_check < generation_click < dispatched_receipt
    assert "transitionDeadline" not in source
    assert "noteText" not in source
