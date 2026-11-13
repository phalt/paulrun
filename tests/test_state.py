"""Tests for saving where a run got to, so it can be resumed."""

import json
import stat
import textwrap
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from rundot import runner, state
from rundot.backends import load_backends
from rundot.inputs import Input, NeedsHumanInput
from rundot.runbook import Block, Step, parse


def test_state_dir_is_under_xdg_state_home(tmp_path):
    """XDG_STATE_HOME, when it's set, holds rundot's runs."""
    assert state.state_dir({"XDG_STATE_HOME": str(tmp_path)}) == tmp_path / "rundot" / "runs"


@pytest.mark.parametrize("env", [{}, {"XDG_STATE_HOME": ""}])
def test_state_dir_defaults_to_local_state_when_xdg_state_home_is_unset_or_empty(env, monkeypatch, tmp_path):
    """An empty variable counts as unset, as it does for the library."""
    monkeypatch.setenv("HOME", str(tmp_path))

    assert state.state_dir(env) == tmp_path / ".local" / "state" / "rundot" / "runs"


def test_state_dir_expands_a_tilde(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))

    assert state.state_dir({"XDG_STATE_HOME": "~/state"}) == tmp_path / "state" / "rundot" / "runs"


def test_key_is_16_hex_characters_and_the_same_every_time(tmp_path):
    runbook = tmp_path / "RELEASING.md"

    key = state.key(runbook, tmp_path)

    assert len(key) == 16
    int(key, 16)
    assert state.key(runbook, tmp_path) == key


def test_key_is_the_same_through_a_symlink_or_dot_dot(tmp_path):
    """Paths are resolved, so one runbook in one directory always has one state."""
    project = tmp_path / "project"
    (project / "sub").mkdir(parents=True)
    (tmp_path / "link").symlink_to(project)
    runbook = project / "RELEASING.md"

    expected = state.key(runbook, project)

    assert state.key(tmp_path / "link" / "RELEASING.md", tmp_path / "link") == expected
    assert state.key(project / "sub" / ".." / "RELEASING.md", project / "sub" / "..") == expected


def test_key_differs_for_another_directory_or_another_runbook(tmp_path):
    """The same book run in two projects keeps two states, and two books in one project do too."""
    runbook = tmp_path / "RELEASING.md"

    keys = {
        state.key(runbook, tmp_path / "one"),
        state.key(runbook, tmp_path / "two"),
        state.key(tmp_path / "B.md", tmp_path / "one"),
    }

    assert len(keys) == 3


def test_state_path_is_the_key_in_the_state_dir(tmp_path):
    runbook = tmp_path / "RELEASING.md"
    env = {"XDG_STATE_HOME": str(tmp_path)}

    assert state.state_path(env, runbook, tmp_path) == state.state_dir(env) / f"{state.key(runbook, tmp_path)}.json"


STEP = Step(
    name="Publish",
    line=3,
    blocks=(Block(kind="run", language="sh", content="uv publish\n", line=5), Block("confirm", None, "Check.\n", 9)),
)


@pytest.mark.parametrize(
    "changed",
    [
        Step("Release", STEP.line, STEP.blocks),
        Step(STEP.name, STEP.line, (Block("run", "bash", "uv publish\n", 5), STEP.blocks[1])),
        Step(STEP.name, STEP.line, (Block("docstring", None, "uv publish\n", 5), STEP.blocks[1])),
        Step(STEP.name, STEP.line, (Block("run", "sh", "uv build\n", 5), STEP.blocks[1])),
        Step(STEP.name, STEP.line, STEP.blocks[:1]),
        Step(STEP.name, STEP.line, STEP.blocks[::-1]),
    ],
    ids=["name", "language", "kind", "content", "a block removed", "blocks reordered"],
)
def test_step_hash_changes_when_the_step_changes(changed):
    assert state.step_hash(changed) != state.step_hash(STEP)


def test_step_hash_ignores_where_the_step_is_in_the_file():
    """Moving a step down the file, e.g. by editing an earlier one, doesn't change it."""
    moved = Step(STEP.name, 30, tuple(Block(b.kind, b.language, b.content, b.line + 27) for b in STEP.blocks))

    assert state.step_hash(moved) == state.step_hash(STEP)
    assert len(state.step_hash(STEP)) == 64


def test_step_hash_does_not_run_parts_together():
    """Each part is kept apart, so moving text between a name and a block can't give the same hash."""
    one = Step("ab", 1, (Block("run", "sh", "c", 2),))
    two = Step("a", 1, (Block("run", "sh", "bc", 2),))

    assert state.step_hash(one) != state.step_hash(two)


