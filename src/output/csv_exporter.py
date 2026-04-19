"""Export measurement results to CSV."""

from __future__ import annotations
from pathlib import Path
import pandas as pd
from ._common import results_to_dataframe


def export_csv(results: list[dict], out_path: Path, nm_per_pixel: float) -> None:
    df = results_to_dataframe(results, nm_per_pixel)
    df.to_csv(out_path, index=False)


def export_csv_from_records(
    records: list,
    out_path: Path,
    image_records: list | None = None,
) -> None:
    from ._common import records_to_dataframe
    df = records_to_dataframe(records, image_records)
    df.to_csv(out_path, index=False)
