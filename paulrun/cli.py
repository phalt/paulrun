import os
import sys
from contextlib import nullcontext
from dataclasses import dataclass
from importlib.metadata import EntryPoint
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.text import Text

from paulrun import library, runner, settings
from paulrun.backends import Backend, BackendError, load_backend_sources, load_backends
from paulrun.inputs import Input, InputError
from paulrun.runbook import Runbook, RunbookError, parse, parse_inputs, read_frontmatter
from paulrun.transcript import Transcript, TranscriptError
from paulrun.validate import Report, validate


class RunsByDefault(click.Group):
    """A group where anything that isn't a command is a runbook to run, so paulrun X is paulrun run X.

    Command names always win, so a book called check.md is run with paulrun run check. With nothing at all,
    the group shows its help.
    """

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        if not args:
            click.echo(ctx.get_help())
            ctx.exit(0)
        if args[0] not in self.commands and args[0] not in ctx.help_option_names and args[0] != "--version":
            args = ["run", *args]
        return super().parse_args(ctx, args)


@click.group("paulrun", cls=RunsByDefault, subcommand_metavar="RUNBOOK | COMMAND [ARGS]...")
@click.version_option(settings.VERSION)
def cli() -> None:
    """Run hand-written markdown runbooks.

    paulrun RUNBOOK executes a runbook.
    """


class RunbookArgument(click.ParamType):
    """A runbook given as a path to a file, or by the name of a book in the runbook library."""

    name = "runbook"

    def convert(self, value: Any, param: click.Parameter | None, ctx: click.Context | None) -> Path:
        if isinstance(value, Path):
            return value
        where = library.location(os.environ)
        found = library.find(value, Path.cwd(), where)
        if found is not None:
            return found
        if "/" in value:
            self.fail(f"no such file: {value}", param, ctx)
        book = value if value.endswith(".md") else f"{value}.md"
        self.fail(f"no runbook {value!r}: no such file here, and no {book} in the library at {where}", param, ctx)


@cli.command("run")
@click.argument("runbook", type=RunbookArgument(), required=False)
@click.option("--dry", is_flag=True, help="Show every block with inputs filled in, without running anything.")
@click.option("--step", is_flag=True, help="Ask before each run block whether to run it, skip it or quit.")
def run_runbook(runbook: Path | None, dry: bool, step: bool) -> None:
    """Run a runbook's steps in order, stopping at the first that fails. Blocks run in the current directory.

    RUNBOOK is a file, or the name of a book in your runbook library: ~/runbooks, or $PAULRUN_LIBRARY.
    With no RUNBOOK, pick a book from the library. paulrun RUNBOOK, with no command, does the same.
    """
    console = Console(highlight=False)
    if runbook is None:
        runbook = _pick(console)
    parsed, backends, report = _validated(runbook)
    _print_report(console, runbook, report, summary_if_ok=False)
    if not report.ok:
        sys.exit(1)
    # Blocks and the transcript both go where paulrun was started.
    cwd = Path.cwd()
    # Nothing runs under --dry, so there's nothing to record.
    transcript = Transcript.for_runbook(parsed, cwd) if parsed.output_path is not None and not dry else None

    def sink(event: runner.Event) -> None:
        _print_event(console, event, dry=dry)
        if transcript is not None:
            transcript(event)

    try:
        with transcript or nullcontext():
            result = runner.run(parsed, backends, sink, ClickPrompter(console), cwd=cwd, dry=dry, step_by_step=step)
    except (runner.RunnerError, InputError, TranscriptError) as e:
        raise click.ClickException(str(e)) from e
    if transcript is not None and transcript.written:
        assert transcript.path is not None  # set once the run started, which it has if anything was written
        console.out(f"transcript: {_shown_from(transcript.path, cwd)}")
    if result.status not in ("ok", "dry"):
        sys.exit(1)


def _pick(console: Console) -> Path:
    """List the library's books by number and ask which to run, until the answer is one of the numbers.

    A blank answer or Ctrl-C runs nothing and exits 1, like answering no to Start?.
    """
    where = library.location(os.environ)
    books = library.books(where)
    if not books:
        raise click.ClickException(
            f"no books in the library at {where} to pick from. "
            f"Give a runbook to run, or set {library.LIBRARY_VARIABLE} to where yours are."
        )
    width = max(len(book.name) for book in books)
    numbers = len(str(len(books)))
    for number, book in enumerate(books, start=1):
        _line(console, Text.assemble((f"  {number:>{numbers}}.", "dim"), " ", _book_line(book, width)))
    question = _styled(console, Text("Run which?", style="bold"))
    while True:
        try:
            answer = _prompt(question, default="", show_default=False, prompt_suffix=" ").strip()
        except KeyboardInterrupt:
            sys.exit(1)
        if not answer:
            sys.exit(1)
        if answer.isdigit() and 1 <= int(answer) <= len(books):
            return books[int(answer) - 1].path
        console.out(f"Pick a number from 1 to {len(books)}.", style="red")


