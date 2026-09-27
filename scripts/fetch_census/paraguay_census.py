#!/usr/bin/env python3
"""Paraguay's 2022 census by department and district, from INE's REDATAM bases.

INE Paraguay publishes the Censo Nacional de Población y Viviendas 2022 for
on-line tabulation as the REDATAM base CPV2022 on CELADE's server
(prod.redatam.org/binpry), and the 2002 census as CPV2002. This sends each
question as a frequency table broken by district and reads the tables back.

What it writes, for the 18 departments and the districts the boundary file
draws:

* **Population, median age and sex ratio** (2022): everyone counted, by sex
  (P03) and single year of age (P04). The median is interpolated within the
  single year holding the middle person.
* **Language** (2022): "¿Qué idiomas o lenguas habla?", several answers
  allowed -- Guaraní, Spanish, Portuguese, German, English, French, another
  indigenous language, another language, or none. Each share is the
  percentage of the people who named at least one language, so the shares
  add up to more than 100, as Poland's and New Zealand's do. The note counts
  who is left out: answers not recorded, people who speak no language, and
  people with no language item at all (children under five, mostly, and
  those counted by the Indigenous Census, whose answers are not in these
  items).
* **Ethnicity** (2022): PERINDI, whether a person was counted as indigenous
  -- 140,049 people, the IV Censo Nacional Indígena taken alongside the
  national census. Districts carry indigenous against everyone else.
  Departments carry the peoples, from the Indigenous Census's Cuadro A2
  (population by department, linguistic family and people), which counts
  136,302 indigenous people in its communities; the 3,747 PERINDI counts
  beyond it are one line, "Indigenous (people not published)". Every
  department's A2 peoples must fit inside its PERINDI count.
* **Religion** (2002): P17, the religion professed by everyone aged 10 and
  over, for departments and for the districts drawn as they were in 2002.
  The 2002 census is the last to ask it: the 2012 questionnaire has no
  religion question (its only "religiosa" is a kind of collective dwelling)
  and the 2022 base carries no religion variable. Twenty-two drawn districts
  were created after 2002 (SINCE_2002, each with its law), and they and the
  21 districts they were carved from carry a stated gap: no 2002 count is
  any of those polygons. Each department's districts must make its table,
  answer by answer.

**Districts drawn before they were split.** The boundary file draws 245
districts as they were about 2012; the 2022 census counts 263. A district
carved since from one drawn district is added back into it, and the note
says so (the creating law is cited for each). Where a new district was
carved from two or three drawn districts -- San José del Rosario, Cerro
Corá, Yby Pytã, Laurel -- no 2022 count is any one of those polygons, and
they carry a stated gap instead. The boundary file also draws Amambay's
Bella Vista and Itapúa's Bella Vista as one polygon, and two slivers of San
Juan del Paraná as polygons of their own; those carry the reason too.

Every table is checked: each district's categories and "No Aplica" make its
population; every language item's "No especificado" is the same count;
the districts make INE's published 6,109,903; and A2's peoples make its
families, departments and total.

Usage:
    python -m scripts.fetch_census.paraguay_census --probe districts
    python -m scripts.fetch_census.paraguay_census
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
from collections import Counter
from typing import Any

from scripts.probe_redatam import Session, report

from ._shared import PROCESSED, gap, http_get, log, measure, record, shares, write_json
from .binding import bind, fold
from .redatam import Server, median_age, tables

CMDSET = "https://prod.redatam.org/binpry/RpWebStats.exe/CmdSet"
PORTAL = "https://prod.redatam.org/binpry/RpWebEngine.exe/Portal?BASE={base}&lang=esp"
BASE = "CPV2022"
BASE_2002 = "CPV2002"
OUT = PROCESSED / "paraguay_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
YEAR = 2022
YEAR_2002 = 2002
NATIONAL = 6_109_903
NATIONAL_2002 = 5_163_198
PEOPLES_URL = "https://www.datos.gov.py/sites/default/files/Cuadro%20A2..csv"
SOURCE = ("INE Paraguay, Censo Nacional de Población y Viviendas 2022, tabulated on "
          "INE's REDATAM base CPV2022")
SOURCE_2002 = ("INE Paraguay (then DGEEC), Censo Nacional de Población y Viviendas 2002, "
               "tabulated on INE's REDATAM base CPV2002")
SOURCE_PEOPLES = ("INE Paraguay, IV Censo Nacional Indígena de Población y Viviendas 2022, "
                  "Cuadro A2: población indígena por departamento, según familia lingüística "
                  "y pueblo")
PAGE = "https://prod.redatam.org/binpry/RpWebEngine.exe/Portal?BASE=CPV2022"
PAGE_2002 = "https://prod.redatam.org/binpry/RpWebEngine.exe/Portal?BASE=CPV2002"

SEXES = {"hombre": "men", "mujer": "women"}
INDIGENOUS = {"indigena": "Indigenous", "resto": "Not indigenous"}
# Each language item is its own variable: its one category is the language,
# the other "No especificado". (item, INE's category, the map's label)
LANGUAGES = [
    ("P1601", "Guaraní", "Paraguayan Guaraní"),
    ("P1602", "Castellano", "Spanish"),
    ("P1604", "Portugués", "Portuguese"),
    ("P1605", "Alemán", "German"),
    ("P1606", "Inglés", "English"),
    ("P1607", "Francés", "French"),
    ("P1608", "Otra lengua indigena especificar", "Other indigenous language"),
    ("P1609", "Otro idioma No indigena especificar", "Other language"),
]
SPEAKS_NONE = ("P1698", "No habla")
UNSPECIFIED = "No especificado"
# Whether a person has any answer to the language question: 1 names a
# language, 2 speaks none, 9 not recorded, 0 no item at all. Each item is
# tested on its own line, because a comparison with an item that does not
# apply to the person is no answer, and an OR of several fails with it.
HABLA = """DEFINE PERSONA.HABLA
    AS SWITCH
    INCASE PERSONA.P1601 = 99
        ASSIGN 9
""" + "".join(f"""    INCASE PERSONA.{item} = {code}
        ASSIGN 1
""" for item, code in (("P1601", 1), ("P1602", 2), ("P1604", 4), ("P1605", 5), ("P1606", 6),
                       ("P1607", 7), ("P1608", 8), ("P1609", 9))) + """    INCASE PERSONA.P1698 = 98
        ASSIGN 2
    DEFAULT 0
    TYPE INTEGER
    RANGE 0-9
