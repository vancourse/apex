"""rails — the Claude Code plugin that keeps application building on the rails.

Everything here is standard library only. Hooks start a fresh interpreter on
every tool call, so an import that pulls a third-party package would cost every
call and break on any machine without it.
"""

VERSION = "1.3.1"
