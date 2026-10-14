# 🚀 Install

paulrun is a command-line tool, so install it on its own rather than into a project:

### uv

```sh
uv tool install paulrun
```

### pip

```sh
pip install paulrun
```

Once installed, check it's working:

```sh
> paulrun --version
paulrun, version 0.2.0
```

## Requirements

- **Python 3.12 or later.**
- **macOS or Linux.** Windows isn't supported.
- **`bash`**, which runs shell blocks. It's on macOS and almost every Linux system already.

## Optional: shellcheck

If [shellcheck](https://www.shellcheck.net/) is installed, `paulrun check` uses it to warn about common mistakes in shell blocks, such as an unquoted variable. Without it, shell blocks are still checked for syntax errors.

```sh
brew install shellcheck      # macOS
sudo apt install shellcheck  # Debian and Ubuntu
```

## Next steps

- [The runbook format](runbook-format.md) to write your first runbook
- [The command line](cli.md) to see everything paulrun can do
