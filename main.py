from observability.logger import get_logger
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt
from agent.orchestrator import handle_query
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

console = Console()
logger = get_logger(__name__)

def run():
    try:
        logger.info("Starting AI Architect")
        console.print("[bold blue]Welcome to the interactive session. Please type your query[/bold blue]")
        console.print("[red]Available commands: /ask /exit /quit /new_session /switch /session"
        "[/red]")
        console.print("Type [bold]'/exit'[/bold] to quit\n")

        while True:
            user_input = Prompt.ask("[bold green]>[/bold green]")

            if not user_input.strip():
                continue

            if user_input.lower() in ("/exit", "/quit"):
                logger.info("Shutting down")
                console.print("[dim]Goodbye![/dim]")
                break

            elif user_input.startswith("/ask "):
                question = user_input.removeprefix("/ask ").strip()
                logger.info(f"Ask command received: {question}")
                console.print(f"[dim]Searching for: {question}...[/dim]")
                response = handle_query(question, 'abc')
                console.print(response)

            # elif user_input == "/new_session":
            #     console.print(f"[green]New session started: {session_id}[/green]")

    except KeyboardInterrupt:
        console.print("\n[bold red]Operation cancelled by user.[/bold red]")


if __name__ == "__main__":
    run()
