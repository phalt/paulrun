# Contributing

First things first: thank you for contributing! This project will be successful thanks to everyone who contributes, and we're happy to have you.

## AI disclosure

Within rundot we use coding agents to prototype and build out ideas, and then take the idea to fruition using human reviewed and approved code.

You, the human and the author of changes are responsible for the contributions, and if you cannot confidently explain or demonstrate understanding of the changes you are contributing, then they will not be accepted.

## Bug or issue?

To raise a bug or issue please use [our GitHub](https://github.com/phalt/rundot/issues).

Please check the issue has not been raised before by using the search feature.

When submitting an issue or bug, please make sure you provide thorough detail on:

1. The version of rundot you are using (`rundot --version`)
2. Your operating system and Python version
3. Any errors or outputs you see in your terminal
4. The smallest runbook that shows the problem (this is particularly important). Take out any secrets first!

## Contribution

If you want to directly contribute you can do so in two ways:

1. Documentation
2. Code

### Documentation

We use [Zensical](https://zensical.org/) and [GitHub pages](https://pages.github.com/) to deploy our docs.

Fixing grammar, spelling mistakes, or expanding the documentation to cover features that are not yet documented, are all valuable contributions.

Please see the **Set up** instructions below to run the docs locally on your computer, then:

```sh
make docs-serve
```

The examples in the docs and the README are tested, so if you change one, run `make test` too.

### Code

Contribution by writing code for new features, or fixing bugs, is a great way to contribute to the project.

Please [open an issue](https://github.com/phalt/rundot/issues) to talk it through before changing the runbook format (frontmatter keys, what a fence does, placeholders or the transcript), adding a command or flag, or adding a dependency. These are hard to change once people's runbooks rely on them.

#### Set up

Clone the repo:

```sh
git clone git@github.com:phalt/rundot.git
cd rundot
```

Move to a feature branch:

```sh
git switch -c my-branch-name
```

Install UV (if not already installed):

```sh
# On macOS and Linux:
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or using pip:
pip install uv
```

Install all the dependencies:

```sh
make install
```

This will use UV to create a virtual environment and install all dependencies, including rundot itself, so its built-in backends are registered. UV handles the virtual environment automatically, so you don't need to manually activate it.

To make sure you have things set up correctly, please run the tests:

```sh
make test
```

You can run your copy of rundot with `uv run rundot`, e.g. on one of the example runbooks in `tests/runbooks/`:

```sh
uv run rundot tests/runbooks/two_steps.md
```

Run `make help` to see every command.

### Adding a backend

rundot runs shell and Python blocks out of the box. To add another language to rundot itself:

1. Write `rundot/backends/<name>.py`, implementing the backend protocol
2. Add one entry point line for it in `pyproject.toml`, then run `make install`
3. Write `tests/backends/test_<name>.py`, which really runs blocks (skipped if the language isn't installed)
4. Add a section about it to `docs/backends.md`
5. Add a CHANGELOG entry

[docs/backends.md](https://docs.rundot.dev/backends/) explains each step, and how backends work.

A backend doesn't have to be part of rundot: the same page shows how to ship one in your own package.

### Preparing changes for review

Once you've made changes, here's a good checklist to run through before publishing for review:

Format and lint the code:

```sh
make format
```

Check the types:

```sh
make ty
```

Check the import contracts:

```sh
make lint-imports
```

[Import Linter](https://import-linter.readthedocs.io/) checks that modules only import in the directions we want: `rundot.cli` sits on top and wires everything together, the runner and validator never import the CLI or each other, backends are only loaded through their entry points, and only the CLI uses `click` and `rich`. The contracts, and the reasons for them, are under `[tool.importlinter]` in `pyproject.toml`. If one breaks, change the import rather than the contract.

Run the tests:

```sh
make test
```

New behaviour needs tests, and each new runbook feature gets an example runbook in `tests/runbooks/` that shows it off.

If you've changed how runbooks are written or run, update `docs/runbook-format.md` or `docs/cli.md` to match.

Make sure you add to `CHANGELOG.md` and `docs/CHANGELOG.md` what changes you have made. The two must be identical, and a test checks they are.

Make sure you add your name to `CONTRIBUTORS.md` as well!

### Making a pull request

Please push your changes up to a feature branch and make a new [pull request](https://github.com/phalt/rundot/compare) on GitHub.

Please add a description to the PR and some information about why the change is being made.

After a review, you might need to make more changes.

Once accepted, a core contributor will merge your changes!
