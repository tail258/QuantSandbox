"""Record the implementation used at execution time, not at export time."""
import hashlib
from pathlib import Path


def engine_fingerprint() -> dict:
    directory = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    files = [directory / "research.py", directory / "core" / "engine.py", directory / "core" / "strategy.py"]
    research_directory = directory / "research"
    if research_directory.exists():
        files.extend(sorted(research_directory.glob("*.py")))
    for path in files:
        if path.exists():
            digest.update(str(path.relative_to(directory)).replace("\\", "/").encode())
            digest.update(path.read_bytes())
    return {"version": "2.0.0", "source_sha256": digest.hexdigest()}
