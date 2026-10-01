import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from agent.orchestrator import handle_query, list_sessions
from observability.logger import get_logger

load_dotenv(Path(__file__).parent.parent / ".env")

console = Console()
logger = get_logger(__name__)

session_id = str(uuid.uuid4())
# thread ids from the last /sessions listing, so /switch can take a row number
listed_sessions: list[str] = []


def _new_session_id() -> str:
    return str(uuid.uuid4())


def cmd_ask(arg: str) -> bool:
    if not arg:
        console.print("[yellow]Usage:[/yellow] /ask <question>")
        return True

    logger.info(f"Ask command received: {arg}")
    try:
        with console.status("[cyan]Thinking...[/cyan]", spinner="dots"):
            response = handle_query(arg, session_id)
    except Exception as e:
        logger.exception("Query failed")
        console.print(
            Panel(str(e), title="Error", border_style="red", title_align="left")
        )
        return True

    console.print(
        Panel(
            Markdown(response),
            title="AI Architect",
            border_style="cyan",
            title_align="left",
        )
    )
    return True


def cmd_new_session(_arg: str) -> bool:
    global session_id
    session_id = _new_session_id()
    console.print(f"[green]New session started:[/green] [bold]{session_id}[/bold]")
    return True


def cmd_session(_arg: str) -> bool:
    console.print(f"[cyan]Current session:[/cyan] [bold]{session_id}[/bold]")
    return True


def _format_ts(ts: str | None) -> str:
    if not ts:
        return "-"
    return datetime.fromisoformat(ts).astimezone().strftime("%Y-%m-%d %H:%M")


def cmd_sessions(_arg: str) -> bool:
    global listed_sessions
    try:
        with console.status("[cyan]Loading sessions...[/cyan]", spinner="dots"):
            sessions = list_sessions()
    except Exception as e:
        logger.exception("Listing sessions failed")
        console.print(
            Panel(str(e), title="Error", border_style="red", title_align="left")
        )
        return True

    if not sessions:
        console.print("[dim]No saved sessions yet. Use /ask to start one.[/dim]")
        return True

    listed_sessions = [s["thread_id"] for s in sessions]
    table = Table(title="Sessions", title_style="bold", border_style="dim")
    table.add_column("#", style="dim", justify="right", no_wrap=True)
    table.add_column("Session", style="bold", no_wrap=True, min_width=10)
    table.add_column("Last active", no_wrap=True, min_width=16)
    table.add_column("First question", overflow="ellipsis", no_wrap=True, max_width=40)
    for i, s in enumerate(sessions, start=1):
        short_id = s["thread_id"][:8]
        if s["thread_id"] == session_id:
            short_id = f"[green]{short_id} ●[/green]"
        table.add_row(str(i), short_id, _format_ts(s["last_active"]), s["preview"])
    console.print(table)
    console.print(
        "[dim]● = current. Use [bold]/switch <#>[/bold] or [bold]/switch <id>[/bold] to resume one.[/dim]"
    )
    return True


def cmd_switch(arg: str) -> bool:
    global session_id
    if not arg:
        console.print("[yellow]Usage:[/yellow] /switch <# | session_id>")
        return True
    if arg.isdigit() and 1 <= int(arg) <= len(listed_sessions):
        arg = listed_sessions[int(arg) - 1]
    elif matches := [t for t in listed_sessions if t.startswith(arg)]:
        if len(matches) > 1:
            console.print(
                f"[yellow]'{arg}' matches {len(matches)} sessions; use more characters.[/yellow]"
            )
            return True
        arg = matches[0]
    session_id = arg
    console.print(f"[green]Switched to session:[/green] [bold]{session_id}[/bold]")
    return True


def cmd_help(_arg: str) -> bool:
    table = Table(
        title="Commands", title_style="bold", border_style="dim", show_lines=False
    )
    table.add_column("Command", style="bold green", no_wrap=True)
    table.add_column("Description")
    for cmd, (usage, _, description) in COMMANDS.items():
        if cmd == "/quit":
            continue
        table.add_row(usage, description)
    console.print(table)
    return True


def cmd_exit(_arg: str) -> bool:
    return False


# command -> (usage, handler, description); handlers return False to end the session
COMMANDS = {
    "/ask": ("/ask <question>", cmd_ask, "Ask the agent a question"),
    "/new_session": ("/new_session", cmd_new_session, "Start a fresh conversation"),
    "/session": ("/session", cmd_session, "Show the current session id"),
    "/sessions": ("/sessions", cmd_sessions, "List saved sessions"),
    "/switch": (
        "/switch <# | session_id>",
        cmd_switch,
        "Resume a session by list number or id",
    ),
    "/help": ("/help", cmd_help, "Show this help"),
    "/exit": ("/exit", cmd_exit, "Quit (also /quit)"),
    "/quit": ("/quit", cmd_exit, "Quit"),
}


def print_banner():
    body = Group(
        Text("Describe a system and let the agent design it for you.", style="italic"),
        Text(),
        Text.assemble(("Session  ", "dim"), (session_id, "bold")),
        Text.assemble(
            ("Type ", "dim"), ("/help", "bold green"), (" to see commands", "dim")
        ),
    )
    console.print(
        Panel(
            body,
            title="[bold blue]AI Architect[/bold blue]",
            border_style="blue",
            padding=(1, 2),
        )
    )


def dispatch(user_input: str) -> bool:
    if not user_input.startswith("/"):
        console.print(
            "[dim]Use [bold]/ask <question>[/bold] to talk to the agent, or [bold]/help[/bold].[/dim]"
        )
        return True

    cmd, _, arg = user_input.partition(" ")
    entry = COMMANDS.get(cmd.lower())
    if entry is None:
        console.print(
            f"[red]Unknown command '{cmd}'.[/red] Type [bold]/help[/bold] to see commands."
        )
        return True

    _, handler, _ = entry
    return handler(arg.strip())


def main():
    """Console entry point: runs the interactive terminal session."""
    logger.info("Starting AI Architect")
    print_banner()

    try:
        while True:
            user_input = console.input("\n[bold green]›[/bold green] ").strip()
            if user_input and not dispatch(user_input):
                break
    except (KeyboardInterrupt, EOFError):
        console.print()

    logger.info("Shutting down")
    console.print("[dim]Goodbye![/dim]")


if __name__ == "__main__":
    main()