"""

# INE's two-digit department code -> the department's name as it is written,
# and the map's first-level unit.
NAMES = {
    "00": "Asunción", "01": "Concepción", "02": "San Pedro", "03": "Cordillera",
    "04": "Guairá", "05": "Caaguazú", "06": "Caazapá", "07": "Itapúa", "08": "Misiones",
    "09": "Paraguarí", "10": "Alto Paraná", "11": "Central", "12": "Ñeembucú",
    "13": "Amambay", "14": "Canindeyú", "15": "Presidente Hayes", "16": "Boquerón",
    "17": "Alto Paraguay",
}
DEPARTMENTS = {
    "00": "ASUNCION", "01": "CONCEPCION", "02": "SAN PEDRO", "03": "CORDILLERA",
    "04": "GUAIRA", "05": "CAAGUAZU", "06": "CAAZAPA", "07": "ITAPUA", "08": "MISIONES",
    "09": "PARAGUARI", "10": "ALTO PARANA", "11": "CENTRAL", "12": "ÑEEMBUCU",
    "13": "AMAMBAY", "14": "CANINDEYU", "15": "PRESIDENTE HAYES", "16": "BOQUERON",
    "17": "ALTO PARAGUAY",
}

# A district created since the boundary file was drawn, from one drawn
# district -> (that district, the law that created it). The laws are the
# Congress's (bacn.gov.py); each desafecta the new district's territory from
# the one named, and nothing else.
SPLITS = {
    "0110": ("0101", "San Alfredo, created by Ley 4927 of 2013 from Concepción"),
    "0111": ("0101", "Paso Barreto, created by Ley 4926 of 2013 from Concepción"),
    "0113": ("0101", "Paso Horqueta, created by Ley 6518 of 2020 from San Alfredo and "
                     "Concepción"),
    "0114": ("0101", "Itacuá, created in 2021 from San Alfredo"),
    "0112": ("0103", "Arroyito, created by Ley 5742 of 2016 from Horqueta"),
    "0221": ("0214", "San Vicente Pancholo, created by Ley 5715 of 2016 from General "
                     "Francisco Isidoro Resquín"),
    "0918": ("0908", "María Antonia, created by Ley 5676 of 2016 from Mbuyapey"),
    "1305": ("1303", "Karapaí, created by Ley 5085 of 2013 from Capitán Bado"),
    "1415": ("1401", "Puerto Adela, created by Ley 6098 of 2018 from Salto del Guairá"),
    "1510": ("1507", "Campo Aceval, created by Ley 6554 of 2020 from Teniente 1° Manuel "
                     "Irala Fernández"),
    "1511": ("1504", "Nueva Asunción, created by Ley 6731 of 2021 from Villa Hayes"),
    "1606": ("1602", "Boquerón, created by Ley 6688 of 2021 from Mariscal José Félix "
                     "Estigarribia"),
}
# Districts created since from two or more drawn districts: (the drawn
# districts, the new ones, the map's polygons they are, why). No 2022 count is
# any one of these polygons.
TANGLES = [
    (("0204", "0213"), ("0222",),
     (("SAN PEDRO", "General Elizardo Aquino"), ("SAN PEDRO", "Villa Del Rosario")),
     "San José del Rosario was created by Ley 6674 of 2020 from both General Elizardo "
     "Aquino and Villa del Rosario"),
    (("1301", "1302", "0702"), ("1306",),
     (("AMAMBAY", "Pedro Juan Caballero"), ("AMAMBAY", "Bella Vista")),
     "Cerro Corá was created by Ley 6555 of 2020 from both Pedro Juan Caballero and "
     "Bella Vista (Amambay), and the boundary file draws Amambay's Bella Vista and "
     "Itapúa's Bella Vista as one polygon"),
    (("1402", "1403", "1404"), ("1413", "1414"),
     (("CANINDEYU", "Corpus Christi"), ("CANINDEYU", "Curuguaty"),
      ("CANINDEYU", "Villa Ygatimí")),
     "Yby Pytã was created by Ley 4894 of 2013 from Villa Ygatimí, Curuguaty and Corpus "
     "Christi, and Maracaná by Ley 5673 of 2016 from Curuguaty"),
    (("1410", "1412"), ("1416",),
     (("CANINDEYU", "Nueva Esperanza"), ("CANINDEYU", "Ybyrarobana")),
     "Laurel was created by Ley 6498 of 2020 from both Ybyrarobaná and Nueva Esperanza"),
]
# Two slivers the boundary file draws beside San Juan del Paraná's polygon.
SLIVERS = (("ITAPUA", "San Juan De Parana"), ("ITAPUA", "San Juan Delparana"))
# Drawn districts that did not exist at the 2002 census: (department, polygon)
# -> (the 2002 districts their ground was then counted in, the creating law).
# Each of those 2002 districts has lost ground since, so neither the new
# polygon nor theirs is any 2002 district, and both carry a stated gap.
SINCE_2002 = {
    ("ALTO PARAGUAY", "Bahia Negra"): (("1701",), "Ley 2563 of 2005, from Fuerte Olimpo"),
    ("ALTO PARAGUAY", "Carmelo Peralta"): (("1702",), "Ley 3471 of 2008, from Puerto Casado"),
    ("ALTO PARANA", "Dr. Raul Peña"): (("1014",), "Ley 4725 of 2012, from Naranjal"),
    ("ALTO PARANA", "Santa Fe Del Parana"): (("1005", "1017"),
                                             "Ley 2180 of 2003, from Hernandarias and Mbaracayú"),
    ("ALTO PARANA", "Tavapy"): (("1015",), "Ley 4322 of 2011, from Santa Rosa del Monday"),
    ("AMAMBAY", "Zanja Pyta"): (("1301",), "Ley 4417 of 2011, from Pedro Juan Caballero"),
    ("BOQUERON", "Filadelfia"): (("1602",), "Ley 2928 of 2006, from Mariscal Estigarribia"),
    ("BOQUERON", "Loma Plata"): (("1602",), "Ley 2927 of 2006, from Mariscal Estigarribia"),
    ("CAAGUAZU", "Nueva Toledo"): (("0514", "0516"),
                                   "Ley 4494 of 2011, from Raúl Arsenio Oviedo and Mariscal "
                                   "Francisco Solano López"),
    ("CAAGUAZU", "Tembiapora"): (("0514",), "Ley 3421 of 2008, from Raúl Arsenio Oviedo"),
    ("CAAZAPA", "3 De Mayo"): (("0610",), "Ley 4604 of 2012, from Yuty"),
    ("CANINDEYU", "Yasy Kañy"): (("1403",), "Ley 2005 of 2002, from Curuguaty"),
    ("CANINDEYU", "Ybyrarobana"): (("1402", "1403"),
                                   "Ley 4571 of 2011, from Corpus Christi and Curuguaty"),
    ("CONCEPCION", "Azotey"): (("0103",), "Ley 3960 of 2009, from Horqueta"),
    ("CONCEPCION", "San Carlos"): (("0101",), "Ley 3516 of 2008, from Concepción"),
    ("CONCEPCION", "Sgto. Jose Felix Lopez"): (("0101",), "Ley 4418 of 2011, from Concepción"),
    ("GUAIRA", "Tebicuary"): (("0404",), "Ley 3469 of 2008, from Coronel Martínez"),
    ("PRESIDENTE HAYES", "General Jose Maria Bruguez"): (("1504",),
                                                         "Ley 3514 of 2008, from Villa Hayes"),
    ("PRESIDENTE HAYES", "Tte 1Ro Manuel Irala Fernandez"): (("1504",),
                                                             "Ley 2873 of 2006, from Villa Hayes"),
    ("PRESIDENTE HAYES", "Tte. Esteban Martinez"): (("1504",), "Ley 3000 of 2006, from Villa Hayes"),
    ("SAN PEDRO", "Liberacion"): (("0203", "0216"), "Ley 4363 of 2011, from Choré and Guajayvi"),
    ("SAN PEDRO", "Yryvu Cua"): (("0208", "0217"),
                                 "Ley 1989 of 2002, from San Estanislao and Capiibary"),
}
# The two Bella Vistas, which the boundary file draws as one polygon.
BELLA_VISTA_2002 = ("0702", "1302")
# 2002's district names -> the boundary file's, beyond ALIASES.
ALIASES_2002 = {
    "GENERAL ISIDORO RESQUIN": "General Resquin", "DR. BOTRELL": "Dr. Bottrell",
    "DR. CECILIO BAEZ": "Cecilio Baez", "TEBICUARYMI": "Tebicuary-Mi", "YBYCUI": "Yvycui",
    "YBYTYMI": "Yvytimi", "JUAN LEON MALLORQUIN": "Dr. Juan Leon Mallorquin",
    "JUAN E OLEARY": "Juan E. O´Leary", "NACUNDAY": "Ñacunday",
    "GRAL. JOSE EDUVIGIS DIAZ": "General Diaz", "LAURELES": "Los Laureles",
    "SAN JUAN BAUTISTA DEL ÑEEMBUCU": "San Juan Bautista De Ñeembucu",
    "SALTO DEL GUAIRA": "Saltos Del Guaira", "YGATIMI": "Villa Ygatimí", "YPEHU": "Ype Jhu",
    "PTO. PINASCO": "Puerto Pinasco", "YBY YA'U": "Yvy Ya´U",
    "SAN PEDRO DEL YCUAMANDIYU": "San Pedro Del Ykuamandiyu",
    "GRAL. HIGINIO MORINIGO": "General Higinio Morinigo",
    "DR. J. EULOGIO ESTIGARRIBIA": "J Eulogio Estigarribia",
    "J. AUGUSTO SALDIVAR": "J Augusto Saldivar", "GUAYAIBI": "Guajayvi",
    "MARISCAL FRANCISCO SOLANO LOPEZ": "Mcal. Francisco Solano Lopez",
    "MCAL. JOSE F. ESTIGARRIBIA": "Mariscal Estigarribia",
    # The district of Puerto Casado was La Victoria until it took the town's name.
    "LA VICTORIA": "Puerto Casado",
}
# INE's district names -> the boundary file's, where they differ by more than
# accents and case.
ALIASES = {
    "YBY YAÚ": "Yvy Ya´U", "SAN CARLOS DEL APA": "San Carlos",
    "SARGENTO JOSÉ FÉLIX LÓPEZ": "Sgto. Jose Felix Lopez",
    "SAN PEDRO DEL YCUAMANDYYÚ": "San Pedro Del Ykuamandiyu",
    "GENERAL FRANCISCO ISIDORO RESQUÍN": "General Resquin", "YRYBUCUA": "Yryvu Cua",
    "CAPITÁN MAURICIO JOSÉ TROCHE": "Mauricio Jose Troche",
    "GRAL. EUGENIO A. GARAY": "General Eugenio A. Garay",
    "INDEPENDENCIA": "Colonia Independencia", "DOCTOR BOTTRELL": "Dr. Bottrell",
    "DR. CECILIO BÁEZ": "Cecilio Baez", "DR. J. EULOGIO ESTIGARRIBIA": "J Eulogio Estigarribia",
    "MARISCAL FRANCISCO SOLANO LÓPEZ": "Mcal. Francisco Solano Lopez",
    "DR. MOISÉS S. BERTONI": "Moises Bertoni",
    "GRAL. HIGINIO MORINIGO": "General Higinio Morinigo", "YEGROS": "Fulgencio Yegros",
    "JOSÉ LEANDRO OVIEDO": "Leandro Oviedo", "MAYOR JULIO DIONISIO OTAÑO": "Mayor Otaño",
    "SAN JUAN BAUTISTA DE LAS MISIONES": "San Juan Bautista",
    "CABALLERO": "General Bernardino Caballero",
    "ROQUE GONZALEZ DE SANTA CRUZ": "San Roque Gonzalez",
    "YBYCUÍ": "Yvycui", "YBYTYMÍ": "Yvytimi",
    "GRAL. JOSÉ EDUVIGIS DÍAZ": "General Diaz", "LAURELES": "Los Laureles",
    "MAYOR JOSÉ DEJESÚS MARTÍNEZ": "Mayor Martinez",
    "LA PALOMA DEL ESPÍRITU SANTO": "La Paloma", "YASY CAÑY": "Yasy Kañy",
    "SALTO DEL GUAIRÁ": "Saltos Del Guaira",
    "TTE. 1° MANUEL IRALA FERNÁNDEZ": "Tte 1Ro Manuel Irala Fernandez",
    "TENIENTE ESTEBAN MARTÍNEZ": "Tte. Esteban Martinez",
    "MARISCAL JOSÉ FÉLIX ESTIGARRIBIA": "Mariscal Estigarribia",
}

# The Indigenous Census's peoples, as Cuadro A2 prints them, and the map's
# names. A family row ("Familia Guarani") is a subtotal and is checked, not
# kept; a row not here stops the run.
PEOPLES = {
    "Ache": "Aché", "Ava Guarani": "Avá Guaraní", "Mbya Guarani": "Mbyá Guaraní",
    "Pai Tavytera": "Paĩ Tavyterã", "Guarani Occidental/Pueblo Guarani": "Guaraní Occidental",
    "Guarani Nandeva": "Guaraní Ñandeva", "Pueblo Enlhet Norte": "Enlhet Norte",
    "Pueblo Enxet Sur": "Enxet Sur", "Pueblo Sanapana": "Sanapaná",
    "Pueblo Angaite": "Angaité", "Guana": "Guaná (Paraguay)",
    "Toba Maskoy/Toba Enenlhet": "Toba Maskoy", "Nivacle": "Nivaclé",
    # Written with the country: the patterns read a bare Maká as Cameroon's Makaa.
    "Maka": "Maká (Paraguay)", "Manjui": "Manjui", "Ayoreo": "Ayoreo",
    "Ybytoso": "Ybytoso", "Tomaraho": "Tomárãho", "Qom": "Qom",
}
UNPUBLISHED = "Indigenous (people not published)"
NOT_INDIGENOUS = "Not indigenous"

# The 2002 religion categories, in English. Protestant churches are one line
# but for the Mennonites and Lutherans, the two the country's German-speaking
# colonies made large; every "indigenous religion + church" answer is filed
# with the indigenous religion, and the note counts them.
RELIGION = {
    "Católica": "Catholic", "Sin religión": "No religion",
    "Religión indígena": "Indigenous religion",
    "Ortodoxa": "Orthodox", "Rusa": "Orthodox", "Otras - Ortodoxa": "Orthodox",
    "Mennonita": "Mennonite", "Luterana": "Lutheran",
    "Alianza Cristiana y Misionera": "Protestant", "Anglicana": "Protestant",
    "Asamblea de Dios": "Protestant", "Bautista. Bautista Maranata": "Protestant",
    "Centro Fam. de Adoración. Aposent": "Protestant", "Comunidad Cristiana": "Protestant",
    "Hermanos Libres": "Protestant", "Independientes": "Protestant",
    "Iglesia de Dios": "Protestant", "Iglesia de Dios de la Profecía": "Protestant",
    "Metodista": "Protestant", "Metodista Libre": "Protestant", "Nazarena": "Protestant",
    "Neotestamentaria": "Protestant", "Pentecostal": "Protestant",
    "Presbiteriana": "Protestant", "Otras - Evangélica": "Protestant",
    "Dios es amor": "Protestant", "Iglesia Universal - Pare de Sufri": "Protestant",
    "Adventista": "Seventh-day Adventist", "Mormones": "Latter-day Saints",
    "Testigos de Jehova": "Jehovah's Witnesses",
    "Pueblo de Dios": "Other Christian", "Monte de Sión": "Other Christian",
    "Otros grupos Pseudo-Cristianos": "Other Christian",
    "Judaismo": "Judaism", "Islamica - Musulmana": "Islam", "Hinduismo(Tao)": "Hinduism",
    "Budismo": "Buddhism", "Reyukai": "Buddhism", "Sintoismo": "Shinto",
    "Fe Bahía": "Baha'i",
    "Espiritualistas - E.C.Basilio": "Spiritism and Afro-Brazilian religions",
    "Otras, Espiritismo": "Spiritism and Afro-Brazilian religions",
    "Umbanda": "Spiritism and Afro-Brazilian religions",
    "Iglesia de la Unificación - Moon": "Other religion", "Rosacruces": "Other religion",
    "Mentalistas(Meditación Transcende": "Other religion",
    "Relig. no incluidas en las anteri": "Other religion",
    "Otra religión No Especificada": "Other religion",
}
DUAL = re.compile(r"^Indígena \+ ")
RELIGION_UNSTATED = "No especificado"

PROBES = {
    "districts": (BASE, """RUNDEF Job
    SELECTION ALL

