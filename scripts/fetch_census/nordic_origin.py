#!/usr/bin/env python3
"""Nationality, country of birth or background on the ethnicity field: the five Nordic countries.

None of the Nordic censuses asks ethnicity: all five are compiled from
population registers, and no register records it. For as long as this map
read only what a census asks, their units said so (``NOT_COLLECTED_POLICY``).
What the registers do record is where people come from -- a country of
birth, a citizenship, and in Denmark, Norway and Finland a parent's country --
and on 19 September 2026 the map's owner decided that the ethnicity field
may carry such a count as a real composition, under an ``ethnicity_basis``
that names exactly what it is (``korea_nationality.py`` is the model). This
module is that decision for the five countries. It is a count throughout:
nothing here estimates anything.

Each office's best measure, by the units the map draws:

* **Sweden** -- SCB ``FolkmRegFlandKCKM``, population by region and country of
  birth on 31 December, for the 290 kommuner and 21 län. SCB publishes
  citizenship by kommun only as a total of foreign citizens, and foreign or
  Swedish background without a country, so country of birth is the finest
  count there is. Basis "country of birth".
* **Denmark** -- StatBank ``FOLK1C``, population by region, ancestry and
  country of origin on the first day of the quarter, for the 98 kommuner and
  5 regions. Persons of Danish origin, and immigrants and their descendants by
  country of origin. Basis "ancestry and country of origin".
* **Norway** -- SSB table 09817, immigrants and Norwegian-born to immigrant
  parents by country background on 1 January, against the population of the
  same kommune and day in 07459; the rest of the population is "Norwegian".
  By the 2017 kommuner the map draws: a kommune unchanged since takes the
  latest year under its number today, a merged or split one its last whole
  year under its number then (``norway.lineage``). The fylker as
  ``norway.py`` reads them. Basis "immigrant background".
* **Finland** -- Statistics Finland 11rv, population by origin and background
  country by municipality on 31 December, summed into the 2020 sub-regions
  and regions the map draws by the classification's municipality keys of
  that year (the regions are the 2020 ones too: Kuhmoinen is drawn in
  Central Finland). Basis "origin and background country".
* **Iceland** -- Hagstofa MAN04203, population by municipality and
  citizenship on 1 January, for the 2017 municipalities the map draws that
  are the same territory today (``iceland.unchanged_since``) and the eight
  regions. The table lays every year out in today's municipalities, so a
  municipality merged since 2017 has no figure of its own, and its record says
  so. Basis "citizenship".

**Labels.** The country an office names is written as its people's adjective
("Syrian", "Polish"), consistent with the group tree and the Factbook rows. A
country is named where it holds at least ``NAMED_SHARE`` of the country's
people nationally; every smaller one is counted in "Other", and a country the
office does not know in "Not stated". The home row is the country's own
adjective, and each note says what that row is in that register: everyone
born in Sweden, everyone of Danish origin, every Icelandic citizen.

**Checks.** Each unit's countries must make the unit's total (within SCB's
cell-key noise for Sweden); the units must make their parents and the
country; every drawn unit must be bound one to one, by the adapters'
own binding for that country; a country above the naming threshold that the
table here does not know stops the run, rather than fold a large community
into "Other" unseen.

Usage:
    python -m scripts.fetch_census.nordic_origin --country SWE
"""

from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from typing import Any, Iterable

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, record, shares, write_json
from .binding import fold
from .nordic_common import (bind_rows, check_parts, load_units, request, request_json,
                            unplaced)
from .pxweb import unstack

# A country of origin is named where it holds at least this share of the
# country's people: 0.1% is some 10,600 people in Sweden and 390 in Iceland,
# which names twenty to forty countries each and folds the long tail.
NAMED_SHARE = 0.001
OTHER = "Other"
UNKNOWN = "Not stated"
STATELESS = "Stateless"

