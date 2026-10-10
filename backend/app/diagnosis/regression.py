"""Regression-test suggestions generated from recorded data.

RunTrace never sees the user's source code, so generated tests use clearly marked
placeholders for imports instead of invented module paths or line numbers.
"""

from __future__ import annotations

import json
import re
from typing import Any

MAX_LITERAL_CHARS = 2500


def _identifier(name: str) -> str:
    ident = re.sub(r"[^0-9a-zA-Z_]", "_", name).strip("_").lower() or "step"
    return f"step_{ident}" if ident[0].isdigit() else ident


def _literal(value: Any) -> str:
    """A Python literal for a JSON-compatible value (repr of JSON-decoded data is valid Python)."""
    text = repr(value)
    if len(text) > MAX_LITERAL_CHARS:
        text = repr(json.dumps(value, default=str)[:MAX_LITERAL_CHARS] + "…")
        return text + "  # NOTE: truncated by RunTrace; paste the full recorded value"
    return text


def _header(run_id: str, note: str) -> str:
    return (
        f"# Regression test suggested by RunTrace from run {run_id}.\n"
        f"# {note}\n"
        "# RunTrace cannot see your source code: replace the TODO import with your real function.\n"
    )


def consumer_test(run_id: str, producer: str | None, consumer: str, failing_input: Any,
                  baseline_input: Any = None, error_type: str | None = None) -> str:
    """Test that the consuming step handles the recorded input that made it fail."""
    func = _identifier(consumer)
    lines = [_header(run_id, f"Step '{consumer}' failed"
                     + (f" on output recorded from '{producer}'." if producer else " on its recorded input."))]
    lines.append("import pytest\n\n")
    lines.append(f"RECORDED_FAILING_INPUT = {_literal(failing_input)}\n")
    if baseline_input is not None:
        lines.append(f"RECORDED_BASELINE_INPUT = {_literal(baseline_input)}\n")
    lines.append("\n\n")
    lines.append(f"def test_{func}_handles_recorded_failing_input():\n")
    lines.append(f"    from your_module import {func}  # TODO: replace with the real import\n\n")
    if error_type:
        lines.append(f"    # Previously raised {error_type}. The fix should make this pass.\n")
    lines.append(f"    result = {func}(RECORDED_FAILING_INPUT)\n")
    lines.append("    assert result is not None\n")
    if baseline_input is not None:
        lines.append("\n\n")
        lines.append(f"def test_{func}_still_handles_baseline_input():\n")
        lines.append(f"    from your_module import {func}  # TODO: replace with the real import\n\n")
        lines.append(f"    assert {func}(RECORDED_BASELINE_INPUT) is not None\n")
    return "".join(lines)


def schema_test(run_id: str, step: str, baseline_output: Any, comparison_output: Any) -> str:
    """Contract test asserting the step's output keeps the baseline structure."""
    func = _identifier(step)
    expected_keys = sorted(baseline_output.keys()) if isinstance(baseline_output, dict) else None
    lines = [_header(run_id, f"Output of step '{step}' changed structure compared with the baseline.")]
    lines.append("\n")
    lines.append(f"BASELINE_OUTPUT = {_literal(baseline_output)}\n")
    lines.append(f"CHANGED_OUTPUT = {_literal(comparison_output)}\n\n\n")
    lines.append(f"def test_{func}_output_matches_baseline_contract():\n")
    lines.append(f"    from your_module import {func}  # TODO: replace with the real import and inputs\n\n")
    lines.append(f"    output = {func}()  # TODO: call with the inputs used in the baseline run\n")
    if expected_keys is not None:
        lines.append(f"    assert isinstance(output, dict), f\"expected an object, got {{type(output).__name__}}\"\n")
        lines.append(f"    assert set({expected_keys!r}).issubset(output.keys())\n")
    else:
        lines.append("    assert type(output) is type(BASELINE_OUTPUT)\n")
    return "".join(lines)


def env_test(run_id: str, variable: str) -> str:
    return (
        _header(run_id, f"A required environment variable ({variable}) appeared to be missing.")
        + "import os\n\n\n"
        + f"def test_{_identifier(variable)}_is_configured():\n"
        + f"    assert os.environ.get({variable!r}), {variable!r} + ' must be set for this workflow'\n"
    )


def module_test(run_id: str, module: str) -> str:
    return (
        _header(run_id, f"Importing '{module}' failed.")
        + "import importlib\n\n\n"
        + f"def test_{_identifier(module)}_is_importable():\n"
        + f"    importlib.import_module({module!r})\n"
    )
