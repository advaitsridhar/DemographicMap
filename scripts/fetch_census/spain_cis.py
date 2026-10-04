#!/usr/bin/env python3
"""Spain: religion by province and by comunidad from the CIS's pre-electoral surveys.

No Spanish census since the Constitution of 1978, which provides that no one
may be obliged to declare their religion (art. 16.2), has asked it. The
Centro de Investigaciones Sociológicas (CIS), the state's survey institute,
asks it in most of its studies: "¿Cómo se define Ud. en materia religiosa:
católico/a practicante, católico/a no practicante, creyente de otra religión,
agnóstico/a, indiferente o no creyente, o ateo/a?", plus N.C. for no answer.
Those are the categories written here, in English: Practising Catholic,
Non-practising Catholic, Believer in another religion, Agnostic, Indifferent /
non-believer, Atheist, Not stated. Each note quotes the question as the study
itself prints it.

The question asks which religion people identify with, practising or not, so
it counts nominal Catholics as Catholics. Surveys that first ask whether one
belongs to any religion at all -- the European Social Survey, which fills the
comunidades this file does not reach -- find fewer Catholics and more people
with none. In Catalonia the gap is large enough to change which group leads:
the ESS gives no religion 54% and Catholics 39%, while the CIS's own 2021
survey of Catalonia (study 3306) gives Catholics 52% and the three irreligious
answers 43%, as does the Catalan government's barometer (``catalonia_ceo``).
Every note says so.

**Why not the monthly barometers.** They interview about 4,000 people a month,
and pooled over a year they would reach most provinces. But the CIS publishes
each barometer's results crossed only by sex, age, education, size of
municipality, vote recall, occupation, class, ideology and religiosity (the
"Resultados y cruces" workbooks) -- never by comunidad or province -- and it
releases the microdata only through a request form that takes the requester's
name, organisation, e-mail address and purpose. This project does not fill in
that form, and does not fetch the files behind it. The CIS's other route to
its microdata, the Ficheros Integrados de Datos, needs an account.

**What is read instead.** Before a regional election the CIS surveys that
comunidad with a sample drawn province by province -- the provinces are the
electoral districts -- and publishes every question's marginals for the
comunidad and, in most studies, for each province. They come in three shapes,
each read as it comes:

* a tabulation workbook (``WORKBOOKS``): one sheet of marginals for the
  comunidad and one per province, the realised sample and the mean weight of
  each province in "Tabla ponderaciones", and the design in "Ficha técnica".
  Extremadura (study 3538, fieldwork late 2025), Aragón (3543), Castilla y
  León (3545) and Andalucía (3558), 2026: 22 provinces and their four
  comunidades. Study 3538's sheet for Cáceres is a copy of Badajoz's, so
  Cáceres is read from the province's PDF marginals instead, which the CIS
  publishes beside the workbook and which agree with the workbook for
  Badajoz and for Extremadura to the decimal they print.
* the comunidad's HTML marginals and a ficha técnica PDF (``TOTALS``):
  Galicia (3437) and the Basque Country (3448), 2024, whose province tables
  answer 404, so only the comunidades are written; and the Community of
  Madrid (3317, 2021), a comunidad of one province, written for the
  comunidad and for the province of Madrid, which is the same ground.
* PDF marginals for the comunidad and for each province (``PROVINCE_PDFS``):
  the Basque Country's survey for the July 2020 election (3286), whose three
  provinces are written. The comunidad is 3448's, which is newer.
* the October 2019 macro-survey for the general election (3263, 17,650
  interviews in every province), whose marginals by comunidad were on the
  CIS's former website only; the Internet Archive captured them on 4
  February 2020 (``ARCHIVED``). Read for the three comunidades of one
  province nothing newer reaches: La Rioja (284 respondents, low precision),
  and Ceuta and Melilla, which with 60 respondents each are left out.

**Looked at and not usable**, each on the CIS's site in October 2026:

* the regional pre-electoral surveys of 2015 (Castilla-La Mancha 3071,
  Canarias 3069, La Rioja 3076, Ceuta 3077, Melilla 3078, Extremadura 3073,
  Comunitat Valenciana 3066), of 2016 (Galicia 3153, the Basque Country
  3152, which ask mother tongue instead) and the Comunitat Valenciana's of
  2019 (3244) do not ask religion -- their marginals have no such question;
* Galicia's surveys of 2020 (3276, 3287) publish the comunidad only, and its
  2024 survey's province tables answer 404, so Galicia's provinces have none;
* the macro-survey 3263 was published by comunidad, not by province, so it
  gives the provinces of Castilla-La Mancha, Canarias, the Comunitat
  Valenciana and Galicia nothing; the earlier 2019 macro-surveys (3242,
  March, which asks "¿Cómo se define Ud. en cuanto a sentimiento
  religioso?", and 3245, April) are older than it, and the Archive holds no
  Ceuta or Melilla PDF of 3245;
* the May 2023 regional and July 2023 general-election surveys (3402, 3411)
  link their marginals on the old site, which answers 404 and 410, and the
  Internet Archive holds none of those pages;
* Catalonia's surveys of 2021 (3306, by province) and 2024 (3453, whose
  tables answer 404): the CEO's barometer, newer, is read there instead.

These are survey estimates of the people each survey was drawn from -- Spanish
citizens aged 18 and over resident in the comunidad and entitled to vote in
its election -- not counts, so the output file's name ends in ``_survey``:
the build lets it fill a composition no count has written, and as a national
office's survey it stands in front of the European Social Survey. The CIS's
shares are written as it publishes them (weighted, without counts): a
province's respondents are no measure of its people, and a roll-up must
price the shares against population rather than add interviews.

Checks, each of which stops the run:

* every answer is one the question offers, and every offered answer is there;
* each unit's shares make 100 (to 0.5 points);
* each unit's respondents are the realised sample the weights table or the
  ficha técnica (its Cuadro 1, for the macro-survey) gives it, and the
  provinces make the comunidad's
  respondents and the ficha's total -- with one exception, which is withheld
  rather than stopping the rest: a province whose sheet is, figure for
  figure, another province's (study 3538's "Provincia de Cáceres" sheet
  repeats Badajoz's shares and its 1,215 respondents; Cáceres's realised
  sample is 822), unless the province's own PDF marginals are published,
  name the study and the province, carry its realised sample and agree with
  no other province;
* where a study publishes both, the PDF marginals agree with the workbook's
  sheet for the same unit to the decimal they print;
* no two provinces carry the same shares;
* the comunidad's shares are, to 1 point in every answer, the provinces'
  shares weighted by their realised samples and weights (the CIS weights the
  comunidad and each province separately, so the two agree to a few tenths
  of a point rather than exactly);
* the ficha técnica still describes Spanish citizens aged 18 and over (or the
  electorate of a regional or general election, which is that), and every
  workbook, page and PDF names the study it is listed as;
* every unit has at least 100 respondents (100-299 is marked low precision);
* every province binds by its INE or NUTS code to exactly one drawn polygon
  whose label is that province's name, inside the polygon its comunidad binds
  to by name.

Usage:
    python -m scripts.fetch_census.spain_cis
"""

from __future__ import annotations

import argparse
import html
import io
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, http_get, log, record, write_json
from .binding import fold

OUT = "spain_cis_survey.json"
SITE = PROCESSED.parent.parent / "site" / "data"

MIN_N = 100
LOW_PRECISION = 300
SHARE_TOLERANCE = 0.5
# How far a comunidad's share may sit from its provinces' combined: see check_region.
REGION_TOLERANCE = 1.0
# A PDF prints one decimal; the workbook keeps them all.
PRINTED = 0.0501
LICENCE = ("CIS reuse conditions (Ley 37/2007): source to be cited as "
           "'Origen de los datos: Centro de Investigaciones Sociológicas'")

# The wording the studies read here print; each note quotes its own study's.
QUESTION_ES = ("¿Cómo se define Ud. en materia religiosa: católico/a practicante, "
               "católico/a no practicante, creyente de otra religión, agnóstico/a, "
               "indiferente o no creyente, o ateo/a?")