# ISO 3166 code (or a historical state's) -> "adjective|the office's English
# names for it". The names are every spelling the five offices use; a name
# matches after folding (case, accents, punctuation).
COUNTRIES: dict[str, str] = {
    "AD": "Andorran|Andorra", "AE": "Emirati|United Arab Emirates",
    "AF": "Afghan|Afghanistan", "AG": "Antiguan|Antigua and Barbuda",
    "AL": "Albanian|Albania", "AM": "Armenian|Armenia", "AO": "Angolan|Angola",
    "AR": "Argentine|Argentina", "AT": "Austrian|Austria", "AU": "Australian|Australia",
    "AZ": "Azerbaijani|Azerbaijan", "BA": "Bosnian|Bosnia and Herzegovina|Bosnia-Herzegovina",
    "BB": "Barbadian|Barbados", "BD": "Bangladeshi|Bangladesh", "BE": "Belgian|Belgium",
    "BF": "Burkinabe|Burkina Faso", "BG": "Bulgarian|Bulgaria", "BH": "Bahraini|Bahrain",
    "BI": "Burundian|Burundi", "BJ": "Beninese|Benin", "BN": "Bruneian|Brunei|Brunei Darussalam",
    "BO": "Bolivian|Bolivia", "BR": "Brazilian|Brazil", "BS": "Bahamian|Bahamas",
    "BT": "Bhutanese|Bhutan", "BW": "Botswanan|Botswana", "BY": "Belarusian|Belarus",
    "BZ": "Belizean|Belize", "CA": "Canadian|Canada",
    "CD": "Congolese|Democratic Republic of the Congo|Congo, the Democratic Republic of the|"
          "Congo, Democratic Republic of the|Congo, Democratic Republic|DR Congo|Congo (Kinshasa)",
    "CF": "Central African|Central African Republic",
    "CG": "Congolese|Congo, the Republic of the|Congo, Republic of the|Congo, Republic|"
          "Congo-Brazzaville|Republic of the Congo|Congo",
    "CH": "Swiss|Switzerland",
    "CI": "Ivorian|Cote d'Ivoire|Côte d'Ivoire|Cote d´Ivoire|Côte d'Ivore|Cote d Ivoire|Ivory Coast",
    "CL": "Chilean|Chile", "CM": "Cameroonian|Cameroon", "CN": "Chinese|China",
    "CO": "Colombian|Colombia", "CR": "Costa Rican|Costa Rica", "CU": "Cuban|Cuba",
    "CV": "Cape Verdean|Cape Verde|Cabo Verde", "CY": "Cypriot|Cyprus",
    "CZ": "Czech|Czech Republic|Czechia", "DE": "German|Germany|Federal Republic of Germany",
    "DJ": "Djiboutian|Djibouti", "DK": "Danish|Denmark", "DM": "Dominican|Dominica",
    "DO": "Dominican|Dominican Republic", "DZ": "Algerian|Algeria", "EC": "Ecuadorian|Ecuador",
    "EE": "Estonian|Estonia", "EG": "Egyptian|Egypt", "EH": "Sahrawi|Western Sahara",
    "ER": "Eritrean|Eritrea", "ES": "Spanish|Spain", "ET": "Ethiopian|Ethiopia",
    "FI": "Finnish|Finland", "FJ": "Fijian|Fiji", "FO": "Faroese|Faroe Islands|Faroes",
    "FR": "French|France", "GA": "Gabonese|Gabon",
    "GB": "British|United Kingdom|Great Britain|United Kingdom of Great Britain and Northern Ireland",
    "GD": "Grenadian|Grenada", "GE": "Georgian|Georgia", "GH": "Ghanaian|Ghana",
    "GL": "Greenlandic|Greenland", "GM": "Gambian|Gambia|The Gambia", "GN": "Guinean|Guinea",
    "GQ": "Equatorial Guinean|Equatorial Guinea", "GR": "Greek|Greece",
    "GT": "Guatemalan|Guatemala", "GW": "Bissau-Guinean|Guinea-Bissau", "GY": "Guyanese|Guyana",
    "HK": "Hong Konger|Hong Kong", "HN": "Honduran|Honduras", "HR": "Croatian|Croatia",
    "HT": "Haitian|Haiti", "HU": "Hungarian|Hungary", "ID": "Indonesian|Indonesia",
    "IE": "Irish|Ireland", "IL": "Israeli|Israel", "IN": "Indian|India",
    "IQ": "Iraqi|Iraq", "IR": "Iranian|Iran|Iran (Islamic Republic of)|Iran, Islamic Republic of",
    "IS": "Icelandic|Iceland", "IT": "Italian|Italy", "JM": "Jamaican|Jamaica",
    "JO": "Jordanian|Jordan", "JP": "Japanese|Japan", "KE": "Kenyan|Kenya",
    "KG": "Kyrgyz|Kyrgyzstan|Kirgizstan", "KH": "Cambodian|Cambodia", "KM": "Comorian|Comoros",
    "KN": "Kittitian|Saint Kitts and Nevis",
    "KP": "North Korean|North Korea|Korea, Democratic People´s Republic of|"
          "Korea, Democratic People's Republic of|Korea, North",
    "KR": "Korean|South Korea|Korea, Republic of Korea|Korea, Republic of|Korea, South",
    "KW": "Kuwaiti|Kuwait", "KZ": "Kazakh|Kazakhstan",
    "LA": "Lao|Laos|Lao People´s Democratic Republic|Lao People's Democratic Republic",
    "LB": "Lebanese|Lebanon", "LC": "Saint Lucian|Saint Lucia", "LI": "Liechtensteiner|Liechtenstein",
    "LK": "Sri Lankan|Sri Lanka", "LR": "Liberian|Liberia", "LS": "Basotho|Lesotho",
    "LT": "Lithuanian|Lithuania", "LU": "Luxembourgish|Luxembourg", "LV": "Latvian|Latvia",
    "LY": "Libyan|Libya|Libyan Arab Jamahiriya", "MA": "Moroccan|Morocco",
    "MC": "Monegasque|Monaco", "MD": "Moldovan|Moldova|Moldova, Republic of",
    "ME": "Montenegrin|Montenegro", "MG": "Malagasy|Madagascar",
    "MK": "North Macedonian|North Macedonia|Macedonia|The former Yugoslav Republic of Macedonia",
    "ML": "Malian|Mali", "MM": "Burmese|Myanmar|Burma", "MN": "Mongolian|Mongolia",
    "MO": "Macanese|Macao|Macau", "MR": "Mauritanian|Mauritania", "MT": "Maltese|Malta",
    "MU": "Mauritian|Mauritius", "MV": "Maldivian|Maldives", "MW": "Malawian|Malawi",
    "MX": "Mexican|Mexico", "MY": "Malaysian|Malaysia", "MZ": "Mozambican|Mozambique|Moçambique",
    "NA": "Namibian|Namibia", "NE": "Nigerien|Niger", "NG": "Nigerian|Nigeria",
    "NI": "Nicaraguan|Nicaragua",
    "NL": "Dutch|Netherlands|Kingdom of the Netherlands|The Netherlands",
    "NO": "Norwegian|Norway", "NP": "Nepalese|Nepal", "NZ": "New Zealander|New Zealand",
    "OM": "Omani|Oman", "PA": "Panamanian|Panama", "PE": "Peruvian|Peru",
    "PG": "Papua New Guinean|Papua New Guinea", "PH": "Filipino|Philippines",
    "PK": "Pakistani|Pakistan",
    "PS": "Palestinian|Palestine|Palestinian territory, occupied|State of Palestine|"
          "Occupied Palestinian Territory|Palestinian Territory",
    "PL": "Polish|Poland", "PT": "Portuguese|Portugal", "PY": "Paraguayan|Paraguay",
    "QA": "Qatari|Qatar", "RO": "Romanian|Romania", "RS": "Serbian|Serbia",
    "RU": "Russian|Russia|Russian Federation", "RW": "Rwandan|Rwanda",
    "SA": "Saudi|Saudi Arabia", "SC": "Seychellois|Seychelles", "SD": "Sudanese|Sudan",
    "SE": "Swedish|Sweden", "SG": "Singaporean|Singapore", "SI": "Slovenian|Slovenia",
    "SK": "Slovak|Slovakia", "SL": "Sierra Leonean|Sierra Leone", "SM": "Sammarinese|San Marino",
    "SN": "Senegalese|Senegal", "SO": "Somali|Somalia", "SR": "Surinamese|Suriname",
    "SS": "South Sudanese|South Sudan", "ST": "Santomean|Sao Tome and Principe|São Tomé and Príncipe",
    "SV": "Salvadoran|El Salvador", "SY": "Syrian|Syria|Syrian Arab Republic",
    "SZ": "Swazi|Eswatini|Swaziland", "TD": "Chadian|Chad", "TG": "Togolese|Togo",
    "TH": "Thai|Thailand", "TJ": "Tajik|Tajikistan|Tadzjikistan",
    "TL": "Timorese|Timor-Leste|East Timor", "TM": "Turkmen|Turkmenistan",
    "TN": "Tunisian|Tunisia", "TO": "Tongan|Tonga", "TR": "Turkish|Turkey|Türkiye",
    "TT": "Trinidadian|Trinidad and Tobago", "TW": "Taiwanese|Taiwan",
    "TZ": "Tanzanian|Tanzania|Tanzania, United Republic of", "UA": "Ukrainian|Ukraine",
    "UG": "Ugandan|Uganda",
    "US": "American|United States|United States of America|USA",
    "UY": "Uruguayan|Uruguay", "UZ": "Uzbek|Uzbekistan",
    "VC": "Vincentian|Saint Vincent and the Grenadines", "VE": "Venezuelan|Venezuela",
    "VN": "Vietnamese|Viet Nam|Vietnam|North Vietnam|South Vietnam", "WS": "Samoan|Samoa",
    "XK": "Kosovar|Kosovo", "YE": "Yemeni|Yemen|South Yemen", "ZA": "South African|South Africa",
    "ZM": "Zambian|Zambia", "ZW": "Zimbabwean|Zimbabwe",
    # States that no longer exist, which a register keeps for the people born
    # in them or who held their citizenship.
    "YU": "Yugoslav|Yugoslavia|Former Yugoslavia",
    "SU": "Soviet|Soviet Union|Former Soviet Union|USSR",
    "CSHH": "Czechoslovak|Czechoslovakia|Former Czechoslovakia",
    "CS": "Serbian and Montenegrin|Serbia and Montenegro|Former Serbia and Montenegro",
    "DD": "German|German Democratic Republic|East Germany",
    "SKM": "Indian|Sikkim",
}

# The rows an office prints for nobody in particular: a country it does not
# know, a person with no state, a remainder it does not itemise.
RESIDUAL_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"stateless|without citizenship", STATELESS),
    (r"unknown|not stated|not known|okänd|ukjent", UNKNOWN),
    (r"not specified|unspecified|other|rest of|islands$|l\d\d$|ls\d\d$", OTHER),
)


def _adjectives() -> tuple[dict[str, str], dict[str, str]]:
    by_code, by_name = {}, {}
    for code, entry in COUNTRIES.items():
        adjective, *names = entry.split("|")
        by_code[code] = adjective
        for name in names:
            by_name[fold(name)] = adjective
    return by_code, by_name


BY_CODE, BY_NAME = _adjectives()