TABLE T1
    AS FREQUENCY
    OF PERSONA.P03
    AREABREAK DISTRITO
"""),
    "ages": (BASE, """RUNDEF Job
    SELECTION ALL

TABLE T1
    AS FREQUENCY
    OF PERSONA.P04
"""),
    "language": (BASE, "RUNDEF Job\n    SELECTION ALL\n\n" + HABLA + """
TABLE T1
    AS CROSSTABS
    OF PERSONA.GEDAD80 BY PERSONA.HABLA

TABLE T2
    AS CROSSTABS
    OF PERSONA.PERINDI BY PERSONA.HABLA
"""),
    "religion02": (BASE_2002, """RUNDEF Job
    SELECTION ALL

TABLE T1
    AS FREQUENCY
    OF PERSONA.P17
    AREABREAK DEPTO
"""),
}


def number(text: str) -> int:
    """A count as INE's CSV prints it: dots between thousands, a dash for none."""
    text = (text or "").strip()
    if text in ("", "-"):
        return 0
    digits = text.replace(".", "")
    if not digits.isdigit():
        raise SystemExit(f"paraguay_census: {text!r} is not a count")
    return int(digits)


def department_named(name: str) -> str:
    """The map's department for a name as Cuadro A2 writes it ('Alto Parana ')."""
    match = [d for d in DEPARTMENTS.values() if fold(d) == fold(name)]
    if len(match) != 1:
        raise SystemExit(f"paraguay_census: {name!r} is no department")
    return match[0]


