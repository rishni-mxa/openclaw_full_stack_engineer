from pathlib import Path


def extract_text_with_markitdown(pdf_path: str) -> str:
    """Extract text from a PDF using markitdown. Returns plain text."""
    p = Path(pdf_path)
    if not p.exists():
        raise FileNotFoundError(pdf_path)
    from markitdown import MarkItDown
    md = MarkItDown()
    result = md.convert(str(p))
    return result.text_content