BASE = state.RunState(
    runbook="/home/you/project/RELEASING.md",
    directory="/home/you/project",
    started_at="2026-11-13T14:02:11+00:00",
    stopped="failed",
    step=1,
    block=0,
    steps=(("Run the tests", "9f2c"), ("Publish", "e5d1")),
    inputs={"VERSION": "1.2.0"},
)


def a_state(**changes) -> state.RunState:
    return replace(BASE, **changes)


def test_a_saved_state_loads_as_it_was(tmp_path):
    path = tmp_path / "runs" / "key.json"
    saved = a_state()

    saved.save(path)

    assert state.RunState.load(path, warn=pytest.fail) == saved


def test_a_saved_state_is_the_documented_json(tmp_path):
    """The file is the format in the spec, so it can be read and debugged by hand."""
    path = tmp_path / "key.json"

    a_state().save(path)

    assert json.loads(path.read_text()) == {
        "version": 1,
        "runbook": "/home/you/project/RELEASING.md",
        "directory": "/home/you/project",
        "started_at": "2026-11-13T14:02:11+00:00",
        "stopped": "failed",
        "step": 1,
        "block": 0,
        "steps": [{"name": "Run the tests", "hash": "9f2c"}, {"name": "Publish", "hash": "e5d1"}],
        "inputs": {"VERSION": "1.2.0"},
        "exit_code": None,
    }


def test_a_saved_state_is_only_readable_by_its_owner_in_a_private_directory(tmp_path):
    path = tmp_path / "state" / "rundot" / "runs" / "key.json"

    a_state().save(path)

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_saving_replaces_the_file_and_leaves_no_temporary_file(tmp_path):
    """The file is written whole and renamed into place, so a killed run never leaves half a file."""
    path = tmp_path / "key.json"
    a_state(step=0).save(path)

    a_state(step=1).save(path)

    assert [p.name for p in tmp_path.iterdir()] == ["key.json"]
    assert state.RunState.load(path, warn=pytest.fail) == a_state(step=1)


def test_a_save_that_cannot_make_its_directory_is_a_state_error(tmp_path):
    (tmp_path / "taken").write_text("a file where the directory should be")

    with pytest.raises(state.StateError, match="can't save the run's state"):
        a_state().save(tmp_path / "taken" / "key.json")


def test_a_failed_rename_leaves_no_temporary_file(tmp_path):
    path = tmp_path / "key.json"
    path.mkdir()  # a directory can't be replaced by a file

    with pytest.raises(state.StateError):
        a_state().save(path)

    assert [p.name for p in tmp_path.iterdir()] == ["key.json"]


def test_there_is_no_state_when_the_file_does_not_exist(tmp_path):
    assert state.RunState.load(tmp_path / "missing.json", warn=pytest.fail) is None


def test_delete_removes_the_file_and_does_nothing_if_it_is_not_there(tmp_path):
    path = tmp_path / "key.json"
    a_state().save(path)

    state.RunState.delete(path)
    state.RunState.delete(path)

    assert not path.exists()


def test_a_failed_delete_is_a_state_error(tmp_path):
    path = tmp_path / "key.json"
    (path / "inside").mkdir(parents=True)  # a non-empty directory can't be unlinked

    with pytest.raises(state.StateError, match="can't delete the run's state"):
        state.RunState.delete(path)


def documented() -> dict:
    return json.loads(json.dumps({**a_state().__dict__, "version": 1, "steps": [{"name": "A", "hash": "h"}]}))


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("{not json", "isn't valid JSON"),
        (b"\xff", "can't be read"),
        ("[]", "isn't a saved run"),
        (json.dumps(documented() | {"version": 2}), "is version 2, not 1"),
        (json.dumps({k: v for k, v in documented().items() if k != "step"}), "isn't a saved run"),
        (json.dumps(documented() | {"step": "1"}), "isn't a saved run"),
        (json.dumps(documented() | {"step": True}), "isn't a saved run"),
        (json.dumps(documented() | {"step": -1}), "isn't a saved run"),
        (json.dumps(documented() | {"stopped": "dry"}), "isn't a saved run"),
        (json.dumps(documented() | {"steps": [{"name": "A"}]}), "isn't a saved run"),
        (json.dumps(documented() | {"steps": "A"}), "isn't a saved run"),
        (json.dumps(documented() | {"inputs": {"PR": 42}}), "isn't a saved run"),
        (json.dumps(documented() | {"inputs": []}), "isn't a saved run"),
        (json.dumps(documented() | {"runbook": None}), "isn't a saved run"),
    ],
    ids=[
        "not json",
        "not utf-8",
        "not an object",
        "another version",
        "a key missing",
        "step not an int",
        "step a bool",
        "step negative",
        "unknown stopped",
        "step without hash",
        "steps not a list",
        "input not a string",
        "inputs not an object",
        "runbook not a string",
    ],
)
def test_a_state_that_cannot_be_read_warns_and_loads_as_none(tmp_path, text, problem):
    """A broken or newer file is treated as if there were none, after saying why."""
    path = tmp_path / "key.json"
    path.write_bytes(text if isinstance(text, bytes) else text.encode())
    warnings: list[str] = []

    assert state.RunState.load(path, warn=warnings.append) is None
    [warning] = warnings
    assert warning.startswith(f"ignoring the saved run at {path}: ")
    assert problem in warning