QUESTION = re.compile(r"c[oó]mo\s+se\s+define\s+ud\.?\s+en\s+materia\s+religiosa", re.I)

CENSUS = ("No Spanish census since the Constitution of 1978, which provides that no one may be "
          "obliged to declare their religion (art. 16.2), has asked it, and the CIS's monthly "
          "barometers publish it by no region.")
WORDING = ("The question records the religion people identify with, practising or not; surveys "
           "that first ask whether one belongs to any religion at all, such as the European "
           "Social Survey, find fewer Catholics and more people with none.")

# The CIS's answers, by how each begins once accents, case and the zero-width
# spaces its HTML puts after "Católico/" are folded away.
ANSWERS: tuple[tuple[str, str], ...] = (
    ("catolicoapracticante", "Practising Catholic"),
    ("catolicoanopracticante", "Non-practising Catholic"),
    ("creyentedeotrareligion", "Believer in another religion"),
    ("agnosticoa", "Agnostic"),
    ("indiferente", "Indifferent / non-believer"),
    ("ateoa", "Atheist"),
)
NOT_STATED = {"nc", "ns", "nsnc", "nocontesta", "nosabe"}
SUBSTANTIVE = tuple(label for _, label in ANSWERS)


@dataclass(frozen=True)
class Study:
    number: int
    title: str          # the CIS's own title
    election: str       # what the survey was for, in English
    ccaa: str           # INE code of the comunidad surveyed
    url: str            # the workbook, or the comunidad's HTML or PDF marginals
    page: str           # the study's page on cis.es
    ficha: str | None = None   # the ficha técnica PDF, where the workbook does not carry it
    # (INE province code, or "CA" for the comunidad; that unit's PDF marginals)
    pdfs: tuple[tuple[str, str], ...] = ()
    province: str | None = None   # a comunidad of one province: that province's INE code
    comunidad: bool = True        # False where a newer study writes the comunidad
    general: bool = False         # a general election's survey: its electorate is Spain's


WORKBOOKS: tuple[Study, ...] = (
    Study(3558, "Preelectoral elecciones autonómicas 2026. Comunidad autónoma de Andalucía",
          "the 2026 election to the Parliament of Andalusia", "01",
          "https://www.cis.es/documents/20117/13957047/3558-multi.xlsx",
          "https://www.cis.es/es/estudios/preelectoral-elecciones-autonomicas-2026-comunidad-"
          "autonoma-de-andalucia"),
    Study(3545, "Preelectoral elecciones autonómicas 2026. Comunidad autónoma de Castilla y León",
          "the 2026 election to the Cortes of Castile and León", "07",
          "https://www.cis.es/documents/20117/13765729/3545-multi.xlsx",
          "https://www.cis.es/es/estudios/preelectoral-elecciones-autonomicas-2026-comunidad-"
          "autonoma-de-castilla-y-leon"),
    # The CIS files study 3543's workbook as "3453-multi.xlsx"; its own header
    # says 3543, which is checked.
    Study(3543, "Preelectoral elecciones autonómicas 2026. Comunidad autónoma de Aragón",
          "the 2026 election to the Cortes of Aragon", "02",
          "https://www.cis.es/documents/20117/13730886/3453-multi.xlsx",
          "https://www.cis.es/es/estudios/preelectoral-elecciones-autonomicas-2026.-comunidad-"
          "autonoma-de-aragon"),
    # The workbook's Cáceres sheet is Badajoz's; the PDF marginals the study's
    # "Resultados PDF" page links are read beside it -- Cáceres's to replace
    # the copy, Badajoz's and Extremadura's to show the two agree.
    Study(3538, "Preelectoral elecciones autonómicas 2025. Comunidad autónoma de Extremadura",
          "the 2025 election to the Assembly of Extremadura", "11",
          "https://www.cis.es/documents/20117/13697506/3538-multi.xlsx",
          "https://www.cis.es/es/estudios/preelectoral-elecciones-autonomicas-2025.-comunidad-"
          "autonoma-de-extremadura",
          pdfs=(("CA", "https://www.cis.es/documents/d/guest/es3538mar_00extremadura-pdf"),
                ("06", "https://www.cis.es/documents/d/guest/es3538mar_01badajoz-pdf"),
                ("10", "https://www.cis.es/documents/d/guest/es3538mar_02caceres-pdf"))),
)

TOTALS: tuple[Study, ...] = (
    Study(3448, "Preelectoral del País Vasco. Elecciones autonómicas 2024",
          "the 2024 election to the Basque Parliament", "16",
          "https://www.cis.es/documents/20117/1559601/es3448mar-html.html",
          "https://www.cis.es/es/estudios/preelectoral-del-pais-vasco.-elecciones-autonomicas-2024",
          "https://www.cis.es/documents/20117/1559601/FT3448.pdf"),
    Study(3437, "Preelectoral de Galicia. Elecciones autonómicas 2024",
          "the 2024 election to the Parliament of Galicia", "12",
          "https://www.cis.es/documents/20117/1559046/es3437mar-htm.html",
          "https://www.cis.es/es/estudios/preelectoral-de-galicia.-elecciones-autonomicas-2024",
          "https://www.cis.es/documents/20117/1559046/FT3437.pdf"),
    Study(3317, "Preelectoral elecciones autonómicas 2021. Comunidad de Madrid",
          "the 2021 election to the Assembly of Madrid", "13",
          "https://www.cis.es/documents/20117/1557271/Es3317marhtml.html",
          "https://www.cis.es/es/estudios/preelectoral-elecciones-autonomicas-2021.-comunidad-de-"
          "madrid",
          "https://www.cis.es/documents/20117/1557271/Ft3317pdf.pdf", province="28"),
)

PROVINCE_PDFS: tuple[Study, ...] = (
    Study(3286, "Preelectoral del País Vasco. Elecciones autonómicas julio 2020",
          "the July 2020 election to the Basque Parliament", "16",
          "https://www.cis.es/documents/20117/1557131/es3286mar.pdf",
          "https://www.cis.es/es/estudios/preelectoral-del-pais-vasco.-elecciones-autonomicas-"
          "julio-2020",
          "https://www.cis.es/documents/20117/1557131/FT3286.pdf",
          pdfs=(("01", "https://www.cis.es/documents/20117/1557131/es3286mar_Alava.pdf"),
                ("20", "https://www.cis.es/documents/20117/1557131/es3286mar_Guipuzcoa.pdf"),
                ("48", "https://www.cis.es/documents/20117/1557131/es3286mar_Vizcaya.pdf")),
          comunidad=False),
)

# The October 2019 macro-survey (18,000 designed interviews in every province)
# published its marginals for each comunidad on the CIS's former website,
# which no longer answers; the study's page on the current site links pages
# that answer 404. The Internet Archive captured the comunidades' PDFs on 4
# February 2020, and three of them are units nothing newer reaches: La Rioja,
# Ceuta and Melilla, each one province. Each is read from the capture and
# checked against the realised interviews the study's ficha técnica (on the
# current site) gives the province in its Cuadro 1.
MACRO = ("https://web.archive.org/web/{stamp}id_/http://www.cis.es/cis/export/sites/default/"
         "-Archivos/Marginales/3260_3279/3263/Marginales/es3263mar_{name}.pdf")
MACRO_PAGE = ("https://www.cis.es/es/estudios/macrobarometro-de-octubre-2019.-preelectoral-"
              "elecciones-generales-2019")
MACRO_FICHA = "https://www.cis.es/documents/20117/1557011/FT3263.pdf"
ARCHIVED: tuple[Study, ...] = tuple(
    Study(3263, "Macrobarómetro de octubre 2019. Preelectoral elecciones generales 2019",
          "the November 2019 general election", ccaa,
          MACRO.format(stamp=stamp, name=name), MACRO_PAGE, MACRO_FICHA, province=province,
          general=True)
    for ccaa, province, name, stamp in (("17", "26", "Rioja", "20200204181945"),
                                        ("18", "51", "Ceuta", "20200204181940"),
                                        ("19", "52", "Melilla", "20200204180431")))