def peoples_table(text: str) -> dict[str, Counter]:
    """{map department name: people -> count} from Cuadro A2, after its checks.

    The table's rows are the country's total, then each linguistic family
    followed by its peoples, then "No indigena" (people living in the
    communities who are not indigenous). The columns are the total and one per
    department that has any.
    """
    text = text.lstrip("﻿")
    first = text.split("\n", 1)[0]
    # datos.gov.py writes this file with semicolons between the columns.
    delimiter = ";" if first.count(";") > first.count(",") else ","
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delimiter)
            if any(c.strip() for c in r)]
    head = [c.strip() for c in rows[0]]
    if not head[0].startswith("Familia") or head[1] != "Total":
        raise SystemExit(f"paraguay_census: Cuadro A2's header is {head[:3]}")
    columns = [department_named(c) for c in head[2:]]
    by_dept: dict[str, Counter] = {d: Counter() for d in columns}
    national = outside = None
    families: list[list[Any]] = []          # [label, printed, summed]
    kept = [0] * (len(columns) + 1)
    for row in rows[1:]:
        label = row[0].strip()
        values = [number(c) for c in row[1:len(columns) + 2]]
        if sum(values[1:]) != values[0]:
            raise SystemExit(f"paraguay_census: Cuadro A2's {label!r} row does not make its "
                             "total across departments")
        if label.startswith("Total"):
            national = values
        elif label.startswith("Familia"):
            families.append([label, values, [0] * len(values)])
        elif label == "No indigena":
            outside = values
        elif not label:
            if values != outside:
                raise SystemExit("paraguay_census: Cuadro A2 has an unnamed row that is not "
                                 "a copy of 'No indigena'")
        else:
            if label not in PEOPLES:
                raise SystemExit(f"paraguay_census: Cuadro A2's people {label!r} is not in "
                                 "PEOPLES")
            if not families:
                raise SystemExit(f"paraguay_census: {label!r} comes before any family")
            families[-1][2] = [a + b for a, b in zip(families[-1][2], values)]
            kept = [a + b for a, b in zip(kept, values)]
            for dept, value in zip(columns, values[1:]):
                if value:
                    by_dept[dept][PEOPLES[label]] += value
    for label, printed, total in families:
        if printed != total:
            raise SystemExit(f"paraguay_census: Cuadro A2's peoples do not make {label}")
    if national is None or outside is None:
        raise SystemExit("paraguay_census: Cuadro A2 has no total or no 'No indigena' row")
    if [a + b for a, b in zip(kept, outside)] != national:
        raise SystemExit("paraguay_census: Cuadro A2's peoples and 'No indigena' do not make "
                         "its total")
    return by_dept