def test_a_state_file_that_cannot_be_opened_warns_and_loads_as_none(tmp_path):
    path = tmp_path / "key.json"
    path.mkdir()
    warnings: list[str] = []

    assert state.RunState.load(path, warn=warnings.append) is None
    assert warnings and "can't be read" in warnings[0]


# --- StateRecorder, driven by the real runner ---

STARTED = datetime(2026, 11, 13, 14, 2, 11, tzinfo=timezone.utc)

# Three steps. Each block prints the state file as it is when the block runs, so tests can see it mid-run.
RUNBOOK = """\
---
title: Release
inputs:
  - name: VERSION
    description: The version
  - name: TOKEN
    description: A token
    secret: true
---

## Build

```sh run
cat "$STATE"
```

## Open <VERSION>

```confirm
Open the pull request.
```

```input
name: PR
description: The pull request number
```

```input
name: OTP
description: A one-time password
secret: true
```

```sh run
cat "$STATE"
```

## Publish

```sh run
cat "$STATE"
exit "${FAIL:-0}"
```
"""


class Prompter:
    """Answers inputs from answers in order, and every question with y unless replies says otherwise."""

    def __init__(self, answers=(), replies=()):
        self.answers = list(answers)
        self.replies = list(replies)

    def ask(self, input: Input, problem: str | None) -> str:
        return self.answers.pop(0)

    def confirm(self, question: str) -> str:
        reply = self.replies.pop(0) if self.replies else "y"
        if isinstance(reply, BaseException):
            raise reply
        return reply


def record(tmp_path, monkeypatch, prompter=None, *, text=RUNBOOK, saved=None, **options):
    """Run the runbook with a StateRecorder listening, returning the state path, the events and the result."""
    path = tmp_path / "project" / "RELEASING.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text(textwrap.dedent(text))
    saved_at = tmp_path / "state" / "key.json"
    monkeypatch.setenv("STATE", str(saved_at))
    monkeypatch.setenv("VERSION", "1.2.0")
    monkeypatch.setenv("TOKEN", "s3cret-token")
    for name in ("PR", "OTP"):  # FAIL is left as the test set it
        monkeypatch.delenv(name, raising=False)
    runbook = parse(path)
    recorder = state.StateRecorder(saved_at, runbook, path.parent, clock=lambda: STARTED, saved=saved or {})
    events: list[runner.Event] = []

    def sink(event: runner.Event) -> None:
        events.append(event)
        recorder(event)

    result = runner.run(
        runbook,
        load_backends(),
        sink,
        prompter or Prompter(["42", "123456"]),
        cwd=path.parent,
        saved=saved or {},
        **options,
    )
    return saved_at, events, result


def printed(events) -> list[dict]:
    """Each state file a block printed, as JSON."""
    text = "\n".join(event.text for event in events if isinstance(event, runner.OutputLine))
    decoder, found, index = json.JSONDecoder(), [], 0
    while (start := text.find("{", index)) != -1:
        value, index = decoder.raw_decode(text, start)
        found.append(value)
    return found


def test_recorder_saves_running_at_each_step_as_it_starts(tmp_path, monkeypatch):
    """A run killed outright can still resume at the step it was in."""
    _, events, _ = record(tmp_path, monkeypatch)

    assert [(seen["stopped"], seen["step"], seen["block"]) for seen in printed(events)] == [
        ("running", 0, 0),
        ("running", 1, 0),
        ("running", 2, 0),
    ]