def _shown_from(path: Path, cwd: Path) -> Path:
    """path relative to cwd if it's inside it, so it's short and works from there, otherwise as it is."""
    return path.relative_to(cwd) if path.is_relative_to(cwd) else path


@cli.command()
@click.argument("runbook", type=RunbookArgument())
def check(runbook: Path) -> None:
    """Check a runbook for problems without running anything. Exits 1 if there are any errors.

    RUNBOOK is a file, or the name of a book in your runbook library: ~/runbooks, or $PAULRUN_LIBRARY.
    """
    console = Console(highlight=False)
    _, _, report = _validated(runbook)
    _print_report(console, runbook, report, summary_if_ok=True)
    if not report.ok:
        sys.exit(1)


@cli.command()
@click.argument("runbook", type=RunbookArgument())
def inputs(runbook: Path) -> None:
    """List the inputs a runbook needs, including ones its input blocks ask for part way through.

    Frontmatter inputs are listed even if the rest of the runbook is broken. RUNBOOK is a file, or the name
    of a book in your runbook library: ~/runbooks, or $PAULRUN_LIBRARY.
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
        padding = " " * (width - len(input.name) + 2)
        _line(console, Text.assemble((input.name, "bold cyan"), padding, input.description))
        details = [f"default: {input.default}"] if input.default is not None else []
        details += [f"choices: {', '.join(input.choices)}"] if input.choices else []
        details += [f"pattern: {input.pattern}"] if input.pattern is not None else []
        details += ["secret"] if input.secret else []
        details += [f'asked in "{step}"'] if step is not None else []
        for detail in details:
            # Details are dim, apart from secret, which is worth noticing.
            _line(console, Text.assemble(" " * (width + 2), (detail, "yellow" if detail == "secret" else "dim")))


@cli.command("library")
def list_library() -> None:
    """List the books in your runbook library, with each one's title and description.

    The library is ~/runbooks, or $PAULRUN_LIBRARY. Run a book from it by name, e.g. paulrun deploy.
    """
    console = Console(highlight=False)
    where = library.location(os.environ)
    books = library.books(where)
    if not books:
        console.out(f"no books in the library at {where}")
        console.out(f"Add runbooks there, or set {library.LIBRARY_VARIABLE} to where yours are.")
        return
    console.out(f"library: {where}", style="dim")
    width = max(len(book.name) for book in books)
    for book in books:
        _line(console, _book_line(book, width))
        if book.description is not None:
            _line(console, Text.assemble(" " * (width + 2), (book.description, "dim")))
        # Command names win, so paulrun <name> wouldn't run this book.
        if book.name in cli.commands:
            note = f"run it with paulrun run {book.name}, since paulrun {book.name} is a command"
            _line(console, Text.assemble(" " * (width + 2), (note, "yellow")))


def _book_line(book: library.Book, width: int) -> Text:
    """A book's name, padded to width, then its title, or why it can't be read. Just the name if it has neither.

    The name is bold cyan, since it's what you type to run the book.
    """
    if book.problem is not None:
        heading: str | tuple[str, str] | None = (f"can't read it: {book.problem}", "red")
    else:
        heading = book.title or None
    if heading is None:
        return Text(book.name, style="bold cyan")
    return Text.assemble((book.name, "bold cyan"), " " * (width - len(book.name) + 2), heading)


def _line(console: Console, line: Text) -> None:
    """Print a line made of styled parts. Text in it is never read as markup or emoji, and never wrapped."""
    console.print(line, soft_wrap=True, emoji=False, markup=False, highlight=False)


def _styled(console: Console, text: Text) -> str:
    """text as the console would print it, for a Click prompt: in colour in a terminal, plain otherwise."""
    with console.capture() as capture:
        console.print(text, end="", soft_wrap=True, emoji=False, markup=False, highlight=False)
    return capture.get()


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
        prompt = Text(f"{input.name} ({input.description})")
        if input.default is not None:
            prompt.append(" ").append(f"[{input.default}]", style="dim")
        if input.choices:
            prompt.append(" ").append(f"({', '.join(input.choices)})", style="dim")
        text = _styled(self.console, prompt)
        if input.default is None:
            return _prompt(text, hide_input=input.secret)
        # Enter gives "" rather than the default, so collect applies the default and checks it like any answer.
        return _prompt(text, default="", show_default=False, hide_input=input.secret)

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
        case runner.Overview(title=title, steps=steps, run_blocks=run_blocks, inputs=inputs, directory=directory):
            console.out(title, style="bold")
            console.out(f"directory: {directory}")
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
