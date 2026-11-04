import os
import sys
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime
from importlib.metadata import EntryPoint
from pathlib import Path
from typing import Any

import click
from rich.box import ROUNDED
from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from paulrun import library, runner, settings
from paulrun.backends import Backend, BackendError, load_backend_sources, load_backends
from paulrun.inputs import Input, InputError
from paulrun.runbook import Runbook, RunbookError, Step, parse, parse_inputs, read_frontmatter
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


PAULRUN_HEADER = r"""
   ___            _
  / _ \__ _ _   _| |_ __ _   _ _ __
 / /_)/ _` | | | | | '__| | | | '_ \
/ ___/ (_| | |_| | | |  | |_| | | | |
\/    \__,_|\__,_|_|_|   \__,_|_| |_|
""".strip("\n")

# \b stops Click rewrapping the header, which would break it apart. The paragraphs after it wrap as normal.
HELP = f"""\b
{PAULRUN_HEADER}

🏃‍♂️‍➡️📕 paulrun runs hand-written markdown runbooks.

🔢 Version {settings.VERSION}

📚 Read the docs: https://phalt.github.io/paulrun/

🐙 Contribute on GitHub: https://github.com/phalt/paulrun

paulrun RUNBOOK executes a runbook.
"""


@click.group("paulrun", cls=RunsByDefault, subcommand_metavar="RUNBOOK | COMMAND [ARGS]...", help=HELP)
@click.version_option(settings.VERSION)
def cli() -> None:
    pass


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
@click.option(
    "--step/--no-step",
    default=None,
    help="Ask before each run block whether to run it, skip it or quit. "
    "--no-step runs straight through, even if the runbook sets step: true.",
)
@click.option("--show-code", is_flag=True, help="Show each block's code above its output. --dry always shows it.")
def run_runbook(runbook: Path | None, dry: bool, step: bool | None, show_code: bool) -> None:
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

    # --step or --no-step wins; with neither, the runbook's step key decides.
    step_by_step = parsed.step if step is None else step
    printer = _Printer(console, dry=dry, show_code=show_code or dry)

    def sink(event: runner.Event) -> None:
        printer(event)
        if transcript is not None:
            transcript(event)

    try:
        with transcript or nullcontext():
            result = runner.run(
                parsed, backends, sink, ClickPrompter(console), cwd=cwd, dry=dry, step_by_step=step_by_step
            )
    except (runner.RunnerError, InputError, TranscriptError) as e:
        raise click.ClickException(str(e)) from e
    if transcript is not None and transcript.written:
        assert transcript.path is not None  # set once the run started, which it has if anything was written
        console.out(f"transcript: {_shown_from(transcript.path, cwd)}")
    if result.status not in ("ok", "dry"):
        sys.exit(1)