# INE's province codes: the names the CIS and the boundary file use, the
# comunidad (INE code) and the NUTS 2024 code where the province is one
# NUTS 3 region (the Balearic and Canary NUTS 3 regions are islands).
PROVINCES: dict[str, tuple[tuple[str, ...], str, str | None]] = {
    "01": (("Araba/Álava", "Álava", "Araba"), "16", "ES211"),
    "02": (("Albacete",), "08", "ES421"),
    "03": (("Alicante/Alacant", "Alicante", "Alacant"), "10", "ES521"),
    "04": (("Almería",), "01", "ES611"),
    "05": (("Ávila",), "07", "ES411"),
    "06": (("Badajoz",), "11", "ES431"),
    "07": (("Balears, Illes", "Illes Balears", "Baleares"), "04", None),
    "08": (("Barcelona",), "09", "ES511"),
    "09": (("Burgos",), "07", "ES412"),
    "10": (("Cáceres",), "11", "ES432"),
    "11": (("Cádiz",), "01", "ES612"),
    "12": (("Castellón/Castelló", "Castellón", "Castelló"), "10", "ES522"),
    "13": (("Ciudad Real",), "08", "ES422"),
    "14": (("Córdoba",), "01", "ES613"),
    "15": (("A Coruña", "Coruña, A", "Coruña", "La Coruña"), "12", "ES111"),
    "16": (("Cuenca",), "08", "ES423"),
    "17": (("Girona", "Gerona"), "09", "ES512"),
    "18": (("Granada",), "01", "ES614"),
    "19": (("Guadalajara",), "08", "ES424"),
    "20": (("Gipuzkoa", "Guipúzcoa"), "16", "ES212"),
    "21": (("Huelva",), "01", "ES615"),
    "22": (("Huesca",), "02", "ES241"),
    "23": (("Jaén",), "01", "ES616"),
    "24": (("León",), "07", "ES413"),
    "25": (("Lleida", "Lérida"), "09", "ES513"),
    "26": (("La Rioja", "Rioja, La"), "17", "ES230"),
    "27": (("Lugo",), "12", "ES112"),
    "28": (("Madrid",), "13", "ES300"),
    "29": (("Málaga",), "01", "ES617"),
    "30": (("Murcia",), "14", "ES620"),
    "31": (("Navarra",), "15", "ES220"),
    "32": (("Ourense", "Orense"), "12", "ES113"),
    "33": (("Asturias",), "03", "ES120"),
    "34": (("Palencia",), "07", "ES414"),
    "35": (("Las Palmas", "Palmas, Las"), "05", None),
    "36": (("Pontevedra",), "12", "ES114"),
    "37": (("Salamanca",), "07", "ES415"),
    "38": (("Santa Cruz de Tenerife",), "05", None),
    "39": (("Cantabria",), "06", "ES130"),
    "40": (("Segovia",), "07", "ES416"),
    "41": (("Sevilla",), "01", "ES618"),
    "42": (("Soria",), "07", "ES417"),
    "43": (("Tarragona",), "09", "ES514"),
    "44": (("Teruel",), "02", "ES242"),
    "45": (("Toledo",), "08", "ES425"),
    "46": (("Valencia/València", "Valencia", "València"), "10", "ES523"),
    "47": (("Valladolid",), "07", "ES418"),
    "48": (("Bizkaia", "Vizcaya"), "16", "ES213"),
    "49": (("Zamora",), "07", "ES419"),
    "50": (("Zaragoza",), "02", "ES243"),
    "51": (("Ceuta",), "18", "ES630"),
    "52": (("Melilla",), "19", "ES640"),
}

# INE's comunidad codes and the names the CIS and the boundary file give them.
COMUNIDADES: dict[str, tuple[str, ...]] = {
    "01": ("Andalucía",), "02": ("Aragón",),
    "03": ("Principado de Asturias", "Asturias", "Asturias (Principado de)"),
    "04": ("Illes Balears", "Balears (Illes)", "Islas Baleares"), "05": ("Canarias",),
    "06": ("Cantabria",), "07": ("Castilla y León",), "08": ("Castilla-La Mancha",),
    "09": ("Cataluña/Catalunya", "Cataluña", "Catalunya"),
    "10": ("Comunitat Valenciana", "Comunidad Valenciana"), "11": ("Extremadura",),
    "12": ("Galicia",),
    "13": ("Comunidad de Madrid", "Madrid (Comunidad de)", "Madrid"),
    "14": ("Región de Murcia", "Murcia (Región de)", "Murcia"),
    "15": ("Comunidad Foral de Navarra", "Navarra (Comunidad Foral de)", "Navarra"),
    "16": ("País Vasco/Euskadi", "País Vasco", "Euskadi"), "17": ("La Rioja",),
    "18": ("Ciudad Autónoma de Ceuta", "Ceuta"), "19": ("Ciudad Autónoma de Melilla", "Melilla"),
}

MONTHS = {"enero": "January", "febrero": "February", "marzo": "March", "abril": "April",
          "mayo": "May", "junio": "June", "julio": "July", "agosto": "August",
          "septiembre": "September", "setiembre": "September", "octubre": "October",
          "noviembre": "November", "diciembre": "December"}


# --- text -----------------------------------------------------------------------

def flatten(text: str) -> str:
    """A ficha's or a PDF's text on one line, with the figures pypdf breaks apart joined.

    pypdf reads some of the CIS's PDFs a few characters at a time -- "Realizada:
    3. 354 entrevistas", "Del 1 9 al 28 de marzo de 20 2 1" -- so a figure
    split by a break is put back together before anything is read from it.
    """
    flat = re.sub(r"\s+", " ", str(text).replace("_x000D_", " ").replace("​", ""))
    flat = re.sub(r"(?<=\d) ?([.,]) ?(?=\d)", r"\1", flat)
    return re.sub(r"(?<=\d) (?=\d)", "", flat).strip()


def squeeze(text: str) -> str:
    """Lower case, without accents or spaces: pypdf breaks words ("Gipu zkoa") as well."""
    stripped = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in stripped.lower() if not c.isspace() and not unicodedata.combining(c))


def plain(text: str) -> str:
    """Lower case and without accents, spaces kept."""
    stripped = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in stripped.lower() if not unicodedata.combining(c))


def tidy_question(text: str) -> str:
    """The question as the study prints it, on one line, from its ¿ to its ?."""
    flat = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(str(text)))
                  .replace("​", "").replace("_x000D_", " ")).strip()
    m = QUESTION.search(flat)
    if m:
        start = flat.rfind("¿", 0, m.start())
        flat = flat[start if 0 <= start and m.start() - start < 40 else m.start():]
    end = flat.find("?")
    return flat[:end + 1] if end >= 0 else flat


# --- reading the CIS's tables ------------------------------------------------

def answer_label(text: str) -> str:
    """The CIS's answer -> the map's label; an answer it does not offer stops the run."""
    key = fold(html.unescape(str(text)).replace("​", ""))
    if key in NOT_STATED:
        return "Not stated"
    for start, label in ANSWERS:
        if key.startswith(start):
            return label
    raise SystemExit(f"spain_cis: an answer the religion question does not offer: {text!r}")


def number(value: Any) -> float:
    """A cell or an HTML figure as a number: 15,2 -> 15.2; (4.998) -> 4998; - -> 0."""
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().strip("()").strip()
    if text == "-":                                      # the CIS's printed zero
        return 0.0
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", text):          # a thousands separator
        return float(text.replace(".", ""))
    return float(text.replace(",", "."))


def composition(pairs: list[tuple[str, Any]], where: str) -> dict[str, float]:
    """(answer, share) pairs -> {label: share}, every answer offered and none other."""
    shares: dict[str, float] = {}
    for text, value in pairs:
        label = answer_label(text)
        shares[label] = shares.get(label, 0.0) + number(value)
    missing = [label for label in SUBSTANTIVE if label not in shares]
    if missing:
        raise SystemExit(f"spain_cis: {where}: the religion question lacks {missing}")
    total = sum(shares.values())
    if abs(total - 100.0) > SHARE_TOLERANCE:
        raise SystemExit(f"spain_cis: {where}: the religion answers make {total:.2f}%")
    return shares


