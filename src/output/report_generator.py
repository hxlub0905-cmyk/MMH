"""Generate an HTML statistical report with embedded histogram."""

from __future__ import annotations
import base64
import io
import statistics as _stats
from datetime import datetime
from pathlib import Path


def generate_report(results: list[dict], out_path: Path, nm_per_pixel: float) -> None:
    from ._common import results_to_dataframe   # lazy — needs pandas
    df = results_to_dataframe(results, nm_per_pixel)
    ok = df[df["status"] == "OK"]["y_cd_nm"].dropna().tolist()

    n_total = len(results)
    n_fail = sum(1 for r in results if r.get("status") != "OK")
    n_ok = n_total - n_fail

    stats = _compute_stats(ok)
    hist_b64 = _histogram_b64(ok) if ok else ""
    fail_list = [Path(r["path"]).name for r in results if r.get("status") != "OK"]

    html = _render_html(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        n_total=n_total,
        n_ok=n_ok,
        n_fail=n_fail,
        nm_per_pixel=nm_per_pixel,
        stats=stats,
        hist_b64=hist_b64,
        fail_list=fail_list,
    )
    out_path.write_text(html, encoding="utf-8")


def _compute_stats(ok: list[float]) -> dict:
    """Return CD statistics dict from a plain float list. No pandas required."""
    if not ok:
        return {k: "N/A" for k in
                ["Count", "Mean (nm)", "Median (nm)", "Std Dev (nm)",
                 "3-Sigma (nm)", "Min (nm)", "Max (nm)"]}
    n = len(ok)
    mean_v   = _stats.mean(ok)
    median_v = _stats.median(ok)
    std_v    = _stats.stdev(ok) if n > 1 else 0.0
    return {
        "Count":       n,
        "Mean (nm)":   f"{mean_v:.3f}",
        "Median (nm)": f"{median_v:.3f}",
        "Std Dev (nm)":f"{std_v:.3f}",
        "3-Sigma (nm)":f"{std_v * 3:.3f}",
        "Min (nm)":    f"{min(ok):.3f}",
        "Max (nm)":    f"{max(ok):.3f}",
    }


def _histogram_b64(values: list[float]) -> str:
    """Render a CD-distribution histogram; requires matplotlib (optional)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        return ""
    arr = np.asarray(values, dtype=float)
    mean_v = float(arr.mean())
    std_v  = float(arr.std())
    fig, ax = plt.subplots(figsize=(7, 3.5), dpi=100)
    ax.hist(arr, bins="auto", color="#4a90d9", edgecolor="white", linewidth=0.5)
    ax.axvline(mean_v, color="red", linestyle="--", linewidth=1.5, label=f"Mean={mean_v:.2f}")
    ax.axvline(mean_v - 3 * std_v, color="orange", linestyle=":", linewidth=1, label="-3σ")
    ax.axvline(mean_v + 3 * std_v, color="orange", linestyle=":", linewidth=1, label="+3σ")
    ax.set_xlabel("CD (nm)")
    ax.set_ylabel("Count")
    ax.set_title("CD Distribution")
    ax.legend(fontsize=8)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def generate_report_from_records(
    records: list,
    out_path: Path,
    image_records: list | None = None,
    batch_run=None,
) -> None:
    """Generate HTML report from MeasurementRecord list — no pandas required."""
    ok = [
        float(r.calibrated_nm)
        for r in records
        if getattr(r, "status", "normal") not in ("rejected",)
    ]

    n_ok    = len(ok)
    n_total = batch_run.total_images if batch_run else len(image_records or []) or 1
    n_fail  = batch_run.fail_count   if batch_run else 0
    nm_per_pixel = float(image_records[0].pixel_size_nm) if image_records else 1.0

    stats    = _compute_stats(ok)
    hist_b64 = _histogram_b64(ok) if ok else ""

    fail_list: list[str] = []
    if batch_run:
        fail_list = [entry.get("image_path", "") for entry in batch_run.error_log]

    html = _render_html(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        n_total=n_total,
        n_ok=n_ok,
        n_fail=n_fail,
        nm_per_pixel=nm_per_pixel,
        stats=stats,
        hist_b64=hist_b64,
        fail_list=[Path(p).name for p in fail_list if p],
    )
    out_path.write_text(html, encoding="utf-8")


def _render_html(
    timestamp: str,
    n_total: int,
    n_ok: int,
    n_fail: int,
    nm_per_pixel: float,
    stats: dict,
    hist_b64: str,
    fail_list: list[str],
) -> str:
    stat_rows = "".join(
        f"<tr><td>{k}</td><td><b>{v}</b></td></tr>" for k, v in stats.items()
    )
    fail_items = "".join(f"<li>{name}</li>" for name in fail_list) or "<li>None</li>"
    hist_tag = (
        f'<img src="data:image/png;base64,{hist_b64}" alt="histogram" style="max-width:700px">'
        if hist_b64 else
        '<p style="color:#888">Histogram unavailable (install matplotlib to enable).</p>'
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>SEM MM Report</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 32px; color: #222; }}
  h1 {{ color: #2c5f8a; }}
  h2 {{ color: #444; border-bottom: 1px solid #ccc; padding-bottom: 4px; }}
  table {{ border-collapse: collapse; margin-bottom: 20px; }}
  td, th {{ border: 1px solid #ccc; padding: 6px 14px; }}
  th {{ background: #eaf0f8; }}
  .summary {{ display: flex; gap: 24px; }}
  .card {{ background: #f5f8fc; border: 1px solid #d0dcea; border-radius: 6px;
           padding: 14px 22px; min-width: 120px; text-align: center; }}
  .card .val {{ font-size: 2em; font-weight: bold; color: #2c5f8a; }}
  .fail {{ color: #c00; }}
</style>
</head>
<body>
<h1>SEM MM — Batch Measurement Report</h1>
<p>Generated: {timestamp} &nbsp;|&nbsp; nm/pixel: {nm_per_pixel}</p>

<h2>Batch Summary</h2>
<div class="summary">
  <div class="card"><div class="val">{n_total}</div>Total Images</div>
  <div class="card"><div class="val" style="color:#2a7a2a">{n_ok}</div>OK</div>
  <div class="card"><div class="val fail">{n_fail}</div>Failed</div>
</div>

<h2>Y-CD Statistics</h2>
<table>
  <tr><th>Metric</th><th>Value</th></tr>
  {stat_rows}
</table>

<h2>Y-CD Distribution</h2>
{hist_tag}

<h2>Failed Images</h2>
<ul class="fail">{fail_items}</ul>
</body>
</html>"""
