"""KLARF writer — round-trip faithful output for both flat and hierarchical formats.

Flat KLARF 1.8
  - All non-DefectList sections reproduced verbatim from parsed raw_sections.
  - DefectList rows: only XREL and YREL are modified; all other fields,
    including Image/Images blocks, are reproduced exactly as parsed.
  - Data N count updated to reflect the output defect count.
  - SummaryRecord / TestSummaryList NDEFECT updated to match output count.

Hierarchical KLARF
  - hier_prefix (everything before "Data N") reproduced verbatim.
  - Data N count updated to reflect the output defect count.
  - Defect rows serialised inside the data block.
  - hier_suffix (closing braces etc.) reproduced verbatim.

Both formats:
  - DEFECTID values are NOT renumbered.
  - XREL and YREL are written as integers (round-half-even of float result).
  - Atomic write: output first to <path>.tmp, then renamed to final path.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)


class KlarfWriter:
    """Write a KLARF file from parsed structure + modified defect list."""

    def write(
        self,
        parsed: dict[str, Any],
        defects: list[dict[str, Any]],
        output_path: str | Path,
    ) -> None:
        output_path = Path(output_path)
        tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")

        fmt = parsed.get("format_type", "flat")
        _log.debug(
            "[writer] Format=%s, defects=%d, output=%s",
            fmt, len(defects), output_path,
        )

        if fmt == "hierarchical":
            content = self._build_hierarchical(parsed, defects)
        else:
            content = self._build(parsed, defects)

        tmp_path.write_text(content, encoding="latin-1")
        os.replace(tmp_path, output_path)
        _log.debug("[writer] Wrote %d bytes to %s", len(content), output_path)

    # ── Hierarchical build ────────────────────────────────────────────────────

    def _build_hierarchical(
        self,
        parsed: dict[str, Any],
        defects: list[dict[str, Any]],
    ) -> str:
        columns     = parsed.get("defect_columns", [])
        n_defects   = len(defects)
        prefix      = parsed.get("hier_prefix", "")
        data_indent = parsed.get("hier_data_indent", "        ")
        rows_indent = parsed.get("hier_rows_indent", "          ")
        suffix      = parsed.get("hier_suffix", "")

        _log.debug(
            "[writer] Hierarchical: data_indent=%r, rows_indent=%r",
            data_indent, rows_indent,
        )

        parts: list[str] = [
            prefix,
            f"{data_indent}Data {n_defects}",
            f"{data_indent}{{",
        ]
        for d in defects:
            row = self._serialise_defect(d, columns)
            parts.append(f"{rows_indent}{row}")
        # suffix starts with the closing "}" of the Data block
        parts.append(suffix)

        return "\n".join(parts) + "\n"

    # ── Flat build ────────────────────────────────────────────────────────────

    def _build(self, parsed: dict[str, Any], defects: list[dict[str, Any]]) -> str:
        columns    = parsed.get("defect_columns", [])
        header_raw = parsed.get("defect_list_header_raw", "")
        n_defects  = len(defects)
        parts: list[str] = []

        for sec in parsed.get("raw_sections", []):
            sec_name = sec["name"]
            raw = sec["text"]
            if sec_name in ("SummaryRecord", "TestSummaryList"):
                raw = _patch_ndefect(raw, n_defects)
            parts.append(raw)
            if sec_name == "WaferRecord":
                parts.append(self._build_defect_list(header_raw, columns, defects))

        section_names = [s["name"] for s in parsed.get("raw_sections", [])]
        if "WaferRecord" not in section_names:
            parts.append(self._build_defect_list(header_raw, columns, defects))

        return "\n".join(parts) + "\n"

    def _build_defect_list(
        self,
        header_raw: str,
        columns: list[str],
        defects: list[dict[str, Any]],
    ) -> str:
        lines: list[str] = []
        lines.append(header_raw if header_raw else f"DefectList {len(defects)}")
        lines.append(f"Data {len(defects)}")
        for d in defects:
            lines.append(self._serialise_defect(d, columns))
        lines.append("EndOfList")
        return "\n".join(lines)

    # ── Shared serialisation ──────────────────────────────────────────────────

    def _serialise_defect(self, defect: dict[str, Any], columns: list[str]) -> str:
        tokens: list[str] = []
        image_block_written = False

        for col in columns:
            col_lower = col.lower()
            if col_lower == "xrel":
                val = next((defect[k] for k in defect if k.lower() == "xrel"), "0")
                tokens.append(_format_coord(val))
            elif col_lower == "yrel":
                val = next((defect[k] for k in defect if k.lower() == "yrel"), "0")
                tokens.append(_format_coord(val))
            elif "image" in col_lower and not image_block_written:
                block = defect.get("_image_block_raw", "")
                if block:
                    tokens.append(block)
                    image_block_written = True
                else:
                    tokens.append(str(defect.get(col, "")))
            else:
                tokens.append(str(defect.get(col, "")))

        # Extra non-column fields parsed beyond the header
        extra_keys = sorted(k for k in defect if k.startswith("_extra_"))
        for ek in extra_keys:
            tokens.append(str(defect[ek]))

        return " ".join(tokens) + " ;"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _format_coord(val: Any) -> str:
    try:
        return str(int(round(float(val))))
    except (TypeError, ValueError):
        return str(val)


def _patch_ndefect(raw: str, n: int) -> str:
    return re.sub(r'(\bNDEFECT\b\s+)\d+', lambda m: m.group(1) + str(n), raw)