def religion_block(rows: list[list[Any]], where: str) -> tuple[dict[str, float], int, str]:
    """The religion question's shares, its (N) and its wording, in one sheet of marginals."""
    for i, row in enumerate(rows):
        first = next((c for c in row if c not in (None, "")), None)
        if first is None or not QUESTION.search(str(first)):
            continue
        question = tidy_question(first)
        pairs: list[tuple[str, Any]] = []
        for follow in rows[i + 1:]:
            cells = [c for c in follow if c not in (None, "")]
            if not cells:
                continue
            label = str(cells[0]).strip()
            if label == "(N)":
                if len(cells) < 2:
                    raise SystemExit(f"spain_cis: {where}: an (N) row with no figure")
                return composition(pairs, where), int(number(cells[1])), question
            if label.lower().startswith("pregunta") or len(cells) < 2:
                break
            pairs.append((label, cells[1]))
        raise SystemExit(f"spain_cis: {where}: the religion question ends without its (N)")
    raise SystemExit(f"spain_cis: {where}: no religion question")


def weights_table(rows: list[list[Any]], where: str) -> tuple[dict[str, dict[str, Any]], int]:
    """'Tabla ponderaciones' -> {INE province code: name, realised, weight}, and the total."""
    # The header row's own cells, not the sheet's title above it ("Muestra
    # diseñada, realizada, coeficientes de ponderación y error"), which names both.
    head = next((i for i, row in enumerate(rows)
                 if any(str(c).strip().lower() == "realizada" for c in row)
                 and any(str(c).strip().lower().startswith("ponderaci") for c in row)), None)
    if head is None:
        raise SystemExit(f"spain_cis: {where}: no weights table")
    table: dict[str, dict[str, Any]] = {}
    total = None
    for row in rows[head + 1:]:
        cells = [c for c in row if c not in (None, "")]
        if not cells:
            continue
        if any(str(c).strip().lower() == "total" for c in cells[:2]):
            numbers = [c for c in cells if not isinstance(c, str) or re.fullmatch(r"[\d.,]+", c)]
            if len(numbers) < 2:
                raise SystemExit(f"spain_cis: {where}: the weights table's total has {cells}")
            total = int(number(numbers[1]))
            break
        code = str(cells[0]).strip()
        if not re.fullmatch(r"\d{1,2}", code) or len(cells) < 5:
            raise SystemExit(f"spain_cis: {where}: a weights table row reads {cells}")
        code = code.zfill(2)
        table[code] = {"name": str(cells[1]).strip(), "designed": int(number(cells[2])),
                       "realised": int(number(cells[3])), "weight": number(cells[4])}
    if total is None or not table:
        raise SystemExit(f"spain_cis: {where}: the weights table has no total")
    if sum(t["realised"] for t in table.values()) != total:
        raise SystemExit(f"spain_cis: {where}: the provinces' realised samples make "
                         f"{sum(t['realised'] for t in table.values()):,}, the total {total:,}")
    return table, total


def ficha(text: str, where: str) -> dict[str, Any]:
    """The design as a ficha técnica states it: universe, sample, fieldwork, method."""
    flat = flatten(text)
    universe = re.search(r"Universo\s*:?\s*(.+?)\s*(?:Tamaño de la muestra|Diseñada)", flat)
    realised = re.search(r"Realizada\s*:?\s*([\d.]+)\s*entrevistas", flat)
    dates = re.search(r"Fecha de realizaci[oó]n\s*:?\s*(.+?\d{4})", flat)
    if not (universe and realised and dates):
        raise SystemExit(f"spain_cis: {where}: the ficha técnica no longer states the universe, "
                         f"sample and fieldwork as it did")
    words = plain(flat)
    out = {"universe": universe.group(1).strip(), "realised": int(number(realised.group(1))),
           "fieldwork": dates.group(1).strip(), "year": int(dates.group(1)[-4:]),
           # How it was asked, as the ficha says, not assumed: by telephone
           # (CATI) or face to face, and the respondent chosen by quotas of
           # sex and age only where the ficha says so.
           "mode": ("telephone" if re.search(r"\bcati\b|telefon", words)
                    else "face" if re.search(r"entrevista personal|domicilio|presencial", words)
                    else None),
           "quotas": "cuotasdesexoyedad" in squeeze(flat),
           "weighted": bool(re.search(r"\bPESO\b", flat)),
           "province_weight": "PESOPROV" in flat,
           "self_weighting": bool(re.search(r"ponderacion\s*:?\s*no\s*procede", words))}
    universe_text = squeeze(out["universe"])
    # The electorate of a regional or general election is Spanish citizens
    # aged 18 and over: the ficha names one or the other.
    voters = bool(re.search(r"derechoavotoenelecciones(?:autonomicas|generales)", universe_text))
    if not (voters or ("espanola" in universe_text and "18" in out["universe"])):
        raise SystemExit(f"spain_cis: {where}: the universe is now {out['universe']!r}; the "
                         f"note says Spanish citizens aged 18 and over")
    out["voters"] = voters or "voto" in universe_text
    return out


def ficha_provinces(text: str, codes: list[str], where: str) -> dict[str, dict[str, Any]]:
    """Each province's realised sample and comunidad weight (PESO), as the ficha lists them."""
    sq = squeeze(flatten(text))
    realised = re.search(r"realizada:?(.*?)afijaci", sq)
    weights = re.search(r"\(peso\):?(.*?)(?:puntosdemuestreo|procedimiento|$)", sq)
    if not (realised and weights):
        raise SystemExit(f"spain_cis: {where}: the ficha técnica lists no provincial sample and "
                         f"weights")
    out: dict[str, dict[str, Any]] = {}
    for code in codes:
        names = sorted({squeeze(n) for n in PROVINCES[code][0]}, key=len, reverse=True)
        n = w = None
        for name in names:
            got = re.search(re.escape(name) + r":?(\d[\d.]*)", realised.group(1))
            if got and n is None:
                n = int(got.group(1).rstrip(".").replace(".", ""))
            got = re.search(re.escape(name) + r":?(\d+,\d+)", weights.group(1))
            if got and w is None:
                w = float(got.group(1).replace(",", "."))
        if n is None or w is None:
            raise SystemExit(f"spain_cis: {where}: the ficha técnica gives "
                             f"{PROVINCES[code][0][0]} no realised sample or weight")
        out[code] = {"realised": n, "weight": w}
    return out


def cuadro_realised(text: str, code: str, where: str) -> int:
    """A province's realised interviews in a macro-survey ficha's Cuadro 1.

    The table reads, a figure to a line: the province's INE code, its name,
    sampling points designed and reached, interviews designed and realised,
    the error and the weights ("26 / Rioja (La) / 15 / 15 / 300 / 284 / 5,9 /
    0,4166").
    """
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines() if ln.strip()]
    start = next((i for i, ln in enumerate(lines) if ln.startswith("Cuadro 1")), None)
    if start is None:
        raise SystemExit(f"spain_cis: {where}: the ficha técnica has no Cuadro 1")
    names = {fold(n) for n in PROVINCES[code][0]}
    for i in range(start, len(lines) - 6):
        if lines[i] == str(int(code)) and fold(lines[i + 1]) in names:
            figures = lines[i + 2:i + 6]
            if all(re.fullmatch(r"\d{1,3}(?:\.\d{3})*", f) for f in figures):
                return int(figures[3].replace(".", ""))
    raise SystemExit(f"spain_cis: {where}: Cuadro 1 gives {PROVINCES[code][0][0]} no realised "
                     f"interviews")


