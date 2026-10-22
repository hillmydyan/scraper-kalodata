"""
Utility script to create a clean deployment zip bundle for VPS.
Excludes local cache, large chrome profile, and dev database.
Includes source code, configurations, deployment scripts, and kalodata_session.json.
"""

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ZIP = ROOT / "kalodata-deploy.zip"

INCLUDE_DIRS = ["app", "config", "deploy", "docs", "tests"]
INCLUDE_FILES = [
    "Dockerfile",
    "docker-compose.yml",
    "pyproject.toml",
    "run.py",
    "README.md",
    ".env.example",
    ".gitignore",
]

def create_bundle():
    print(f"Creating deployment bundle at {OUTPUT_ZIP}...")
    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        # 1. Add essential code directories
        for folder in INCLUDE_DIRS:
            for file_path in (ROOT / folder).rglob("*"):
                if file_path.is_file() and "__pycache__" not in file_path.parts and not file_path.name.endswith(".pyc"):
                    rel = file_path.relative_to(ROOT)
                    z.write(file_path, rel.as_posix())

        # 2. Add root configuration files
        for fname in INCLUDE_FILES:
            fp = ROOT / fname
            if fp.exists():
                z.write(fp, fname)

        # 3. Add authenticated session json (critical for zero-VNC login)
        sess = ROOT / "runtime" / "kalodata_session.json"
        if sess.exists():
            z.write(sess, "runtime/kalodata_session.json")
            print("Included runtime/kalodata_session.json (authenticated session)")

    size_mb = OUTPUT_ZIP.stat().st_size / (1024 * 1024)
    print(f"Bundle created successfully! Size: {size_mb:.2f} MB ({OUTPUT_ZIP.stat().st_size:,} bytes)")

if __name__ == "__main__":
    create_bundle()
