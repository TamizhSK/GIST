"""B1b/B8 — the tier-0 cycle walk and topological layering.

Both the planner (tier 4) and Layer 3 (tier 3) adapt their own Job-shaped
types to this plain `{node: [deps]}` map, so it is the one place the walk
lives and the one place it is tested.
"""

from __future__ import annotations

import pytest

from yeet.core.graph import find_cycle, topo_waves

# --- find_cycle -------------------------------------------------------------


def test_no_cycle_returns_none():
    assert find_cycle({"build": [], "test": ["build"], "deploy": ["build", "test"]}) is None


def test_returns_the_cycle_as_a_path():
    assert find_cycle({"build": ["test"], "test": ["build"]}) == ["build", "test", "build"]


def test_three_node_cycle():
    assert find_cycle({"a": ["b"], "b": ["c"], "c": ["a"]}) == ["a", "b", "c", "a"]


def test_self_reference_is_a_cycle():
    assert find_cycle({"a": ["a"]}) == ["a", "a"]


def test_cycle_in_a_disconnected_subgraph():
    """The cycle is not at the start of the map — iteration order must not hide it."""
    assert find_cycle({"x": [], "y": ["z"], "z": ["y"]}) == ["y", "z", "y"]


def test_unknown_dependency_is_not_a_cycle():
    assert find_cycle({"build": ["typo-job"]}) is None


def test_diamond_has_no_cycle():
    deps = {"a": [], "b": ["a"], "c": ["a"], "d": ["b", "c"]}
    assert find_cycle(deps) is None


def test_empty_graph():
    assert find_cycle({}) is None


# --- topo_waves -------------------------------------------------------------


def test_simple_chain_becomes_sequential_waves():
    assert topo_waves({"build": [], "test": ["build"], "deploy": ["test"]}) == [
        ["build"],
        ["test"],
        ["deploy"],
    ]


def test_independent_jobs_share_a_wave():
    assert topo_waves({"a": [], "b": [], "c": ["a", "b"]}) == [["a", "b"], ["c"]]


def test_diamond_dependency():
    waves = topo_waves({"a": [], "b": ["a"], "c": ["a"], "d": ["b", "c"]})
    assert waves[0] == ["a"]
    assert set(waves[1]) == {"b", "c"}
    assert waves[2] == ["d"]


def test_single_job():
    assert topo_waves({"build": []}) == [["build"]]


def test_unknown_dependency_is_treated_as_satisfied():
    """A typo'd needs: must not drag the graph into a cycle error — E301 reports it."""
    assert topo_waves({"build": ["typo-job"]}) == [["build"]]


def test_cycle_raises_value_error_with_the_path():
    with pytest.raises(ValueError, match="build -> test -> build"):
        topo_waves({"build": ["test"], "test": ["build"]})


def test_empty_graph_is_an_empty_plan():
    assert topo_waves({}) == []


def test_waves_are_deterministic():
    deps = {"a": [], "b": [], "c": ["a"], "d": ["a", "b"]}
    assert topo_waves(deps) == topo_waves(deps)