def archive_date(url: str) -> str:
    """'https://web.archive.org/web/20200204181945id_/...' -> '4 February 2020'."""
    m = re.search(r"/web/(\d{4})(\d{2})(\d{2})\d*id_/", url)
    if not m:
        raise SystemExit(f"spain_cis: {url} is not an Internet Archive capture")
    year, month, day = m.groups()
    english = ("January", "February", "March", "April", "May", "June", "July", "August",
               "September", "October", "November", "December")
    return f"{int(day)} {english[int(month) - 1]} {year}"


def read_archived(text: str, ficha_text: str, study: Study) -> dict[str, Any]:
    """A comunidad's PDF marginals from a captured macro-survey, and its design.

    The PDF must name the study and the comunidad, and its respondents must be
    the realised interviews the ficha's Cuadro 1 gives the comunidad's one
    province.
    """
    assert study.province
    where = f"study {study.number} {COMUNIDADES[study.ccaa][0]}"
    design = ficha(ficha_text, where)
    shares, n, question = pdf_marginals(text, study, COMUNIDADES[study.ccaa], where)
    realised = cuadro_realised(ficha_text, study.province, where)
    if n != realised:
        raise SystemExit(f"spain_cis: {where}: {n:,} respondents in the PDF, {realised:,} "
                         f"realised in the ficha's Cuadro 1")
    return {"design": design, "region": {"shares": shares, "n": n, "question": question},
            "archived": archive_date(study.url)}


def names_study(text: str, number_: int) -> bool:
    """Whether a page or sheet names the study -- after "nº" too, which \\b misses."""
    return re.search(rf"(?<!\d){number_}(?!\d)", text) is not None


def english_dates(text: str) -> str:
    """'Del 6 al 13 de febrero de 2026' -> '6-13 February 2026', or the text as it is."""
    t = text.strip().rstrip(".")
    m = re.fullmatch(r"(?i)del (\d{1,2})(?: de (\w+))? (?:y )?al (\d{1,2}) de (\w+) de (\d{4})", t)
    if m:
        d1, m1, d2, m2, year = m.groups()
        m2e = MONTHS.get(m2.lower())
        m1e = MONTHS.get(m1.lower()) if m1 else None
        if m2e and (m1 is None or m1e):
            return (f"{d1} {m1e} - {d2} {m2e} {year}" if m1e and m1e != m2e
                    else f"{d1}-{d2} {m2e} {year}")
    return t


def sheet_unit(name: str) -> str:
    """A results sheet's name -> the unit it describes, folded."""
    name = re.sub(r"(?i)^\s*resultados[\s_]*", "", name)
    name = re.sub(r"(?i)^(?:de\s+)?(?:la\s+)?provincia\s+de\s+", "", name)
    return fold(name)


# --- PDF marginals ---------------------------------------------------------------

# A page's running foot and head, which a table can be broken by.
FOOT = re.compile(r"(?i)^(?:CIS|P[áa]g\.?\s*\d+|Estudio\s+n.*)$")
ANSWER_LINE = re.compile(r"(.+?)\s+(\d{1,3}(?:,\d+)?|-)")


def pdf_text(raw: bytes) -> str:
    from pypdf import PdfReader                        # noqa: PLC0415 -- the runner has it
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(raw)).pages)


def pdf_marginals(text: str, study: Study, names: tuple[str, ...], where: str
                  ) -> tuple[dict[str, float], int, str]:
    """A unit's PDF marginals -> the religion question's shares, its (N) and its wording.

    The first page must name the study ("Estudio nº 3286_1") and the unit the
    file is listed as ("ARABA/ÁLAVA"): a file that describes another place
    stops the run.
    """
    head = text[:1500]
    if not names_study(flatten(head), study.number):
        raise SystemExit(f"spain_cis: {where}: the PDF does not name study {study.number}: "
                         f"{flatten(head)[:160]!r}")
    if not any(squeeze(n) in squeeze(head) for n in names):
        raise SystemExit(f"spain_cis: {where}: the PDF's first page does not name {names[0]}: "
                         f"{flatten(head)[:160]!r}")
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines() if ln.strip()]
    at = next((i for i, ln in enumerate(lines) if QUESTION.search(ln)), None)
    if at is None:
        raise SystemExit(f"spain_cis: {where}: no religion question")
    end = at
    while "?" not in lines[end] and end + 1 < len(lines) and end - at < 4:
        end += 1
    rows: list[list[Any]] = [[" ".join(lines[at:end + 1])]]
    for line in lines[end + 1:end + 40]:
        if line.startswith("(N)"):
            rows.append(["(N)", line[3:].strip()])
            break
        if FOOT.match(line):
            continue
        m = ANSWER_LINE.fullmatch(line)
        if m:
            rows.append([m.group(1), m.group(2)])
    return religion_block(rows, where)


def gap_between(sheet: dict[str, float], printed: dict[str, float]) -> float:
    """The largest difference between two compositions, answer by answer."""
    return max(abs(sheet.get(k, 0.0) - printed.get(k, 0.0)) for k in set(sheet) | set(printed))


def agree(sheet: dict[str, float], printed: dict[str, float], where: str) -> None:
    """A workbook's shares and the PDF's of the same unit, to the decimal the PDF prints.

    The PDF rounds each share to one decimal, so a share it prints is within
    0.05 of the workbook's -- unless the two are different tables.
    """
    worst = gap_between(sheet, printed)
    if worst > PRINTED:
        raise SystemExit(f"spain_cis: {where}: the PDF and the workbook differ by {worst:.2f} "
                         f"points: {printed} against {sheet}")


# --- workbooks -------------------------------------------------------------------

def read_workbook(raw: bytes, study: Study, pdfs: dict[str, str] | None = None
                  ) -> dict[str, Any]:
    """A pre-electoral study's workbook -> its design, its provinces and its comunidad.

    ``pdfs`` holds the text of the PDF marginals the study is listed with,
    by INE province code ("CA" for the comunidad).
    """
    import openpyxl                                    # noqa: PLC0415 -- the runner has it
    book = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    where = f"study {study.number}"

    def rows_of(title: str) -> list[list[Any]]:
        return [list(r) for r in book[title].iter_rows(values_only=True)]

    names = book.sheetnames
    header = " ".join(str(c) for row in rows_of(names[0])[:4] for c in row if c)
    if not re.search(rf"(?<!\d){study.number}/\d", header):
        raise SystemExit(f"spain_cis: the workbook listed as study {study.number} is headed "
                         f"{header[:120]!r}")
    sheet = next((n for n in names if fold(n).startswith("fichatecnica")), None)
    table = next((n for n in names if fold(n).startswith("tablaponderaciones")), None)
    if sheet is None or table is None:
        raise SystemExit(f"spain_cis: {where}: sheets are {names}")
    design = ficha(" ".join(f"{c}:" if j == 0 and isinstance(c, str) else str(c)
                            for row in rows_of(sheet) for j, c in enumerate(row) if c), where)
    weights, total = weights_table(rows_of(table), where)
    if total != design["realised"]:
        raise SystemExit(f"spain_cis: {where}: the weights table totals {total:,}, the ficha "
                         f"técnica {design['realised']:,}")
    by_unit = {sheet_unit(n): n for n in names}
    region_names = COMUNIDADES[study.ccaa]
    region_sheet = next((by_unit[fold(n)] for n in region_names if fold(n) in by_unit), None)
    if region_sheet is None:
        raise SystemExit(f"spain_cis: {where}: no sheet for {region_names[0]} among {names}")
    region, region_n, region_q = religion_block(rows_of(region_sheet),
                                                f"{where} {region_sheet!r}")
    read: dict[str, dict[str, Any]] = {}
    for code, entry in weights.items():
        if code not in PROVINCES or PROVINCES[code][1] != study.ccaa:
            raise SystemExit(f"spain_cis: {where}: province code {code} ({entry['name']}) is not "
                             f"in comunidad {study.ccaa}")
        known = {fold(n) for n in PROVINCES[code][0]}
        if fold(entry["name"]) not in known:
            raise SystemExit(f"spain_cis: {where}: province {code} is {entry['name']!r} in the "
                             f"weights table")
        title = next((by_unit[k] for k in known if k in by_unit), None)
        if title is None:
            raise SystemExit(f"spain_cis: {where}: no results sheet for {entry['name']}")
        shares, n, question = religion_block(rows_of(title), f"{where} {title!r}")
        read[code] = {"name": entry["name"], "shares": shares, "n": n, "question": question,
                      "weight": entry["weight"], "sheet": title, "realised": entry["realised"]}
    printed: dict[str, dict[str, Any]] = {}
    for key, text in (pdfs or {}).items():
        unit = region_names if key == "CA" else PROVINCES[key][0]
        shares, n, question = pdf_marginals(text, study, unit, f"{where} PDF of {unit[0]}")
        printed[key] = {"shares": shares, "n": n, "question": question}
    if "CA" in printed:
        if printed["CA"]["n"] != region_n:
            raise SystemExit(f"spain_cis: {where}: the comunidad's PDF has {printed['CA']['n']:,} "
                             f"respondents, its sheet {region_n:,}")
        agree(region, printed["CA"]["shares"], f"{where} {region_names[0]}")
    provinces, withheld = sort_out(read, where, printed)
    expected = {c for c, (_, ccaa, _) in PROVINCES.items() if ccaa == study.ccaa}
    if set(provinces) | set(withheld) != expected:
        raise SystemExit(f"spain_cis: {where}: provinces {sorted(read)}, expected "
                         f"{sorted(expected)}")
    if region_n != total:
        raise SystemExit(f"spain_cis: {where}: the comunidad has {region_n:,} respondents, the "
                         f"weights table {total:,}")
    if withheld:
        log(f"  {where}: the comunidad is not checked against its provinces: "
            f"{', '.join(read[c]['name'] for c in withheld)} withheld")
    else:
        check_region(region, provinces, where)
    modified = getattr(book.properties, "modified", None)
    return {"design": design, "region": {"shares": region, "n": region_n, "question": region_q},
            "provinces": provinces, "withheld": withheld,
            "modified": modified.date().isoformat() if modified else None}


