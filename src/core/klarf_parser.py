"""KLARF 1.8 file parser.

Token-scan architecture: the file is split into whitespace-separated tokens
(preserving quoted strings as single tokens).  A state machine drives section
dispatch.  All non-DefectList sections are stored as raw text for round-trip
fidelity.  The DefectList section is parsed into a list of dicts keyed by the
dynamic column header.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


# ── Tokeniser ─────────────────────────────────────────────────────────────────

_QUOTED = re.compile(r'"[^"]*"')
_NEWLINE = re.compile(r'\r\n|\r|\n')


def _tokenise(text: str) -> list[str]:
    """Split KLARF text into tokens, preserving quoted strings intact."""
    tokens: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in (' ', '\t', '\r', '\n'):
            i += 1
            continue
        if ch == '"':
            end = text.find('"', i + 1)
            if end == -1:
                tokens.append(text[i:])
                break
            tokens.append(text[i:end + 1])
            i = end + 1
        else:
            j = i
            while j < n and text[j] not in (' ', '\t', '\r', '\n'):
                j += 1
            tokens.append(text[i:j])
            i = j
    return tokens


def _unquote(s: str) -> str:
    """Strip surrounding quotes from a quoted token."""
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    return s


# ── Parser ────────────────────────────────────────────────────────────────────

class KlarfParser:
    """Parse a KLARF 1.8 text file.

    Returns a dict with keys:
      raw_sections      list[dict]   – non-DefectList sections (order preserved)
                                       each dict: {"name": str, "text": str}
      defect_columns    list[str]    – column names from DefectList header
      defects           list[dict]   – one dict per defect, keyed by column name
      image_count       int          – value from IMAGECOUNT field (0 if absent)
      data_count        int          – value from "Data N" line (0 if absent)
      defect_list_header_raw str     – the "DefectList N col1 col2 …" line verbatim
    """

    def parse(self, filepath: str | Path) -> dict[str, Any]:
        text = Path(filepath).read_text(encoding="latin-1")
        return self._parse_text(text)

    def parse_text(self, text: str) -> dict[str, Any]:
        return self._parse_text(text)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _parse_text(self, text: str) -> dict[str, Any]:
        result: dict[str, Any] = {
            "raw_sections": [],
            "defect_columns": [],
            "defects": [],
            "image_count": 0,
            "data_count": 0,
            "defect_list_header_raw": "",
        }

        tokens = _tokenise(text)
        idx = 0
        n = len(tokens)

        # Track raw text for non-DefectList sections by accumulating lines
        current_section_lines: list[str] = []
        current_section_name: str = ""

        # We rebuild raw section text from the original file by line, using
        # the token positions as anchors only for section boundaries.
        # Simpler approach: split the file into lines, detect section headers,
        # and collect line groups.
        lines = _NEWLINE.split(text)
        result.update(self._parse_by_lines(lines))
        return result

    def _parse_by_lines(self, lines: list[str]) -> dict[str, Any]:
        result: dict[str, Any] = {
            "raw_sections": [],
            "defect_columns": [],
            "defects": [],
            "image_count": 0,
            "data_count": 0,
            "defect_list_header_raw": "",
        }

        i = 0
        n = len(lines)

        while i < n:
            stripped = lines[i].strip()
            if not stripped:
                i += 1
                continue

            # ── DefectList section ────────────────────────────────────────────
            if stripped.startswith("DefectList"):
                result["defect_list_header_raw"] = lines[i]
                parts = stripped.split()
                # "DefectList N col1 col2 …" — parts[0]="DefectList", parts[1]=N
                columns = parts[2:] if len(parts) > 2 else []
                result["defect_columns"] = columns

                # Parse data_count from "Data N" keyword right after header
                i += 1
                if i < n and lines[i].strip().lower().startswith("data "):
                    data_parts = lines[i].strip().split()
                    try:
                        result["data_count"] = int(data_parts[1])
                    except (IndexError, ValueError):
                        pass
                    i += 1

                # Now parse defect rows until EndOfList or EOF
                i = self._parse_defect_rows(lines, i, columns, result)
                continue

            # ── SummaryRecord — capture NDEFECT ──────────────────────────────
            if stripped.startswith("SummaryRecord") or stripped.startswith("TestSummaryList"):
                section_lines = [lines[i]]
                i += 1
                while i < n:
                    section_lines.append(lines[i])
                    if lines[i].strip().startswith("EndOfList"):
                        i += 1
                        break
                    i += 1
                raw_text = "\n".join(section_lines)
                # Find NDEFECT value inside this block
                for sl in section_lines:
                    m = re.search(r'\bNDEFECT\b\s+(\d+)', sl)
                    if m:
                        pass  # stored in raw text; writer will update it
                result["raw_sections"].append({
                    "name": stripped.split()[0],
                    "text": raw_text,
                })
                continue

            # ── All other sections — collect raw text ─────────────────────────
            keyword = stripped.split()[0] if stripped else ""
            if keyword and keyword[0].isupper() and keyword not in ("Data",):
                section_lines = [lines[i]]
                i += 1
                while i < n:
                    next_stripped = lines[i].strip()
                    # Check if next non-empty line starts a new top-level keyword
                    if next_stripped and _is_section_start(next_stripped) and not _is_continuation(next_stripped):
                        break
                    section_lines.append(lines[i])
                    i += 1
                raw_text = "\n".join(section_lines)
                # Extract IMAGECOUNT if present
                for sl in section_lines:
                    m = re.search(r'\bIMAGECOUNT\b\s+(\d+)', sl)
                    if m:
                        try:
                            result["image_count"] = int(m.group(1))
                        except ValueError:
                            pass
                result["raw_sections"].append({"name": keyword, "text": raw_text})
                continue

            i += 1

        return result

    def _parse_defect_rows(
        self,
        lines: list[str],
        start: int,
        columns: list[str],
        result: dict[str, Any],
    ) -> int:
        """Parse defect data rows; return the line index after EndOfList."""
        i = start
        n = len(lines)
        defects = result["defects"]

        while i < n:
            stripped = lines[i].strip()

            if not stripped:
                i += 1
                continue

            if stripped.startswith("EndOfList"):
                i += 1
                break

            # Accumulate tokens for one defect row (ends at ';')
            row_tokens: list[str] = []
            while i < n:
                line_stripped = lines[i].strip()
                if line_stripped.startswith("EndOfList"):
                    break
                # Tokenise this line and add to row_tokens
                toks = _tokenise(lines[i])
                row_tokens.extend(toks)
                i += 1
                # Check if row is complete (ends with ';')
                if row_tokens and row_tokens[-1] == ";":
                    break

            if not row_tokens:
                continue
            # Remove trailing ';'
            if row_tokens and row_tokens[-1] == ";":
                row_tokens = row_tokens[:-1]

            defect = self._map_row_tokens(row_tokens, columns)
            defects.append(defect)

        return i

    def _map_row_tokens(self, tokens: list[str], columns: list[str]) -> dict[str, Any]:
        """Map a flat token list (from one defect row) to a column-keyed dict.

        Handles embedded Image N { … } blocks as a single compound token.
        """
        result: dict[str, Any] = {}
        col_idx = 0
        tok_idx = 0
        n_tok = len(tokens)
        n_col = len(columns)

        while tok_idx < n_tok:
            tok = tokens[tok_idx]

            # ── Image block: "Image" N "{" … "}" ─────────────────────────────
            if tok == "Image" and tok_idx + 1 < n_tok:
                # Consume until closing brace
                block_tokens = [tok]
                tok_idx += 1
                while tok_idx < n_tok:
                    block_tokens.append(tokens[tok_idx])
                    tok_idx += 1
                    if tokens[tok_idx - 1] == "}":
                        break
                # Extract image filename: first quoted string inside braces
                image_stem = ""
                in_brace = False
                for bt in block_tokens:
                    if bt == "{":
                        in_brace = True
                        continue
                    if bt == "}":
                        break
                    if in_brace and bt.startswith('"'):
                        image_stem = _unquote(bt)
                        break
                result["_image_block_raw"] = " ".join(block_tokens)
                result["_image_filename"] = image_stem
                # This block occupies the "ImageInfo" column slot if present
                if col_idx < n_col and "image" in columns[col_idx].lower():
                    col_idx += 1
                continue

            # ── Normal token ──────────────────────────────────────────────────
            if col_idx < n_col:
                result[columns[col_idx]] = tok
            else:
                # Extra columns beyond header — store with generated key
                result[f"_extra_{tok_idx}"] = tok
            col_idx += 1
            tok_idx += 1

        return result


# ── Helpers ───────────────────────────────────────────────────────────────────

_TOP_LEVEL_KEYWORDS = {
    "RecordFileRecord", "LotRecord", "WaferRecord", "DefectList",
    "SummaryRecord", "TestRecord", "ClassLookupList", "EndOfList",
    "TestSummaryList", "FileVersion",
}


def _is_section_start(stripped: str) -> bool:
    word = stripped.split()[0] if stripped else ""
    return word in _TOP_LEVEL_KEYWORDS or (
        word and word[0].isupper() and "Record" in word
    )


def _is_continuation(stripped: str) -> bool:
    """Lines that look like data rows rather than section headers."""
    # Defect data rows start with a numeric DEFECTID
    return bool(stripped) and stripped[0].isdigit()