def label_of(name: str = "", code: str = "") -> str | None:
    """The map's label for an office's country row: its people's adjective,
    a residual, or None for a name nobody here knows."""
    if code and code in BY_CODE:
        return BY_CODE[code]
    text = str(name).strip()
    if fold(text) in BY_NAME:
        return BY_NAME[fold(text)]
    # "Republic of North Macedonia", "The Gambia", "Congo, Democratic Republic of"
    bare = re.sub(r"^(?:the |republic of |kingdom of |state of |federal republic of )", "",
                  text, flags=re.I)
    bare = re.sub(r",\s*(?:the\s+)?(?:republic|kingdom|state)(?:\s+of)?(?:\s+the)?\s*$", "",
                  bare, flags=re.I)
    if fold(bare) in BY_NAME:
        return BY_NAME[fold(bare)]
    for pattern, label in RESIDUAL_PATTERNS:
        if re.search(pattern, text, re.I):
            return label
    return None


def named_labels(national: dict[str, float], population: float, home: str) -> set[str]:
    """The labels named on the map: the home row, and every country holding at
    least NAMED_SHARE of the country's people."""
    floor = NAMED_SHARE * population
    return {home} | {label for label, n in national.items()
                     if n >= floor and label not in (OTHER, UNKNOWN)}


def compose(counts: dict[str, float], named: set[str]) -> dict[str, float]:
    """One unit's counts by label, the unnamed countries counted in "Other"."""
    out: dict[str, float] = defaultdict(float)
    for label, n in counts.items():
        if not n:
            continue
        out[label if label in named or label == UNKNOWN else OTHER] += n
    return dict(out)


def code_labels(national: dict[str, float], names: dict[str, str], label, floor: float,
                what: str) -> dict[str, str]:
    """{office code: the map's label} for every country row the office prints.

    ``label(code, name)`` is the office's own reader. A row it cannot label is
    counted in "Other" when it is small nationally, and stops the run when it
    is not: a large community folded away unseen is a misread, not a tail."""
    out: dict[str, str] = {}
    for code, name in names.items():
        got = label(code, name)
        if got is None:
            if national.get(code, 0) >= floor:
                raise SystemExit(f"{what}: no label for {code} {name!r}, "
                                 f"{national.get(code, 0):,.0f} people nationally")
            got = OTHER
        out[code] = got
    return out


def by_label(counts: dict[str, float], labels: dict[str, str]) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for code, n in counts.items():
        out[labels.get(code, OTHER)] += n
    return dict(out)


def ethnicity_block(counts: dict[str, float], total: float, *, year: int, basis: str,
                    note: str, source: dict[str, Any]) -> dict[str, Any]:
    if abs(sum(counts.values()) - total) > max(2.0, 0.0005 * total):
        raise SystemExit(f"{source['name']}: a unit's labels make {sum(counts.values()):,.0f} "
                         f"of {total:,.0f}")
    return {
        "ethnicity": shares({k: v for k, v in counts.items() if v > 0}, total=total),
        "ethnicity_year": year,
        "ethnicity_basis": basis,
        "ethnicity_note": note,
        "sources": [source],
    }


def folded_note(floor: float) -> str:
    return (f" 'Other' is every country holding fewer than {floor:,.0f} of the country's "
            f"people ({NAMED_SHARE:.1%}), and 'Not stated' a country the register does not "
            "know.")


# ---------------------------------------------------------------------------
# Sweden
# ---------------------------------------------------------------------------

SCB_TABLE = ("https://api.scb.se/OV0104/v1/doris/{lang}/ssd/BE/BE0101/BE0101E/"
             "FolkmRegFlandKCKM")
SCB_PAGE = ("https://www.statistikdatabasen.scb.se/pxweb/en/ssd/START__BE__BE0101__BE0101E/"
            "FolkmRegFlandKCKM/")
# SCB perturbs every cell (the cell-key method): a kommun's 188 countries
# make its own perturbed total to within a few dozen people.
SCB_CELLS_SLACK = 150
SCB_TOTALS_SLACK = 60


def scb_rows(body: dict[str, Any]) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    """{region: {country code: n}} and {region: published total} from json-stat2."""
    rows: dict[str, dict[str, float]] = defaultdict(dict)
    total: dict[str, float] = {}
    for key, value in unstack(body):
        region, country = key["Region"][0], key["Fodelseregion"][0]
        if country == "TOTfod":
            total[region] = value
        else:
            rows[region][country] = rows[region].get(country, 0.0) + value
    return rows, total


def scb_label(code: str, name: str) -> str | None:
    if code == "ÖOF" or "unknown" in name.lower():
        return UNKNOWN
    if code == "OVFOD":
        return OTHER
    return label_of(name, code)


def sweden() -> list[dict[str, Any]]:
    from .sweden import bind_kommuner, bind_lan
    url = SCB_TABLE.format(lang="en")
    meta = {v["code"]: v for v in request_json(url)["variables"]}
    year = meta["Tid"]["values"][-1]
    countries = dict(zip(meta["Fodelseregion"]["values"], meta["Fodelseregion"]["valueTexts"]))
    sex_total = next(c for c in meta["Kon"]["values"] if not c.isdigit())
    body = request_json(url, {"query": [
        {"code": "Region", "selection": {"filter": "item", "values": meta["Region"]["values"]}},
        {"code": "Fodelseregion", "selection": {"filter": "item",
                                                "values": meta["Fodelseregion"]["values"]}},
        {"code": "Kon", "selection": {"filter": "item", "values": [sex_total]}},
        {"code": "ContentsCode", "selection": {"filter": "item",
                                               "values": meta["ContentsCode"]["values"][:1]}},
        {"code": "Tid", "selection": {"filter": "item", "values": [year]}},
    ], "response": {"format": "json-stat2"}})
    rows, total = scb_rows(body)
    local = {v["code"]: v for v in request_json(SCB_TABLE.format(lang="sv"))["variables"]}
    sv = dict(zip(local["Region"]["values"], local["Region"]["valueTexts"]))
    counties = sorted(c for c in total if len(c) == 2 and c != "00")
    kommuner = sorted(c for c in total if len(c) == 4)
    log(f"  FolkmRegFlandKCKM {year}: {len(kommuner)} kommuner, {len(counties)} län, "
        f"{len(countries) - 1} countries of birth; Sweden {total['00']:,.0f}")
    worst = 0.0
    for region, counts in rows.items():
        off = abs(sum(counts.values()) - total[region])
        worst = max(worst, off)
        if off > max(SCB_CELLS_SLACK, 0.002 * total[region]):
            raise SystemExit(f"FolkmRegFlandKCKM {region}: countries make "
                             f"{sum(counts.values()):,.0f} of {total[region]:,.0f}")
    log(f"  countries against each region's own total: worst {worst:,.0f} people (cell-key noise)")
    check_parts({c: total[c] for c in counties}, total["00"], "län -> Sweden", 0.0002,
                SCB_TOTALS_SLACK)
    for county in counties:
        check_parts({c: total[c] for c in kommuner if c[:2] == county}, total[county],
                    f"kommuner -> {sv[county]}", 0.0002, SCB_TOTALS_SLACK)
    floor = NAMED_SHARE * total["00"]
    labels = code_labels(rows["00"], {c: n for c, n in countries.items() if c != "TOTfod"},
                         scb_label, floor, "FolkmRegFlandKCKM")
    national = by_label(rows["00"], labels)
    named = named_labels(national, total["00"], "Swedish")
    log(f"  named ({len(named)}): {', '.join(sorted(named, key=lambda k: -national[k]))}")
    source = {"field": "ethnicity", "name": "Statistics Sweden (SCB), FolkmRegFlandKCKM",
              "url": SCB_PAGE, "year": int(year)}
    note = (f"Country of birth as recorded in the population register on 31 December {year} "
            "(Statistics Sweden, FolkmRegFlandKCKM): COUNTRY OF BIRTH, not ethnicity, which "
            "no Swedish register records. 'Swedish' is everyone born in Sweden, the children of "
            "immigrants among them; a person born abroad is counted under the country of "
            "birth, Swedes born abroad included. SCB publishes no citizenship by country below "
            "the country, so this is the finest count of origin there is. SCB perturbs every "
            "cell slightly (the cell-key method), so the counts can differ by a few people "
            "from the register itself." + folded_note(floor))

    def block(region: str) -> dict[str, Any]:
        made = compose(by_label(rows[region], labels), named)
        return ethnicity_block(made, sum(made.values()), year=int(year),
                               basis="country of birth", note=note, source=source)

    bound = bind_kommuner(sv, kommuner)
    lan = bind_lan(sv, counties)
    records = [record(f"SWE-ORIGIN-{c}", sv[c], level="admin2", parent="SWE", country="SWE",
                      parent_name=sv[c[:2]], codes={"scb": c}, match_by="shape_id",
                      shape_id=bound[c], **block(c)) for c in kommuner]
    records += [record(f"SWE-ORIGIN-{c}", lan[c]["name"], level="admin1", parent="SWE",
                       country="SWE", codes={"scb": c}, match_by="shape_id",
                       shape_id=lan[c]["id"], **block(c)) for c in counties]
    return records


