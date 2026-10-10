"""What the central European nationality readers share.

By the owner's decision of 19 September 2026 a country whose census or
register counts citizenship (or country of birth, or migration background)
and not ethnicity carries that count on the ethnicity field, as a real
composition under ``ethnicity_basis`` -- the model is
``korea_nationality.py``. Germany, Austria, Switzerland, Liechtenstein, the
Netherlands, Belgium and Luxembourg all count nationality; their readers
each read their own office's table and bind it to the map, and everything
after that is the same job and lives here:

* the labels: an office's country names (German, Dutch) or Eurostat's codes
  become the nationality adjectives the group tree files ("Turkish",
  "Syrian", "Polish"), the way the Factbook's country rows write them;
* which nationalities are named: those at or above a share of the whole
  country's population, so that a district's bars and its country's bars
  name the same groups; the rest of the foreign population is "Other
  nationalities", and a nationality above the threshold with no label is a
  refusal rather than a silent fold into the residual;
* the composition itself, with the checks: the named groups and the residual
  make the unit's total, nothing is negative, and the shares make 100 to
  rounding.

Nothing here estimates anything: every figure is a count from the office's
table, and the note says what the register or census counted, on what date,
and that it is not an ethnicity question.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable

from ._shared import shares

OTHER = "Other nationalities"
STATELESS = "Stateless"
UNKNOWN = "Nationality unknown"
SUM_TOLERANCE = 0.3          # points, a unit's shares against 100

# Country names as the German-speaking offices write them (Destatis' Zensus
# 2022, Statistik Austria, BFS, Liechtenstein's Amt für Statistik) -> the
# nationality adjective. Keys are folded (see ``key``), so "Türkei" and
# "Tuerkei" meet, and a parenthesised former name ("Nordmazedonien (bis
# 2019: Mazedonien)") is dropped before the lookup.
GERMAN: dict[str, str] = {
    "deutschland": "German", "osterreich": "Austrian", "schweiz": "Swiss",
    "liechtenstein": "Liechtensteiner", "italien": "Italian", "frankreich": "French",
    "spanien": "Spanish", "portugal": "Portuguese", "griechenland": "Greek",
    "turkei": "Turkish", "turkiye": "Turkish", "polen": "Polish", "rumanien": "Romanian", "bulgarien": "Bulgarian",
    "ungarn": "Hungarian", "kroatien": "Croatian", "serbien": "Serbian",
    "serbienundmontenegro": "Serbian", "bosnienundherzegowina": "Bosnian and Herzegovinian",
    "bosnienherzegowina": "Bosnian and Herzegovinian", "kosovo": "Kosovan",
    "nordmazedonien": "North Macedonian", "mazedonien": "North Macedonian",
    "albanien": "Albanian", "montenegro": "Montenegrin", "slowenien": "Slovene",
    "slowakei": "Slovak", "tschechischerepublik": "Czech", "tschechien": "Czech",
    "ukraine": "Ukrainian", "russischefoderation": "Russian", "russland": "Russian",
    "belarus": "Belarusian", "weissrussland": "Belarusian", "moldau": "Moldovan",
    "republikmoldau": "Moldovan", "moldawien": "Moldovan", "litauen": "Lithuanian",
    "lettland": "Latvian", "estland": "Estonian", "niederlande": "Dutch",
    "belgien": "Belgian", "luxemburg": "Luxembourger", "vereinigteskonigreich": "British",
    "grossbritannien": "British", "irland": "Irish", "danemark": "Danish",
    "schweden": "Swedish", "norwegen": "Norwegian", "finnland": "Finnish",
    "island": "Icelandic", "malta": "Maltese", "zypern": "Cypriot",
    "syrien": "Syrian", "arabischerepubliksyrien": "Syrian",
    "irak": "Iraqi", "iran": "Iranian", "islamischerepublikiran": "Iranian",
    "afghanistan": "Afghan", "pakistan": "Pakistani", "indien": "Indian", "china": "Chinese",
    "vietnam": "Vietnamese", "thailand": "Thai", "philippinen": "Filipino",
    "srilanka": "Sri Lankan", "eritrea": "Eritrean", "somalia": "Somali",
    "nigeria": "Nigerian", "ghana": "Ghanaian", "marokko": "Moroccan",
    "tunesien": "Tunisian", "algerien": "Algerian", "agypten": "Egyptian",
    "athiopien": "Ethiopian", "kamerun": "Cameroonian",
    "vereinigtestaaten": "American", "vereinigtestaatenvonamerika": "American",
    "kanada": "Canadian", "brasilien": "Brazilian", "kolumbien": "Colombian",
    "kasachstan": "Kazakh", "georgien": "Georgian", "armenien": "Armenian",
    "aserbaidschan": "Azerbaijani", "libanon": "Lebanese", "israel": "Israeli",
    "japan": "Japanese", "korearepublik": "South Korean", "republikkorea": "South Korean",
    "sudkorea": "South Korean", "dominikanischerepublik": "Dominican",
    "mexiko": "Mexican", "argentinien": "Argentine", "chile": "Chilean", "peru": "Peruvian",
    "venezuela": "Venezuelan", "kuba": "Cuban", "bangladesch": "Bangladeshi",
    "nepal": "Nepalese", "mongolei": "Mongolian", "usbekistan": "Uzbek",
    "tadschikistan": "Tajik", "kirgisistan": "Kyrgyz", "jemen": "Yemeni",
    "jordanien": "Jordanian", "libyen": "Libyan", "sudan": "Sudanese",
    "sudafrika": "South African", "kenia": "Kenyan", "kongodemokratischerepublik": "Congolese",
    "demokratischerepublikkongo": "Congolese", "angola": "Angolan", "guinea": "Guinean",
    "senegal": "Senegalese", "gambia": "Gambian", "elfenbeinkuste": "Ivorian",
    "cotedivoire": "Ivorian", "australien": "Australian", "neuseeland": "New Zealander",
    "indonesien": "Indonesian", "malaysia": "Malaysian", "taiwan": "Taiwanese",
    "staatenlos": STATELESS, "ungeklart": UNKNOWN, "unbekannt": UNKNOWN,
    "ohneangabe": UNKNOWN, "ungeklartohneangabe": UNKNOWN,
}


# Eurostat's citizenship codes (ISO 3166 alpha-2, with EL for Greece, UK for
# the United Kingdom and XK for Kosovo) -> the nationality adjective.
ISO2: dict[str, str] = {
    "BE": "Belgian", "BG": "Bulgarian", "CZ": "Czech", "DK": "Danish", "DE": "German",
    "EE": "Estonian", "IE": "Irish", "EL": "Greek", "ES": "Spanish", "FR": "French",
    "HR": "Croatian", "IT": "Italian", "CY": "Cypriot", "LV": "Latvian", "LT": "Lithuanian",
    "LU": "Luxembourger", "HU": "Hungarian", "MT": "Maltese", "NL": "Dutch", "AT": "Austrian",
    "PL": "Polish", "PT": "Portuguese", "RO": "Romanian", "SI": "Slovene", "SK": "Slovak",
    "FI": "Finnish", "SE": "Swedish", "IS": "Icelandic", "LI": "Liechtensteiner",
    "NO": "Norwegian", "CH": "Swiss", "UK": "British", "BA": "Bosnian and Herzegovinian",
    "ME": "Montenegrin", "MD": "Moldovan", "MK": "North Macedonian", "GE": "Georgian",
    "AL": "Albanian", "RS": "Serbian", "TR": "Turkish", "UA": "Ukrainian", "XK": "Kosovan",
    "BY": "Belarusian", "RU": "Russian", "CM": "Cameroonian", "CD": "Congolese",
    "ER": "Eritrean", "ET": "Ethiopian", "SO": "Somali", "DZ": "Algerian", "EG": "Egyptian",
    "MA": "Moroccan", "TN": "Tunisian", "GN": "Guinean", "SN": "Senegalese",
    "NG": "Nigerian", "GH": "Ghanaian", "CI": "Ivorian", "CA": "Canadian", "US": "American",
    "BR": "Brazilian", "CO": "Colombian", "VE": "Venezuelan", "PE": "Peruvian",
    "AF": "Afghan", "SY": "Syrian", "IQ": "Iraqi", "IR": "Iranian", "IN": "Indian",
    "PK": "Pakistani", "CN": "Chinese", "PH": "Filipino", "VN": "Vietnamese", "TH": "Thai",
    "JP": "Japanese", "KR": "South Korean", "LB": "Lebanese", "IL": "Israeli",
    "AM": "Armenian", "AZ": "Azerbaijani", "KZ": "Kazakh", "BD": "Bangladeshi", "NP": "Nepalese",
    "LK": "Sri Lankan", "AU": "Australian", "CV": "Cape Verdean", "AO": "Angolan",
    "RW": "Rwandan", "BI": "Burundian", "PS": "Palestinian",
}


def key(name: str) -> str:
    """A country name folded for lookup: no accents, no punctuation, no
    parenthesised remark, no indentation marks, lower case."""
    text = re.sub(r"\([^)]*\)", "", str(name or ""))
    text = text.strip().lstrip(".-> ").strip()
    text = unicodedata.normalize("NFKD", text.replace("ß", "ss"))
    return "".join(c for c in text.lower() if c.isalnum() and not unicodedata.combining(c))


def label_for(name: str, table: dict[str, str]) -> str | None:
    return table.get(key(name))


def named(national: dict[str, float], total: float, labels: dict[str, str | None], *,
          share: float, always: Iterable[str] = ()) -> list[str]:
    """The source categories named on the map: those whose national count is at
    least ``share`` of the national ``total``, and those in ``always``.

    ``labels`` maps every source category to its label or None. A category at
    or above the threshold with no label stops the run: it would otherwise
    disappear into the residual, and the residual is for the small ones.
    """
    always = set(always)
    out, unlabelled = [], []
    for category, count in sorted(national.items(), key=lambda kv: (-kv[1], kv[0])):
        if category in always or (total and count / total >= share):
            if labels.get(category) is None:
                unlabelled.append(f"{category} ({count:,.0f})")
                continue
            out.append(category)
    if unlabelled:
        raise SystemExit("nationalities above the naming threshold with no label: "
                         + ", ".join(unlabelled))
    return out


def composition(counts: dict[str, float], total: float, names: list[str],
                labels: dict[str, str | None], *, residual: str = OTHER,
                where: str = "") -> list[dict[str, Any]]:
    """Shares of ``total`` for the named categories (by label, merged where two
    categories share one) and ``residual`` for the rest of the unit.

    ``counts`` holds the unit's counts by source category, every category of
    the table, so that their sum can be checked against the total; the named
    ones are kept and the residual is the total less them.
    """
    if total <= 0:
        return []
    made = sum(counts.values())
    if abs(made - total) > max(2.0, 0.0005 * total):
        raise SystemExit(f"{where}: the categories make {made:,.0f}, the total is {total:,.0f}")
    by_label: dict[str, float] = {}
    for category in names:
        label = labels[category]
        by_label[label] = by_label.get(label, 0.0) + counts.get(category, 0.0)
    rest = total - sum(by_label.values())
    if rest < -0.5:
        raise SystemExit(f"{where}: the named nationalities make {sum(by_label.values()):,.0f}, "
                         f"more than the total {total:,.0f}")
    if rest > 0.5:
        by_label[residual] = by_label.get(residual, 0.0) + rest
    rows = shares({k: v for k, v in by_label.items() if v > 0}, total=total)
    pct = sum(r["pct"] for r in rows)
    if abs(pct - 100.0) > SUM_TOLERANCE + 0.05 * len(rows):
        raise SystemExit(f"{where}: shares sum to {pct}")
    return rows


def note(what: str, when: str, question: str, *, extra: str = "",
         residual: str | None = OTHER) -> str:
    """The ethnicity note every reader writes: what was counted, when, and that
    it is not ethnicity, which the census does not ask. ``residual`` is the bar the
    nationalities below the naming threshold go to, or None where the office's
    own groups are written whole and nothing is folded."""
    rest = (f"; nationalities below the naming threshold are '{residual}'" if residual else "")
    return (f"{what} on {when}: {question} -- NATIONALITY, not ethnicity, which this country's "
            f"census does not ask. A person's own nationality is counted, naturalised "
            f"citizens with the country's own nationals{rest}.{(' ' + extra) if extra else ''}")