def test_recorder_saves_where_the_run_is_and_what_it_is(tmp_path, monkeypatch):
    """The file names the runbook, the directory, when the run started and every step's name and hash."""
    _, events, _ = record(tmp_path, monkeypatch)

    [first, *_] = printed(events)
    project = (tmp_path / "project").resolve()
    runbook = parse(project / "RELEASING.md")
    assert first["version"] == 1
    assert first["runbook"] == str(project / "RELEASING.md")
    assert first["directory"] == str(project)
    assert first["started_at"] == "2026-11-13T14:02:11+00:00"
    assert first["steps"] == [{"name": step.name, "hash": state.step_hash(step)} for step in runbook.steps]


def test_recorder_deletes_the_state_when_the_run_finishes_ok(tmp_path, monkeypatch):
    saved_at, _, result = record(tmp_path, monkeypatch)

    assert result.status == "ok"
    assert not saved_at.exists()


def test_recorder_saves_a_failed_run_at_the_start_of_its_step(tmp_path, monkeypatch):
    monkeypatch.setenv("FAIL", "1")
    saved_at, _, result = record(tmp_path, monkeypatch)

    assert result.status == "failed"
    saved = state.RunState.load(saved_at, warn=pytest.fail)
    assert saved is not None
    assert (saved.stopped, saved.step, saved.block) == ("failed", 2, 0)


@pytest.mark.parametrize(
    ("reply", "stopped"), [("n", "aborted"), (KeyboardInterrupt(), "interrupted")], ids=["aborted", "interrupted"]
)
def test_recorder_saves_a_run_stopped_at_a_confirm_at_the_start_of_its_step(tmp_path, monkeypatch, reply, stopped):
    """A confirm answered no, or Ctrl-C at it, resumes at the start of the step, as a failure does."""
    saved_at, _, result = record(tmp_path, monkeypatch, Prompter(replies=["y", reply]))

    assert result.status == stopped
    saved = state.RunState.load(saved_at, warn=pytest.fail)
    assert saved is not None
    assert (saved.stopped, saved.step, saved.block) == (stopped, 1, 0)


class NoAnswer(Prompter):
    def ask(self, input: Input, problem: str | None) -> str:
        raise NeedsHumanInput

    def confirm(self, question: str) -> str:
        raise NeedsHumanInput


@pytest.mark.parametrize(("start", "block"), [(None, 0), ((1, 1), 1)], ids=["confirm", "input"])
def test_recorder_saves_a_run_that_needs_human_input_at_the_block_it_stopped_at(tmp_path, monkeypatch, start, block):
    """The next run carries on at that block, rather than at the start of its step."""
    saved_at, _, result = record(tmp_path, monkeypatch, NoAnswer(), start=start, ask_to_start=False)

    assert result.status == "needs_human_input"
    saved = state.RunState.load(saved_at, warn=pytest.fail)
    assert saved is not None
    assert (saved.stopped, saved.step, saved.block) == ("needs_human_input", 1, block)


@pytest.mark.parametrize("reply", ["n", KeyboardInterrupt()], ids=["aborted", "interrupted"])
def test_recorder_leaves_an_existing_state_alone_when_the_run_stops_at_start(tmp_path, monkeypatch, reply):
    """A run stopped at Start? hasn't started, so the last run's state is kept for the next one."""
    saved_at = tmp_path / "state" / "key.json"
    a_state().save(saved_at)
    before = saved_at.read_bytes()

    _, _, result = record(tmp_path, monkeypatch, Prompter(replies=[reply]))

    assert result.step is None
    assert saved_at.read_bytes() == before


def test_recorder_saves_plain_inputs_as_they_are_collected_and_never_secrets(tmp_path, monkeypatch):
    """Frontmatter values are saved from the first step, and an input block's as soon as it's answered."""
    _, events, _ = record(tmp_path, monkeypatch)

    assert [seen["inputs"] for seen in printed(events)] == [
        {"VERSION": "1.2.0"},
        {"VERSION": "1.2.0", "PR": "42"},
        {"VERSION": "1.2.0", "PR": "42"},
    ]


def test_recorder_carries_saved_values_forward(tmp_path, monkeypatch):
    """Values from steps done in an earlier run are kept, so resuming twice still has them."""
    monkeypatch.setenv("FAIL", "1")
    saved_at, _, result = record(
        tmp_path, monkeypatch, start=(2, 0), saved={"PR": "42", "GONE": "kept"}, prompter=Prompter(["123456"])
    )

    assert result.status == "failed"
    saved = state.RunState.load(saved_at, warn=pytest.fail)
    assert saved is not None
    assert saved.inputs == {"PR": "42", "GONE": "kept", "VERSION": "1.2.0"}


