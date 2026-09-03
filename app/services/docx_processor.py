from pathlib import Path


class DocxProcessor:
    """Placeholder for DOCX-to-HTML chapter extraction logic."""

    async def process(self, source_path: Path, output_dir: Path) -> list[dict[str, object]]:
        raise NotImplementedError("DOCX processing is not implemented yet.")


docx_processor = DocxProcessor()
