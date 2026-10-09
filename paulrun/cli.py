import sys
from dataclasses import dataclass
from pathlib import Path

import click
from rich.console import Console

from paulrun import runner, settings
from paulrun.backends import BackendError, load_backends
from paulrun.inputs import Input, InputError
from paulrun.runbook import RunbookError, parse


@click.group("paulrun")
@click.version_option(settings.VERSION)
def cli() -> None:
    """Run hand-written markdown runbooks."""


@cli.command()
@click.argument("runbook", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--dry", is_flag=True, help="Show every block with inputs filled in, without running anything.")
def go(runbook: Path, dry: bool) -> None:
    """Run a runbook's steps in order, stopping at the first that fails."""
    console = Console(highlight=False)
    try:
        result = runner.run(
            parse(runbook),
            load_backends(),
            lambda event: _print_event(console, event, dry=dry),
            ClickPrompter(console),
            dry=dry,
        )
    except (RunbookError, BackendError, runner.RunnerError, InputError) as e:
        raise click.ClickException(str(e)) from e
    if result.status not in ("ok", "dry"):
        sys.exit(1)


@dataclass(frozen=True)
class ClickPrompter:
    """Prompts in the terminal, hiding what's typed for secrets."""

    console: Console

    def ask(self, input: Input, problem: str | None) -> str:
        if problem is not None:
            # console.out, because a pattern such as [a-z] would be read as markup.
            self.console.out(problem, style="red")
        return click.prompt(f"{input.name} ({input.description})", hide_input=input.secret)

    def confirm(self, question: str) -> str:
        # An empty default lets enter through as "", which the runner reads as no.
        return click.prompt(question, default="", show_default=False, prompt_suffix=" ")


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
        case runner.Confirm(text=text):
            for line in text.splitlines():
                console.out(line, style="yellow")
        case runner.BlockStarted(code=code):
            for index, line in enumerate(code.splitlines()):
                console.out(f"{'$' if index == 0 else ' '} {line}", style="cyan")
        case runner.OutputLine(text=text):
            console.out(text)
        case runner.BlockFinished(exit_code=exit_code, duration=duration):
            console.out(f"exit {exit_code} ({_duration(duration)})", style="green" if exit_code == 0 else "red")
        case runner.RunFinished(status="ok", duration=duration):
            console.out()
            console.out(f"finished: ok ({_duration(duration)})", style="green")
        case runner.RunFinished(status="dry"):
            console.out()
            console.out("finished: dry run, nothing was run", style="yellow")
        case runner.RunFinished(status="aborted", step=step):
            console.out()
            where = "before starting" if step is None else f'at "{step.name}"'
            console.out(f"finished: aborted {where}", style="red")
        case runner.RunFinished(step=step, exit_code=exit_code):
            assert step is not None  # always set when a run fails
            console.out()
            console.out(f'finished: failed at "{step.name}" (exit {exit_code})', style="red")


def _duration(seconds: float) -> str:
    """Tenths of a second under a minute, e.g. 4.2s, then minutes and seconds, e.g. 3m12s."""
    if round(seconds, 1) < 60:
        return f"{seconds:.1f}s"
    minutes, seconds = divmod(round(seconds), 60)
    return f"{minutes}m{seconds:02d}s"
