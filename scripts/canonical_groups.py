#!/usr/bin/env python3
"""Cross-country names for the same religion, language or ethnic group.

A global filter is only possible if "Muslim" and "Islam" are known to be the
same answer. They are not the same *string*: across nine countries the religion
field alone carries 39 distinct labels for perhaps a dozen religions, because
each statistical office writes its own. Filtering on raw labels would show a
world map of Islam that silently omits every country whose census says
"Muslim" -- 865 units in one spelling, 737 in the other.

So this is the one table that says which labels name the same thing. It is
consumed by build_entities.py to emit site/data/groups.json, which the frontend
reads; there is deliberately no second copy of it in JavaScript.

Three rules govern what may be merged.

**Only merge what is genuinely the same question.** A rolled-up group must mean
the same thing in each country, not merely sound similar.

**Roll up, never across.** Where a country reports finer categories than the
canonical group -- the US reports Protestant, Catholic, Orthodox, Latter-day
Saints and Jehovah's Witnesses where Australia reports "Christianity" -- the
children sum to the parent. A source is never asked to supply both levels, so
summing cannot double count; the guard in ``canonicalise`` enforces that.

**Never merge an ambiguity into a certainty.** The US "Unaffiliated or not
reported" is deliberately absent from ``No religion`` below. It mixes people
who belong to nothing with members of bodies that did not report, and folding
it in would turn "we cannot tell" into a count of the non-religious.
"""

from __future__ import annotations

from typing import Any, Iterable

# canonical name -> the source labels that mean it
RELIGION: dict[str, tuple[str, ...]] = {
    "Christianity": (
        "Christian", "Christianity",
        # Reported at denomination or tradition level by some offices. These
        # are children of Christianity, never siblings of it in one source.
        "Catholic", "Roman Catholic", "Católica Apostólica Romana",
        "Protestant", "Evangélicas", "Orthodox Christian", "Other Christian",
        "Latter-day Saints", "Jehovah's Witnesses",
    ),
    "Islam": ("Islam", "Muslim"),
    "Hinduism": ("Hindu", "Hinduism"),
    "Buddhism": ("Buddhist", "Buddhism"),
    "Judaism": ("Jewish", "Judaism"),
    "Sikhism": ("Sikh", "Sikhism"),
    "Jainism": ("Jain", "Jainism"),
    "Taoism and folk religion": ("Taoist", "Taoism"),
    "Spiritism and Afro-Brazilian religions": (
        "Espírita", "Umbanda e Candomblé",
    ),
    "No religion": (
        "No religion", "No religion / secular", "Sem religião",
        "Secular Other Spiritual and No Religious Affiliation",
    ),
    "Not stated": (
        "Not stated", "Not answered", "Religious affiliation not stated",
        "Sem declaração", "Não sabe",
    ),
    "Other religions": (
        "Other", "Other religion", "Other religions", "Other Religions",
        "Outras religiosidades",
    ),
}

# Language is mostly *not* reconcilable and the table stays small on purpose.
# The US ACS reports bands ("German or other West Germanic", "Chinese (incl.
# Mandarin, Cantonese)") where India reports individual mother tongues, and a
# band is not a language. Only names that denote the same language are here.
LANGUAGE: dict[str, tuple[str, ...]] = {
    "Tamil": ("Tamil",),
    "Hindi": ("Hindi",),
    "Bengali": ("Bengali",),
    "Malay": ("Malay",),
    "German": ("German",),
    "French": ("French",),
    "Italian": ("Italian",),
    "Romansh": ("Romansh",),
    "English": ("English",),
}

# Ethnicity is not merged at all. Every country's categories are an artefact of
# its own history -- Brazil's cor ou raça, the UK's tick-boxes, China's 56
# nationalities, the US race-and-Hispanic-origin pair -- and none of them is a
# subdivision of another. Offering "White" as a worldwide filter would invite a
# comparison that the sources do not support. Raw labels remain filterable
# per country; there is simply no canonical layer above them.
ETHNICITY: dict[str, tuple[str, ...]] = {}

TABLES: dict[str, dict[str, tuple[str, ...]]] = {
    "religion": RELIGION,
    "language": LANGUAGE,
    "ethnicity": ETHNICITY,
}


def lookup(field: str) -> dict[str, str]:
    """Source label -> canonical name, for one field."""
    out: dict[str, str] = {}
    for canonical, labels in TABLES.get(field, {}).items():
        for label in labels:
            out[label] = canonical
    return out


def canonicalise(rows: Iterable[dict[str, Any]], field: str) -> dict[str, float]:
    """Sum one record's composition into canonical groups.

    Labels with no canonical name keep their own, so nothing is dropped: an
    unmapped group stays filterable under exactly the name its census used.
    """
    table = lookup(field)
    out: dict[str, float] = {}
    for row in rows or ():
        pct = row.get("pct")
        if not isinstance(pct, (int, float)):
            continue
        name = table.get(row.get("group", ""), row.get("group", ""))
        out[name] = out.get(name, 0.0) + pct
    return out


def check_no_double_counting(rows: Iterable[dict[str, Any]], field: str,
                             ) -> list[str]:
    """Names in one record that would be summed with their own parent.

    Rolling children into a parent is only safe while no source reports both
    levels at once. If one ever does -- an "ABS Christianity Total" row beside
    its denominations -- this returns the offending labels rather than letting
    the total quietly double.
    """
    table = lookup(field)
    seen: dict[str, list[str]] = {}
    for row in rows or ():
        if not isinstance(row.get("pct"), (int, float)):
            continue
        label = row.get("group", "")
        canonical = table.get(label, label)
        seen.setdefault(canonical, []).append(label)
    # A canonical group reached by its own name AND by a *different* label that
    # rolls into it means the source published the parent and the child side by
    # side. The same label twice is a different thing -- the Factbook lists
    # Bissa twice for Burkina Faso -- and summing those is right, not a fault.
    return [c for c, labels in seen.items()
            if len(set(labels)) > 1 and c in labels]
