"""Writing test cases from uploaded schema files."""
from nl2sql_evalkit.core.config.base import Settings


class GenerationSettings(Settings):
    """Options for writing test cases from uploaded schema files: model, upload limits and batch lifetime."""

    # Model that writes the questions; empty means "use judge_model". The tables and columns of the schema are sent to it.
    generator_model: str = ""
    generate_max_files: int = 5        # schema files accepted per generation request
    generate_max_file_mb: int = 10     # largest single schema file, in megabytes (a dump with data can be large)
    generate_per_category_max: int = 10  # most questions a request may ask for in one category
    generate_workers: int = 4          # questions written in parallel
    batch_ttl_hours: int = 24          # generated questions not approved within this time are deleted