def peoples_text() -> str:
    """Cuadro A2 from datos.gov.py, or the Internet Archive's copy of the same file.

    datos.gov.py timed out four times running on one run that had answered a
    probe an hour before; the Archive's raw capture (``id_``) is the same
    official file, and the log says which was read.
    """
    for url in (PEOPLES_URL, f"https://web.archive.org/web/2025id_/{PEOPLES_URL}"):
        try:
            text = http_get(url, cache=False)
        except Exception as exc:                       # noqa: BLE001 -- the next source
            log(f"  {url}: {type(exc).__name__}: {exc}")
            continue
        log(f"  Cuadro A2 read from {url}")
        return text
    raise SystemExit("paraguay_census: Cuadro A2 is reachable neither at datos.gov.py nor in "
                     "the Internet Archive")


def age_of(label: str) -> int:
    """A single year of age from its category label."""
    if re.match(r"(?i)menos|menor", label):
        return 0
    found = re.search(r"\d+", label)
    if found:
        return int(found.group())
    raise SystemExit(f"paraguay_census: an age label with no number: {label!r}")


def by_key(rows: list[tuple[str, int]], names: dict[str, str], what: str) -> Counter:
    """Counts keyed by the map's label, refusing a category not in ``names``."""
    out: Counter = Counter()
    for label, n in rows:
        key = names.get(fold(label))
        if key is None:
            raise SystemExit(f"paraguay_census: {what}: a category this file does not know: "
                             f"{label!r}")
        out[key] += n
    return out


def district_tables(found: list[dict], what: str) -> dict[str, dict]:
    """{district code: table}, and the whole base's table checked against their sum."""
    whole = [t for t in found if not t["area"]]
    out = {}
    for table in found:
        code = table["area"]
        if not code:
            continue
        if not re.fullmatch(r"\d{4}", code) or code in out:
            raise SystemExit(f"paraguay_census: {what}: {code!r} is not one district code")
        out[code] = table
    if len(whole) != 1 or whole[0]["total"] != sum(t["total"] for t in out.values()):
        raise SystemExit(f"paraguay_census: {what}: the whole base's table is not the "
                         "districts' sum")
    return out


def district_counts(by_question: dict[str, dict[str, dict]]) -> dict[str, dict[str, Any]]:
    """District code -> its names and counts, every table checked against its population."""
    units: dict[str, dict[str, Any]] = {}
    for code, table in by_question["sex"].items():
        sexes = by_key(table["rows"], SEXES, "sex")
        people = table["total"]
        if sum(sexes.values()) != people or table["na"]:
            raise SystemExit(f"paraguay_census: {code}'s sexes do not make its population")
        units[code] = {"name": table["name"], "people": people, "sex": sexes}
    for question in by_question:
        if set(by_question[question]) != set(units):
            raise SystemExit(f"paraguay_census: {question}: districts "
                             f"{sorted(set(by_question[question]) ^ set(units))} are in one "
                             "table and not the other")
    for code, unit in units.items():
        people = unit["people"]
        ages: Counter = Counter()
        for label, n in by_question["age"][code]["rows"]:
            ages[age_of(label)] += n
        if sum(ages.values()) != people:
            raise SystemExit(f"paraguay_census: {unit['name']}'s ages make {sum(ages.values())}, "
                             f"not {people}")
        unit["ages"] = ages
        indigenous = by_key(by_question["indigenous"][code]["rows"], INDIGENOUS, "PERINDI")
        if sum(indigenous.values()) != people:
            raise SystemExit(f"paraguay_census: {unit['name']}'s PERINDI does not make it")
        unit["indigenous"] = indigenous
        habla = Counter({int(label): n for label, n in by_question["habla"][code]["rows"]})
        if sum(habla.values()) != people or set(habla) - {0, 1, 2, 9}:
            raise SystemExit(f"paraguay_census: {unit['name']}'s HABLA is {dict(habla)} of "
                             f"{people}")
        unit["habla"] = habla
        spoken: Counter = Counter()
        for item, category, label in LANGUAGES + [(SPEAKS_NONE[0], SPEAKS_NONE[1], "none")]:
            table = by_question[item][code]
            rows = {fold(k): v for k, v in table["rows"]}
            unknown = set(rows) - {fold(category), fold(UNSPECIFIED)}
            if unknown:
                raise SystemExit(f"paraguay_census: {item}: categories {unknown}")
            if table["total"] + (table["na"] or 0) != people:
                raise SystemExit(f"paraguay_census: {item}: {unit['name']} has {table['total']} "
                                 f"and {table['na']} not applicable against {people}")
            if rows.get(fold(UNSPECIFIED), 0) != habla[9]:
                raise SystemExit(f"paraguay_census: {item}: {unit['name']}'s unrecorded "
                                 "answers differ from the other items'")
            spoken[label] = rows.get(fold(category), 0)
        # "Speaks no language" is HABLA 2, those who said so and named none: a
        # few said so and named one too (59 in the country), and they are
        # counted with the languages they named.
        if spoken["none"] < habla[2] or any(spoken[l] > habla[1] for _, _, l in LANGUAGES):
            raise SystemExit(f"paraguay_census: {unit['name']}'s languages do not fit its "
                             "respondents")
        unit["spoken"] = spoken
    national = sum(u["people"] for u in units.values())
    if national != NATIONAL:
        raise SystemExit(f"paraguay_census: {len(units)} districts make {national:,}; INE "
                         f"published {NATIONAL:,}")
    log(f"  {len(units)} districts making INE's {NATIONAL:,}; every question's categories "
        "and 'No Aplica' making each district")
    return units


def summed(parts: list[dict[str, Any]]) -> dict[str, Any]:
    """Several districts' counts added into one unit's."""
    out: dict[str, Any] = {"people": sum(p["people"] for p in parts),
                           "name": parts[0]["name"], "parts": [p["name"] for p in parts]}
    for key in ("sex", "ages", "indigenous", "habla", "spoken"):
        total: Counter = Counter()
        for part in parts:
            total.update(part[key])
        out[key] = total
    return out


def title(name: str) -> str:
    """INE's capitals, as a name is written: 'SAN JUAN DEL PARANÁ' -> 'San Juan del Paraná'."""
    small = {"de", "del", "la", "las", "los", "y"}
    words = name.lower().split()
    return " ".join(w if i and w in small else w[:1].upper() + w[1:]
                    for i, w in enumerate(words))