def sort_out(read: dict[str, dict[str, Any]], where: str,
             printed: dict[str, dict[str, Any]] | None = None
             ) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Provinces whose sheet is theirs, and those whose sheet is another's copy.

    A province's respondents to the religion question are its realised sample;
    a sheet that disagrees stops the run -- except where it is, figure for
    figure, another province's sheet, whose own sample it carries. That is the
    CIS's workbook repeating one province under another's name, as study 3538
    does: its "Provincia de Cáceres" sheet is Badajoz's, every share to the
    fifteenth decimal and its 1,215 respondents (Cáceres's realised sample is
    822). Such a province is read from its own PDF marginals where the study
    publishes them (``printed``) -- which must carry its realised sample and
    agree with no other province -- and is withheld, and said so, otherwise.
    It is never given the copy. A province read from both must find them
    agreeing.
    """
    printed = printed or {}
    good = {c: p for c, p in read.items() if p["n"] == p["realised"]}
    for code, prov in good.items():
        if code in printed:
            if printed[code]["n"] != prov["n"]:
                raise SystemExit(f"spain_cis: {where}: {prov['name']}'s PDF has "
                                 f"{printed[code]['n']:,} respondents, its sheet {prov['n']:,}")
            agree(prov["shares"], printed[code]["shares"], f"{where} {prov['name']}")
    withheld: dict[str, str] = {}
    for code, prov in read.items():
        if code in good:
            continue
        twin = next((c for c, p in good.items()
                     if p["n"] == prov["n"] and p["shares"] == prov["shares"]), None)
        if twin is None:
            raise SystemExit(f"spain_cis: {where}: {prov['name']} has {prov['n']:,} respondents "
                             f"to the religion question and a realised sample of "
                             f"{prov['realised']:,}")
        copy = (f"the CIS's workbook sheet for {prov['name']} repeats {good[twin]['name']}'s, "
                f"every share and its {prov['n']:,} respondents ({prov['name']}'s realised "
                f"sample is {prov['realised']:,})")
        own = printed.get(code)
        if own is not None:
            if own["n"] != prov["realised"]:
                raise SystemExit(f"spain_cis: {where}: {prov['name']}'s PDF has {own['n']:,} "
                                 f"respondents, its realised sample {prov['realised']:,}")
            clash = [p["name"] for c, p in good.items()
                     if gap_between(p["shares"], own["shares"]) <= PRINTED]
            if clash:
                raise SystemExit(f"spain_cis: {where}: {prov['name']}'s PDF repeats {clash}")
            good[code] = dict(prov, shares=own["shares"], n=own["n"], question=own["question"],
                              pdf=True, via=copy)
            log(f"  {where}: {prov['name']} read from its PDF marginals: {copy}")
            continue
        withheld[code] = copy
        log(f"  {where}: {prov['name']} withheld: {copy}")
    for code, prov in good.items():
        twins = [p["name"] for c, p in good.items() if c != code and p["shares"] == prov["shares"]]
        if twins:
            raise SystemExit(f"spain_cis: {where}: {prov['name']} and {twins} carry the same "
                             f"shares")
    return good, withheld


def check_region(region: dict[str, float], provinces: dict[str, dict[str, Any]],
                 where: str) -> float:
    """The comunidad's shares against its provinces' weighted by sample and weight.

    A province's realised sample times its weight is its weighted size, so the
    comunidad's share is close to the provinces' shares in those proportions.
    Not exactly: the CIS weights the comunidad's marginals with PESO
    (calibrated to sex, age, province, education and size of municipality)
    and each province's with PESOPROV or none, so the two agree to a few
    tenths of a point -- 0.32 at most in Andalucía, 0.54 in Castilla y León.
    The log gives the agreement for each study, beside what the provinces'
    shares make added up unweighted.
    """
    mass = {c: p["n"] * p["weight"] for c, p in provinces.items()}
    whole = sum(mass.values())
    sample = sum(p["n"] for p in provinces.values())
    worst, flat = 0.0, 0.0
    for label in region:
        made = sum(mass[c] * p["shares"].get(label, 0.0) for c, p in provinces.items()) / whole
        even = sum(p["n"] * p["shares"].get(label, 0.0) for p in provinces.values()) / sample
        worst = max(worst, abs(made - region[label]))
        flat = max(flat, abs(even - region[label]))
        if abs(made - region[label]) > REGION_TOLERANCE:
            raise SystemExit(f"spain_cis: {where}: the provinces make {label} {made:.2f}%, the "
                             f"comunidad {region[label]:.2f}%")
    log(f"  {where}: the provinces make the comunidad's shares to within {worst:.2f} points "
        f"weighted by their samples and weights ({flat:.2f} unweighted)")
    return worst


# --- the comunidad's HTML marginals, and PDF studies ----------------------------

def read_html_total(text: str, study: Study) -> tuple[dict[str, float], int, str]:
    """A comunidad's HTML marginals -> the religion question's shares, (N) and wording."""
    if not names_study(text, study.number):
        raise SystemExit(f"spain_cis: the marginals listed as study {study.number} do not name it")
    page = html.unescape(text)
    m = QUESTION.search(page)
    if not m:
        raise SystemExit(f"spain_cis: study {study.number}: no religion question")
    start = page.rfind("¿", 0, m.start())
    start = start if 0 <= start and m.start() - start < 40 else m.start()
    end = page.find("?", m.end())
    question = page[start:end + 1] if end > 0 else page[start:m.end()]
    table = re.search(r"(?is)<table.*?</table>", page[m.end():])
    if not table:
        raise SystemExit(f"spain_cis: study {study.number}: the religion question has no table")
    rows: list[list[Any]] = []
    for row in re.findall(r"(?is)<tr.*?</tr>", table.group(0)):
        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()
                 for c in re.findall(r"(?is)<td.*?</td>", row)]
        rows.append(cells)
    return religion_block([[question]] + rows, f"study {study.number}")


def read_pdf_study(total: str, ficha_text: str, provinces: dict[str, str], study: Study
                   ) -> dict[str, Any]:
    """A study published as PDF marginals for the comunidad and for each province.

    The ficha técnica lists each province's realised sample and its weight
    (PESO) in the comunidad; each province's PDF must carry that sample, the
    provinces must make the comunidad's respondents, and the comunidad's
    shares must be the provinces' weighted by sample and PESO. Each
    province's own shares are its sample's, unweighted: PESO only combines
    the provinces into the comunidad.
    """
    where = f"study {study.number}"
    design = ficha(ficha_text, where)
    figures = ficha_provinces(ficha_text, list(provinces), where)
    region, region_n, region_q = pdf_marginals(total, study, COMUNIDADES[study.ccaa],
                                               f"{where} {COMUNIDADES[study.ccaa][0]}")
    if region_n != design["realised"]:
        raise SystemExit(f"spain_cis: {where}: the comunidad's marginals have {region_n:,} "
                         f"respondents, the ficha técnica {design['realised']:,}")
    read: dict[str, dict[str, Any]] = {}
    for code, text in provinces.items():
        name = PROVINCES[code][0][0]
        shares, n, question = pdf_marginals(text, study, PROVINCES[code][0], f"{where} {name}")
        if n != figures[code]["realised"]:
            raise SystemExit(f"spain_cis: {where}: {name} has {n:,} respondents, its realised "
                             f"sample {figures[code]['realised']:,}")
        read[code] = {"name": name, "shares": shares, "n": n, "question": question,
                      "weight": figures[code]["weight"], "realised": n}
    expected = {c for c, (_, ccaa, _) in PROVINCES.items() if ccaa == study.ccaa}
    if set(read) != expected:
        raise SystemExit(f"spain_cis: {where}: provinces {sorted(read)}, expected "
                         f"{sorted(expected)}")
    if sum(p["n"] for p in read.values()) != region_n:
        raise SystemExit(f"spain_cis: {where}: the provinces make "
                         f"{sum(p['n'] for p in read.values()):,} respondents, the comunidad "
                         f"{region_n:,}")
    provinces_read, withheld = sort_out(read, where)
    check_region(region, provinces_read, where)
    return {"design": design, "region": {"shares": region, "n": region_n, "question": region_q},
            "provinces": provinces_read, "withheld": withheld}


# --- the map -------------------------------------------------------------------

def load_units() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from common import as_drawn                       # noqa: PLC0415 -- on the path via _shared
    a1 = as_drawn(json.loads((SITE / "admin1" / "ESP.units.json").read_text()))
    a2 = as_drawn(json.loads((SITE / "admin2" / "ESP.units.json").read_text()))
    return a1, a2


def bind(admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]
         ) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Every INE province -> its drawn polygon, and every comunidad -> the polygon around them.

    A province binds by its code -- INE's, or the NUTS 3 region it is -- to
    exactly one drawn polygon, and that polygon's own label must be the
    province's name. A comunidad is the one polygon all its provinces are
    drawn inside, and its label must be the comunidad's name.
    """
    provinces: dict[str, dict[str, Any]] = {}
    used: set[str] = set()
    for code, (names, _, nuts) in PROVINCES.items():
        hits = [u for u in admin2 if (u.get("codes") or {}).get("ine_province") == code
                or (nuts and (u.get("codes") or {}).get("nuts") == nuts)]
        if not hits:
            hits = [u for u in admin2 if fold(u["name"]) in {fold(n) for n in names}]
        if len(hits) != 1:
            raise SystemExit(f"spain_cis: province {code} ({names[0]}) matches "
                             f"{[u['name'] for u in hits]} on the map")
        unit = hits[0]
        if fold(unit["name"]) not in {fold(n) for n in names}:
            raise SystemExit(f"spain_cis: province {code} ({names[0]}) has code-matched the "
                             f"polygon labelled {unit['name']!r}")
        if unit["id"] in used:
            raise SystemExit(f"spain_cis: polygon {unit['name']} bound twice")
        used.add(unit["id"])
        provinces[code] = unit
    by_id = {u["id"]: u for u in admin1}
    comunidades: dict[str, dict[str, Any]] = {}
    for ccaa, names in COMUNIDADES.items():
        parents = {provinces[c]["parent"] for c, (_, cc, _) in PROVINCES.items() if cc == ccaa}
        if len(parents) != 1 or next(iter(parents)) not in by_id:
            raise SystemExit(f"spain_cis: comunidad {ccaa}'s provinces are drawn inside {parents}")
        unit = by_id[next(iter(parents))]
        if fold(unit["name"]) not in {fold(n) for n in names}:
            raise SystemExit(f"spain_cis: comunidad {ccaa} ({names[0]}) is drawn as "
                             f"{unit['name']!r}")
        comunidades[ccaa] = unit
    return provinces, comunidades


