"""Tests for loading backends from entry points."""

from importlib.metadata import EntryPoint

import pytest

from paulrun import backends
from paulrun.backends.shell import ShellBackend


class FakeBackend:
    name = "fake"
    languages = ("fake", "fk")

    def validate(self, code):
        return []

    def run(self, code, *, frontmatter, env, cwd, output):
        return 0


class RivalShellBackend:
    name = "rival"
    languages = ("zsh", "sh")

    def validate(self, code):
        return []

    def run(self, code, *, frontmatter, env, cwd, output):
        return 0


def entry_point(name: str, cls: type) -> EntryPoint:
    """An entry point for a class defined in this module, as if a package had registered it."""
    return EntryPoint(name=name, value=f"{__name__}:{cls.__name__}", group="paulrun.backends")


def test_plain_classes_satisfy_the_backend_protocol():
    """A backend needs no base class or annotations, just the right attributes and methods."""
    fake: backends.Backend = FakeBackend()

    assert fake.name == "fake"


def test_load_backends_finds_shell_backend_from_installed_entry_points():
    """paulrun's own pyproject.toml registers the shell backend for sh, bash and shell."""
    loaded = backends.load_backends()

    assert isinstance(loaded["sh"], ShellBackend)
    assert loaded["sh"] is loaded["bash"] is loaded["shell"]


def test_load_backends_maps_every_language_to_its_backend():
    """A backend is listed once for each language it claims."""
    loaded = backends.load_backends([entry_point("fake", FakeBackend)])

    assert set(loaded) == {"fake", "fk"}
    assert isinstance(loaded["fake"], FakeBackend)
    assert loaded["fake"] is loaded["fk"]


def test_load_backends_uses_only_the_entry_points_given():
    """Passing entry points replaces the installed ones, so the shell backend isn't loaded."""
    loaded = backends.load_backends([entry_point("fake", FakeBackend)])

    assert "sh" not in loaded


def test_load_backends_rejects_two_backends_claiming_one_language():
    """When two backends claim one language, the error names both, with where each came from."""
    entry_points = [
        EntryPoint(name="shell", value="paulrun.backends.shell:ShellBackend", group="paulrun.backends"),
        entry_point("rival", RivalShellBackend),
    ]

    with pytest.raises(backends.BackendError) as error:
        backends.load_backends(entry_points)

    assert str(error.value) == (
        "language 'sh' is claimed by both 'shell' (paulrun.backends.shell:ShellBackend) "
        f"and 'rival' ({__name__}:RivalShellBackend)"
    )