def _pick(console: Console) -> Path:
    """List the library's books by number and ask which to run, until the answer is one of the numbers.

    q, a blank answer or Ctrl-C runs nothing and exits 1, like answering no to Start?.
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
    question = _styled(console, Text.assemble(("Run which?", "bold"), " ", ("(q to quit)", "dim")))
    while True:
        try:
            answer = _prompt(question, default="", show_default=False, prompt_suffix=" ").strip()
        except KeyboardInterrupt:
            sys.exit(1)
        if answer in ("", "q"):
            sys.exit(1)
        if answer.isdigit() and 1 <= int(answer) <= len(books):
            return books[int(answer) - 1].path
        console.out(f"Pick a number from 1 to {len(books)}, or q to quit.", style="red")


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
        if question == runner.STEP_QUESTION:
            # Asked inside the block's bracket, between its heading and its output.
            question = _styled(self.console, Text.assemble(("  ├ ", FRAME), question))
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


# One meaning per colour: blue is structure, green success, yellow a confirm or a dry run, red failure only.
STRUCTURE = "blue"
FRAME = "dim"


def block_time(at: datetime) -> str:
    """When a block started, as its bracket shows it: the local time to the millisecond."""
    return at.strftime("%H:%M:%S.") + f"{at.microsecond // 1000:03d}"


def _now() -> datetime:
    return datetime.now().astimezone()


@dataclass
class _Printer:
    """Prints run events in the terminal: the overview and the end in boxes, each step under a rule, and each
    block's output in a bracket closed by its result."""

    console: Console
    dry: bool = False
    show_code: bool = False
    steps: tuple[Step, ...] = ()
    in_output: bool = False  # whether the current block's output has started, to put ├ output before it
    under_rule: bool = False  # whether nothing has been printed since the step's rule
    in_block: bool = False  # whether a block's bracket is open, so the run ending part way through closes it

    def __call__(self, event: runner.Event) -> None:
        self._print(event)
        self.under_rule = isinstance(event, runner.StepStarted)

    def _print(self, event: runner.Event) -> None:
        # Everything from the runbook or a block is Text, so it's never read as markup or emoji, and never wrapped.
        match event:
            case runner.Overview(title=title, steps=steps, run_blocks=run_blocks, inputs=inputs, directory=directory):
                self.steps = steps
                self._overview(title, steps, run_blocks, inputs, directory)
                if self.dry:
                    self.console.out("dry run: nothing will be run", style="yellow")
            case runner.StepStarted(step=step):
                number = self.steps.index(step) + 1
                self.console.print()
                heading = Text(f"{number}/{len(self.steps)}  {step.name}", style=f"bold {STRUCTURE}")
                self.console.print(Rule(heading, align="left", style=STRUCTURE, characters="━"))
            case runner.Docstring(text=text):
                for line in text.splitlines():
                    self._line(("  ", ""), (line, "dim italic"))
            case runner.InputBlock(input=input) if self.dry:
                self.console.print()
                self._line(("  ", ""), (f"input: {input.name} ({input.description}), asked here", "yellow"))
            case runner.Confirm(text=text):
                if not self.under_rule:
                    self.console.print()
                title = Text("confirm", style="bold yellow")
                self._box(Text(text.rstrip("\n"), style="yellow"), "yellow", title=title)
            case runner.BlockStarted(block=block, code=code):
                self.console.print()
                # Nothing runs under --dry, so there's no time it started.
                started = "" if self.dry else f" · {block_time(_now())}"
                self._line(("  ┌ ", FRAME), (block.language or "", "bold"), (started, FRAME))
                if self.show_code:
                    for line in code.splitlines():
                        self._line(("  │", FRAME), (f" {line}" if line else "", "cyan"))
                self.in_block = True
                if self.dry:
                    self._not_run()
                self.in_output = False
            case runner.BlockSkipped():
                self.in_block = False
                self._line(("  └ ", FRAME), ("↷ skipped", "yellow"))
            case runner.OutputLine(text=text, stderr=stderr):
                if self.show_code and not self.in_output:
                    self._line(("  ├ output", FRAME))
                self.in_output = True
                # Only the bar is red for stderr, so the line stays as readable as any other.
                self._line(("  │", "red" if stderr else FRAME), (f" {text}" if text else "", ""))
            case runner.BlockFinished(exit_code=exit_code, duration=duration):
                self.in_block = False
                mark, style = ("✓", "green") if exit_code == 0 else ("✗", "red")
                self._line(
                    ("  └ ", FRAME),
                    (f"{mark} exit {exit_code}", style),
                    (f" · {runner.format_duration(duration)}", FRAME),
                )
            case runner.RunFinished() if self.in_block:
                # Quit, or Ctrl-C, at --step's question: the block never ran.
                self._not_run()
                self._print(event)
            case runner.RunFinished(status="ok", duration=duration):
                self._finished("✓", "green", "finished ok", duration)
            case runner.RunFinished(status="dry"):
                self._finished("", "yellow", "dry run, nothing was run")
            case runner.RunFinished(status="aborted" | "interrupted" as status, step=step):
                where = "before starting" if step is None else f'at "{step.name}"'
                self._finished("✗", "red", f"{status} {where}")
            case runner.RunFinished(step=step, exit_code=exit_code, duration=duration):
                assert step is not None  # always set when a run fails
                self._finished("✗", "red", f'failed at "{step.name}" (exit {exit_code})', duration)

    def _not_run(self) -> None:
        self.in_block = False
        self._line(("  └ ", FRAME), ("not run", "yellow"))

    def _overview(
        self,
        title: str,
        steps: tuple[Step, ...],
        run_blocks: int,
        inputs: tuple[tuple[str, str], ...],
        directory: Path,
    ) -> None:
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style=FRAME)
        # Fold rather than cut a value too long for the box, so a long directory is still shown whole.
        grid.add_column(overflow="fold")
        grid.add_row(Text("directory"), Text(str(directory)))
        if inputs:
            grid.add_row(Text("inputs"), Text(" ".join(f"{name}={value}" for name, value in inputs)))
        numbered = "\n".join(f"{number}. {step.name}" for number, step in enumerate(steps, start=1))
        grid.add_row(Text("steps"), Text(numbered))
        grid.add_row(Text("blocks"), Text(f"{run_blocks} run block{'' if run_blocks == 1 else 's'}"))
        self._box(grid, STRUCTURE, title=Text(title, style=f"bold {STRUCTURE}"))

    def _finished(self, mark: str, style: str, text: str, duration: float | None = None) -> None:
        line = Text.assemble((f"{mark} " if mark else "", style), (text, "bold"))
        if duration is not None:
            line.append(f" · {runner.format_duration(duration)}", style=FRAME)
        self.console.print()
        self._box(line, style)

    def _box(self, content: RenderableType, style: str, *, title: Text | None = None) -> None:
        self.console.print(
            Panel(content, title=title, title_align="left", border_style=style, box=ROUNDED, expand=False)
        )

    def _line(self, *parts: tuple[str, str]) -> None:
        _line(self.console, Text.assemble(*parts))
