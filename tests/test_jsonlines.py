"""Tests for printing the runner's events as JSON lines, one object per event."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from rundot import jsonlines, runner
from rundot.inputs import Input
from rundot.runbook import Block, Step

AT = datetime(2026, 11, 13, 14, 2, 11, 482915, tzinfo=timezone.utc)
WHEN = "2026-11-13T14:02:11.482+00:00"

RUN = Block("run", "sh", 'uv publish --token "$PUBLISH_TOKEN"\n', 41)
CONFIRM = Block("confirm", None, "Publish the notes.\n", 50)
DOCSTRING = Block("docstring", None, "Why.\n", 12)
PR = Input("PR", "The pull request number")
INPUT = Block("input", None, "name: PR\n", 60, input=PR)
BUILD = Step("Build", 8, (DOCSTRING,))
PUBLISH = Step("Publish", 40, (RUN, CONFIRM, INPUT))
STEPS = (BUILD, PUBLISH)


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        (
            runner.Overview("Release", STEPS, 1, (("VERSION", "1.2.0"), ("TOKEN", "****")), Path("/p"), 1),
            {
                "event": "overview",
                "title": "Release",
                "directory": "/p",
                "inputs": {"VERSION": "1.2.0", "TOKEN": "****"},
                "steps": ["Build", "Publish"],
                "resuming_at": 1,
            },
        ),
        (
            runner.Overview("Release", STEPS, 2, (), Path("/p")),
            {
                "event": "overview",
                "title": "Release",
                "directory": "/p",
                "inputs": {},
                "steps": ["Build", "Publish"],
                "resuming_at": None,
            },
        ),
        (runner.StepStarted(PUBLISH), {"event": "step_started", "number": 2, "name": "Publish"}),
        (runner.Docstring(DOCSTRING, "Why.\n"), {"event": "docstring", "line": 12, "text": "Why.\n"}),
        (
            runner.Confirm(CONFIRM, "Publish the notes.\n"),
            {"event": "confirm", "line": 50, "text": "Publish the notes.\n"},
        ),
        (
            runner.ConfirmAnswered(CONFIRM, "Publish the notes.\n", True),
            {"event": "confirm_answered", "line": 50, "yes": True},
        ),
        (
            runner.InputBlock(INPUT, PR),
            {"event": "input_block", "line": 60, "name": "PR", "description": "The pull request number"},
        ),
        (
            runner.InputCollected(INPUT, "PR", "42"),
            {"event": "input_collected", "line": 60, "name": "PR", "value": "42"},
        ),
        (
            runner.BlockStarted(RUN, 'uv publish --token "$PUBLISH_TOKEN"\n'),
            {"event": "block_started", "line": 41, "language": "sh", "code": 'uv publish --token "$PUBLISH_TOKEN"\n'},
        ),
        (runner.BlockSkipped(RUN), {"event": "block_skipped", "line": 41}),
        (runner.OutputLine("Uploading"), {"event": "output", "text": "Uploading", "stderr": False}),
        (runner.OutputLine("warning", stderr=True), {"event": "output", "text": "warning", "stderr": True}),
        (
            runner.BlockFinished(RUN, 0, 1.23456),
            {"event": "block_finished", "line": 41, "exit_code": 0, "duration": 1.235},
        ),
        (
            runner.RunFinished("failed", 3.4, PUBLISH, 1),
            {
                "event": "run_finished",
                "status": "failed",
                "step": "Publish",
                "exit_code": 1,
                "duration": 3.4,
                "message": None,
            },
        ),
        (
            runner.RunFinished("aborted", 0.0),
            {
                "event": "run_finished",
                "status": "aborted",
                "step": None,
                "exit_code": None,
                "duration": 0.0,
                "message": None,
            },
        ),
        (
            runner.RunFinished(
                "needs_human_input", 2.0, PUBLISH, block=CONFIRM, message="Publish the notes. Run again."
            ),
            {
                "event": "run_finished",
                "status": "needs_human_input",
                "step": "Publish",
                "exit_code": None,
                "duration": 2.0,
                "message": "Publish the notes. Run again.",
            },
        ),
    ],
    ids=lambda value: value.get("event") if isinstance(value, dict) else None,
)
def test_each_event_is_one_object_with_exactly_its_fields(event, expected):
    """Every object has event and at first, then the fields the spec lists for its type, and nothing else."""
    assert jsonlines.to_json(event, STEPS, AT) == {"event": expected["event"], "at": WHEN} | expected


def test_at_is_iso_8601_with_milliseconds():
    assert jsonlines.to_json(runner.OutputLine("x"), STEPS, AT)["at"] == WHEN


def test_the_sink_writes_one_json_line_per_event_and_numbers_steps_from_the_overview():
    lines: list[str] = []
    sink = jsonlines.JsonLines(lines.append, clock=lambda: AT)

    sink(runner.Overview("Release", STEPS, 1, (), Path("/p")))
    sink(runner.StepStarted(PUBLISH))

    assert [json.loads(line)["event"] for line in lines] == ["overview", "step_started"]
    assert json.loads(lines[1])["number"] == 2
    assert all("\n" not in line for line in lines)


def test_the_sink_keeps_text_that_is_not_ascii_readable():
    lines: list[str] = []
    sink = jsonlines.JsonLines(lines.append, clock=lambda: AT)

    sink(runner.OutputLine("café ✓"))

    assert "café ✓" in lines[0]


def test_the_sink_times_events_by_the_local_clock_by_default():
    lines: list[str] = []

    jsonlines.JsonLines(lines.append)(runner.OutputLine("x"))

    assert datetime.fromisoformat(json.loads(lines[0])["at"]).tzinfo is not None
