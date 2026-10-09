import sys
from pathlib import Path

import click
from rich.console import Console

from paulrun import runner, settings
from paulrun.backends import BackendError, load_backends
from paulrun.runbook import RunbookError, parse


@click.group("paulrun")
@click.version_option(settings.VERSION)
def cli() -> None:
    """Run hand-written markdown runbooks."""


@cli.command()
@click.argument("runbook", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def go(runbook: Path) -> None:
    """Run a runbook's steps in order, stopping at the first that fails."""
    console = Console(highlight=False)
    try:
        result = runner.run(parse(runbook), load_backends(), lambda event: _print_event(console, event))
    except (RunbookError, BackendError, runner.RunnerError) as e:
        raise click.ClickException(str(e)) from e
    if result.status != "ok":
        sys.exit(1)


def _print_event(console: Console, event: runner.Event) -> None:
    # console.out never reads markup or emoji codes and never wraps, so code and output appear as written.
    match event:
        case runner.StepStarted(step=step):
            console.out()
            console.out(f"=== {step.name} ===", style="bold")
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