# --- records ---------------------------------------------------------------------

def rows_of(shares: dict[str, float]) -> list[dict[str, Any]]:
    rows = [{"group": label, "pct": round(share, 1)} for label, share in shares.items()]
    rows.sort(key=lambda r: (-r["pct"], r["group"]))
    return rows


def method_of(design: dict[str, Any]) -> str:
    """How the ficha says the survey was taken: mode, then quotas where it names them."""
    mode = {"telephone": "telephone interviews (CATI)",
            "face": "face-to-face interviews at home"}.get(design.get("mode") or "", "")
    if mode and design.get("quotas"):
        mode += " with quotas of sex and age"
    return f"{mode}, " if mode else ""


def weighting_of(design: dict[str, Any], kind: str) -> str:
    """What weights stand behind the shares, by what the ficha says of them.

    ``kind`` is "comunidad", "province" (a workbook's province, weighted by
    PESOPROV where the ficha names it) or "province-pdf" (a province of a
    study published as PDFs, whose ficha weights only the whole).
    """
    if design.get("self_weighting"):
        return "a self-weighting sample: the CIS applies no weights; these are its published shares"
    if kind == "macro":
        return ("the comunidad's own sample of its one province, for which the ficha técnica "
                "gives only the weight that combines provinces into the national total; these "
                "are its published shares")
    if kind == "province" and design.get("province_weight"):
        return ("weighted by the CIS's post-stratification coefficients for the province "
                "(PESOPROV); these are its published weighted shares")
    if kind == "province-pdf" and design.get("weighted"):
        return ("the province's own sample, unweighted: the CIS's coefficients (PESO) only "
                "combine the provinces into the comunidad; these are its published shares")
    if kind == "comunidad" and design.get("weighted"):
        return ("weighted by the CIS's coefficients for the comunidad (PESO); these are its "
                "published weighted shares")
    return "shares as the CIS publishes them"


def fields(study: Study, design: dict[str, Any], unit: str, n: int,
           shares: dict[str, float], what: str, updated: str | None, question: str,
           kind: str = "comunidad", url: str | None = None, extra: str = "") -> dict[str, Any]:
    precision = (" Low precision: under 300 respondents." if n < LOW_PRECISION else "")
    comunidad = COMUNIDADES[study.ccaa][0]
    voters = design.get("voters", False)
    electorate = "general elections" if study.general else "the regional election"
    return {
        "religion": rows_of(shares),
        "religion_year": design["year"],
        "religion_basis": ("survey estimate: self-identification, Spanish citizens aged 18+"
                           + (f" entitled to vote in {electorate}" if voters else "")),
        "religion_note": (
            f"CIS study {study.number}, the pre-electoral survey for {study.election}, fieldwork "
            f"{english_dates(design['fieldwork'])}: \"{question}\" Answers as the CIS offers "
            f"them; its N.C. (no answer) is Not stated. A survey estimate, not a count: "
            f"{n:,} respondents in {what} ({method_of(design)}{weighting_of(design, kind)})."
            f"{precision}{(' ' + extra) if extra else ''} Universe: Spanish citizens aged 18 and "
            f"over resident in {comunidad}"
            + ((" and entitled to vote in general elections" if study.general
                else " and entitled to vote in its election") if voters else "")
            + f", so foreign residents, among whom Muslims and Orthodox Christians are many, are "
              f"not in it. {WORDING} {CENSUS}"),
        "sources": [{"field": "religion",
                     "name": (f"CIS, study {study.number}: {study.title} -- "
                              + ("PDF marginals" if url and url.lower().split("?")[0].endswith(
                                  ("pdf", "-pdf")) else "marginals")
                              + f" for {unit}" + (f" (updated {updated})" if updated else "")),
                     "url": url or study.url, "year": design["year"], "license": LICENCE}],
    }


