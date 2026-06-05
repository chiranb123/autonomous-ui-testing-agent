import re


# Recognizes AC headers like:
#   AC1 - Successful Login
#   AC1 – Successful Login        (em-dash)
#   AC1 — Successful Login        (em-dash 2)
#   AC1. Successful Login
#   AC1: Successful Login
#   AC1) Successful Login
#   AC 1 - Successful Login
_AC_HEADER_RE = re.compile(
    r'^\s*AC\s*\d+\s*[-\u2013\u2014.:)]\s*(.+?)\s*$',
    re.IGNORECASE,
)


class ACExtractor:

    def extract(self, text: str) -> list[str]:
        """
        Extract acceptance criteria from issue body text.

        Strategy:
          1. If "AC<N>" headers are present (AC1, AC2 ...), each block from one
             header to the next is treated as ONE acceptance criterion, with
             the title + body collapsed into a single readable string.
          2. Otherwise fall back to bullet/numbered-list parsing.
        """
        if not text:
            return []

        # ---- Strategy 1: AC<N> header blocks ----------------------------
        blocks = self._extract_ac_blocks(text)
        if blocks:
            return blocks

        # ---- Strategy 2: line-by-line bullet/number parsing -------------
        ac_section = self._extract_ac_section(text)
        source = ac_section if ac_section else text

        acs: list[str] = []
        for line in source.splitlines():
            line = line.strip()
            if not line:
                continue

            # "- Some text" or "* Some text"
            if line.startswith(("-", "*")):
                cleaned = line.lstrip("-* ").strip()
                if cleaned:
                    acs.append(cleaned)
                continue

            # "1. Some text"
            m = re.match(r'^\d+\.\s+(.+)', line)
            if m:
                acs.append(m.group(1).strip())

        return acs

    # ------------------------------------------------------------------
    # AC<N> block extraction
    # ------------------------------------------------------------------

    def _extract_ac_blocks(self, text: str) -> list[str]:
        """Return one combined string per AC<N> block, or [] if none found."""
        lines = text.splitlines()

        # Locate every AC header line
        headers: list[tuple[int, str]] = []  # (line_index, title)
        for idx, line in enumerate(lines):
            m = _AC_HEADER_RE.match(line)
            if m:
                headers.append((idx, m.group(1).strip()))

        if not headers:
            return []

        blocks: list[str] = []
        for i, (start, title) in enumerate(headers):
            end = headers[i + 1][0] if i + 1 < len(headers) else len(lines)
            body_lines = [
                ln.strip() for ln in lines[start + 1 : end]
                if ln.strip()
                and not self._is_section_heading(ln.strip())
            ]
            # Combine title + key body lines into one readable AC
            if body_lines:
                # Keep body compact — most Gherkin blocks are short
                body = " ".join(body_lines)
                blocks.append(f"{title}: {body}")
            else:
                blocks.append(title)
        return blocks

    @staticmethod
    def _is_section_heading(line: str) -> bool:
        """Skip section dividers like '### Negative Acceptance Criteria'."""
        if line.startswith("#"):
            return True
        lower = line.lower().rstrip(":").strip()
        return lower in {
            "acceptance criteria",
            "negative acceptance criteria",
            "positive acceptance criteria",
        }

    # ------------------------------------------------------------------
    # Fallback: section extraction
    # ------------------------------------------------------------------

    def _extract_ac_section(self, text: str) -> str | None:
        """Return only the text under an Acceptance Criteria heading."""
        heading_pattern = re.compile(
            r'^#{0,3}\s*Acceptance Criteria[:\s]*$', re.IGNORECASE
        )
        next_heading_pattern = re.compile(r'^#{1,3}\s+\S', re.IGNORECASE)

        lines = text.splitlines()
        capturing = False
        collected = []

        for line in lines:
            if heading_pattern.match(line.strip()):
                capturing = True
                continue
            if capturing:
                if next_heading_pattern.match(line.strip()):
                    break
                collected.append(line)

        return "\n".join(collected).strip() if collected else None
