"""CLI interface for RFP requirement extraction"""

import json
import logging
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich import print as rprint

from rfp_extractor.models import (
    DocumentFormat,
    ExtractionConfig,
    ExtractionResult,
    LLMConfig,
    LLMProvider,
    OutputFormat,
)
from rfp_extractor.parsers import DocumentParserFactory
from rfp_extractor.extraction import ExtractionOptions, create_extractor
from rfp_extractor.llm import create_llm_client

console = Console()
logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)]
    )


def load_config(config_path: Optional[Path] = None) -> ExtractionConfig:
    """Load configuration from file or environment"""
    import os

    # Default config
    config = ExtractionConfig(
        llm=LLMConfig(
            provider=LLMProvider(os.getenv("LLM_PROVIDER", "openai")),
            model=os.getenv("LLM_MODEL", "gpt-4o"),
            api_key=os.getenv("LLM_API_KEY"),
            base_url=os.getenv("LLM_BASE_URL"),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.0")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "8192")),
        ),
        chunk_size=int(os.getenv("CHUNK_SIZE", "8000")),
        chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "500")),
        min_confidence=float(os.getenv("MIN_CONFIDENCE", "0.5")),
    )

    # Override with config file if provided
    if config_path and config_path.exists():
        import tomli
        with open(config_path, "rb") as f:
            file_config = tomli.load(f)
        # Merge configs (simplified)
        if "llm" in file_config:
            config.llm = LLMConfig(**{**config.llm.model_dump(), **file_config["llm"]})
        for key in ["chunk_size", "chunk_overlap", "min_confidence", "extract_tables", "extract_footnotes", "extract_appendices"]:
            if key in file_config:
                setattr(config, key, file_config[key])

    return config


def save_config(config: ExtractionConfig, config_path: Path):
    """Save configuration to file"""
    import tomli_w
    data = config.model_dump(exclude_none=True)
    with open(config_path, "wb") as f:
        tomli_w.dump(data, f)


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.option("--config", "-c", type=click.Path(exists=True, path_type=Path), help="Config file path")
@click.pass_context
def cli(ctx: click.Context, verbose: bool, config: Optional[Path]):
    """RFP Requirement Extractor - Extract requirements from RFP/RFQ/RFI documents"""
    setup_logging(verbose)
    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config(config)
    ctx.obj["config_path"] = config


@cli.command()
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.option("--output", "-o", type=click.Path(path_type=Path), help="Output file path (default: stdout)")
@click.option("--format", "-f", type=click.Choice(["json", "jsonl", "csv"]), default="json", help="Output format")
@click.option("--provider", type=click.Choice(["openai", "anthropic", "gemini"]), help="LLM provider")
@click.option("--model", help="LLM model name")
@click.option("--min-confidence", type=float, help="Minimum confidence threshold (0-1)")
@click.option("--chunk-size", type=int, help="Chunk size for large documents")
@click.pass_context
def extract(
    ctx: click.Context,
    input_path: Path,
    output: Optional[Path],
    format: str,
    provider: Optional[str],
    model: Optional[str],
    min_confidence: Optional[float],
    chunk_size: Optional[int],
):
    """Extract requirements from a document"""
    config: ExtractionConfig = ctx.obj["config"]

    # Override config with CLI options
    if provider:
        config.llm.provider = LLMProvider(provider)
    if model:
        config.llm.model = model
    if min_confidence is not None:
        config.min_confidence = min_confidence
    if chunk_size is not None:
        config.chunk_size = chunk_size

    console.print(f"[bold blue]Processing:[/bold blue] {input_path}")
    console.print(f"[bold blue]Provider:[/bold blue] {config.llm.provider.value} ({config.llm.model})")

    try:
        # Parse document
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Parsing document...", total=None)
            doc = DocumentParserFactory.parse_file(input_path)
            progress.update(task, description=f"Parsed {doc.word_count} words, {len(doc.sections)} sections")

            # Extract requirements
            progress.update(task, description="Extracting requirements...")
            options = ExtractionOptions(
                min_confidence=config.min_confidence,
                chunk_size=config.chunk_size,
                chunk_overlap=config.chunk_overlap,
            )
            extractor = create_extractor(config.llm, options)
            result = extractor.extract(doc)
            progress.update(task, description="Complete!")

        # Display summary
        _display_summary(result)

        # Output results
        _output_results(result, output, OutputFormat(format))

        console.print(f"[green]✓[/green] Extracted {len(result.requirements)} requirements")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        logger.exception("Extraction failed")
        sys.exit(1)