# ---------------------------------------------------------------------------
# Denmark
# ---------------------------------------------------------------------------

DST_PAGE = "https://www.statbank.dk/FOLK1C"
DANISH_ORIGIN, IMMIGRANTS, DESCENDANTS = "5", "4", "3"


def dst_counts(rows: Iterable[dict[str, str]]
               ) -> tuple[dict[str, dict[str, float]], dict[str, float], list[str]]:
    """FOLK1C rows -> ({area: {country of origin: n}}, {area: total}, the rows
    of foreign ancestry whose country of origin is Denmark).

    Persons of Danish origin are one row, under the key "DK", whatever country
    FOLK1C writes beside them; immigrants and descendants are keyed by their
    country of origin's code."""
    from .denmark import number
    counts: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    totals: dict[str, float] = {}
    odd: list[str] = []
    for row in rows:
        area, kind, origin = row["OMRÅDE"], row["HERKOMST"], row["IELAND"]
        n = number(row["INDHOLD"])
        if kind == "TOT":
            if origin == "0000":
                totals[area] = n
            continue
        if origin == "0000":
            continue
        if kind == DANISH_ORIGIN:
            counts[area]["DK"] += n
            continue
        if origin == "5100" and n:
            odd.append(f"{area} {kind}: {n:,.0f}")
        counts[area][origin] += n
    return {a: dict(c) for a, c in counts.items()}, totals, odd


def dst_label(code: str, name: str) -> str | None:
    if code == "DK":
        return "Danish"
    if code == "5100":        # Denmark as an immigrant's or descendant's country of origin
        return OTHER
    if code == "5103":
        return STATELESS
    if code == "5999":
        return UNKNOWN
    return label_of(name)


def denmark() -> list[dict[str, Any]]:
    from . import denmark as dk
    meta = dk.info("FOLK1C")
    variable = {v["id"]: v for v in meta["variables"]}
    quarter = variable["Tid"]["values"][-1]["id"]
    names, region_of = dk.areas(meta, "OMRÅDE")
    origin_names = {v["id"]: v["text"] for v in variable["IELAND"]["values"] if v["id"] != "0000"}
    rows = dk.data("FOLK1C", {"OMRÅDE": ["*"], "KØN": ["TOT"], "ALDER": ["IALT"],
                              "HERKOMST": ["*"], "IELAND": ["*"], "Tid": [quarter]})
    counts, totals, odd = dst_counts(rows)
    year = int(quarter[:4])
    date = {"1": "1 January", "2": "1 April", "3": "1 July", "4": "1 October"}[quarter[-1]]
    log(f"  FOLK1C {quarter}: {len(rows):,} rows, {len(counts)} areas")
    if odd:
        log(f"  immigrants or descendants with Denmark as country of origin, counted in "
            f"'Other': {odd[:8]}")
    for area, got in counts.items():
        if abs(sum(got.values()) - totals.get(area, -1)) > 0.5:
            raise SystemExit(f"FOLK1C {area}: ancestry and origin make {sum(got.values()):,.0f} "
                             f"of {totals.get(area)}")
    regions = sorted(c for c in names if names[c].startswith("Region "))
    kommuner = sorted(c for c in names if c != "000" and c not in regions)
    check_parts({c: totals[c] for c in regions}, totals["000"], "FOLK1C regions -> Denmark", 0)
    for region in regions:
        check_parts({c: totals[c] for c in kommuner if region_of.get(c) == region},
                    totals[region], f"FOLK1C kommuner -> {names[region]}", 0)
    floor = NAMED_SHARE * totals["000"]
    labels = code_labels(counts["000"], {"DK": "Denmark", **origin_names}, dst_label, floor,
                         "FOLK1C")
    national = by_label(counts["000"], labels)
    named = named_labels(national, totals["000"], "Danish")
    log(f"  named ({len(named)}): {', '.join(sorted(named, key=lambda k: -national[k]))}")
    source = {"field": "ethnicity", "name": "Statistics Denmark, FOLK1C", "url": DST_PAGE,
              "year": year}
    note = (f"Ancestry and country of origin on {date} {year}, as the Civil Registration "
            "System records them (Statistics Denmark, FOLK1C): ANCESTRY, not ethnicity, which no "
            "Danish register records. 'Danish' is every person of Danish origin -- one parent at "
            "least a Danish citizen born in Denmark; immigrants and their descendants are "
            "counted under their country of origin, which for an immigrant is the country of "
            "birth and for a descendant the parents' country." + folded_note(floor))

    def block(area: str) -> dict[str, Any]:
        made = compose(by_label(counts[area], labels), named)
        return ethnicity_block(made, totals[area], year=year,
                               basis="ancestry and country of origin", note=note, source=source)

    shapes = load_units("DNK", "admin2")
    region_names = {c: names[c].removeprefix("Region ").strip() for c in regions}
    bound, missing, left, _p = bind_rows(
        "DNK", "admin2", {c: (names[c], region_names[region_of[c]]) for c in kommuner
                          if c in region_of}, aliases=dk.ALIASES)
    if left:
        raise SystemExit(f"denmark: polygons with no kommune: {[s['name'] for s in left]}")
    parent_map = {u["id"]: u["name"] for u in load_units("DNK", "admin1")}
    records = []
    for code in kommuner:
        sid = bound.get(code)
        if sid is None:
            continue
        records.append(record(
            f"DNK-ORIGIN-{code}", names[code], level="admin2", parent="DNK", country="DNK",
            parent_name=parent_map.get(next(s["parent"] for s in shapes if s["id"] == sid)),
            codes={"dst": code}, match_by="shape_id", shape_id=sid, **block(code)))
    admin1 = {fold(u["name"]): u for u in load_units("DNK", "admin1")}
    for region in regions:
        shape = admin1.get(fold(region_names[region]))
        if shape is None:
            raise SystemExit(f"denmark: region {names[region]!r} has no polygon")
        records.append(record(
            f"DNK-ORIGIN-{region}", shape["name"], level="admin1", parent="DNK", country="DNK",
            codes={"dst": region}, match_by="shape_id", shape_id=shape["id"], **block(region)))
    return records


# ---------------------------------------------------------------------------
# Norway
# ---------------------------------------------------------------------------

SSB_PAGE = "https://www.ssb.no/en/statbank/table/09817"
# 09817's own sums: every country, and the two groups of countries it
# publishes beside them.
SSB_TOTAL, SSB_GROUPS = "999", ("VES", "IVE")
# SSB protects 09817's cells, so a kommune's countries can miss its printed
# total by a person or two (Hof 0709 in 2017: 6,101 against 6,100). The share
# is then of the countries' own sum. A misread misses by hundreds.
SSB_SLACK = 5


