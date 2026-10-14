# 📚 Your runbook library

Some runbooks belong to a project, like the `RELEASING.md` at the root of a package. Others are jobs you do the same way across every project. Those go in your **runbook library**.

Your library is a directory of markdown files that paulrun can execute, and we call these **books**. Move a book there once, and run it by name from wherever you are:

```sh
cd ~/Projects/website
paulrun rebuild-frontend
```

## Where your library is

Your library is `~/runbooks`. Every `.md` file directly inside it is a book, named after its file: `~/runbooks/rebuild-frontend.md` is the book `rebuild-frontend`. Folders and other files in it aren't books, so `~/runbooks/logs/` is a fine place for transcripts.

To keep it somewhere else, set `PAULRUN_LIBRARY`:

```sh
export PAULRUN_LIBRARY=~/work-runbooks
```

## Running a book

```sh
paulrun rebuild-frontend        # run it
paulrun --dry rebuild-frontend  # see what it would do first
paulrun check rebuild-frontend  # find problems in it
```

A file in the current directory always comes first, so a book never hides a runbook in your project. See [Naming a runbook](cli.md#naming-a-runbook).

A book runs in the directory you're in, not in your library, and paulrun shows it as `directory:` before anything runs. See [Where blocks run](runbook-format.md#where-blocks-run).

## Finding a book

`paulrun library` lists your books, with each one's `title` and `description`:

```
$ paulrun library
library: /home/you/runbooks
rebuild-frontend     Rebuild the frontend
                     Clean install the frontend's dependencies under nvm, then rebuild it.
update-project-deps  Update a project's dependencies
```

Or run `paulrun run` with no runbook, and pick one by number:

```
$ paulrun run
  1. rebuild-frontend     Rebuild the frontend
  2. update-project-deps  Update a project's dependencies
Run which? 1
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

Two things in it apply to any book:

- **Load what your profile sets up.** paulrun runs shell blocks with a plain `bash`, which doesn't read your profile, so shell functions like `nvm`, `pyenv` and `rbenv` aren't there. `source` them in the block.
- **Keep one environment in one block.** A `cd` or `nvm use` is gone by the next block, and that fails quietly: the next block just runs with your default Node. So everything that needs the project's Node goes in the block with `nvm use`.