def test_recorder_never_saves_a_secret_named_in_saved(tmp_path, monkeypatch):
    """A secret's name is never a key, even if saved has one, e.g. from a runbook that's since made it secret."""
    monkeypatch.setenv("FAIL", "1")
    saved_at, _, _ = record(
        tmp_path, monkeypatch, start=(2, 0), saved={"PR": "42", "OTP": "old", "TOKEN": "old"}, prompter=Prompter(["1"])
    )

    saved = state.RunState.load(saved_at, warn=pytest.fail)
    assert saved is not None
    assert "OTP" not in saved.inputs and "TOKEN" not in saved.inputs


def test_no_secret_value_is_ever_in_the_state_file(tmp_path, monkeypatch):
    """Not a frontmatter secret, not a secret input block, and not a secret written into a step's name."""
    text = RUNBOOK.replace("## Open <VERSION>", "## Open s3cret-token")
    monkeypatch.setenv("FAIL", "1")

    saved_at, events, _ = record(tmp_path, monkeypatch, text=text)

    contents = [saved_at.read_text(), *(json.dumps(seen) for seen in printed(events))]
    for content in contents:
        assert "s3cret-token" not in content
        assert "123456" not in content
    assert json.loads(contents[0])["steps"][1]["name"] == "Open ****"


def test_recorder_lets_a_failed_save_end_the_run(tmp_path, monkeypatch):
    """Like a transcript that can't be written, a state that can't be saved is an error the caller reports."""
    path = tmp_path / "project" / "RELEASING.md"
    path.parent.mkdir()
    path.write_text("## Only\n\n```sh run\ntrue\n```\n")
    (tmp_path / "taken").write_text("a file where the directory should be")
    recorder = state.StateRecorder(tmp_path / "taken" / "key.json", parse(path), path.parent, saved={})

    with pytest.raises(state.StateError):
        runner.run(parse(path), load_backends(), recorder, Prompter(), cwd=path.parent)


def test_recorder_times_the_run_by_the_local_clock_by_default(tmp_path, monkeypatch):
    path = tmp_path / "RELEASING.md"
    path.write_text("## Only\n\n```sh run\nexit 1\n```\n")
    saved_at = tmp_path / "key.json"
    before = datetime.now().astimezone() - timedelta(seconds=1)

    runner.run(
        parse(path), load_backends(), state.StateRecorder(saved_at, parse(path), tmp_path), Prompter(), cwd=tmp_path
    )

    saved = state.RunState.load(saved_at, warn=pytest.fail)
    assert saved is not None
    assert datetime.fromisoformat(saved.started_at) >= before.replace(microsecond=0)


def test_a_saved_state_keeps_the_failed_blocks_exit_code(tmp_path):
    """So the next run can say how the last one failed."""
    path = tmp_path / "key.json"

    a_state(exit_code=3).save(path)

    assert json.loads(path.read_text())["exit_code"] == 3
    assert state.RunState.load(path, warn=pytest.fail) == a_state(exit_code=3)


def test_a_saved_state_without_an_exit_code_loads(tmp_path):
    """exit_code is null, or left out, for a run that didn't fail."""
    path = tmp_path / "key.json"
    data = documented()
    del data["exit_code"]
    path.write_text(json.dumps(data))

    loaded = state.RunState.load(path, warn=pytest.fail)

    assert loaded is not None and loaded.exit_code is None


@pytest.mark.parametrize("exit_code", ["1", True, 1.5])
def test_a_state_with_an_exit_code_that_is_not_an_int_warns_and_loads_as_none(tmp_path, exit_code):
    path = tmp_path / "key.json"
    path.write_text(json.dumps(documented() | {"exit_code": exit_code}))
    warnings: list[str] = []

    assert state.RunState.load(path, warn=warnings.append) is None
    assert warnings


def test_recorder_saves_the_exit_code_of_a_failed_run(tmp_path, monkeypatch):
    monkeypatch.setenv("FAIL", "4")
    saved_at, _, _ = record(tmp_path, monkeypatch)

    saved = state.RunState.load(saved_at, warn=pytest.fail)
    assert saved is not None and saved.exit_code == 4


def test_recorder_saves_no_exit_code_while_running(tmp_path, monkeypatch):
    _, events, _ = record(tmp_path, monkeypatch)

    assert {seen["exit_code"] for seen in printed(events)} == {None}