def ssb_counts(body: dict[str, Any]) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    """09817 json-stat2 -> ({region: {country code: n}}, {region: total})."""
    counts: dict[str, dict[str, float]] = defaultdict(dict)
    totals: dict[str, float] = {}
    for key, value in unstack(body):
        region, country = key["Region"][0], key["Landbakgrunn"][0]
        if country == SSB_TOTAL:
            totals[region] = value
        elif country not in SSB_GROUPS:
            counts[region][country] = counts[region].get(country, 0.0) + value
    for region, got in counts.items():
        if abs(sum(got.values()) - totals.get(region, 0.0)) > max(SSB_SLACK,
                                                                   0.001 * totals.get(region, 0)):
            raise SystemExit(f"09817 {region}: countries make {sum(got.values()):,.0f} of "
                             f"{totals.get(region)}")
        # The countries are what is itemised; their sum is the count of
        # immigrants and Norwegian-born to immigrant parents used below.
        totals[region] = sum(got.values())
    return counts, totals


def ssb_label(code: str, name: str) -> str | None:
    if code == "980":
        return STATELESS
    if code == "990":
        return UNKNOWN
    return label_of(name)


def norway() -> list[dict[str, Any]]:
    from . import norway as no
    meta = {v["code"]: v for v in request_json(f"{no.SSB}/09817")["variables"]}
    country_names = dict(zip(meta["Landbakgrunn"]["values"], meta["Landbakgrunn"]["valueTexts"]))
    category = next(c for c in meta["InnvandrKat"]["values"] if c == "B-C")
    latest = min(int(meta["Tid"]["values"][-1]),
                 int({v["code"]: v for v in request_json(f"{no.SSB}/07459")["variables"]}
                     ["Tid"]["values"][-1]))

    def background(codes: list[str], year: int) -> tuple[dict, dict]:
        counts: dict[str, dict[str, float]] = {}
        totals: dict[str, float] = {}
        for chunk in (codes[i:i + 120] for i in range(0, len(codes), 120)):
            c, t = ssb_counts(no.query("09817", {
                "Region": chunk, "InnvandrKat": [category],
                "Landbakgrunn": meta["Landbakgrunn"]["values"],
                "ContentsCode": ["Personer1"], "Tid": [str(year)]}))
            counts.update(c)
            totals.update(t)
        return counts, totals

    def population(codes: list[str], year: int) -> dict[str, float]:
        return {key["Region"][0]: value for key, value in unstack(no.query(
            "07459", {"Region": codes, "ContentsCode": ["Personer1"], "Tid": [str(year)]}))}

    klass = request_json(no.KLASS.format(date=f"{no.VINTAGE}-01-01"))["codes"]
    names = {c["code"]: no.office_names(c["name"]) for c in klass}
    people_2017 = population(sorted(names), no.VINTAGE)
    kommuner = [c for c in sorted(names) if people_2017.get(c, 0) > 0]
    lines = no.lineage(kommuner, f"{no.VINTAGE}-01-02", f"{latest}-01-02")
    last = {c: (latest if ended is None else no.last_whole_year(ended))
            for c, (_h, ended) in lines.items()}
    code_then = {c: no.code_on(lines[c][0], f"{last[c]}-01-01") for c in kommuner}
    by_year: dict[int, tuple[dict, dict, dict]] = {}
    for year in sorted(set(last.values())):
        codes = sorted({code_then[c] for c in kommuner if last[c] == year})
        counts, totals = background(codes, year)
        by_year[year] = (counts, totals, population(codes, year))
    log(f"  09817: {len(kommuner)} kommuner of {no.VINTAGE}; by year read: "
        + ", ".join(f"{y}: {sum(1 for c in kommuner if last[c] == y)}" for y in sorted(by_year)))

    # The country's own row for the naming threshold, in the latest year.
    nat_counts, nat_totals = background(["0"], latest)
    nat_people = population(["0"], latest)["0"]
    floor = NAMED_SHARE * nat_people
    labels = code_labels(nat_counts["0"], {c: n for c, n in country_names.items()
                                          if c not in (SSB_TOTAL, *SSB_GROUPS)},
                         ssb_label, floor, "09817")
    national = by_label(nat_counts["0"], labels)
    national["Norwegian"] = nat_people - nat_totals["0"]
    named = named_labels(national, nat_people, "Norwegian")
    log(f"  named ({len(named)}): {', '.join(sorted(named, key=lambda k: -national[k]))}")
    source = {"field": "ethnicity", "name": "Statistics Norway (SSB), tables 09817 and 07459",
              "url": SSB_PAGE}

    def block(counts: dict[str, float], immigrants: float, people: float, year: int,
              where: str, extra: str) -> dict[str, Any]:
        if immigrants > people:
            raise SystemExit(f"09817 {where} {year}: {immigrants:,.0f} immigrants and "
                             f"Norwegian-born to immigrant parents of {people:,.0f} people")
        got = by_label(counts, labels)
        got["Norwegian"] = people - immigrants
        made = compose(got, named)
        note = (f"Immigrant background on 1 January {year} (Statistics Norway, table 09817, "
                "against the population of the same day in 07459): IMMIGRANT BACKGROUND, not "
                "ethnicity, which no Norwegian register records. Immigrants and Norwegian-born "
                "to two immigrant parents are counted under their country background -- their "
                "own country of birth, or their parents' -- and 'Norwegian' is everyone else, "
                "the rest of the population in SSB's own term: people born in Norway to one "
                "Norwegian-born parent or more, and people born abroad to Norwegian-born "
                "parents. Sami and Kven Norwegians are among them; no register counts them."
                + extra + folded_note(floor))
        return ethnicity_block(made, people, year=year, basis="immigrant background",
                               note=note, source={**source, "year": year})

    shapes = load_units("NOR", "admin2")
    drawn = {fold(no.map_name(s)) for s in shapes}
    rows = {}
    for c in kommuner:
        forms = names[c] + [no.ALIASES[f] for f in names[c] if f in no.ALIASES]
        rows[c] = (next((f for f in forms if fold(f) in drawn), forms[0]), c[:2])
    bound, _m, _l, _p = bind_rows("NOR", "admin2", rows, shape_name=no.map_name,
                                  aliases=no.ALIASES)
    records = []
    for c in kommuner:
        sid = bound.get(c)
        if sid is None:
            continue
        year = last[c]
        counts, totals, people = by_year[year]
        code = code_then[c]
        if code not in people or people[code] <= 0:
            raise SystemExit(f"07459 {year}: no population for {rows[c][0]} ({code})")
        _hist, ended = lines[c]
        extra = (f" The kommune (number {code} today) has not been merged or split since "
                 f"{no.VINTAGE}, the year the map draws." if ended is None else
                 f" The kommune as the map draws it (its {no.VINTAGE} territory), at its last "
                 f"count before it was merged or split on {ended}"
                 + (f", when its number was {code}." if code != c else "."))
        records.append(record(
            f"NOR-ORIGIN-{no.VINTAGE}-{c}", rows[c][0], level="admin2", parent="NOR",
            country="NOR", codes={"ssb": c, "vintage": no.VINTAGE}, match_by="shape_id",
            shape_id=sid, **block(counts.get(code, {}), totals.get(code, 0.0), people[code],
                                  year, rows[c][0], extra)))

    # The fylker, by the years norway.py reads them.
    region_meta = {v["code"]: v for v in request_json(f"{no.SSB}/07459")["variables"]}
    region_names = dict(zip(region_meta["Region"]["values"], region_meta["Region"]["valueTexts"]))
    moves = request_json(no.CHANGES.format(start=f"{no.FYLKE_YEAR}-01-02", end=f"{latest}-01-02"))
    crossed = {code[:2] for change in moves.get("codeChanges", [])
               if change["oldCode"][:2] != change["newCode"][:2]
               for code in (change["oldCode"], change["newCode"])}
    admin1 = {fold(u["name"]): u for u in load_units("NOR", "admin1")}
    for f in no.FYLKER:
        forms = no.office_names(region_names.get(f, f))
        if f in no.SPLIT_FYLKER:
            year = no.FYLKE_YEAR
            extra = f" {forms[0]} existed from 2020 to 2023; this is its last count."
        elif f not in crossed:
            year = latest
            extra = (f" The fylke has kept its kommuner since {no.FYLKE_YEAR}, the last year of "
                     "the division the map draws, so this is its latest count.")
        else:
            log(f"  fylke {f}: a kommune has crossed its border since {no.FYLKE_YEAR}; left out")
            continue
        counts, totals = background([f], year)
        people = population([f], year)
        shape = next((admin1[fold(n)] for n in forms if fold(n) in admin1), None)
        if shape is None:
            raise SystemExit(f"norway: fylke {f} {forms} has no polygon")
        records.append(record(
            f"NOR-ORIGIN-F{f}", shape["name"], level="admin1", parent="NOR", country="NOR",
            codes={"ssb": f}, match_by="shape_id", shape_id=shape["id"],
            **block(counts.get(f, {}), totals.get(f, 0.0), people[f], year, f, extra)))
    return records