def language_fields(unit: dict[str, Any], where: str) -> dict[str, Any]:
    habla, spoken = unit["habla"], unit["spoken"]
    counts = {label: spoken[label] for _, _, label in LANGUAGES if spoken[label]}
    return {
        "language": shares(counts, total=habla[1]),
        "language_year": YEAR,
        "language_note": (
            "Which languages each person speaks, as the 2022 census asked (\"¿Qué idiomas o "
            "lenguas habla?\"), several answers allowed: each share is the percentage of the "
            f"{habla[1]:,} people {where} who named at least one language, so the shares add up "
            f"to more than 100. Left out: {habla[9]:,} whose answer was not recorded, "
            f"{habla[2]:,} who speak no language, and {habla[0]:,} with no language item at all "
            "-- most of them children under five, and people counted by the Indigenous "
            "Census, whose answers are not in these items."),
    }


def core_fields(unit: dict[str, Any]) -> dict[str, Any]:
    sexes = unit["sex"]
    return {
        "population": measure(unit["people"], year=YEAR, source=SOURCE),
        "median_age": measure(median_age(unit["ages"]), unit="years", year=YEAR, source=SOURCE),
        "median_age_note": (
            "Interpolated within the single year of age that holds the middle person, from "
            "the 2022 census's count of everyone by single year of age; INE tabulates the "
            "ages, not the median."),
        "sex_ratio": measure(round(1000 * sexes["men"] / sexes["women"]),
                             unit="males_per_1000_females", year=YEAR, source=SOURCE),
    }


def district_ethnicity(unit: dict[str, Any]) -> dict[str, Any]:
    ind = unit["indigenous"]
    return {
        "ethnicity": shares(dict(ind)),
        "ethnicity_year": YEAR,
        "ethnicity_note": (
            f"Whether each person was counted as indigenous: {ind['Indigenous']:,} of the "
            f"{unit['people']:,} people here, by the IV Censo Nacional Indígena taken alongside "
            "the 2022 census (140,049 people in all, each belonging to one of the country's 19 "
            "peoples). Everyone else the census counted is one line. Which people is "
            "published by department only."),
    }


def department_ethnicity(unit: dict[str, Any], peoples: Counter, name: str) -> dict[str, Any]:
    ind = unit["indigenous"]
    published = sum(peoples.values())
    rest = ind["Indigenous"] - published
    if rest < 0:
        raise SystemExit(f"paraguay_census: {name}: Cuadro A2 names {published:,} indigenous "
                         f"people, more than the {ind['Indigenous']:,} the census counts")
    counts = Counter(peoples)
    if rest:
        counts[UNPUBLISHED] = rest
    counts[NOT_INDIGENOUS] = ind["Not indigenous"]
    return {
        "ethnicity": shares(dict(counts)),
        "ethnicity_year": YEAR,
        "ethnicity_note": (
            f"The indigenous peoples of the {ind['Indigenous']:,} people here counted as "
            "indigenous by the IV Censo Nacional Indígena 2022, which was taken alongside the "
            f"national census. {published:,} of them are named by people in the Indigenous "
            "Census's Cuadro A2 (population by department and people); "
            + (f"the other {rest:,} are one line, their people not published by department. "
               if rest else "")
            + "Everyone else the census counted is one line."),
    }


def religion_fields(table: dict) -> dict[str, Any]:
    counts: Counter = Counter()
    dual = unstated = 0
    for label, n in table["rows"]:
        if label == RELIGION_UNSTATED:
            unstated += n
        elif DUAL.match(label):
            dual += n
            counts["Indigenous religion"] += n
        elif label in RELIGION:
            counts[RELIGION[label]] += n
        else:
            raise SystemExit(f"paraguay_census: 2002 religion: {label!r} is not in RELIGION")
    answered = sum(counts.values())
    return {
        "religion": shares(dict(counts)),
        "religion_year": YEAR_2002,
        "religion_note": (
            "The religion professed by everyone aged 10 and over, from the 2002 census -- the "
            "last Paraguayan census to ask it: the 2012 questionnaire has no religion question "
            "and the 2022 census's base carries no religion variable. "
            f"{answered:,} people of that age answered here; {unstated:,} gave no answer and are "
            "left out."
            + (f" {dual:,} named an indigenous religion together with a church and are counted "
               "with the indigenous religion." if dual else "")),
    }


def fetch(session: Session) -> tuple[dict[str, dict[str, dict]], list[dict], list[dict]]:
    """Every 2022 question by district; the 2002 religion and sex by department."""
    server = Server(CMDSET, BASE, session=session, who="paraguay_census")
    by_question: dict[str, dict[str, dict]] = {}
    for question, variable in [("sex", "P03"), ("age", "P04"), ("indigenous", "PERINDI")] + [
            (item, item) for item, _, _ in LANGUAGES] + [(SPEAKS_NONE[0], SPEAKS_NONE[0])]:
        found = server.frequency(f"PERSONA.{variable}", areabreak="DISTRITO")
        by_question[question] = district_tables(found, question)
        log(f"  {variable}: {len(by_question[question])} districts")
    program = ("RUNDEF Job\n    SELECTION ALL\n\n" + HABLA + "\nTABLE T1\n    AS FREQUENCY\n"
               "    OF PERSONA.HABLA\n    AREABREAK DISTRITO\n")
    by_question["habla"] = district_tables(
        [t for page in server.output(program) for t in tables(page)], "habla")
    session.get(PORTAL.format(base=BASE_2002))
    old = Server(CMDSET, BASE_2002, session=session, who="paraguay_census")
    religion = {level: old.frequency("PERSONA.P17", areabreak=level)
                for level in ("DEPTO", "DISTRITO")}
    sexes_2002 = {level: old.frequency("PERSONA.P03", areabreak=level)
                  for level in ("DEPTO", "DISTRITO")}
    return by_question, religion, sexes_2002


def religion_by_area(religion: list[dict], sexes: list[dict], width: int) -> dict[str, dict]:
    """{area code: its 2002 religion table}, each making its population.

    Every area's answers and its "No Aplica" (the under-tens) must make the
    people counted there, and the areas must make the 2002 census's
    5,163,198. ``width`` is the code's length: 2 for departments, 4 for
    districts.
    """
    people = {t["area"]: t["total"] for t in sexes if t["area"]}
    what = "departments" if width == 2 else "districts"
    if sum(people.values()) != NATIONAL_2002:
        raise SystemExit(f"paraguay_census: 2002's {what} make {sum(people.values()):,}, "
                         f"not {NATIONAL_2002:,}")
    out = {}
    for table in religion:
        code = table["area"]
        if not code:
            continue
        if (len(code) != width or code[:2] not in DEPARTMENTS
                or table["total"] + (table["na"] or 0) != people.get(code)):
            raise SystemExit(f"paraguay_census: 2002 religion: {code!r} has "
                             f"{table['total']} answers and {table['na']} not applicable "
                             f"against {people.get(code)}")
        if sum(n for _, n in table["rows"]) != table["total"]:
            raise SystemExit(f"paraguay_census: 2002 religion: {code}'s rows do not make it")
        out[code] = table
    if set(out) != set(people) or (width == 2 and set(out) != set(DEPARTMENTS)):
        raise SystemExit(f"paraguay_census: 2002 religion covers {sorted(set(out) ^ set(people))} "
                         "and the population table does not, or the other way round")
    return out


