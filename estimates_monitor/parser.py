from pathlib import Path
import subprocess


def extract_text_with_markitdown(pdf_path: str) -> str:
    """Call markitdown to extract markdown/text from the given PDF path.
    This uses the CLI if the Python API is not available. Returns plain text.
    """
    p = Path(pdf_path)
    if not p.exists():
        raise FileNotFoundError(pdf_path)
    # Prefer Python API if available
    try:
        import markitdown
        # markitdown.convert_file may exist; attempt conservative call
        md = markitdown.convert_file(str(p))
        return md
    except Exception:
        # Fallback to CLI
        res = subprocess.run(["markitdown", str(p)], capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"markitdown failed: {res.stderr}")
        return res.stdout