# ---------------------------------------------------------------------------
# Finland
# ---------------------------------------------------------------------------

STATFIN_TABLE = "https://pxdata.stat.fi/PxWeb/api/v1/en/StatFin/vaerak/11rv.px"
STATFIN_PAGE = ("https://pxdata.stat.fi/PxWeb/pxweb/en/StatFin/StatFin__vaerak/"
                "statfin_vaerak_pxt_11rv.px")
REGION_KEY = ("https://data.stat.fi/api/classifications/v2/correspondenceTables/"
              "kunta_1_{y}0101%23maakunta_1_{y}0101/maps?content=data&meta=max&lang=fi")
# The statistics of 11rv's background-country variable that sum others.
STATFIN_SUMS = ("SSS", "ULK", "EUR", "AFR", "AME", "AAS", "OSE")
# The maakunta codes -> the boundary file's region names.
FIN_REGIONS = {"01": "Uusimaa", "02": "Finland Proper", "04": "Satakunta",
               "05": "Tavastia Proper", "06": "Pirkanmaa", "07": "Päijät-Häme",
               "08": "Kymenlaakso", "09": "South Karelia", "10": "Southern Savonia",
               "11": "Northern Savonia", "12": "North Karelia", "13": "Central Finland",
               "14": "South Ostrobothnia", "15": "Ostrobothnia", "16": "Keski-Pohjanmaa",
               "17": "Northern Ostrobothnia", "18": "Kainuu", "19": "Lapland",
               "21": "Åland Islands"}
# Municipalities of the map's year that have since merged into another, and
# the one they merged into: the merged one's people are in its successor's
# figure today, which must then lie in the same sub-region of the map's year.
# Honkajoki into Kankaanpää, 1 January 2021; Pertunmaa into Mäntyharju, which
# 11ra's 2024 figure for Mäntyharju in today's division shows to the person
# (7,057 = 11rf's 5,532 + 1,525 in 2024's own; church_probe round c8).
FIN_MERGED_SINCE = {"099": "214", "588": "507"}
# The most of a municipality's total its withheld small cells may make.
WITHHELD_SHARE = 0.05
WITHHELD_FLOOR = 200


def statfin_counts(body: dict[str, Any], area: str, country: str
                   ) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    """11rv json-stat2 -> ({municipality: {country code: n}}, {municipality: total})."""
    counts: dict[str, dict[str, float]] = defaultdict(dict)
    totals: dict[str, float] = {}
    for key, value in unstack(body):
        muni, code = key[area][0], key[country][0]
        if code == "SSS":
            totals[muni] = value
        elif code not in STATFIN_SUMS:
            counts[muni][code] = counts[muni].get(code, 0.0) + value
    return counts, totals


def withheld_cells(counts: dict[str, dict[str, float]], totals: dict[str, float],
                   current: list[str]) -> dict[str, float]:
    """{municipality: people in its withheld cells}.

    A municipality's small background-country counts are withheld for
    confidentiality, so its itemised countries fall a little short of its
    published total. The shortfall is people of some withheld (small)
    background: the caller counts it in "Other" and says so in the unit's note.
    A shortfall larger than max(WITHHELD_SHARE of the total, WITHHELD_FLOOR) is
    not suppression and stops the run, as do an excess and a missing total."""
    out: dict[str, float] = {}
    for muni in current:
        got = counts.setdefault(muni, {})
        if muni not in totals:
            raise SystemExit(f"11rv {muni}: no total")
        short = totals[muni] - sum(got.values())
        if short < -0.5 or short > max(WITHHELD_SHARE * totals[muni], WITHHELD_FLOOR):
            raise SystemExit(f"11rv {muni}: countries make {sum(got.values()):,.0f} of "
                             f"{totals[muni]:,.0f}")
        if short > 0.5:
            out[muni] = short
    return out


def statfin_label(code: str, name: str) -> str | None:
    if code == "246":
        return "Finnish"
    if code in ("X", "MUU") or "unknown" in name.lower():
        return UNKNOWN
    if code == "991":
        return STATELESS
    return label_of(name)


def finland_key(year: int) -> tuple[dict[str, str], dict[str, str]]:
    """{municipality code: maakunta code} and {maakunta code: name} for one year,
    from the maps list and the region classification's items, as
    finland.key_for reads the sub-regions (REGION_KEY's parameters answer 500)."""
    from .finland import PAUSE
    from .finland_religion import CLASS_API, item_names, key_pairs
    muni = key_pairs(request_json(
        f"{CLASS_API}/correspondenceTables/kunta_1_{year}0101%23maakunta_1_{year}0101/maps",
        pause=PAUSE))
    names = item_names(request_json(
        f"{CLASS_API}/classifications/maakunta_1_{year}0101/classificationItems"
        "?content=data&meta=max&lang=fi", pause=PAUSE))
    return muni, {c: n for c, n in names.items() if c in set(muni.values())}


def drawn_subregion_key() -> tuple[int, dict[str, str], dict[str, str], dict[str, str]]:
    """The latest year whose sub-regions are exactly the seventy the map draws,
    as finland.py chooses it: (year, {municipality: sub-region},
    {sub-region: name}, {drawn name: sub-region})."""
    from . import finland as fi
    for year in range(2027, 2009, -1):
        try:
            muni, names = fi.key_for(year)
        except SystemExit:
            continue
        found, missing = fi.match(names)
        if not missing and len(names) == len(fi.DRAWN):
            return year, muni, names, found
    raise SystemExit("finland: no year's sub-regions are the seventy the map draws")


def place_current(current: list[str], muni: dict[str, str], what: str) -> dict[str, str]:
    """Today's municipalities -> the map's year's units, by code. A code the
    key does not know stops the run; one the key knows that has since merged
    away must be in FIN_MERGED_SINCE, and lie in the same unit as its
    successor, or the run stops too."""
    unknown = [c for c in current if c not in muni]
    if unknown:
        raise SystemExit(f"{what}: today's municipalities {unknown} are not in the map's key")
    gone = sorted(set(muni) - set(current))
    for code in gone:
        into = FIN_MERGED_SINCE.get(code)
        if into is None or muni.get(into) != muni[code]:
            raise SystemExit(f"{what}: municipality {code} of the map's year is gone today and "
                             "its successor is not known to lie in the same unit")
    return {c: muni[c] for c in current}


