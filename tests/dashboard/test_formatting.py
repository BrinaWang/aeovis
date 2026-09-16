"""Tests for dashboard display formatting helpers."""

from aeo_eval.dashboard.formatting import normalize_implementation_step


def test_dict_step_passes_through():
    step = {"step": "Write draft", "effort": "High",
            "owner": "Content Team", "notes": "n"}
    out = normalize_implementation_step(step, 1)
    assert out == {"step": "Write draft", "effort": "High",
                   "owner": "Content Team", "notes": "n"}


def test_dict_step_fills_missing_fields():
    out = normalize_implementation_step({"step": "Review"}, 2)
    assert out["step"] == "Review"
    assert out["effort"] == ""
    assert out["owner"] == ""
    assert out["notes"] == ""


def test_string_step_becomes_step_name():
    """Social media recommendations store steps as plain strings; the
    renderer crashed calling .get() on them."""
    out = normalize_implementation_step("Post the thread in r/dataengineering", 1)
    assert out["step"] == "Post the thread in r/dataengineering"
    assert out["effort"] == ""
    assert out["owner"] == ""
    assert out["notes"] == ""


def test_unexpected_type_is_stringified():
    out = normalize_implementation_step(42, 3)
    assert out["step"] == "42"


def test_dict_without_step_key_gets_positional_name():
    out = normalize_implementation_step({"effort": "Low"}, 4)
    assert out["step"] == "Step 4"


def test_app_has_single_implementation_steps_renderer():
    """Two copies of render_implementation_steps drifted apart: the
    module-level one handled string steps, the nested duplicate crashed
    on them (AttributeError: 'str' object has no attribute 'get').
    There must be exactly one, and it must use the shared normalizer.
    """
    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "aeo_eval" / "dashboard" / "app.py"
    ).read_text()
    tree = ast.parse(source)

    defs = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "render_implementation_steps"
    ]
    assert len(defs) == 1, (
        f"expected exactly one render_implementation_steps, found "
        f"{len(defs)} (lines {[d.lineno for d in defs]})"
    )
    renderer_src = ast.get_source_segment(source, defs[0])
    assert "normalize_implementation_step" in renderer_src, (
        "render_implementation_steps must normalize steps via the shared "
        "helper so string steps (social media recs) cannot crash it"
    )
