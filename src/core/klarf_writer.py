"""KLARF 1.8 writer — round-trip faithful output.

Rules:
  - All non-DefectList sections reproduced verbatim from parsed raw_sections.
  - DefectList rows: only XREL and YREL are modified; every other field,
    including ImageInfo blocks, is reproduced exactly as parsed.
  - Data N count updated to reflect the output defect count.
  - SummaryRecord / TestSummaryList NDEFECT updated to match output count.
  - DEFECTID values are NOT renumbered.
  - XREL and YREL are written as integers (round-half-even of float result).
  - Atomic write: output first to <path>.tmp, then renamed to final path.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any


class KlarfWriter:
    """Write a KLARF 1.8 file from parsed structure + modified defect list."""

    def write(
        self,
        parsed: dict[str, Any],
        defects: list[dict[str, Any]],
        output_path: str | Path,
    ) -> None:
        """Serialise parsed KLARF structure with the given defect list.

        parsed   – dict returned by KlarfParser.parse()
        defects  – modified defect list (same schema as parsed["defects"])
        output_path – destination file path (atomic write via .tmp)
        """
        output_path = Path(output_path)
        tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
        content = self._build(parsed, defects)
        tmp_path.write_text(content, encoding="latin-1")
        os.replace(tmp_path, output_path)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _build(self, parsed: dict[str, Any], defects: list[dict[str, Any]]) -> str:
        columns = parsed.get("defect_columns", [])
        header_raw = parsed.get("defect_list_header_raw", "")
        n_defects = len(defects)
        parts: list[str] = []

        # Split raw_sections into pre-DefectList and post-DefectList groups,
        # and also handle SummaryRecord NDEFECT update inline.
        for sec in parsed.get("raw_sections", []):
            sec_name = sec["name"]
            raw = sec["text"]
            if sec_name in ("SummaryRecord", "TestSummaryList"):
                raw = _patch_ndefect(raw, n_defects)
            parts.append(raw)
            # Inject DefectList after WaferRecord (KLARF convention)
            if sec_name == "WaferRecord":
                parts.append(self._build_defect_list(header_raw, columns, defects))

        # Fallback: if WaferRecord wasn't found, append DefectList at end
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
                # Write ImageInfo block verbatim if present
                block = defect.get("_image_block_raw", "")
                if block:
                    tokens.append(block)
                    image_block_written = True
                else:
                    tokens.append(defect.get(col, ""))
            else:
                tokens.append(str(defect.get(col, "")))

        # Extra non-column fields (Image block already handled above)
        # Append any _extra_N fields that were parsed beyond the column list
        extra_keys = sorted(k for k in defect if k.startswith("_extra_"))
        for ek in extra_keys:
            tokens.append(str(defect[ek]))

        return " ".join(tokens) + " ;"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _format_coord(val: Any) -> str:
    """Round float coordinate to nearest integer and return as string."""
    try:
        return str(int(round(float(val))))
    except (TypeError, ValueError):
        return str(val)


def _patch_ndefect(raw: str, n: int) -> str:
    """Replace NDEFECT value in a SummaryRecord / TestSummaryList block."""
    return re.sub(r'(\bNDEFECT\b\s+)\d+', lambda m: m.group(1) + str(n), raw)