def finland() -> list[dict[str, Any]]:
    from . import finland as fi
    meta = {v["code"]: v for v in request_json(STATFIN_TABLE, pause=fi.PAUSE)["variables"]}
    area = next(c for c in meta if c.startswith(("alue", "kunta")))
    country = next(c for c in meta if c.startswith("valtio"))
    year = meta["timeperiod_y"]["values"][-1]
    others = {c: ("SSS" if "SSS" in meta[c]["values"] else meta[c]["values"][0])
              for c in meta if c not in (area, country, "timeperiod_y")}
    if any(v != "SSS" for c, v in others.items() if c != "contentscode"):
        raise SystemExit(f"11rv: a variable without a total to pin: {others}")
    current = [c for c in meta[area]["values"] if c.startswith("KU")]
    names = dict(zip(meta[country]["values"], meta[country]["valueTexts"]))
    counts: dict[str, dict[str, float]] = {}
    totals: dict[str, float] = {}
    for chunk in (current[i:i + 60] for i in range(0, len(current), 60)):
        body = request_json(STATFIN_TABLE, {"query": [
            {"code": area, "selection": {"filter": "item", "values": chunk}},
            {"code": country, "selection": {"filter": "item", "values": meta[country]["values"]}},
            {"code": "timeperiod_y", "selection": {"filter": "item", "values": [year]}},
            *({"code": c, "selection": {"filter": "item", "values": [v]}}
              for c, v in others.items()),
        ], "response": {"format": "json-stat2"}}, pause=fi.PAUSE)
        c, t = statfin_counts(body, area, country)
        counts.update(c)
        totals.update(t)
    withheld = withheld_cells(counts, totals, current)
    log(f"  11rv {year}: withheld small counts counted in 'Other' in {len(withheld)} "
        f"municipalities, {sum(withheld.values()):,.0f} people in all")
    national_people = sum(totals[c] for c in current)
    floor = NAMED_SHARE * national_people
    national_codes: dict[str, float] = defaultdict(float)
    for got in counts.values():
        for code, n in got.items():
            national_codes[code] += n
    labels = code_labels(national_codes, {c: n for c, n in names.items()
                                          if c not in STATFIN_SUMS}, statfin_label, floor, "11rv")
    national = by_label(national_codes, labels)
    named = named_labels(national, national_people, "Finnish")
    log(f"  11rv {year}: {len(current)} municipalities, {national_people:,.0f} people; named "
        f"({len(named)}): {', '.join(sorted(named, key=lambda k: -national[k]))}")

    key_year, sk_of, sk_names, found = drawn_subregion_key()
    mk_of, mk_names = finland_key(key_year)
    place_sk = place_current([c[2:] for c in current], sk_of, "11rv sub-regions")
    place_mk = place_current([c[2:] for c in current], mk_of, "11rv regions")
    for sk in set(sk_of.values()):
        homes = {mk_of[k] for k, s in sk_of.items() if s == sk}
        if len(homes) != 1:
            raise SystemExit(f"finland: sub-region {sk_names[sk]} lies in regions {homes}")
    sums: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    people: dict[str, float] = defaultdict(float)
    hidden: dict[str, float] = defaultdict(float)
    for code in current:
        for unit in (f"SK{place_sk[code[2:]]}", f"MK{place_mk[code[2:]]}"):
            people[unit] += totals[code]
            for c, n in counts.get(code, {}).items():
                sums[unit][labels[c]] += n
            if withheld.get(code):
                sums[unit][OTHER] += withheld[code]
                hidden[unit] += withheld[code]
    check_parts({u: n for u, n in people.items() if u.startswith("MK")}, national_people,
                "11rv: regions -> Finland", 0)
    source = {"field": "ethnicity", "name": "Statistics Finland, table 11rv", "url": STATFIN_PAGE,
              "year": int(year)}
    note = (f"Origin and background country on 31 December {year} (Statistics Finland, table "
            "11rv), summed from today's municipalities into the units of the regional division "
            f"of {key_year}, which the map draws: BACKGROUND COUNTRY, not ethnicity, which no "
            "Finnish register records. 'Finnish' is everyone of Finnish background -- one parent "
            "at least born in Finland -- Swedish-speaking Finns and Sami among them; people of "
            "foreign background are counted under their background country, which is their "
            "parents' country of birth, or their own where the parents' is not known."
            + folded_note(floor))

    def block(unit: str) -> dict[str, Any]:
        made = compose(dict(sums[unit]), named)
        extra = (f" {hidden[unit]:,.0f} people whose background country Statistics Finland "
                 "withholds at municipal level as too small a count are in 'Other'."
                 if hidden.get(unit) else "")
        return ethnicity_block(made, people[unit], year=int(year),
                               basis="origin and background country", note=note + extra,
                               source=source)

    shapes_rows = {found[d]: (d, "") for d in fi.DRAWN}
    bound, missing, left, _p = bind_rows("FIN", "admin2", shapes_rows)
    if missing or left:
        raise SystemExit(f"finland: sub-regions unbound {missing}, polygons unbound "
                         f"{[s['name'] for s in left]}")
    records = [record(f"FIN-ORIGIN-SK{key_year}-{sk}", drawn, level="admin2", parent="FIN",
                      country="FIN", codes={"seutukunta": sk, "vintage": key_year},
                      match_by="shape_id", shape_id=bound[sk], **block(f"SK{sk}"))
               for sk, (drawn, _) in sorted(shapes_rows.items())]
    admin1 = {u["name"]: u for u in load_units("FIN", "admin1")}
    if set(FIN_REGIONS.values()) != set(admin1) or set(FIN_REGIONS) != set(mk_names):
        raise SystemExit(f"finland: regions {sorted(mk_names)} against the drawn "
                         f"{sorted(admin1)}")
    # The drawn sub-regions must lie in the drawn region of their maakunta.
    shape_parent = {s["id"]: s["parent"] for s in load_units("FIN", "admin2")}
    wrong = sorted(f"{sk_names[sk]} in {admin1[FIN_REGIONS[mk_of[k]]]['name']}"
                   for k, sk in sk_of.items() if sk in bound
                   and shape_parent[bound[sk]] != admin1[FIN_REGIONS[mk_of[k]]]["id"])
    if wrong:
        log(f"  sub-regions the boundary file files under another region than their "
            f"maakunta's (the regions are summed from municipalities, not from these): "
            f"{sorted(set(wrong))}")
    records += [record(f"FIN-ORIGIN-MK{key_year}-{mk}", FIN_REGIONS[mk], level="admin1",
                       parent="FIN", country="FIN", codes={"maakunta": mk, "vintage": key_year},
                       match_by="shape_id", shape_id=admin1[FIN_REGIONS[mk]]["id"],
                       **block(f"MK{mk}")) for mk in sorted(FIN_REGIONS)]
    return records


# ---------------------------------------------------------------------------
# Iceland
# ---------------------------------------------------------------------------

HAGSTOFA_TABLE = ("https://px.hagstofa.is/pxen/api/v1/en/Ibuar/mannfjoldi/3_bakgrunnur/"
                  "Rikisfang/MAN04203.px")
HAGSTOFA_PAGE = ("https://px.hagstofa.is/pxen/pxweb/en/Ibuar/Ibuar__mannfjoldi__3_bakgrunnur__"
                 "Rikisfang/MAN04203.px")


def hagstofa_counts(body: dict[str, Any]) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    counts: dict[str, dict[str, float]] = defaultdict(dict)
    totals: dict[str, float] = {}
    for key, value in unstack(body):
        muni, code = key["Sveitarfélag"][0], key["Ríkisfang"][0]
        if code == "01":
            totals[muni] = value
        else:
            counts[muni][code] = counts[muni].get(code, 0.0) + value
    for muni, got in counts.items():
        if abs(sum(got.values()) - totals.get(muni, -1)) > 0.5:
            raise SystemExit(f"MAN04203 {muni}: citizenships make {sum(got.values()):,.0f} of "
                             f"{totals.get(muni)}")
    return counts, totals


