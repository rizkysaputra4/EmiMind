"""XBRL instance document parser and fact extractor."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation

from services.shared.types import BBox, ExtractedFact, PeriodType


def parse_xbrl(xbrl_bytes: bytes) -> list[ExtractedFact]:
    """Parses raw XBRL instance XML bytes into ExtractedFact objects with 1.0 confidence."""
    facts: list[ExtractedFact] = []

    try:
        root = ET.fromstring(xbrl_bytes)  # noqa: S314
    except ET.ParseError:
        return facts

    # Map contexts to period types
    context_period_types: dict[str, PeriodType] = {}
    for elem in root.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag == "context":
            context_id = elem.attrib.get("id", "")
            period_elem = None
            for child in elem:
                c_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if c_tag == "period":
                    period_elem = child
                    break

            pt: PeriodType = "duration_ytd"
            if period_elem is not None:
                for p_child in period_elem:
                    p_tag = p_child.tag.split("}")[-1] if "}" in p_child.tag else p_child.tag
                    if p_tag == "instant":
                        pt = "instant"
                        break
                    elif p_tag in ("startDate", "endDate"):
                        pt = "duration_ytd"
            context_period_types[context_id] = pt

    # Map units
    unit_map: dict[str, str] = {}
    for elem in root.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag == "unit":
            unit_id = elem.attrib.get("id", "")
            measure_text = ""
            for child in elem.iter():
                c_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if c_tag == "measure" and child.text:
                    measure_text = child.text.strip()
            unit_map[unit_id] = measure_text or "IDR"

    # Extract concept facts
    for elem in root:
        tag_full = elem.tag
        if not tag_full.startswith("{"):
            continue

        ns, local_name = tag_full[1:].split("}", 1)
        # Skip standard infrastructure elements
        if local_name in ("context", "unit", "schemaRef"):
            continue

        text_val = (elem.text or "").strip()
        if not text_val:
            continue

        # Try parsing numeric value
        try:
            val_num = float(Decimal(text_val))
        except (InvalidOperation, ValueError):
            continue

        context_ref = elem.attrib.get("contextRef", "")
        unit_ref = elem.attrib.get("unitRef", "")

        unit_str = unit_map.get(unit_ref, "IDR")
        if ":" in unit_str:
            unit_str = unit_str.split(":")[-1]

        period_type = context_period_types.get(context_ref, "duration_ytd")
        full_concept_uri = f"{ns}/{local_name}"

        facts.append(
            ExtractedFact(
                concept_local=full_concept_uri,
                value_numeric=val_num,
                unit=unit_str,
                period_type=period_type,
                source_page=0,
                source_bbox=BBox(0.0, 0.0, 0.0, 0.0),
                confidence=1.0,
                method="xbrl",
            )
        )

    return facts
