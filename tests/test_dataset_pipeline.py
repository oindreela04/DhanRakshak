import csv
import subprocess
import sys
from pathlib import Path


def test_small_dataset_generation_and_validation(tmp_path: Path) -> None:
    root = tmp_path / "data"
    repository_root = Path(__file__).parents[1]
    command = [sys.executable, str(repository_root / "scripts/generate_dataset.py"), "--output-root", str(root), "--clean", "--customers", "20", "--transactions", "40", "--subscriptions", "20", "--invoices", "20", "--checkouts", "20", "--recovery-events", "40"]
    subprocess.run(command, check=True)
    subprocess.run([sys.executable, str(repository_root / "scripts/validate_dataset.py"), "--root", str(root)], check=True)
    with (root / "raw" / "recovery_events.csv").open(newline="", encoding="utf-8") as stream:
        assert len(list(csv.DictReader(stream))) == 40
    assert (root / "train" / "recovery_events.csv").exists()
    assert (root / "validation" / "recovery_events.csv").exists()
    assert (root / "test" / "recovery_events.csv").exists()