@cli.command()
@click.argument("input_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--output-dir", "-o", type=click.Path(path_type=Path), required=True, help="Output directory")
@click.option("--format", "-f", type=click.Choice(["json", "jsonl", "csv"]), default="json", help="Output format")
@click.option("--pattern", default="**/*", help="File glob pattern")
@click.pass_context
def batch(
    ctx: click.Context,
    input_dir: Path,
    output_dir: Path,
    format: str,
    pattern: str,
):
    """Batch process multiple documents"""
    config: ExtractionConfig = ctx.obj["config"]
    output_dir.mkdir(parents=True, exist_ok=True)

    files = list(input_dir.glob(pattern))
    supported_exts = {".md", ".markdown", ".html", ".htm", ".pdf", ".docx"}
    files = [f for f in files if f.suffix.lower() in supported_exts]

    console.print(f"[bold blue]Found {len(files)} documents to process[/bold blue]")

    options = ExtractionOptions(
        min_confidence=config.min_confidence,
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
    )
    extractor = create_extractor(config.llm, options)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Processing documents...", total=len(files))

        for file_path in files:
            progress.update(task, description=f"Processing {file_path.name}...")
            try:
                doc = DocumentParserFactory.parse_file(file_path)
                result = extractor.extract(doc)

                # Save individual result
                output_file = output_dir / f"{file_path.stem}_requirements.{format}"
                _output_results(result, output_file, OutputFormat(format))

                progress.advance(task)
            except Exception as e:
                console.print(f"[red]Failed to process {file_path.name}: {e}[/red]")
                progress.advance(task)

    console.print(f"[green]✓[/green] Batch processing complete. Results in {output_dir}")


@cli.command()
@click.option("--provider", type=click.Choice(["openai", "anthropic", "gemini"]), default="openai", help="LLM provider")
@click.option("--model", default="gpt-4o", help="LLM model name")
@click.option("--output", "-o", type=click.Path(path_type=Path), default=Path("config.toml"), help="Config file path")
@click.pass_context
def init_config(ctx: click.Context, provider: str, model: str, output: Path):
    """Generate a default configuration file"""
    # Provider-specific defaults
    default_models = {
        "openai": "gpt-4o",
        "anthropic": "claude-sonnet-4-20250514",
        "gemini": "gemini-2.0-flash",
    }
    if model == "gpt-4o":
        model = default_models.get(provider, model)

    config = ExtractionConfig(
        llm=LLMConfig(
            provider=LLMProvider(provider),
            model=model,
            temperature=0.0,
            max_tokens=8192,
        )
    )
    save_config(config, output)
    console.print(f"[green]✓[/green] Configuration saved to {output}")
    console.print("Edit the file to add your API key and adjust settings.")


@cli.command()
@click.pass_context
def validate_config(ctx: click.Context):
    """Validate current configuration"""
    config: ExtractionConfig = ctx.obj["config"]

    table = Table(title="Current Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("LLM Provider", config.llm.provider.value)
    table.add_row("LLM Model", config.llm.model)
    table.add_row("API Key", "***" if config.llm.api_key else "Not set (uses env var)")
    table.add_row("Temperature", str(config.llm.temperature))
    table.add_row("Max Tokens", str(config.llm.max_tokens))
    table.add_row("Chunk Size", str(config.chunk_size))
    table.add_row("Chunk Overlap", str(config.chunk_overlap))
    table.add_row("Min Confidence", str(config.min_confidence))

    console.print(table)

    # Test connection
    try:
        client = create_llm_client(config.llm)
        response = client.complete([{"role": "user", "content": "Hello"}])
        console.print("[green]✓[/green] LLM connection successful")
    except Exception as e:
        console.print(f"[red]✗[/red] LLM connection failed: {e}")


def _display_summary(result: ExtractionResult):
    """Display extraction summary"""
    table = Table(title=f"Extraction Summary: {result.document_id}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Document", result.source_path)
    table.add_row("Format", result.format.value)
    table.add_row("Requirements Found", str(len(result.requirements)))
    table.add_row("Extraction Time", f"{result.extraction_metadata.extraction_time_seconds:.2f}s")
    table.add_row("Total Tokens", str(result.extraction_metadata.total_tokens))
    table.add_row("Model", result.extraction_metadata.llm_model)

    console.print(table)


def _output_results(result: ExtractionResult, output: Optional[Path], format: OutputFormat):
    """Output results in specified format"""
    if format == OutputFormat.JSON:
        data = {
            "document_id": result.document_id,
            "source_path": result.source_path,
            "format": result.format.value,
            "requirements": [r.model_dump() for r in result.requirements],
            "metadata": result.extraction_metadata.model_dump(),
        }
        json_str = json.dumps(data, indent=2, default=str)
    elif format == OutputFormat.JSONL:
        json_str = "\n".join(r.model_dump_json() for r in result.requirements)
    elif format == OutputFormat.CSV:
        import csv
        import io
        output_io = io.StringIO()
        if result.requirements:
            writer = csv.DictWriter(output_io, fieldnames=result.requirements[0].model_fields.keys())
            writer.writeheader()
            for r in result.requirements:
                writer.writerow(r.model_dump())
        json_str = output_io.getvalue()
    else:
        json_str = json.dumps([r.model_dump() for r in result.requirements], indent=2, default=str)

    if output:
        output.write_text(json_str)
        console.print(f"[green]✓[/green] Results saved to {output}")
    else:
        console.print(json_str)


if __name__ == "__main__":
    cli()