"""
LaTeX Citation Reordering Agent.
Parses a .tex file, finds all \\cite{} commands in document order,
then renumbers the \\bibitem entries in the bibliography so they appear
as [1], [2], [3], ... in citation order.
"""
import re
from typing import Dict, List, Tuple, Optional


def reorder_citations(latex_source: str) -> Tuple[str, dict]:
    """
    Reorder bibliography entries in a LaTeX document so that citation numbers
    match the order in which keys first appear in the document body.

    Returns:
        (reordered_latex_str, info_dict)
        info_dict has keys: citation_map (old_key -> new_number), total_citations
    """
    # 1. Extract all cite keys in document-appearance order (before \bibliography or \begin{thebibliography})
    body, bib_block = _split_body_and_bib(latex_source)

    if bib_block is None:
        return latex_source, {"error": "No bibliography block found (\\begin{thebibliography} ... \\end{thebibliography})"}

    # 2. Find cite keys in body order
    ordered_keys = _extract_cite_keys_in_order(body)

    # 3. Parse bibitem entries from the bib block
    bibitems = _parse_bibitems(bib_block)

    if not bibitems:
        return latex_source, {"error": "No \\bibitem entries found in bibliography"}

    # 4. Build mapping: cite_key -> new sequential number
    seen: Dict[str, int] = {}
    counter = 1
    for key in ordered_keys:
        if key not in seen:
            seen[key] = counter
            counter += 1

    # Assign numbers to any remaining bibitem keys not cited in the body
    for key in bibitems.keys():
        if key not in seen:
            seen[key] = counter
            counter += 1

    # 5. Rebuild bibliography in new order
    new_bib_lines = ["\\begin{thebibliography}{99}\n"]
    sorted_items = sorted(seen.items(), key=lambda x: x[1])
    for cite_key, num in sorted_items:
        if cite_key in bibitems:
            entry_body = bibitems[cite_key]
            new_bib_lines.append(f"\\bibitem{{{cite_key}}}\n{entry_body}\n\n")

    new_bib_lines.append("\\end{thebibliography}")
    new_bib_block = "".join(new_bib_lines)

    # 6. Reassemble document
    result = _replace_bib_block(latex_source, new_bib_block)

    return result, {
        "citation_map": seen,
        "total_citations": len(seen),
        "keys_found_in_body": len([k for k in seen if k in set(ordered_keys)]),
    }


def _split_body_and_bib(source: str) -> Tuple[str, Optional[str]]:
    """Split source into (body, bibliography_block)."""
    pattern = re.compile(
        r"(\\begin\{thebibliography\}.*?\\end\{thebibliography\})",
        re.DOTALL,
    )
    m = pattern.search(source)
    if not m:
        return source, None
    bib_block = m.group(1)
    body = source[: m.start()]
    return body, bib_block


def _extract_cite_keys_in_order(body: str) -> List[str]:
    """Return cite keys in the order they first appear, preserving duplicates for ordering."""
    # Matches \cite{key}, \cite[opt]{key}, \citep{key,key2}, etc.
    pattern = re.compile(r"\\cite[a-z]*\*?\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}")
    keys: List[str] = []
    for m in pattern.finditer(body):
        for key in m.group(1).split(","):
            key = key.strip()
            if key:
                keys.append(key)
    return keys


def _parse_bibitems(bib_block: str) -> Dict[str, str]:
    """Parse \\bibitem{key} entries, returning {key: entry_text}."""
    # Remove the thebibliography wrapper
    inner = re.sub(r"\\begin\{thebibliography\}\{[^}]*\}", "", bib_block)
    inner = re.sub(r"\\end\{thebibliography\}", "", inner)

    bibitems: Dict[str, str] = {}
    # Split on \bibitem
    parts = re.split(r"\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}", inner)
    # parts[0] is text before first bibitem (ignore), then alternating key, content
    i = 1
    while i < len(parts) - 1:
        key = parts[i].strip()
        content = parts[i + 1].strip()
        bibitems[key] = content
        i += 2

    return bibitems


def _replace_bib_block(source: str, new_bib_block: str) -> str:
    pattern = re.compile(
        r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}",
        re.DOTALL,
    )
    # Use a lambda so re.sub never interprets backslashes in new_bib_block as backreferences
    return pattern.sub(lambda _: new_bib_block, source, count=1)
