import sys
from contextlib import nullcontext
from dataclasses import dataclass
from importlib.metadata import EntryPoint
from pathlib import Path
from typing import Any

import click
from rich.console import Console

from paulrun import runner, settings
from paulrun.backends import Backend, BackendError, load_backend_sources, load_backends
from paulrun.inputs import Input, InputError
from paulrun.runbook import Runbook, RunbookError, parse, parse_inputs, read_frontmatter
from paulrun.transcript import Transcript, TranscriptError
from paulrun.validate import Report, validate


@click.group("paulrun")
@click.version_option(settings.VERSION)
def cli() -> None:
    """Run hand-written markdown runbooks."""


@cli.command()
@click.argument("runbook", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--dry", is_flag=True, help="Show every block with inputs filled in, without running anything.")
@click.option("--step", is_flag=True, help="Ask before each run block whether to run it, skip it or quit.")
def go(runbook: Path, dry: bool, step: bool) -> None:
    """Run a runbook's steps in order, stopping at the first that fails."""
    console = Console(highlight=False)
    parsed, backends, report = _validated(runbook)
    _print_report(console, runbook, report, summary_if_ok=False)
    if not report.ok:
        sys.exit(1)
    # Nothing runs under --dry, so there's nothing to record.
    transcript = Transcript.for_runbook(parsed) if parsed.output_path is not None and not dry else None

    def sink(event: runner.Event) -> None:
        _print_event(console, event, dry=dry)
        if transcript is not None:
            transcript(event)

    try:
        with transcript or nullcontext():
            result = runner.run(parsed, backends, sink, ClickPrompter(console), dry=dry, step_by_step=step)
    except (runner.RunnerError, InputError, TranscriptError) as e:
        raise click.ClickException(str(e)) from e
    if transcript is not None and transcript.written:
        console.out(f"transcript: {transcript.path}")
    if result.status not in ("ok", "dry"):
        sys.exit(1)


@cli.command()
@click.argument("runbook", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def check(runbook: Path) -> None:
    """Check a runbook for problems without running anything. Exits 1 if there are any errors."""
    console = Console(highlight=False)
    _, _, report = _validated(runbook)
    _print_report(console, runbook, report, summary_if_ok=True)
    if not report.ok:
        sys.exit(1)


@cli.command()
@click.argument("runbook", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def inputs(runbook: Path) -> None:
    """List the inputs a runbook needs, including ones its input blocks ask for part way through.

    Frontmatter inputs are listed even if the rest of the runbook is broken.
    """
    console = Console(highlight=False)
    try:
        declared: list[tuple[Input, str | None]] = [
            (input, None) for input in parse_inputs(read_frontmatter(runbook).get("inputs"))
        ]
    except RunbookError as e:
        raise click.ClickException(str(e)) from e
    declared += _input_blocks(runbook)
    if not declared:
        console.out("no inputs")
        return
    width = max(len(input.name) for input, _ in declared)
    for input, step in declared:
        console.out(f"{input.name:<{width}}  {input.description}")
        details = [f"pattern: {input.pattern}"] if input.pattern is not None else []
        details += ["secret"] if input.secret else []
        details += [f'asked in "{step}"'] if step is not None else []
        for detail in details:
            console.out(f"{'':<{width}}  {detail}")


def _input_blocks(path: Path) -> list[tuple[Input, str | None]]:
    """The inputs a runbook's input blocks declare, with the step each is in. Nothing if the body can't be read."""
    try:
        parsed = parse(path)
    except RunbookError:
        return []
    return [(block.input, step.name) for step in parsed.steps for block in step.blocks if block.input is not None]


@cli.command("backends")
def list_backends() -> None:
    """List the installed backends, the languages each runs, and the package that registered it."""
    console = Console(highlight=False)
    try:
        sources = sorted(load_backend_sources(), key=lambda source: source.backend.name)
    except BackendError as e:
        raise click.ClickException(str(e)) from e
    rows = [
        (source.backend.name, ", ".join(source.backend.languages), _registered_by(source.entry_point))
        for source in sources
    ]
    name_width = max((len(name) for name, _, _ in rows), default=0)
    languages_width = max((len(languages) for _, languages, _ in rows), default=0)
    for name, languages, registered_by in rows:
        console.out(f"{name:<{name_width}}  {languages:<{languages_width}}  {registered_by}")


def _registered_by(entry_point: EntryPoint) -> str:
    """The entry point's target, with the package and version that registered it when that's known."""
    if entry_point.dist is None:
        return entry_point.value
    return f"{entry_point.value} ({entry_point.dist.name} {entry_point.dist.version})"


def _validated(path: Path) -> tuple[Runbook, dict[str, Backend], Report]:
    """Parse and validate a runbook, turning anything that stops it being read into a clean error."""
    try:
        parsed = parse(path)
        backends = load_backends()
    except (RunbookError, BackendError) as e:
        raise click.ClickException(str(e)) from e
    return parsed, backends, validate(parsed, backends)


def _print_report(console: Console, path: Path, report: Report, *, summary_if_ok: bool) -> None:
    """Print each finding as path:line: kind: message, then a count. A clean report prints only if asked."""
    if not report.findings:
        if summary_if_ok:
            console.out(f"{path}: ok", style="green")
        return
    for finding in report.findings:
        kind, style = ("warning", "yellow") if finding.warning else ("error", "red")
        console.out(f"{path}:{finding.line}: {kind}: {finding.message}", style=style)
    counts = [_count(len(report.errors), "error"), _count(len(report.warnings), "warning")]
    console.out()
    console.out(", ".join(count for count in counts if count), style="bold")


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}{'' if number == 1 else 's'}" if number else ""


@dataclass(frozen=True)
class ClickPrompter:
    """Prompts in the terminal, hiding what's typed for secrets."""

    console: Console

    def ask(self, input: Input, problem: str | None) -> str:
        if problem is not None:
            # console.out, because a pattern such as [a-z] would be read as markup.
            self.console.out(problem, style="red")
        return _prompt(f"{input.name} ({input.description})", hide_input=input.secret)

    def confirm(self, question: str) -> str:
        # An empty default lets enter through as "", which the runner reads as no.
        return _prompt(question, default="", show_default=False, prompt_suffix=" ")


def _prompt(text: str, **options: Any) -> str:
    """click.prompt, but Ctrl-C raises KeyboardInterrupt so the runner can finish the run as interrupted.

    Click turns both Ctrl-C and running out of input into Abort; only Ctrl-C is turned back.
    """
    try:
        return click.prompt(text, **options)
    except click.Abort as e:
        if isinstance(e.__context__, KeyboardInterrupt):
            raise KeyboardInterrupt from None
        raise


def _print_event(console: Console, event: runner.Event, *, dry: bool = False) -> None:
    # console.out never reads markup or emoji codes and never wraps, so code and output appear as written.
    match event:
        case runner.Overview(title=title, steps=steps, run_blocks=run_blocks, inputs=inputs):
            console.out(title, style="bold")
            if inputs:
                console.out("inputs: " + " ".join(f"{name}={value}" for name, value in inputs))
            for number, step in enumerate(steps, start=1):
                console.out(f"  {number}. {step.name}")
            console.out(f"{run_blocks} run block{'' if run_blocks == 1 else 's'}")
            if dry:
                console.out("dry run: nothing will be run", style="yellow")
        case runner.StepStarted(step=step):
            console.out()
            console.out(f"=== {step.name} ===", style="bold")
        case runner.Docstring(text=text):
            for line in text.splitlines():
                console.out(line)
        case runner.InputBlock(input=input) if dry:
            console.out(f"input: {input.name} ({input.description}), asked here", style="yellow")
        case runner.Confirm(text=text):
            for line in text.splitlines():
                console.out(line, style="yellow")
        case runner.BlockStarted(code=code):
            for line in runner.code_lines(code):
                console.out(line, style="cyan")
        case runner.BlockSkipped():
            console.out("skipped (--step)", style="yellow")
        case runner.OutputLine(text=text):
            console.out(text)
        case runner.BlockFinished(exit_code=exit_code, duration=duration):
            console.out(
                f"exit {exit_code} ({runner.format_duration(duration)})", style="green" if exit_code == 0 else "red"
            )
        case runner.RunFinished(status="ok", duration=duration):
            console.out()
            console.out(f"finished: ok ({runner.format_duration(duration)})", style="green")
        case runner.RunFinished(status="dry"):
            console.out()
            console.out("finished: dry run, nothing was run", style="yellow")
        case runner.RunFinished(status="aborted" | "interrupted" as status, step=step):
            console.out()
            where = "before starting" if step is None else f'at "{step.name}"'
            console.out(f"finished: {status} {where}", style="red")
        case runner.RunFinished(step=step, exit_code=exit_code):
            assert step is not None  # always set when a run fails
            console.out()
            console.out(f'finished: failed at "{step.name}" (exit {exit_code})', style="red")