def build(results: list[tuple[Study, dict[str, Any]]], provinces: dict[str, dict[str, Any]],
          comunidades: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    skipped: list[str] = []
    for study, got in results:
        design, updated = got["design"], got.get("modified")
        region = got["region"]
        unit = comunidades[study.ccaa]
        question = region.get("question") or QUESTION_ES
        archived = got.get("archived")
        kind = "macro" if archived else "comunidad"
        url = study.url if archived else None
        via = (f"Read from the CIS's PDF marginals for {unit['name']} as its former website "
               f"published them, captured by the Internet Archive on {archived}: the study's "
               f"page on the CIS's current site links them to pages that no longer answer."
               if archived else "")
        if not study.comunidad:
            pass
        elif region["n"] < MIN_N:
            skipped.append(f"{unit['name']}"
                           + (f" and the province of {provinces[study.province]['name']}"
                              if study.province else "")
                           + f": {region['n']} respondents (study {study.number})")
        else:
            records.append(record(
                f"ESP-CIS{study.number}-CA{study.ccaa}", unit["name"], level="admin1",
                parent="ESP", country="ESP", match_by="shape_id", shape_id=unit["id"],
                codes={"ine_ccaa": study.ccaa, "cis_study": study.number, "cis_n": region["n"]},
                **fields(study, design, unit["name"], region["n"], region["shares"],
                         unit["name"], updated, question, kind=kind, url=url, extra=via)))
            if study.province:
                # A comunidad of one province: the province is the same
                # ground, so it carries the comunidad's own figures -- not a
                # region's copied onto a part of it.
                shape = provinces[study.province]
                if shape["parent"] != unit["id"]:
                    raise SystemExit(f"spain_cis: {shape['name']} is not drawn inside "
                                     f"{unit['name']}")
                others = [c for c, (_, cc, _) in PROVINCES.items()
                          if cc == study.ccaa and c != study.province]
                if others:
                    raise SystemExit(f"spain_cis: comunidad {study.ccaa} has provinces {others} "
                                     f"besides {study.province}")
                whole = (f"The province of {PROVINCES[study.province][0][0]} is the whole of "
                         f"{unit['name']}, so these are the comunidad's figures.")
                records.append(record(
                    f"ESP-CIS{study.number}-{study.province}", shape["name"], level="admin2",
                    parent="ESP", country="ESP", match_by="shape_id", shape_id=shape["id"],
                    codes={"ine_province": study.province, "cis_study": study.number,
                           "cis_n": region["n"]},
                    **fields(study, design, unit["name"], region["n"], region["shares"],
                             f"the province of {PROVINCES[study.province][0][0]}", updated,
                             question, kind=kind, url=url,
                             extra=" ".join(x for x in (via, whole) if x))))
        for code, why in sorted(got.get("withheld", {}).items()):
            skipped.append(f"{provinces[code]['name']}: {why} (study {study.number})")
        pdfs = dict(study.pdfs)
        for code, prov in sorted(got.get("provinces", {}).items()):
            shape = provinces[code]
            if shape["parent"] != unit["id"]:
                raise SystemExit(f"spain_cis: {shape['name']} is not drawn inside {unit['name']}")
            if prov["n"] < MIN_N:
                skipped.append(f"{shape['name']}: {prov['n']} respondents (study {study.number})")
                continue
            from_pdf = prov.get("pdf") or study in PROVINCE_PDFS
            extra = ""
            if prov.get("via"):
                extra = (f"Read from the CIS's PDF marginals for the province: {prov['via']}, "
                         f"so the workbook's sheet is not used.")
            elif study in PROVINCE_PDFS and not study.comunidad:
                extra = ("The CIS's newer surveys of the comunidad publish it as a whole only; "
                         "this is its newest by province.")
            records.append(record(
                f"ESP-CIS{study.number}-{code}", shape["name"], level="admin2",
                parent="ESP", country="ESP", match_by="shape_id", shape_id=shape["id"],
                codes={"ine_province": code, "cis_study": study.number, "cis_n": prov["n"]},
                **fields(study, design, prov["name"], prov["n"], prov["shares"],
                         f"the province of {prov['name']}", updated,
                         prov.get("question") or question,
                         kind=("province-pdf" if study in PROVINCE_PDFS else "province"),
                         url=pdfs.get(code) if from_pdf else None, extra=extra)))
    ids = [r["shape_id"] for r in records]
    if len(ids) != len(set(ids)):
        raise SystemExit("spain_cis: a polygon was written twice")
    return records, skipped


def fetch_text(url: str) -> str:
    raw = http_get(url, binary=True, cache=False, timeout=180)
    assert isinstance(raw, bytes)
    if raw[:4] != b"%PDF":
        raise SystemExit(f"spain_cis: {url} is not a PDF: {raw[:80]!r}")
    return pdf_text(raw)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    admin1, admin2 = load_units()
    provinces, comunidades = bind(admin1, admin2)
    log(f"  bound {len(provinces)} provinces and {len(comunidades)} comunidades by code")

    results: list[tuple[Study, dict[str, Any]]] = []
    for study in WORKBOOKS:
        raw = http_get(study.url, binary=True, cache=False, timeout=180)
        assert isinstance(raw, bytes)
        got = read_workbook(raw, study, {key: fetch_text(url) for key, url in study.pdfs})
        log(f"  study {study.number}: {len(got['provinces'])} provinces, "
            f"{got['region']['n']:,} respondents, fieldwork {got['design']['fieldwork']}")
        results.append((study, got))
    for study in TOTALS:
        assert study.ficha
        page = http_get(study.url, cache=False, timeout=180)
        assert isinstance(page, str)
        shares, n, question = read_html_total(page, study)
        design = ficha(fetch_text(study.ficha), f"study {study.number}")
        if n != design["realised"]:
            raise SystemExit(f"spain_cis: study {study.number}: {n:,} answered the religion "
                             f"question of {design['realised']:,} interviewed")
        log(f"  study {study.number}: {n:,} respondents, fieldwork {design['fieldwork']}")
        results.append((study, {"design": design,
                                "region": {"shares": shares, "n": n, "question": question}}))
    for study in PROVINCE_PDFS:
        assert study.ficha
        got = read_pdf_study(fetch_text(study.url), fetch_text(study.ficha),
                             {code: fetch_text(url) for code, url in study.pdfs}, study)
        log(f"  study {study.number}: {len(got['provinces'])} provinces, "
            f"{got['region']['n']:,} respondents, fieldwork {got['design']['fieldwork']}")
        results.append((study, got))
    fichas: dict[str, str] = {}
    for study in ARCHIVED:
        assert study.ficha
        if study.ficha not in fichas:
            fichas[study.ficha] = fetch_text(study.ficha)
        got = read_archived(fetch_text(study.url), fichas[study.ficha], study)
        log(f"  study {study.number} {COMUNIDADES[study.ccaa][0]}: {got['region']['n']:,} "
            f"respondents, fieldwork {got['design']['fieldwork']}, captured {got['archived']}")
        results.append((study, got))

    records, skipped = build(results, provinces, comunidades)
    for r in records:
        log(f"  {r['level']} {r['name']} (n={r['codes']['cis_n']:,}, {r['religion_year']}): "
            + ", ".join(f"{g['group']} {g['pct']}" for g in r["religion"]))
    for line in skipped:
        log(f"  left out: {line}")
    write_json(Path(args.out) if args.out else PROCESSED / OUT, records)
    log(f"  {len(records)} records: "
        f"{sum(r['level'] == 'admin1' for r in records)} comunidades, "
        f"{sum(r['level'] == 'admin2' for r in records)} provinces")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
