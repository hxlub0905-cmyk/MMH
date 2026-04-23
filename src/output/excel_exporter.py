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


# ── Legacy exporters (preserved for backward compatibility / tests) ────────────

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
    # stats use cd_nm column (new name); fall back to y_cd_nm for older callers
    cd_col = "cd_nm" if "cd_nm" in df.columns else "y_cd_nm"
    ok = df[df["status"].isin(("normal", "min", "max", "OK"))][cd_col].dropna()
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


# ── Rich multi-sheet exporter ─────────────────────────────────────────────────

def export_excel_rich(
    datasets: list[tuple[list, list | None, str]],
    out_path: Path,
) -> None:
    """Export one rich Excel file for one or more datasets.

    Parameters
    ----------
    datasets:
        List of ``(records, image_records, label)`` tuples.
        Pass a single-element list for single-dataset runs (label may be empty).
    out_path:
        Destination .xlsx path.

    Sheet layout (multi-dataset)
    ----------------------------
    [Label_A]  [Label_B]  …  [Summary]  [Min CD per Image]

    Sheet layout (single-dataset)
    ----------------------------
    [Measurements]  [Statistics]  [Min CD per Image]
    """
    pd = _require_pandas()
    _require_openpyxl()
    from openpyxl.styles import PatternFill, Font
    from openpyxl.utils import get_column_letter
    from ._common import records_to_dataframe, records_to_min_cd_dataframe

    is_multi = len(datasets) > 1
    red_fill  = PatternFill("solid", fgColor="FFAAAA")
    blue_fill = PatternFill("solid", fgColor="AAAAFF")
    hdr_font  = Font(bold=True)

    def _safe_sheet_name(label: str, idx: int) -> str:
        name = label.strip() or f"Dataset_{idx + 1}"
        # Excel sheet names: max 31 chars, no special chars
        for ch in r"\/?*[]":
            name = name.replace(ch, "_")
        return name[:31]

    def _color_measurement_sheet(ws, df):
        for row_idx, flag in enumerate(df["flag"], start=2):
            if flag == "MIN":
                for cell in ws[row_idx]:
                    cell.fill = red_fill
            elif flag == "MAX":
                for cell in ws[row_idx]:
                    cell.fill = blue_fill

    def _autofit_columns(ws):
        for col_cells in ws.columns:
            max_len = max(
                (len(str(c.value)) if c.value is not None else 0) for c in col_cells
            )
            ws.column_dimensions[get_column_letter(col_cells[0].column)].width = min(
                max(max_len + 2, 8), 40
            )

    def _stats_for_values(vals) -> dict:
        if not vals:
            return {k: "N/A" for k in ("count", "mean_nm", "median_nm", "q25_nm",
                                        "q75_nm", "std_nm", "3sigma_nm", "min_nm", "max_nm")}
        import statistics as _s
        n = len(vals)
        mean = _s.mean(vals)
        med  = _s.median(vals)
        std  = _s.stdev(vals) if n > 1 else 0.0
        qs   = _s.quantiles(vals, n=4) if n >= 2 else [vals[0], vals[0], vals[0]]
        return {
            "count":    n,
            "mean_nm":  round(mean, 3),
            "median_nm": round(med, 3),
            "q25_nm":   round(qs[0], 3),
            "q75_nm":   round(qs[2], 3),
            "std_nm":   round(std, 3),
            "3sigma_nm": round(std * 3, 3),
            "min_nm":   round(min(vals), 3),
            "max_nm":   round(max(vals), 3),
        }

    all_min_dfs: list = []
    summary_rows: list[dict] = []

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        for idx, (records, image_records, label) in enumerate(datasets):
            sheet_label = _safe_sheet_name(label, idx)
            meas_sheet  = sheet_label if is_multi else "Measurements"

            df_meas = records_to_dataframe(records, image_records, dataset_label="")
            df_meas.to_excel(writer, sheet_name=meas_sheet, index=False)

            # Colour measurement rows
            ws_meas = writer.book[meas_sheet]
            _color_measurement_sheet(ws_meas, df_meas)
            _autofit_columns(ws_meas)

            # Bold header row
            for cell in ws_meas[1]:
                cell.font = hdr_font

            # Collect stats for summary
            valid_vals = [
                float(r.calibrated_nm) for r in records
                if r.status not in ("rejected",)
            ]
            stats = _stats_for_values(valid_vals)
            summary_rows.append({"dataset": label or meas_sheet, **stats})

            # Collect min-CD rows for the combined Min CD per Image sheet
            df_min = records_to_min_cd_dataframe(records, image_records, dataset_label=label if is_multi else "")
            if not df_min.empty:
                all_min_dfs.append(df_min)

        # ── Statistics / Summary sheet ─────────────────────────────────────
        if is_multi:
            df_summary = pd.DataFrame(summary_rows)
            df_summary.to_excel(writer, sheet_name="Summary", index=False)
            ws_sum = writer.book["Summary"]
            for cell in ws_sum[1]:
                cell.font = hdr_font
            _autofit_columns(ws_sum)
        else:
            # Single-dataset: classic Statistics sheet
            records_single, image_records_single, _ = datasets[0]
            valid_vals = [
                float(r.calibrated_nm) for r in records_single
                if r.status not in ("rejected",)
            ]
            stats = _stats_for_values(valid_vals)
            stats_display = {
                "Metric": ["Count", "Mean (nm)", "Median (nm)", "Q25 (nm)", "Q75 (nm)",
                           "Std Dev (nm)", "3-Sigma (nm)", "Min (nm)", "Max (nm)"],
                "Value": [
                    stats["count"], stats["mean_nm"], stats["median_nm"],
                    stats["q25_nm"], stats["q75_nm"], stats["std_nm"],
                    stats["3sigma_nm"], stats["min_nm"], stats["max_nm"],
                ],
            }
            df_stats = pd.DataFrame(stats_display)
            df_stats.to_excel(writer, sheet_name="Statistics", index=False)
            ws_stat = writer.book["Statistics"]
            for cell in ws_stat[1]:
                cell.font = hdr_font
            _autofit_columns(ws_stat)

        # ── Min CD per Image sheet ─────────────────────────────────────────
        if all_min_dfs:
            df_all_min = pd.concat(all_min_dfs, ignore_index=True)
            df_all_min = df_all_min.sort_values("min_cd_nm").reset_index(drop=True)
            df_all_min.to_excel(writer, sheet_name="Min CD per Image", index=False)
            ws_min = writer.book["Min CD per Image"]
            for cell in ws_min[1]:
                cell.font = hdr_font
            # Highlight every row in red (all are min-CD rows)
            for row_idx in range(2, len(df_all_min) + 2):
                for cell in ws_min[row_idx]:
                    cell.fill = red_fill
            _autofit_columns(ws_min)
