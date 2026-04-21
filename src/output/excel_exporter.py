"""Export measurement results to Excel with a summary statistics sheet."""

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


def _require_openpyxl():
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        raise ImportError(
            "openpyxl 未安裝或無法載入。\n"
            "請在正確的虛擬環境中執行：\n"
            "  pip install \"pandas>=2.0\" openpyxl"
        )


def export_excel(results: list[dict], out_path: Path, nm_per_pixel: float) -> None:
    pd = _require_pandas()
    _require_openpyxl()
    from ._common import results_to_dataframe
    df = results_to_dataframe(results, nm_per_pixel)
    ok = df[df["status"] == "OK"]["y_cd_nm"].dropna()

    stats = {
        "Metric": ["Count", "Mean (nm)", "Median (nm)", "Q25 (nm)", "Q75 (nm)",
                   "Std Dev (nm)", "3-Sigma (nm)", "Min (nm)", "Max (nm)"],
        "Value": [
            len(ok),
            round(ok.mean(), 3) if len(ok) else "N/A",
            round(ok.median(), 3) if len(ok) else "N/A",
            round(ok.quantile(0.25), 3) if len(ok) else "N/A",
            round(ok.quantile(0.75), 3) if len(ok) else "N/A",
            round(ok.std(), 3) if len(ok) else "N/A",
            round(ok.std() * 3, 3) if len(ok) else "N/A",
            round(ok.min(), 3) if len(ok) else "N/A",
            round(ok.max(), 3) if len(ok) else "N/A",
        ],
    }
    df_stats = pd.DataFrame(stats)

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Measurements", index=False)
        df_stats.to_excel(writer, sheet_name="Statistics", index=False)

        wb = writer.book
        ws = wb["Measurements"]
        from openpyxl.styles import PatternFill
        red_fill = PatternFill("solid", fgColor="FFAAAA")
        blue_fill = PatternFill("solid", fgColor="AAAAFF")
        flag_col = df.columns.get_loc("flag") + 1  # 1-based

        for row_idx, flag in enumerate(df["flag"], start=2):  # row 1 = header
            if flag == "MIN":
                for cell in ws[row_idx]:
                    cell.fill = red_fill
            elif flag == "MAX":
                for cell in ws[row_idx]:
                    cell.fill = blue_fill


def export_excel_from_records(
    records: list,
    out_path: Path,
    image_records: list | None = None,
) -> None:
    pd = _require_pandas()
    _require_openpyxl()
    from ._common import records_to_dataframe
    df = records_to_dataframe(records, image_records)
    ok = df[df["status"] == "OK"]["y_cd_nm"].dropna()
    stats = {
        "Metric": ["Count", "Mean (nm)", "Median (nm)", "Q25 (nm)", "Q75 (nm)",
                   "Std Dev (nm)", "3-Sigma (nm)", "Min (nm)", "Max (nm)"],
        "Value": [
            len(ok),
            round(ok.mean(), 3) if len(ok) else "N/A",
            round(ok.median(), 3) if len(ok) else "N/A",
            round(ok.quantile(0.25), 3) if len(ok) else "N/A",
            round(ok.quantile(0.75), 3) if len(ok) else "N/A",
            round(ok.std(), 3) if len(ok) else "N/A",
            round(ok.std() * 3, 3) if len(ok) else "N/A",
            round(ok.min(), 3) if len(ok) else "N/A",
            round(ok.max(), 3) if len(ok) else "N/A",
        ],
    }
    df_stats = pd.DataFrame(stats)

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Measurements", index=False)
        df_stats.to_excel(writer, sheet_name="Statistics", index=False)

        wb = writer.book
        ws = wb["Measurements"]
        from openpyxl.styles import PatternFill
        red_fill = PatternFill("solid", fgColor="FFAAAA")
        blue_fill = PatternFill("solid", fgColor="AAAAFF")

        for row_idx, flag in enumerate(df["flag"], start=2):
            if flag == "MIN":
                for cell in ws[row_idx]:
                    cell.fill = red_fill
            elif flag == "MAX":
                for cell in ws[row_idx]:
                    cell.fill = blue_fill
