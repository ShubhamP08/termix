"""
CLI entrypoint for CLP1.

Responsibilities:
- Parse CLI args
- Handle file-create fast path (deterministic, no graph needed)
- Run the graph in two phases:
    Phase 1: resolve + validate  (approved=False → graph stops before executor)
    Phase 2: confirm with user, then re-invoke with approved=True → graph executes
- Display results
"""

from __future__ import annotations

from typing import Any, Dict
import typer

from agent.graph import graph
from utils.file_ops import build_filename, generate_file_commands, is_create_file_intent
from security.validator import validate_commands
from execution.executor import execute_commands
from utils.history_logger import log_history

app = typer.Typer(add_completion=False)


def _format_source(source: str) -> str:
    return {
        "kb_fuzzy":   "Knowledge Base (Fuzzy Match)",
        "kb_semantic": "Knowledge Base (Semantic)",
        "llm":        "LLM (Gemini)",
        "file_ops":   "File Operations",
        "gemini":     "LLM (Gemini)",
    }.get(source, source or "Unknown")


@app.callback(invoke_without_command=True)
def _main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(code=0)


@app.command()
def run(
    instruction: str = typer.Argument(..., help="Natural language instruction."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation and execute immediately."),
) -> None:
    """Generate commands from an instruction, confirm, then execute."""

    from utils.kb import ensure_embeddings_exist
    ensure_embeddings_exist()

    # ------------------------------------------------------------------ #
    # Fast path: deterministic file-create (no graph, no LLM)             #
    # ------------------------------------------------------------------ #
    if is_create_file_intent(instruction):
        filename = build_filename(instruction)
        commands = generate_file_commands(filename)

        if not validate_commands(commands):
            typer.echo("Blocked: command(s) failed safety validation.")
            raise typer.Exit(code=2)

        _show_and_execute(instruction, commands, source="file_ops", yes=yes)
        return

    # ------------------------------------------------------------------ #
    # Phase 1: resolve + validate (no execution yet)                       #
    # ------------------------------------------------------------------ #
    initial_state: Dict[str, Any] = {
        "user_input": instruction,
        "commands": [],
        "validated": False,
        "approved": False,   # graph stops before executor
        "execution_result": {},
        "error": "",
    }

    resolved = graph.invoke(initial_state)

    commands = list(resolved.get("commands") or [])
    source = resolved.get("source") or ""
    error = resolved.get("error") or ""

    if error:
        typer.echo(f"Blocked: {error}")
        raise typer.Exit(code=2)

    if not commands:
        typer.echo("No commands generated.")
        raise typer.Exit(code=1)

    # ------------------------------------------------------------------ #
    # Phase 2: show commands → confirm → execute via graph                 #
    # ------------------------------------------------------------------ #
    typer.echo("Generated commands:")
    for i, cmd in enumerate(commands, start=1):
        typer.echo(f"  {i}. {cmd}")
    typer.echo(f"\n[Source: {_format_source(source)}]")

    approved = yes or typer.confirm("\nExecute these command(s)?", default=False)
    if not approved:
        typer.echo("Cancelled.")
        raise typer.Exit(code=0)

    # Re-invoke graph with approved=True so executor_node runs
    execution_state: Dict[str, Any] = {
        **resolved,
        "approved": True,
    }
    final_state = graph.invoke(execution_state)

    # ------------------------------------------------------------------ #
    # Display results                                                       #
    # ------------------------------------------------------------------ #
    results = final_state.get("execution_result") or []
    for item in results:
        cmd  = item["command"]
        code = 0 if item["success"] else 1
        out  = (item.get("output") or "").rstrip()
        err  = (item.get("error") or "").rstrip()

        typer.echo(f"\n$ {cmd}  (exit {code})")
        if out:
            typer.echo(out)
        if err:
            typer.echo(err)


def _show_and_execute(
    instruction: str,
    commands: list,
    source: str,
    yes: bool,
) -> None:
    """Shared display+execute helper for the file-ops fast path."""
    typer.echo("Generated commands:")
    for i, cmd in enumerate(commands, start=1):
        typer.echo(f"  {i}. {cmd}")
    typer.echo(f"\n[Source: {_format_source(source)}]")

    approved = yes or typer.confirm("\nExecute these command(s)?", default=False)
    if not approved:
        typer.echo("Cancelled.")
        raise typer.Exit(code=0)

    results = execute_commands(commands)
    log_history(instruction, commands, source)

    for item in results:
        code = 0 if item["success"] else 1
        out  = (item.get("output") or "").rstrip()
        err  = (item.get("error") or "").rstrip()
        typer.echo(f"\n$ {item['command']}  (exit {code})")
        if out:
            typer.echo(out)
        if err:
            typer.echo(err)


# ------------------------------------------------------------------ #
# Utility subcommands                                                  #
# ------------------------------------------------------------------ #

@app.command()
def history() -> None:
    """Show command execution history."""
    import json, os
    path = os.path.join("data", "history.json")
    if not os.path.exists(path):
        typer.echo("No history found.")
        raise typer.Exit()
    with open(path) as f:
        data = json.load(f)
    if not data:
        typer.echo("History is empty.")
        raise typer.Exit()
    for i, entry in enumerate(data, start=1):
        typer.echo(f"\n{i}. {entry['query']}")
        typer.echo(f"   Source: {_format_source(entry.get('source', ''))}")
        typer.echo(f"   Time:   {entry['timestamp']}")
        typer.echo("   Commands:")
        for cmd in entry["commands"]:
            typer.echo(f"     - {cmd}")


@app.command()
def clear_history() -> None:
    """Clear command history."""
    import json
    with open("data/history.json", "w") as f:
        json.dump([], f)
    typer.echo("History cleared.")


@app.command()
def knowledge() -> None:
    """Show knowledge base."""
    import json
    with open("knowledge/knowledge_base.json") as f:
        typer.echo(json.dumps(json.load(f), indent=2))


@app.command("rebuild-embeddings")
def rebuild_embeddings_cmd() -> None:
    """Regenerate Gemini embeddings for every KB rule."""
    from knowledge.semantic import rebuild_embeddings
    rebuild_embeddings()
    typer.echo("Embeddings rebuilt and knowledge_base.json updated.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
