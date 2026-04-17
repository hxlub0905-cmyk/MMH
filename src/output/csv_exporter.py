"""Export measurement results to CSV."""

from pathlib import Path
import pandas as pd
from ._common import results_to_dataframe


def export_csv(results: list[dict], out_path: Path, nm_per_pixel: float) -> None:
    df = results_to_dataframe(results, nm_per_pixel)
    df.to_csv(out_path, index=False)
