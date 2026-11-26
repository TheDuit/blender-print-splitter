"""Build an installable Blender Extension ZIP with the manifest at its root."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parent
PACKAGE = ROOT / "blender_print_splitter"
OUTPUT = ROOT / "blender_print_splitter-0.4.0.zip"

with ZipFile(OUTPUT, "w", compression=ZIP_DEFLATED) as archive:
    for path in sorted(PACKAGE.iterdir()):
        if path.is_file() and path.suffix in {".py", ".toml"}:
            archive.write(path, path.name)

print(f"Created {OUTPUT}")
