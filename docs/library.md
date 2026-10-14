# 📚 Your runbook library

Some runbooks belong to a project, like the `RELEASING.md` at the root of a package. Others are jobs you do the same way across every project. Those go in your **runbook library**.

Your library is a directory of markdown files that paulrun can execute and we call these **books**. 

Move a book there once, and run it by name from wherever you are:

```sh
cd ~/Projects/website
paulrun rebuild-frontend
```

## Where your library is

Your library is, by default, in `~/runbooks`. Every `.md` file directly inside it is a **book**, named after its file: `~/runbooks/rebuild-frontend.md` is the book `rebuild-frontend`. Folders and other files in it aren't books, so `~/runbooks/logs/` is a fine place to keep transcripts.

To keep it somewhere else, set `PAULRUN_LIBRARY`, e.g. in your shell's profile:

```sh
export PAULRUN_LIBRARY=~/work-runbooks
```

## Running a book

Run a book by its name, with or without `.md`:

```sh
paulrun rebuild-frontend
paulrun rebuild-frontend.md     # the same book
paulrun --dry rebuild-frontend  # see what it would do first
```

A file with the same name in the current directory always comes first, so a runbook in your project is never hidden by a book with the same name, and anything with a `/` in it is only ever a path. See [Naming a runbook](cli.md#naming-a-runbook) for exactly how paulrun works out which runbook you mean.

`paulrun check`, `paulrun inputs` and `paulrun run` all take a book's name, the same way.

## Finding a book

`paulrun library` lists the books in your library, with each one's `title` and `description`, so a good title is worth writing:

```
$ paulrun library
library: /home/you/runbooks
rebuild-frontend     Rebuild the frontend
                     Clean install the frontend's dependencies under nvm, then rebuild it.
update-project-deps  Update a project's dependencies
```

If you can't remember the name, run `paulrun run` with no runbook. It lists the same books by number, and runs the one you pick:

```
$ paulrun run
  1. rebuild-frontend     Rebuild the frontend
  2. update-project-deps  Update a project's dependencies
Run which? 1
```

See [`paulrun library`](cli.md#paulrun-library) and [Picking a book](cli.md#picking-a-book) for the details.

## Where a book runs

A book's blocks run in the directory you are in, not in your library. 

Its transcript, if it has an `output_path`, is written relative to the current directory too. See [Where blocks run](runbook-format.md#where-blocks-run).

paulrun shows the folder before anything runs, so check it before you answer `Start?`:

```
Rebuild the frontend
directory: /home/you/Projects/website
```

A book that needs files kept next to it in the library, like a template, can find them through `PAULRUN_RUNBOOK_DIR`:

```sh
cp "$PAULRUN_RUNBOOK_DIR/templates/pull-request.md" .github/
```

## Example: rebuilding a frontend under nvm

This book clean-installs a frontend's dependencies with the Node version the project asks for, then rebuilds it. Save it as `~/runbooks/rebuild-frontend.md`, and run it from the project's root.

````markdown
---
title: Rebuild the frontend
description: Clean install the frontend's dependencies under nvm, then rebuild it.
inputs:
  - name: FE_SET
    description: Which frontend set to rebuild
    choices: [main, admin, all]
    default: main
---

# Rebuild the frontend

Run this from the project's root. It uses the Node version in
`frontend/.nvmrc`, and needs [nvm](https://github.com/nvm-sh/nvm).

## Check the project

```sh run
test -f frontend/.nvmrc || { echo "No frontend/.nvmrc here; run this from the project's root."; exit 1; }
```

## Clean install and rebuild

nvm is a shell function your profile loads, so the block loads it itself.
Everything that needs the project's Node is in this one block, since a later
block would be back on your default Node.

```sh run
source "$NVM_DIR/nvm.sh"
cd frontend
nvm install
nvm use
rm -rf node_modules
npm ci
npm run build -- --set=<FE_SET>
```
````

Three things in it are worth knowing for your own books.

**Loading nvm.** paulrun runs each shell block with a plain `bash`, which doesn't read your shell's profile, so shell functions it defines, like `nvm`, aren't there. Load them in the block with `source`. The same goes for anything else your profile sets up, like `pyenv` or `rbenv`.

**One block for one environment.** Each block is its own `bash`, so a `cd`, an `export` or `nvm use` in one block is gone by the next. That fails quietly: a later block doesn't stop with an error, it runs with whatever Node your login shell has on its `PATH`, which may not be the one the project needs. So everything that needs the project's Node goes in the same block as `nvm use`, and the first step, which doesn't, is on its own.

**Choices.** `FE_SET` takes one of three values, and pressing enter at the prompt takes `main`. `FE_SET=all paulrun rebuild-frontend` skips the question. See [Choices](runbook-format.md#choices) and [Defaults](runbook-format.md#defaults).
