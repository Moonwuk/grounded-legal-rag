"""Independently verify the freshly built competition ZIP against runtime sources."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {
    "solution.py", "psb_corpus.py", "psb_retrieval.py", "psb_policy.py",
    "psb_llm.py", "requirements.txt",
}


def main() -> None:
    path = ROOT / "dist" / "PSB_baseline_submission.zip"
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(EXPECTED) or set(names) != EXPECTED:
            raise SystemExit("Submission must contain exactly the six allowed root files")
        if archive.testzip() is not None:
            raise SystemExit("Submission ZIP has a damaged entry")
        for name in sorted(EXPECTED):
            if archive.read(name) != (ROOT / "prototype" / name).read_bytes():
                raise SystemExit("Submission ZIP does not match the current runtime sources")
    print("Submission: six root files, current source bytes, no corpus or test answers")


if __name__ == "__main__":
    main()
