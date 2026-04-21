"""Export measurement results to CSV."""

from __future__ import annotations
from pathlib import Path


def _require_pandas():
    try:
        import pandas as pd
        return pd
    except ImportError:
        raise ImportError(
            "pandas 未安裝或無法載入。\n"
            "請在正確的虛擬環境中執行：\n"
            "  pip install \"pandas>=2.0\" openpyxl\n"
            "若使用 PyCharm，請確認 Project Interpreter 已設定正確。"
        )


def export_csv(results: list[dict], out_path: Path, nm_per_pixel: float) -> None:
    pd = _require_pandas()
    from ._common import results_to_dataframe
    df = results_to_dataframe(results, nm_per_pixel)
    df.to_csv(out_path, index=False)


def export_csv_from_records(
    records: list,
    out_path: Path,
    image_records: list | None = None,
) -> None:
    _require_pandas()
    from ._common import records_to_dataframe
    df = records_to_dataframe(records, image_records)
    df.to_csv(out_path, index=False)