def religion_by_department(religion: list[dict], sexes: list[dict]) -> dict[str, dict]:
    return religion_by_area(religion, sexes, 2)


def rows_of(tables_: list[dict]) -> Counter:
    total: Counter = Counter()
    for table in tables_:
        for label, n in table["rows"]:
            total[label] += n
    return total


def districts_2002(religion: dict[str, dict], departments: dict[str, dict]) -> dict[str, dict]:
    """{2002 district: its religion table}, Asunción's six as one (code "0000").

    Each department's districts must make, answer by answer, INE's table for
    the department.
    """
    for code, table in departments.items():
        mine = [t for c, t in religion.items() if c[:2] == code]
        if rows_of(mine) != rows_of([table]):
            raise SystemExit(f"paraguay_census: 2002 religion: {NAMES[code]}'s districts do not "
                             "make its table")
    out = {c: t for c, t in religion.items() if c[:2] != "00"}
    capital = [t for c, t in religion.items() if c[:2] == "00"]
    out["0000"] = {"area": "0000", "name": "ASUNCION",
                   "rows": sorted(rows_of(capital).items()),
                   "total": sum(t["total"] for t in capital), "na": None,
                   "parts": [t["name"] for t in capital]}
    return out


def religion_gaps() -> tuple[dict[tuple[str, str], str], dict[str, str]]:
    """Why a polygon has no 2002 religion: ({(department, new polygon): why},
    {2002 district that has lost ground since: why})."""
    lost: dict[str, list[str]] = {}
    for (dept, polygon), (olds, law) in SINCE_2002.items():
        for code in olds:
            lost.setdefault(code, []).append(f"{polygon} ({law})")
    new = {(dept, polygon): (
        f"This district did not exist at the 2002 census, the last to ask religion: it was "
        f"created by {law}, and its people were counted as part of "
        f"{'the district' if len(olds) == 1 else 'the districts'} it came from.")
        for (dept, polygon), (olds, law) in SINCE_2002.items()}
    shrunk = {code: (
        "This district has lost ground since the 2002 census, the last to ask religion: "
        + "; ".join(news) + (" was" if len(news) == 1 else " were") + " carved from it. The 2002 "
        "count is of the larger district, so it is not this polygon's.")
        for code, news in lost.items()}
    return new, shrunk


def religion_by_polygon(districts: dict[str, dict], admin2: list[dict[str, Any]],
                        parents: dict[str, str]) -> dict[str, dict[str, Any]]:
    """{polygon id: its 2002 religion fields, or the gap that says why there are none}.

    Every 2002 district but the two Bella Vistas binds by name to one polygon
    of its own department, and every polygon not set aside is bound: a
    polygon left over, or a district, stops the run.
    """
    new, shrunk = religion_gaps()
    shape_of = {(parents[s["parent"]], s["name"]): s for s in admin2}
    missing = sorted(k for k in list(new) + list(SLIVERS) + [("AMAMBAY", "Bella Vista")]
                     if k not in shape_of)
    if missing:
        raise SystemExit(f"paraguay_census: 2002 religion: no polygon for {missing}")
    out: dict[str, dict[str, Any]] = {
        shape_of[key]["id"]: {"religion": gap("not_available", why)} for key, why in new.items()}
    for key in SLIVERS:
        out[shape_of[key]["id"]] = {"religion": gap(
            "not_available", "A sliver the boundary file draws beside San Juan del Paraná's own "
            "polygon, which carries the district's 2002 religion; the census counts no one here "
            "apart from the district.")}
    answered = " and ".join(f"{districts[c]['total']:,}" for c in BELLA_VISTA_2002)
    out[shape_of[("AMAMBAY", "Bella Vista")]["id"]] = {"religion": gap(
        "not_available", "The boundary file draws Itapúa's Bella Vista and Amambay's Bella Vista "
        f"as one polygon. The 2002 census counts them apart ({answered} people aged 10 and over "
        "answering), and neither district is this polygon.")}
    shapes = [s for s in admin2 if s["id"] not in out]
    wanted = {c: (t["name"], DEPARTMENTS[c[:2]]) for c, t in districts.items()
              if c not in BELLA_VISTA_2002}
    bound, unbound = bind(wanted, shapes, parents, {**ALIASES, **ALIASES_2002})
    if unbound:
        raise SystemExit(f"paraguay_census: 2002 districts with no polygon: {unbound}")
    empty = sorted(s["name"] for s in shapes if s["id"] not in set(bound.values()))
    if empty:
        raise SystemExit(f"paraguay_census: polygons with no 2002 district: {empty}")
    drawn = {s["id"]: s for s in admin2}
    for code, sid in bound.items():
        if parents[drawn[sid]["parent"]] != DEPARTMENTS[code[:2]]:
            raise SystemExit(f"paraguay_census: 2002's {wanted[code][0]} bound to "
                             f"{drawn[sid]['name']}, in another department")
        out[sid] = ({"religion": gap("not_available", shrunk[code])} if code in shrunk
                    else religion_fields(districts[code]))
    if set(shrunk) - set(bound):
        raise SystemExit(f"paraguay_census: 2002 districts {sorted(set(shrunk) - set(bound))} "
                         "lost ground and are not drawn")
    if len(out) != len(admin2):
        raise SystemExit("paraguay_census: 2002 religion: not every polygon is accounted for")
    log(f"  2002 religion: {len(bound) - len(set(shrunk))} district polygons filled; "
        f"{len(out) - len(bound) + len(set(shrunk))} with the reason they are not")
    return out


def unfilled(reason: str) -> dict[str, Any]:
    """The 2022 fields of a polygon no 2022 count is, each saying why.

    A gap never replaces a figure another source has for the polygon (OCHA's
    projections cover the tangled districts); it says why this source has none.
    """
    return {field: gap("not_available", reason)
            for field in ("population", "median_age", "sex_ratio", "ethnicity", "language")}


