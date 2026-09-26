"""Polygons a statistics office's code is pinned to, where matching by name fails.

Matching a row to a polygon by name within its parent is right almost always,
and where it fails the unit reads as empty. It fails in three ways this table
answers, each checked before a pin is written here:

* the boundary file files the polygon under a neighbouring first-level unit,
  so the name is refused as outside its parent (Brazil);
* the boundary file writes the unit under another name -- its full legal
  title, its seat's name, a misspelling -- that no row shares (Colombia);
* two units share a name within one parent, and only location separates them.

A pin is the strongest claim an adapter makes about a polygon (the build stops
on a pin to a polygon it does not draw), so each group says what established
it. Adapters that read the same office's codes share the table, so a pin fixed
for one source is fixed for every source keyed by those codes.
"""

from __future__ import annotations

from typing import Any

PINS: dict[str, dict[str, str]] = {
    # IBGE municipality codes. The boundary file draws these where they are
    # but files them under the next state -- Amparo (PB) under Pernambuco,
    # Tibau (RN) under Ceará, Águas de Lindóia (SP) under Minas Gerais -- so a
    # name match within the state refuses them. Fifteen are pinned because
    # GeoNames' seat for the IBGE code lies inside the polygon; Quixaba (PE) as
    # the one Quixaba polygon and row left once Quixaba (PB), whose seat is
    # 110 km away in the other, is placed.
    "BRA": {
        "2500734": "56859067B25087670535038",  # Amparo (PB)
        "2501005": "56859067B30270285588633",  # Araruna (PB)
        "2502003": "56859067B47597011454876",  # Belém do Brejo do Cruz (PB)
        "2502201": "56859067B58755230690339",  # Bom Jesus (PB)
        "2502300": "56859067B88877822125825",  # Bom Sucesso (PB)
        "2602506": "56859067B9303192166892",   # Brejinho (PE)
        "2512606": "56859067B6462044474109",   # Quixaba (PB)
        "2611533": "56859067B2724242969158",   # Quixaba (PE)
        "2612471": "56859067B75266900672705",  # Santa Cruz da Baixa Verde (PE)
        "2612802": "56859067B87497954327615",  # Santa Terezinha (PE)
        "2412500": "56859067B85156148538476",  # São Miguel (RN)
        "2613800": "56859067B99318407457286",  # São Vicente Férrer (PE)
        "2411056": "56859067B59166838740608",  # Tibau (RN)
        "2414704": "56859067B38668332786629",  # Várzea (RN)
        "2517100": "56859067B31592745893521",  # Várzea (PB)
        "3500501": "56859067B8082951902088",   # Águas de Lindóia (SP)
    },
    # DANE DIVIPOLA codes. Each polygon is the only one in its department the
    # name can be: the boundary file writes Barranquilla by its legal title
    # (truncated with an asterisk), Tiquisio as "Tiquiso", Chibolo as
    # "Chivolo", Santacruz (Nariño) by its seat Guachavés, Puerto Santander
    # (Amazonas) by its seat Araracuara, and the non-municipal areas (ANM) of
    # Amazonas, Guainía and Vaupés with their seats or "Cor. Departamental" in
    # the name. None of the seventeen reached a polygon by name.
    "COL": {
        "08001": "7082276B33268622823443",  # Barranquilla
        "13810": "7082276B69446027092984",  # Tiquisio ("Tiquiso")
        "23670": "7082276B77383139939829",  # San Andrés de Sotavento
        "47170": "7082276B43456063324941",  # Chibolo ("Chivolo")
        "52699": "7082276B62156244785095",  # Santacruz ("Santa Cruz (Guachavés)")
        "54553": "7082276B36155963658062",  # Puerto Santander (Norte de Santander)
        "70823": "7082276B69726867253152",  # San José de Toluviejo ("Tolú Viejo")
        "91430": "7082276B65279517003270",  # La Victoria (ANM, Amazonas)
        "91460": "7082276B32823628766031",  # Mirití-Paraná (ANM)
        "91669": "7082276B22108715685729",  # Puerto Santander (ANM, "Santander (Araracuara)")
        "94343": "7082276B12505915261295",  # Barrancominas ("Barranco Mina")
        "94663": "7082276B54584642345614",  # Mapiripana (ANM)
        "94887": "7082276B62655490891692",  # Pana Pana (ANM)
        "94888": "7082276B96401380433737",  # Morichal (ANM)
        "97511": "7082276B7457968430038",   # Pacoa (ANM)
        "97777": "7082276B69012408325747",  # Papunahua (ANM)
        "97889": "7082276B57930571389360",  # Yavaraté (ANM)
    },
    # INEGI municipio codes. Oaxaca has two San Juan Mixtepec and two San
    # Pedro Mixtepec, which the boundary file tells apart by judicial district
    # ("-Dto. 08 -") and INEGI by code; the district is the one each code's
    # municipio sits in (San Pedro's Distrito 22, Juquila, holds Puerto
    # Escondido and 49,780 of its 50,752 people). Hueyapan (Puebla) and
    # Xoxocotla (Veracruz) lost their polygons to Morelos's Hueyapan and
    # Xoxocotla, municipios created in 2019 that the boundary file does not
    # draw -- their people are still inside Tetela del Volcán and Puente de
    # Ixtla, whose figures no longer include them.
    "MEX": {
        "20208": "50627088B120983506636",    # San Juan Mixtepec (Distrito 08, Juxtlahuaca)
        "20209": "50627088B88987154065702",  # San Juan Mixtepec (Distrito 26, Miahuatlán)
        "20318": "50627088B24493610345769",  # San Pedro Mixtepec (Distrito 22, Juquila)
        "20319": "50627088B31998279857894",  # San Pedro Mixtepec (Distrito 26, Miahuatlán)
        "21075": "50627088B56291356806731",  # Hueyapan (Puebla)
        "30195": "50627088B45118812748540",  # Xoxocotla (Veracruz)
    },
}


# Codes whose unit the boundary file does not draw at all, so a row for it
# must reach no polygon: matched by name alone it finds a namesake elsewhere,
# as Morelos's Hueyapan found Puebla's. The build counts these as declared
# gaps ("no_shape"), which cannot become a wrong answer.
UNDRAWN: dict[str, frozenset[str]] = {
    # Morelos's indigenous municipios of 2019, carved from Miacatlán
    # (Coatetelco), Puente de Ixtla (Xoxocotla) and Tetela del Volcán
    # (Hueyapan); the boundary file predates them.
    "MEX": frozenset({"17034", "17035", "17036"}),
}


def pin(iso3: str, code: str) -> dict[str, Any]:
    """The record fields binding an office's code to its polygon, or nothing."""
    if code in UNDRAWN.get(iso3, ()):
        return {"no_shape": True}
    shape = PINS.get(iso3, {}).get(code)
    return {"match_by": "shape_id", "shape_id": shape} if shape else {}
