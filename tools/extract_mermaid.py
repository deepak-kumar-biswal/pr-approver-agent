import sys
import re
from pathlib import Path


def extract_mermaid(md_path: Path, out_dir: Path) -> list[Path]:
    text = md_path.read_text(encoding="utf-8")
    pattern = re.compile(r"```mermaid\n(.*?)\n```", re.DOTALL | re.IGNORECASE)
    blocks = pattern.findall(text)
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    base = md_path.stem.lower()
    for i, block in enumerate(blocks, start=1):
        out = out_dir / f"{base}_{i:02d}.mmd"
        out.write_text(block.strip() + "\n", encoding="utf-8")
        outputs.append(out)
    return outputs


def main():
    if len(sys.argv) < 3:
        print("usage: extract_mermaid.py <input.md> <out_dir>")
        sys.exit(2)
    md = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    files = extract_mermaid(md, out_dir)
    print("extracted", len(files), "diagrams to", out_dir)
    for p in files:
        print(" -", p)


if __name__ == "__main__":
    main()