def drawn_groups(units: dict[str, Any]) -> dict[str, list[str]]:
    """The districts as drawn: {drawn district: the 2022 districts inside it}."""
    tangled = {code for olds, news, _, _ in TANGLES for code in olds + news}
    groups: dict[str, list[str]] = {}
    for code in sorted(units):
        if code in tangled:
            continue
        target, _ = SPLITS.get(code, (code, None))
        if target in tangled or target not in units:
            raise SystemExit(f"paraguay_census: {code} is split into {target}, which is not "
                             "drawn")
        groups.setdefault(target, []).append(code)
    return groups


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", choices=sorted(PROBES))
    ap.add_argument("--limit", type=int, default=20000)
    args = ap.parse_args()
    session = Session()
    if args.probe:
        base, program = PROBES[args.probe]
        session.get(PORTAL.format(base=base))
        server = Server(CMDSET, base, session=session, who="paraguay_census")
        for page in server.output(program):
            report(CMDSET, page, args.limit)
            for t in tables(page):
                print(f"  table: area={t['area']} name={t['name']!r} title={t['title']!r} "
                      f"total={t['total']} na={t['na']} rows={t['rows'][:30]}")
        return 0

    # The small table first, so an unreachable host fails the run before the
    # long tabulation rather than after it.
    peoples = peoples_table(peoples_text())
    session.get(PORTAL.format(base=BASE))
    by_question, religion_2002, sexes_2002 = fetch(session)
    units = district_counts(by_question)
    religion = religion_by_department(religion_2002["DEPTO"], sexes_2002["DEPTO"])
    districts_02 = districts_2002(
        religion_by_area(religion_2002["DISTRITO"], sexes_2002["DISTRITO"], 4), religion)

    admin1 = json.loads((SITE / "admin1" / "PRY.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "PRY.units.json").read_text())
    parents = {u["id"]: u["name"] for u in admin1}
    first = {u["name"]: u for u in admin1}
    if set(first) != set(DEPARTMENTS.values()):
        raise SystemExit(f"paraguay_census: the map's departments are {sorted(first)}")
    shape_of = {(parents[s["parent"]], s["name"]): s for s in admin2}

    groups = drawn_groups(units)
    set_aside = {pair for _, _, polys, _ in TANGLES for pair in polys} | set(SLIVERS)
    missing = sorted(p for p in set_aside if p not in shape_of)
    if missing:
        raise SystemExit(f"paraguay_census: no polygon for {missing}")
    shapes = [s for s in admin2 if (parents[s["parent"]], s["name"]) not in set_aside]
    districts = {code: (units[code]["name"], DEPARTMENTS[code[:2]]) for code in groups}
    bound, unbound = bind(districts, shapes, parents, ALIASES)
    log(f"  {len(bound)} of {len(groups)} districts bound; not: {unbound}")
    if unbound:
        raise SystemExit(f"paraguay_census: districts with no polygon: {unbound}")
    empty = sorted(s["name"] for s in shapes if s["id"] not in set(bound.values()))
    if empty:
        raise SystemExit(f"paraguay_census: polygons with no district: {empty}")
    religion_of = religion_by_polygon(districts_02, admin2, parents)

    records: list[dict[str, Any]] = []
    source_2022 = {"name": SOURCE, "url": PAGE, "year": YEAR}
    source_2002 = {"field": "religion", "name": SOURCE_2002, "url": PAGE_2002, "year": YEAR_2002}
    drawn = {s["id"]: s for s in admin2}
    for target, codes in sorted(groups.items()):
        unit = summed([units[c] for c in codes])
        shape = drawn[bound[target]]
        added = [SPLITS[c][1] for c in codes if c != target]
        name = title(units[target]["name"])
        fields = core_fields(unit)
        if added:
            fields["population"]["note"] = (
                "Includes " + "; ".join(added) + ": created since the boundary file was drawn, "
                "and inside this polygon.")
        records.append(record(
            f"PRY-INE-{target}", name, level="admin2", parent="PRY", country="PRY",
            parent_name=DEPARTMENTS[target[:2]], codes={"ine": target},
            match_by="shape_id", shape_id=shape["id"],
            aliases=[shape["name"]] if fold(shape["name"]) != fold(name) else [],
            **fields, **district_ethnicity(unit), **language_fields(unit, "here"),
            **religion_of[shape["id"]],
            sources=[{"field": "population/median age/sex ratio/ethnicity/language",
                      **source_2022}, source_2002]))
    for olds, news, polys, why in TANGLES:
        people = sum(units[c]["people"] for c in olds + news)
        names = ", ".join(title(units[c]["name"]) for c in olds + news)
        for dept, polygon in polys:
            shape = shape_of[(dept, polygon)]
            reason = (f"The boundary file draws this district as it was before {why}. The 2022 "
                      f"census counts {names} apart -- {people:,} people in all -- and no count "
                      "divides a new district between the ones it came from, so no 2022 figure "
                      "is this polygon's.")
            records.append(record(
                f"PRY-INE-{fold(dept)}-{fold(polygon)}", polygon, level="admin2", parent="PRY",
                country="PRY", parent_name=dept, match_by="shape_id", shape_id=shape["id"],
                **unfilled(reason), **religion_of[shape["id"]],
                sources=[{"field": "note", **source_2022}, source_2002]))
    for dept, polygon in SLIVERS:
        shape = shape_of[(dept, polygon)]
        reason = ("A sliver the boundary file draws beside San Juan del Paraná's own polygon, "
                  "which carries the district's 2022 figures; the census counts no one here "
                  "apart from the district.")
        records.append(record(
            f"PRY-INE-{fold(dept)}-{fold(polygon)}", polygon, level="admin2", parent="PRY",
            country="PRY", parent_name=dept, match_by="shape_id", shape_id=shape["id"],
            **unfilled(reason), **religion_of[shape["id"]],
            sources=[{"field": "note", **source_2022}, source_2002]))

    for code, dept in sorted(DEPARTMENTS.items()):
        unit = summed([u for c, u in units.items() if c[:2] == code])
        records.append(record(
            f"PRY-INE-{code}", NAMES[code], level="admin1", parent="PRY", country="PRY",
            codes={"ine": code}, match_by="shape_id", shape_id=first[dept]["id"],
            **core_fields(unit), **department_ethnicity(unit, peoples.get(dept, Counter()), dept),
            **language_fields(unit, "in the department"),
            **religion_fields(religion[code]),
            sources=[{"field": "population/median age/sex ratio/language", **source_2022},
                     {"field": "ethnicity", "name": f"{SOURCE}; {SOURCE_PEOPLES}",
                      "url": PEOPLES_URL, "year": YEAR},
                     {"field": "religion", "name": SOURCE_2002, "url": PAGE_2002,
                      "year": YEAR_2002}]))
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {sum(r['level'] == 'admin1' for r in records)} departments, "
        f"{sum(r['level'] == 'admin2' for r in records)} district polygons "
        f"({len(groups)} with figures)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
