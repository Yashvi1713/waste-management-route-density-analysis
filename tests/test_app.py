from __future__ import annotations

import ast
import inspect
from pathlib import Path

import streamlit as st


def test_altair_chart_arguments_match_installed_streamlit() -> None:
    tree = ast.parse(Path("app.py").read_text())
    supported = set(inspect.signature(st.altair_chart).parameters)
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "altair_chart"
    ]
    assert calls
    for call in calls:
        assert {kw.arg for kw in call.keywords if kw.arg} <= supported


def test_overview_has_pickup_total_and_status_donut() -> None:
    source = Path("app.py").read_text()
    tree = ast.parse(source)
    arc_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "mark_arc"
    ]
    assert '"Total pickups"' in source
    assert '"Completed"' in source
    assert '"Missed"' in source
    assert arc_calls
    assert any(
        any(keyword.arg == "innerRadius" for keyword in call.keywords)
        for call in arc_calls
    )