def hagstofa_label(code: str, name: str) -> str | None:
    if code == "XZ":
        return STATELESS
    if code == "XX":
        return OTHER
    return label_of(name, code)


def iceland() -> list[dict[str, Any]]:
    from . import iceland as ic
    old = ic.yearly_totals(ic.OLD, [str(ic.VINTAGE)])[ic.VINTAGE]
    old_meta = {v["code"]: v for v in request_json(ic.OLD, pause=ic.PAUSE,
                                                    attempts=ic.ATTEMPTS)["variables"]}
    old_names = {code: re.sub(r"\s*\((?:fyrir|eftir) \d{4}\)\s*$", "", text) for code, text in
                 zip(old_meta["Sveitarfélag"]["values"], old_meta["Sveitarfélag"]["valueTexts"])}
    units = sorted(c for c, n in old.items() if c != "9999" and n > 0)
    now_meta = {v["code"]: v for v in request_json(ic.NOW, pause=ic.PAUSE,
                                                    attempts=ic.ATTEMPTS)["variables"]}
    meta = {v["code"]: v for v in request_json(HAGSTOFA_TABLE, pause=ic.PAUSE,
                                                attempts=ic.ATTEMPTS)["variables"]}
    year = min(meta["Ár"]["values"][-1], now_meta["Ár"]["values"][-1])
    series = ic.yearly_totals(ic.NOW, [str(ic.VINTAGE + 1), year])
    then, now_totals = series[ic.VINTAGE + 1], series[int(year)]
    now_names = dict(zip(now_meta["Sveitarfélag"]["values"], now_meta["Sveitarfélag"]["valueTexts"]))
    today, kept_number = ic.unchanged_since(units, old, old_names, then, now_totals, now_names)
    log(f"  {len(today)} of {len(units)} municipalities of {ic.VINTAGE} are the same territory "
        f"today; merged since: {sorted(old_names[c] for c in units if c not in today)}")
    names = dict(zip(meta["Ríkisfang"]["values"], meta["Ríkisfang"]["valueTexts"]))
    body = request_json(HAGSTOFA_TABLE, {"query": [
        {"code": "Sveitarfélag", "selection": {"filter": "all", "values": ["*"]}},
        {"code": "Ríkisfang", "selection": {"filter": "all", "values": ["*"]}},
        {"code": "Kyn", "selection": {"filter": "item", "values": ["0"]}},
        {"code": "Ár", "selection": {"filter": "item", "values": [year]}},
    ], "response": {"format": "json-stat2"}}, pause=ic.PAUSE, attempts=ic.ATTEMPTS)
    counts, totals = hagstofa_counts(body)
    country = "IS" if "IS" in totals else next(c for c in totals if not c.isdigit())
    floor = NAMED_SHARE * totals[country]
    labels = code_labels(counts[country], {c: n for c, n in names.items() if c != "01"},
                         hagstofa_label, floor, "MAN04203")
    national = by_label(counts[country], labels)
    named = named_labels(national, totals[country], "Icelandic")
    log(f"  MAN04203 {year}: {totals[country]:,.0f} people; named ({len(named)}): "
        f"{', '.join(sorted(named, key=lambda k: -national[k]))}")
    munis = sorted(c for c in totals if c != country)
    check_parts({c: totals[c] for c in munis}, totals[country],
                f"MAN04203 {year}: municipalities -> Iceland", 0)
    source = {"field": "ethnicity", "name": "Statistics Iceland, MAN04203", "url": HAGSTOFA_PAGE,
              "year": int(year)}
    note = (f"Citizenship as recorded in the population register on 1 January {year} "
            "(Statistics Iceland, MAN04203): NATIONALITY, not ethnicity, which no Icelandic "
            "register records. 'Icelandic' is every Icelandic citizen, naturalised citizens "
            "included; foreign citizens are counted under their citizenship."
            + folded_note(floor))

    def block(got: dict[str, float], total: float, extra: str = "") -> dict[str, Any]:
        made = compose(by_label(got, labels), named)
        return ethnicity_block(made, total, year=int(year), basis="citizenship",
                               note=note + extra, source=source)

    shapes = load_units("ISL", "admin2")
    bound, _m, _l, _p = bind_rows("ISL", "admin2",
                                  {c: (old_names[c], ic.REGION[c[0]]) for c in units},
                                  aliases=ic.ALIASES)
    records = []
    merged_into = {}
    for c in units:
        sid = bound.get(c)
        if sid is None:
            continue
        if c in today:
            n = today[c]
            fields = block(counts[n], totals[n],
                           extra=(f" The municipality (number {n} today) has not been merged "
                                  f"since {ic.VINTAGE}, the division the map draws."))
        else:
            merged_into[c] = old_names[c]
            fields = {"ethnicity": gap(NOT_AVAILABLE, (
                "Not given: Statistics Iceland publishes citizenship by municipality (MAN04203) "
                "and country of birth (MAN12104) only in today's municipalities, every year from "
                f"1998 laid out in them, and {old_names[c]} has been merged since {ic.VINTAGE}, "
                "the division the map draws; the merged municipality's figure is not this "
                "one's, and no table keeps the municipalities of earlier years."))}
        records.append(record(
            f"ISL-ORIGIN-{ic.VINTAGE}-{c}", old_names[c], level="admin2", parent="ISL",
            country="ISL", parent_name=ic.REGION[c[0]], codes={"hagstofa": c,
                                                               "vintage": ic.VINTAGE},
            match_by="shape_id", shape_id=sid, **fields))
    # The regions, from today's municipalities, each in the region the map
    # draws it in (Hornafjörður was renumbered into the Southern Region).
    drawn_in = {n: ic.REGION[c[0]] for c, n in today.items()}
    region_counts: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    region_total: dict[str, float] = defaultdict(float)
    for code in munis:
        region = drawn_in.get(code, ic.REGION[code[0]])
        region_total[region] += totals[code]
        for c, n in counts[code].items():
            region_counts[region][c] += n
    check_parts(dict(region_total), totals[country], f"MAN04203 {year}: regions -> Iceland", 0)
    admin1 = {fold(u["name"]): u for u in load_units("ISL", "admin1")}
    for region in sorted(region_total):
        shape = admin1.get(fold(region))
        if shape is None:
            raise SystemExit(f"iceland: region {region!r} has no polygon")
        records.append(record(
            f"ISL-ORIGIN-{fold(region)}", shape["name"], level="admin1", parent="ISL",
            country="ISL", match_by="shape_id", shape_id=shape["id"],
            **block(region_counts[region], region_total[region],
                    extra=" Summed from today's municipalities in the region.")))
    log(f"  municipalities given no figure, merged since {ic.VINTAGE}: {sorted(merged_into.values())}")
    return records


# ---------------------------------------------------------------------------

READERS = {"SWE": (sweden, "sweden_origin.json"), "DNK": (denmark, "denmark_origin.json"),
           "NOR": (norway, "norway_origin.json"), "FIN": (finland, "finland_origin.json"),
           "ISL": (iceland, "iceland_origin.json")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--country", required=True, choices=sorted(READERS))
    args = ap.parse_args()
    reader, out = READERS[args.country]
    log(f"nordic_origin: {args.country}")
    records = reader()
    labels = {g["group"] for r in records if isinstance(r.get("ethnicity"), list)
              for g in r["ethnicity"]}
    log(f"  {len(records)} records: "
        + ", ".join(f"{lvl} {n}" for lvl, n in sorted(Counter(r['level'] for r in records).items()))
        + f"; labels the group tree cannot place: {unplaced('ethnicity', labels) or 'none'}")
    write_json(PROCESSED / out, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
