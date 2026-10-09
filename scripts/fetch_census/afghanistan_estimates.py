#!/usr/bin/env python3
"""Afghanistan -- the statistics office's estimated settled population, 1396 (2017-18).

Afghanistan has no census since the abandoned count of 1979. What its
statistics office (the Central Statistics Organization, renamed the National
Statistics and Information Authority in 2018) publishes every year instead is
an *estimate*: the settled population of every province and district, urban
and rural, by sex, projected from the 2003-05 household listing (``Pt = P0
e^rt``). The 1396 edition (21 March 2017 - 20 March 2018) is the newest one
the office ever published as a workbook; it is read here from the Internet
Archive's capture of the office's own file, sheet "به تفکیک ولسوالی" (by
district). The 1397 edition exists only as a PDF set on its side, and the
1398-1402 ones are gone from the office's site (the archive holds their URLs
as 404s), so 1396 is the newest edition that can be read whole.

What this writes, and only this:

* **population and sex ratio for the districts**, bound to the 398 polygons
  the boundary file draws -- the settled population; the 1.5 million Kuchi
  nomads the office counts nationally are allocated to no province or
  district, and the notes say so;
* **population and sex ratio for the 22 provinces the boundary file draws as
  the office counts them.** The other 12 are drawn otherwise: the file links
  nine districts to another province than the office counts them in (Rukha
  and Unaba in Kapisa rather than Panjshir, Kapisa's own centre Mahmudi Raqi
  in Parwan, Mata Khan in Paktia rather than Paktika, ...), and the map's own
  province polygons hold the points of five more districts than the ones
  they are linked to (``POINT_ELSEWHERE``). For those 12 the office's total
  is not the polygon's, and the note says which districts differ. Five of
  them -- Parwan, Ghazni, Samangan, Zabul and Kandahar -- differ only by the
  links, every district point inside them being linked to them and no other,
  so the polygon is the districts drawn in it and takes their summed rows
  (``drawn_sums``); the seven a point falls across are not written.

Ages are published for the nation alone (the same release's "گروپ سنین"
workbook has no province or district rows), so the median age is a stated
gap.

**The drawn districts are the office's 398 "original" units** -- 364
districts and the 34 provincial centres -- and the 19 *temporary* districts
the 1396 table lists beside them (each starred, "... is temporary") were cut
from them later and are drawn as part of them. So a drawn district carved up
since takes the sum of its own row and its temporary districts' rows; which
original each one came from is read off the office's own earlier estimates
rather than assumed: the 1388 (2009-10) edition, on the same base, still
counts the parent whole, and in every case the parent's 1396 rural count plus
the temporary district's is the 1388 parent times the province's rural growth
factor, 1.140 (``TEMPORARY_PARENT`` gives the figures). The three already
listed apart in 1388 are read the same way against the 1385 (2006-07)
edition, and Shindand's four, first listed in 1396, against 1395. In each
province exactly one district falls short of its growth, by the temporary
district's count. A starred row with no parent here stops the run.

**Every row is the office's arithmetic, checked.** Females and males make
both sexes in each area (rural, urban, total), rural and urban make the total,
the districts make their province's Total row column by column, the province
blocks are identified by those Total rows against the summary table at the
top of the sheet, and the provinces make the settled national total, 28,224,323.
Two rows do not reconcile, and both are named rather than smoothed:

* Baghlan's Khost wa Firing prints 69,568 people, both rural and in total,
  against 32,201 females and 34,367 males -- 66,568. The province's own Total
  row agrees with the sexes, as does the 1388 edition (58,400 x 1.140). The
  sex ratio stands; the head count of the row is not written.
* Jowzjan's Khanaqa and Aqcha: between 1388 and 1396 the office moved about
  17,000 people from the first to the second (Khanaqa x0.674, Aqcha x1.645
  against 1.140 everywhere else), a boundary change the drawn polygons cannot
  be shown to follow, so neither district is written.

Usage:
    python -m scripts.fetch_census.afghanistan_estimates
"""

from __future__ import annotations

import argparse
import io
import re
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json
from .south_asia_common import load_units, males_per_100

OUT = "afghanistan_estimates.json"
YEAR = 2017
URL = ("https://web.archive.org/web/20170703022722id_/http://cso.gov.af/Content/files/"
       "%D8%AA%D8%AE%D9%85%DB%8C%D9%86%20%D9%86%D9%81%D9%88%D8%B3/"
       "%D8%A8%D8%B1%D8%A2%D9%88%D8%B1%D8%AF%20%D9%86%D9%81%D9%88%D8%B3%20%D8%B3%D8%A7%D9%84%201396.xlsx")
SHEET = "به تفکیک ولسوالی"
SOURCE = ("Central Statistics Organization of Afghanistan (now the National Statistics "
          "and Information Authority), Estimated Population of Afghanistan 1396 "
          "(2017-18): estimated settled population by civil division, urban, rural "
          "and sex")
LICENCE = "Afghanistan Central Statistics Organization publication"
# The settled population the sheet's district table opens with ("Total
# Including ..." in the summary, before the Kuchi are added on the first sheet).
SETTLED = 28_224_323
NOMADS = 1_500_000

# Province code -> the drawn first-level unit's ISO 3166-2 code, as the units
# carry it. Ghazni's polygon carries none (the boundary file spells it
# "Ghanzi") and is named instead.
PROVINCE_ISO = {
    "01": "AF-KAB", "02": "AF-KAP", "03": "AF-PAR", "04": "AF-WAR", "05": "AF-LOG",
    "06": "AF-NAN", "07": "AF-LAG", "08": "AF-PAN", "09": "AF-BGL", "10": "AF-BAM",
    "11": "Ghanzi", "12": "AF-PKA", "13": "AF-PIA", "14": "AF-KHO", "15": "AF-KNR",
    "16": "AF-NUR", "17": "AF-BDS", "18": "AF-TAK", "19": "AF-KDZ", "20": "AF-SAM",
    "21": "AF-BAL", "22": "AF-SAR", "23": "AF-GHO", "24": "AF-DAY", "25": "AF-URU",
    "26": "AF-ZAB", "27": "AF-KAN", "28": "AF-JOW", "29": "AF-FYB", "30": "AF-HEL",
    "31": "AF-BDG", "32": "AF-HER", "33": "AF-FRA", "34": "AF-NIM",
}

# Each temporary district (province code + its number in the 1396 table) ->
# the original it was cut from, with the arithmetic that shows it: the
# parent's rural count in the last edition that counts it whole (thousands,
# as the older editions print them), and the parent's and the temporary
# district's rural counts added together in a later one, against the
# province's rural growth factor between the two -- 1.140 from 1388 to 1396.
# In each province exactly one district falls short of that growth, by the
# temporary district's count.
TEMPORARY_PARENT = {
    "0706": "0701",   # Bad Pakh <- Mehtarlam (centre): 126.6k -> 136,810 + 7,810 = 1.142
    "0808": "0803",   # Abshar <- Dara: 23.0k -> 14,628 + 11,652 = 1.143
    "1008": "1005",   # Yakawlang No. 2 <- Yakawlang: 80.9k -> 64,212 + 28,016 = 1.140
    "1313": "1306",   # Mirzaka <- Sayyid Karam: 59.4k -> 58,758 + 9,050 = 1.142
    "1516": "1506",   # Sheltan <- Shigal (1388's "Shigal wa Sheltan", 27.1k)
    #                   -> 12,675 + 18,191 = 1.139
    "1908": "1905",   # Kalbad <- Imam Sahib: rural 183.2k -> 175,314 + 33,563 = 1.140
    "1909": "1901",   # Gul Tepa <- Kunduz (centre): rural 152.9k -> 164,429 + 9,986 = 1.141
    "1910": "1904",   # Aqtash <- Khan Abad: rural 111.7k -> 101,582 + 25,727 = 1.140
    "2717": "2701",   # Dand <- Kandahar (centre): rural 131.0k -> 102,021 + 47,354 = 1.140
    #                   (1392 lists it first: 95.6k + 44.3k = 131.0k x 1.068, the
    #                   province's rural factor 1388 -> 1392)
    "2718": "2711",   # Takhta Pul <- Spin Boldak: 104.8k -> 106,111 + 13,388 = 1.140
    "3014": "3002",   # Marja <- Nad Ali: 109.3k -> 96,195 + 28,388 = 1.140
    "3015": "3012",   # Nawamish <- Baghran: 75.4k -> 68,244 + 17,786 = 1.141
    # Listed apart already in 1388, and read against 1385 (2006-07), whose
    # rural factor to 1388 is 1.044 in each of the three provinces (each sum
    # of rounded thousands is good to about +-0.004):
    "1312": "1308",   # Laja Mangal <- Laja Ahmad Khel: 36.8k -> 21.1k + 17.4k = 1.046
    "2506": "2503",   # Chinarto <- Chora: 56.6k -> 47.3k + 11.9k = 1.046
    "3406": "3405",   # Dularam <- Khash Rod: 28.3k -> 23.5k + 6.0k = 1.042
    # Shindand's four, first listed in 1396: 1395's rural Shindand 180,403 x
    # Herat's rural factor 1.0163 = 183,343 against 39,418 + 143,921 = 183,339.
    "3217": "3214", "3218": "3214", "3219": "3214", "3220": "3214",
}

# Rows whose printed both-sexes figures contradict their own sex columns; see
# the module docstring. The sex ratio stands, the head count is not written.
MISPRINTED = {"0913": ("Khost wa Firing prints 69,568 people against 32,201 females "
                       "and 34,367 males, 66,568; the province's Total row and the "
                       "1388 edition agree with the sexes.")}
# Districts between which the office moved population after the drawn
# boundaries were set; see the module docstring.
SHIFTED = {"2803", "2807"}
SHIFTED_NOTE = (
    "Not written: between its 1388 and 1396 editions the statistics office moved "
    "about 17,000 people from Khanaqa to Aqcha (Khanaqa's rural count grew 0.674 "
    "times and Aqcha's 1.645 times, against 1.140 for every other district of "
    "Jowzjan), a boundary change that the polygon drawn here cannot be shown to "
    "follow.")

# The drawn district (as the boundary file labels it, inside its drawn
# province) -> the 1396 table's code (province + number). Read off the
# office's own numbering, which is the Afghanistan Geodesy and Cartography
# Head Office's district code; every pair was checked by name against the
# table's English and Dari columns. "24--" is Gizab, which the 1396 table
# prints unnumbered at the foot of Daykundi.
CROSSWALK: dict[str, dict[str, str]] = {
    'Badakhshan': {
        'Fayzabad': '1701',  # province center (Faiz Abad)
        'Argo': '1702',  # Argo
        'Arghanj Khaw': '1703',  # Arghanj Khwah
        'Yaftal Sufla': '1704',  # Yaftal-e-Sufla
        'Khash': '1705',  # Khash
        'Baharak': '1706',  # Baharak
        'Darayim': '1707',  # Darayim
        'Kohistan': '1708',  # Kohistan
        'Yawan': '1709',  # Yawan
        'Jurm': '1710',  # Jurm
        'Tashkan': '1711',  # Tashkan
        'Shahada': '1712',  # Shuhada
        'Shahri Buzurg': '1713',  # Shahri Buzurg
        'Raghistan': '1714',  # Raghistan
        'Kishim': '1715',  # Kishm
        'Warduj': '1716',  # Wardooj
        'Tagab (Kishmi Bala)': '1717',  # Tagab
        'Yamgan (Girwan)': '1718',  # Yamgan(Girwan)
        'Shighnan': '1719',  # Shighnan
        'Khwahan': '1720',  # Khwahan
        'Kuf Ab': '1721',  # Kufab
        'Darwaz': '1722',  # Darwaz-e- Payin (Mamay)
        'Ishkashiem': '1723',  # Eshkashim
        'Shaki': '1724',  # Shiki
        'Zebak': '1725',  # Zebak
        'Kuran Wa Munjan': '1726',  # Kiran Wa Menjan
        'Darwazbala': '1727',  # Darwaz-e- Bala ( Nesay)
        'Wakhan': '1728',  # Wakhan
    },
    'Badghis': {
        'Qala-I- Naw': '3101',  # province Center  (Qala-i- Now)
        'Ab Kamari': '3102',  # Ab Kamari
        'Muqur': '3103',  # Muqur
        'Qadis': '3104',  # Qadis
        'Bala Murghab': '3105',  # Murghab (Bala Murghab)
        'Jawand': '3106',  # Jawand
        'Ghormach': '3107',  # Ghormach
    },
    'Baghlan': {
        'Puli Khumri': '0901',  # province Center (Pul-i-Khumri)
        'Dahana-I- Ghuri': '0902',  # Dahana-e-Ghuri
        'Dushi': '0903',  # Dushi
        'Nahrin': '0904',  # Nahreen
        'Baghlani Jadid': '0905',  # Baghlan-e- Jadeed
        'Khinjan': '0906',  # Khinjan
        'Andarab': '0907',  # Andarab
        'Dih Salah': '0908',  # Deh  Salah
        'Khwaja Hijran (Jilga Nahrin)': '0909',  # Khwaja hejran (Jalga )
        'Burka': '0910',  # Burka
        'Tala Wa Barfak': '0911',  # Tala Wa Barfak
        'Puli Hisar': '0912',  # Pul –e-Hisar
        'Khost Wa Firing': '0913',  # Khost Wa Firing
        'Guzargahi Nur': '0914',  # Gozargah-e- Noor
        'Farang Wa Gharu': '0915',  # Firing Wa Gharu
    },
    'Balkh': {
        'Feroz Nakhchir': '2004',  # Feroz  Nakhcheer
        'Mazari Sharif': '2101',  # province Center (Mazar-e- sharif)
        'Nahri Shahi': '2102',  # Nahri Shahi
        'Dihdadi': '2103',  # Dehdadi
        'Chahar Kint': '2104',  # Char kent
        'Marmul': '2105',  # Marmul
        'Balkh': '2106',  # Balkh
        'Sholgara': '2107',  # Sholgara
        'Chimtal': '2108',  # Chimtal
        'Dawlatabad': '2109',  # Dawlat Abad
        'Khulm': '2110',  # Khulm
        'Chahar Bolak': '2111',  # Char Bolak
        'Shortepa': '2112',  # Shortepa
        'Kaldar': '2113',  # Kaldar
        'Kishindih': '2114',  # Kishindeh
        'Zari': '2115',  # Zari
    },
    'Bamyan': {
        'Bamyan': '1001',  # province Center (Bamyan )
        'Shibar': '1002',  # Shebar
        'Sayghan': '1003',  # Saighan
        'Kahmard': '1004',  # Kahmard
        'Yakawlang': '1005',  # Yakawlang
        'Panjab': '1006',  # Panjab
        'Waras': '1007',  # Waras
    },
    'Daykundi': {
        'Gizab': '24--',  # (unnumbered Gizab row)
        'Nili': '2401',  # province Center (Nili)
        'Shahristan': '2402',  # Shahristan
        'Ishtarlay': '2403',  # Ishterlai
        'Khadir': '2404',  # Khedir
        'Gaiti': '2405',  # kiti
        'Miramor': '2406',  # Miramor
        'Sangi Takht': '2407',  # Sang -e- Takht
        'Kajran': '2408',  # Kejran
    },
    'Farah': {
        'Farah': '3301',  # province Center (Farah)
        'Pusht Rod': '3302',  # Pushtrud
        'Khaki Safed': '3303',  # Khak-i-safed
        'Qala Ka': '3304',  # Qala-i-kah
        'Shib Koh': '3305',  # Shibkoh
        'Bala Buluk': '3306',  # Bala Buluk
        'Anar Dara': '3307',  # Anar Dara
        'Bakwa': '3308',  # Bakwa
        'Lash Wa Juwayn': '3309',  # Lash-i- Juwayn
        'Gulistan': '3310',  # Gulistan
        'Pur Chaman': '3311',  # Pur Chaman
    },
    'Faryab': {
        'Maymana': '2901',  # province Center (Maimana)
        'Pashtun Kot': '2902',  # Pashtun kot
        'Khwaja Sabz Posh': '2903',  # Khwaja Sabz Posh i Wali
        'Almar': '2904',  # Almar
        'Bilchiragh': '2905',  # Bilchiragh
        'Shirin Tagab': '2906',  # Shirin Tagab
        'Qaysar': '2907',  # Qaisar
        'Gurziwan': '2908',  # Gurziwan
        'Dawlatabad': '2909',  # Dawlat Abad
        'Kohistan': '2910',  # Kohistan
        'Qaramqol': '2911',  # Qaram Qul
        'Qurghan': '2912',  # Qurghan
        'Andkhoy': '2913',  # Andkhoy
        'Khani Chahar Bagh': '2914',  # Khani Charbagh
    },
    'Ghanzi': {
        'Ghazni': '1101',  # province Center(Ghazni)
        'Wali Muhammadi Shahid': '1102',  # Wali M. Shahid (khugyani)
        'Khwaja Umari': '1103',  # Khwaja Omari
        'Waghaz': '1104',  # Waghaz
        'Dih Yak': '1105',  # Deh Yak
        'Bahrami Shahid (Jaghatu)': '1106',  # Jaghatu
        'Andar': '1107',  # Andar
        'Zana Khan': '1108',  # Zanakhan
        'Rashidan': '1109',  # Rashidan
        'Nawur': '1110',  # Nawur
        'Qarabagh': '1111',  # Qara Bagh
        'Giro': '1112',  # Giro
        'Ab Band': '1113',  # Ab Band
        'Jaghuri': '1114',  # Jaghuri
        'Muqur': '1115',  # Muqur
        'Malistan': '1116',  # Malistan
        'Gelan': '1117',  # Gelan
        'Ajristan': '1118',  # Ajristan
        'Nawa': '1119',  # Nawa
        'Naw Bahar': '2609',  # Naw Bahar
    },
    'Ghor': {
        'Chaghcharan': '2301',  # province  Center (Chighcheran)
        'Du Layna': '2302',  # Duleena
        'Dawlat Yar': '2303',  # Dawlatyar
        'Charsada': '2304',  # Char Sada
        'Pasaband': '2305',  # Pasaband
        'Shahrak': '2306',  # Shahrak
        'Lal Wa Sarjangal': '2307',  # Lal Wa SarJangal
        'Taywara': '2308',  # Taywara
        'Tulak': '2309',  # Tulak
        'Saghar': '2310',  # Saghar
    },
    'Helmand': {
        'Lashkar Gah': '3001',  # province Center (Lashkargah)
        'Nad Ali': '3002',  # Nad Ali
        'Nawa-I- Barak Zayi': '3003',  # Nawa-i- Barikzayi
        'Nahri Sarraj': '3004',  # Nahr-i- Saraj
        'Washer': '3005',  # Washer
        'Garmser': '3006',  # Garm Ser
        'Naw Zad': '3007',  # Nawzad
        'Sangin': '3008',  # Sangin
        'Musa Qala': '3009',  # Musa Qala
        'Kajaki': '3010',  # Kajaki
        'Reg(Khanshin)': '3011',  # Reg-i-Khan Nishin
        'Baghran': '3012',  # Baghran
        'Dishu': '3013',  # Dishu
    },
    'Herat': {
        'Hirat': '3201',  # province  Center (Herat)
        'Injil': '3202',  # Enjil
        'Guzara': '3203',  # Guzera (Nizam-i- Shahid)
        'Karukh': '3204',  # Karrukh
        'Zanda  Jan': '3205',  # Zendahjan
        'Pashtun Zarghun': '3206',  # Pashtun Zarghun
        'Koshk': '3207',  # Kushk (Rubat-i-Sangi)
        'Gulran': '3208',  # Gulran
        'Adraskan': '3209',  # Adraskan
        'Koshki Kohna': '3210',  # Kushk-i- Kuhna
        'Ghoryan': '3211',  # Ghoryan
        'Obe': '3212',  # Obe
        'Kohsan': '3213',  # Kohsan
        'Shindand': '3214',  # Shindand
        'Farsi': '3215',  # Fersi
        'Chishti Sharif': '3216',  # Chishti Sharif
    },
    'Jowzjan': {
        'Shibirghan': '2801',  # province Center (Sheberghan)
        'Khwaja Du Koh': '2802',  # Khwaja Dukoh
        'Khaniqa': '2803',  # Khanaqa
        'Mangajek': '2804',  # Mingajik
        'Qush Tepa': '2805',  # Qush Tepa
        'Kham Ab': '2806',  # Khamyab
        'Aqcha': '2807',  # Aqchah
        'Fayzabad': '2808',  # Faizabad
        'Mardyan': '2809',  # Mardyan
        'Qarqin': '2810',  # Qarqin
        'Darzab': '2811',  # Darzab
    },
    'Kabul': {
        'Kabul': '0101',  # province Center (Kabul )
        'Paghman': '0102',  # Paghman
        'Chahar Asyab': '0103',  # Chahar Asyab
        'Bagrami': '0104',  # Bagrami
        'Dih Sabz': '0105',  # DehSabz
        'Shakardara': '0106',  # Shakar Dara
        'Musayi': '0107',  # Musahi
        'Mir Bacha Kot': '0108',  # Mir Bacha kot
        'Khaki Jabbar': '0109',  # Khak-e-Jabar
        'Kalakan': '0110',  # Kalakan
        'Guldara': '0111',  # Guldara
        'Farza': '0112',  # Farza
        'Istalif': '0113',  # Estalef
        'Qarabagh': '0114',  # Qara Bagh
        'Surobi': '0115',  # Surubi
    },
    'Kandahar': {
        'Kandahar': '2701',  # province Center (Kandahar)
        'Arghandab': '2702',  # Arghandab
        'Daman': '2703',  # Daman
        'Panjwayi': '2704',  # Panjwayee
        'Zhari': '2705',  # Zhire
        'Shah Wali Kot': '2706',  # Shah Wali Kot
        'Khakrez': '2707',  # Khakrez
        'Arghistan': '2708',  # Arghistan
        'Ghorak': '2709',  # Ghorak
        'Maywand': '2710',  # Maiwand
        'Spin Boldak': '2711',  # Spin Boldak
        'Nesh': '2712',  # Nesh
        'Shorabak': '2714',  # Shorabak
        'Maruf': '2715',  # Maruf
        'Registan': '2716',  # Reg ( Shiga )
    },
    'Kapisa': {
        'Hisa-i-Duwumi Kohistan': '0202',  # Hissa-e-Duwumi Kohistan
        'Koh Band': '0203',  # Koh Band
        'Hisa-i-Awali Kohistan': '0204',  # Hissa-e-Awali Kohistan
        'Nijrab': '0205',  # Nijrab
        'Tagab': '0206',  # Tagab
        'Alasay': '0207',  # Alasai
        'Rukha': '0802',  # Rukha
        'Unaba': '0805',  # Unaba
    },
    'Khost': {
        'Khost(Matun)': '1401',  # province Center(Khost)
        'Mando Zayi': '1402',  # Manduzay (Esmayel khil)
        'Gurbuz': '1403',  # Gurbuz
        'Tani': '1404',  # Tanay
        'Mosa Khail': '1405',  # Musa khel
        'Nadir Shah Kot': '1406',  # Nadir Shah kot
        'Sabri': '1407',  # Sabari (Yaqubi)
        'Tere Zayi': '1408',  # Tirzayee (Ali Sher )
        'Bak': '1409',  # Baak
        'Qalandar': '1410',  # Qalandar
        'Shamal': '1412',  # Shamul
        'Jaji Maidan': '1413',  # Jaji Maidan
    },
    'Kunar': {
        'Asadabad': '1501',  # province Center (Asad Abad)
        'Marawara': '1502',  # Mara wara
        'Wata Pur': '1503',  # Watapoor
        'Narang': '1504',  # Narang Wa Badil
        'Sarkani': '1505',  # Sar Kani
        'Shaygal wa shital': '1506',  # Shigal
        'Dara-I-Pech': '1507',  # Dara-e- Pech
        'Bar Kunar': '1508',  # Bar Kunar
        'Chawkay': '1509',  # Sawkai
        'Khas Kunar': '1510',  # Khas Kunar
        'Ghaziabad': '1511',  # Ghazi Abad
        'Dangam': '1512',  # Dangam
        'Chapa Dara': '1513',  # Chapa Dara
        'Nurgal': '1514',  # Noorgal
        'Nari': '1515',  # Nari
    },
    'Kunduz': {
        'Kunduz': '1901',  # province Center (Kunduz)
        'Chahar Dara': '1902',  # Chahar Darah
        'Aliabad': '1903',  # Ali Abad
        'Khanabad': '1904',  # Khan Abad
        'Imam Sahib': '1905',  # Hazrati Imam Sahib
        'Dashte Archi': '1906',  # Dasht-e- Archi
        'Qalay-I- Zal': '1907',  # Qala -e-Zal
    },
    'Laghman': {
        'Mihtarlam': '0701',  # province Center (Mehterlam)
        'Qarghayi': '0702',  # Qarghayee
        'Alishing': '0703',  # Alishing
        'Alingar': '0704',  # Alingar
        'Daulatshahi': '0705',  # Dawlat Shah
    },
    'Logar': {
        'Puli Alam': '0501',  # province Center(Puli Alam)
        'Baraki Barak': '0502',  # Baraki Barak
        'Charkh': '0503',  # Charkh
        'Khoshi': '0504',  # khushi
        'Mohammad Agha': '0505',  # Mohammad Agha
        'Kharwar': '0506',  # Khar war
        'Azra': '0507',  # Azra
    },
    'Nangarhar': {
        'Jalalabad': '0601',  # province Center (Jalalabad)
        'Bihsud': '0602',  # Behsud
        'Surkh Rod': '0603',  # Surkh Rud
        'Chaparhar': '0604',  # Chapar har
        'Kama': '0605',  # Kama
        'Kuz Kunar': '0606',  # Kuzkunar
        'Rodat': '0607',  # Rodat
        'Khogayani': '0608',  # Khugyani
        'Bati Kot': '0609',  # Bati Kot
        'Deh Bala': '0610',  # Deh Bala
        'Pachier Agam': '0611',  # Pachir Waagam
        'Dara-I-Nur': '0612',  # Darah -e- Noor
        'Kot': '0613',  # Kot
        'Goshta': '0614',  # Goshta
        'Acheen': '0615',  # Achin
        'Shinwar': '0616',  # Shinwar
        'Muhmand Dara': '0617',  # Muhmand ِِDara
        'Lal Por': '0618',  # Lalpoor
        'Shirzad': '0619',  # Sher Zad
        'Nazyan': '0620',  # Nazyan
        'Hesarak': '0621',  # Hesarak
        'Dur Baba': '0622',  # Dur  Baba
    },
    'Nimruz': {
        'Zaranj': '3401',  # province Center (Zaranj)
        'Kang': '3402',  # Kang
        'Chakhansur': '3403',  # Asl-i-chakhansur
        'Chahar Burjak': '3404',  # Char Burjak
        'Khash Rod': '3405',  # Khashrod
    },
    'Nuristan': {
        'Parun': '1601',  # province Center (Paroon)
        'Waygal': '1602',  # Waygal
        'Wama': '1603',  # Wama
        'Nurgaram': '1604',  # Noor Gram
        'Du Ab': '1605',  # Duab
        'Kamdesh': '1606',  # Kamdesh
        'Mandol': '1607',  # Mandol
        'Bargi Matal': '1608',  # Bargi Matal
    },
    'Paktia': {
        'Mata Khan': '1202',  # Mata Khan
        'Gardiz': '1301',  # province Center(Gardez)
        'Ahmad Abad': '1302',  # Ahmadaba
        'Zurmat': '1303',  # Zurmat
        'Shawak': '1304',  # Shwak
        'Zadran': '1305',  # Wuza Zadran
        'Sayed Karam': '1306',  # Sayyid Karam
        'Ali Khail (Jaji)': '1307',  # Jaji
        'Laja Ahmad Khail': '1308',  # Laja Ahmad khel
        'Jani Khail': '1309',  # Jani Khel
        'Chamkani': '1310',  # Samkani
        'Dand Patan': '1311',  # Dand Patan
    },
    'Paktika': {
        'Sharan': '1201',  # province Center(Sharan)
        'Yosuf Khel': '1203',  # Yosuf Khel
        'Yahya Khel': '1204',  # Yahya Khel
        'Sar Hawza': '1205',  # Sar Rawza
        'Omna': '1206',  # Omna
        'Zarghun Shahr': '1207',  # Zarghun Shahr
        'Gomal': '1208',  # Gomal
        'Jani Khel': '1209',  # Jani Khel
        'Sarobi': '1210',  # Surubi
        'Urgun': '1211',  # Urgoon
        'Ziruk': '1212',  # Ziruk
        'Nika': '1213',  # Nika
        'Barmal': '1214',  # Barmal
        'Gayan': '1215',  # Giyan
        'Dila': '1216',  # DilaWa Khushamand
        'Waza Khwa': '1217',  # Wazakhwah
        'Wor Mayi': '1218',  # Wormamay
        'Turwo': '1219',  # Turwo
        'Spira': '1411',  # Spera
    },
    'Panjshir': {
        'Bazarak': '0801',  # province  Center (Bazarak)
        'Dara': '0803',  # Darah
        'Khenj (Hese- Awal)': '0804',  # Hissa-e- Awal   (Khinj)
        'Paryan': '0807',  # Paryan
    },
    'Parwan': {
        'Mahmudi Raqi': '0201',  # province Center (Mahmood Raqi)
        'Chaharikar': '0301',  # province Center (Charikar )
        'Bagram': '0302',  # Bagram
        'Shinwari': '0303',  # Shinwari
        'Sayd Khel': '0304',  # Sayyid  Khel
        'Jabalussaraj': '0305',  # Jabulussaraj
        'Salang': '0306',  # Salang
        'Sia Gird ( Ghorbund)': '0307',  # syahgird  ('Ghurband)
        'Kohi Safi': '0308',  # Koh-e- Safi
        'Surkhi Parsa': '0309',  # Surkhi  parsa
        'Shekh  Ali': '0310',  # Shaykh  Ali
        'Shutul': '0806',  # Shutul
    },
    'Samangan': {
        'Aybak': '2001',  # province Center (Aybak)
        'Hazrati Sultan': '2002',  # Hazrat -e-Sultan
        'Khuram Wa Sarbagh': '2003',  # Khuram Wa Sarbagh
        'Ruyi Du Ab': '2005',  # Rui- Do- Ab
        'Dara-I-Sufi Payin': '2006',  # Dara -e-soof-i-Payin
        'Dara-I-Sufi Bala': '2007',  # Dara -e-soof-e- Bala
    },
    'Sar-e Pol': {
        'Sari Pul': '2201',  # province Center (Sar-e-Pul)
        'Sayyad': '2202',  # Sayyad
        'Kohistanat': '2203',  # Kohistanat
        'Sozma Qala': '2204',  # Sozma Qala
        'Sangcharak': '2205',  # Sancharak
        'Gosfandi': '2206',  # Gosfandi
        'Balkhab': '2207',  # Balkhab
    },
    'Takhar': {
        'Taluqan': '1801',  # province  Center (Taluqan)
        'Hazar Sumuch': '1802',  # Hazar Sumuch
        'Baharak': '1803',  # Baharak
        'Bangi': '1804',  # Bangi
        'Chal': '1805',  # Chal
        'Namak Ab': '1806',  # Namak Ab
        'Kalfagan': '1807',  # Kalafgan
        'Farkhar': '1808',  # Farkhar
        'Khwaja Ghar': '1809',  # Khwaja Ghar
        'Rustaq': '1810',  # Rustaq
        'Ishkamish': '1811',  # Eshkamesh
        'Dashti Qala': '1812',  # Dashti Qala
        'Warsaj': '1813',  # Warsaj
        'Khwaja Bahawuddin': '1814',  # Khwaja Bahawuddin
        'Darqad': '1815',  # Darqad
        'Chah Ab': '1816',  # Chahab
        'Yangi Qala': '1817',  # Yangi Qala
    },
    'Uruzgan': {
        'Tirin Kot': '2501',  # province Center (Tirinkot)
        'Dihrawud': '2502',  # Dehraoud
        'Chora': '2503',  # Chora
        'Shahidi Hassas': '2504',  # Shahidhassas
        'Khas Uruzgan': '2505',  # Khas Urozgan
    },
    'Wardak': {
        'Maydan Shahr': '0401',  # province  Center (Maidan Shahr)
        'Nirkh': '0402',  # Nerkh
        'Jalrez': '0403',  # Jalrez
        'Chaki Wardak': '0404',  # Chak-e- Wardak
        'Saydabad': '0405',  # Sayyid Abad
        'Day Mirdad': '0406',  # Daimir Dad
        'Hisa-I- Awali Bihsud': '0407',  # Hissa-e- awali Behsud
        'Jaghatu': '0408',  # Jaghatu
        'Markazi Bihsud': '0409',  # Markaz-e- Behsud
    },
    'Zabul': {
        'Qalat': '2601',  # province Center (Qalat)
        'Tarnak Wa Jaldak': '2602',  # Tarang Wa Jaldak
        'Shinkay': '2603',  # Shinkai
        'Mizan': '2604',  # Mizan
        'Arghandab': '2605',  # Arghandab
        'Shahjoy': '2606',  # Shah Joi
        'Daychopan': '2607',  # Daichopan
        'Atghar': '2608',  # Atghar
        'Shamulzayi': '2610',  # Shemel Zayi
        'Kakar': '2611',  # Kakar (khak-e-afghan )
        'Miya Nishin': '2713',  # Miyanishin
    },
}

# Districts whose point the map's own first-level polygons put in another
# province than the boundary file's parent link for them names: row code ->
# (the drawn province linked, the drawn province whose polygon holds the
# point). Read against site/tiles/admin1.pmtiles at its deepest zoom (7) for
# all 398 drawn districts on 9 October 2026; Sarkani's point, which falls
# just across the border with Pakistan, is in no other province and is left
# out. Nine more districts are linked to another province than the office
# counts them in, which CROSSWALK itself shows; neither kind of province is
# given the office's total.
POINT_ELSEWHERE = {
    "0803": ("Panjshir", "Kapisa"),       # Dara
    "1309": ("Paktia", "Khost"),          # Jani Khail
    "1405": ("Khost", "Paktia"),          # Mosa Khail
    "1411": ("Paktika", "Khost"),         # Spira
    "2206": ("Sar-e Pol", "Balkh"),       # Gosfandi
}

FIELDS = ("female", "male", "both")


def number(value: Any) -> int:
    """A cell as people: blank or a dash (the table's zero) is 0."""
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(round(value))
    text = str(value).replace(",", "").strip()
    if not text or set(text) <= set("_-ـ. "):
        return 0
    return int(round(float(text)))


def figures(row: list[Any]) -> list[int] | None:
    """Rural, urban and total, each female, male, both: nine numbers, or None."""
    cells = row[2:11]
    if len(cells) < 9:
        return None
    try:
        return [number(c) for c in cells]
    except ValueError:
        return None


def code_of(cell: Any) -> tuple[str | None, bool]:
    """A row's number and whether it carries the temporary star."""
    text = str(cell if cell is not None else "").strip()
    star = "*" in text
    digits = re.sub(r"[^\d]", "", text)
    return (digits.zfill(2) if digits else None), star


def read_sheet(rows: list[list[Any]]) -> tuple[dict[str, list[int]], list[dict[str, Any]]]:
    """The 34-row summary, and every block: its Total row and its districts."""
    summary: dict[str, list[int]] = {}
    blocks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for row in rows:
        row = list(row) + [None] * (13 - len(row))
        label = str(row[1] if row[1] is not None else "").strip()
        nums = figures(row)
        if label.lower() == "total" and nums and nums[8]:
            current = {"total": nums, "rows": []}
            blocks.append(current)
            continue
        code, star = code_of(row[0])
        tail_star = any("*" in str(c or "") for c in row[11:13])
        if current is None:
            if code and label and nums and nums[8]:
                summary[code] = nums
            continue
        if not nums or not nums[8] or not label:
            continue
        if code is None and str(row[0] or "").strip():
            continue                     # a footnote that happens to carry a number
        current["rows"].append({"no": code, "en": label, "fa": str(row[11] or "").strip(),
                                "figs": nums, "temporary": star or tail_star})
    return summary, blocks


def check_row(where: str, f: list[int]) -> list[str]:
    bad = []
    for i, area in enumerate(("rural", "urban", "total")):
        if f[3 * i] + f[3 * i + 1] != f[3 * i + 2]:
            bad.append(f"{where} {area}: {f[3 * i]:,} + {f[3 * i + 1]:,} != {f[3 * i + 2]:,}")
    for j, sex in enumerate(FIELDS):
        if f[j] + f[3 + j] != f[6 + j]:
            bad.append(f"{where} {sex}: rural {f[j]:,} + urban {f[3 + j]:,} != {f[6 + j]:,}")
    return bad


def provinces_of(summary: dict[str, list[int]], blocks: list[dict[str, Any]]
                 ) -> dict[str, dict[str, Any]]:
    """Each block placed by its Total row, and every check that ties them up."""
    if set(summary) != set(PROVINCE_ISO):
        raise SystemExit(f"afghanistan_estimates: the summary's provinces are "
                         f"{sorted(summary)}, not the 34 expected")
    if sum(f[8] for f in summary.values()) != SETTLED:
        raise SystemExit("afghanistan_estimates: the provinces add up to "
                         f"{sum(f[8] for f in summary.values()):,}, not {SETTLED:,}")
    placed: dict[str, dict[str, Any]] = {}
    for block in blocks:
        codes = [c for c, f in summary.items() if f == block["total"]]
        if len(codes) != 1:
            raise SystemExit(f"afghanistan_estimates: a block's Total row matches "
                             f"{len(codes)} provinces")
        if codes[0] in placed:
            raise SystemExit(f"afghanistan_estimates: province {codes[0]} has two blocks")
        placed[codes[0]] = block
    if set(placed) != set(summary):
        raise SystemExit(f"afghanistan_estimates: no block for {sorted(set(summary) - set(placed))}")
    bad: list[str] = []
    for code, block in placed.items():
        for row in block["rows"]:
            key = f"{code}{row['no'] or '--'}"
            figs = list(row["figs"])
            if key in MISPRINTED:
                # Read as its sexes say; check_row would otherwise stop the run
                # on the two both-sexes cells the docstring names.
                figs[2], figs[8] = figs[0] + figs[1], figs[6] + figs[7]
                row["corrected"] = figs
            bad += check_row(f"{key} {row['en']}", figs)
        sums = [sum((r.get("corrected") or r["figs"])[i] for r in block["rows"])
                for i in range(9)]
        if sums != block["total"]:
            bad.append(f"province {code}: its rows make {sums}, its Total row {block['total']}")
    if bad:
        raise SystemExit(f"afghanistan_estimates: {len(bad)} checks failed -- "
                         + "; ".join(bad[:6]))
    log(f"    {len(placed)} provinces placed by their Total rows; every row's sexes and areas add "
        f"up, every province's districts make its Total row, and the provinces make "
        f"{SETTLED:,} settled people")
    return placed


def district_rows(placed: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for code, block in placed.items():
        for row in block["rows"]:
            key = f"{code}{row['no']}" if row["no"] else f"{code}--"
            if key in out:
                raise SystemExit(f"afghanistan_estimates: {key} twice")
            out[key] = row
    return out


def sexes(row: dict[str, Any]) -> tuple[int, int, int]:
    f = row.get("corrected") or row["figs"]
    return f[6], f[7], f[8]


def province_units(units1: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Province code -> the drawn first-level unit."""
    by_iso = {u.get("iso_3166_2"): u for u in units1 if u.get("iso_3166_2")}
    by_name = {u["name"]: u for u in units1}
    out = {}
    for code, key in PROVINCE_ISO.items():
        unit = by_iso.get(key) or by_name.get(key)
        if unit is None:
            raise SystemExit(f"afghanistan_estimates: no drawn province for {code} ({key})")
        out[code] = unit
    return out


def shown(unit: dict[str, Any]) -> str:
    """A unit's name as the map shows it."""
    return unit.get("site_name") or unit["name"]


def drawn_districts(units1: list[dict[str, Any]], units2: list[dict[str, Any]]
                    ) -> list[tuple[dict[str, Any], str, str]]:
    """Each drawn district, its drawn province's label and its row's code."""
    prov_label = {u["id"]: u["name"] for u in units1}
    out, used = [], set()
    for unit in units2:
        province = prov_label.get(unit.get("parent"), "")
        key = CROSSWALK.get(province, {}).get(unit["name"])
        if key is None:
            raise SystemExit(f"afghanistan_estimates: no row for the drawn {unit['name']!r} "
                             f"({province})")
        if key in used:
            raise SystemExit(f"afghanistan_estimates: {key} claimed twice")
        used.add(key)
        out.append((unit, province, key))
    return out


def drawn_apart(units1: list[dict[str, Any]], units2: list[dict[str, Any]]
                ) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Where the boundary file draws a province otherwise than the office counts it.

    Province code -> what differs, said from that province's side; and drawn
    district code -> where the office counts it, for each district drawn in
    another province.
    """
    provinces = province_units(units1)
    code_of_label = {u["name"]: c for c, u in provinces.items()}
    apart: dict[str, list[str]] = {}
    counted_in: dict[str, str] = {}
    districts = drawn_districts(units1, units2)
    for unit, province, key in districts:
        here, counted = code_of_label[province], key[:2]
        if here != counted:
            name, there = shown(unit), shown(provinces[counted])
            drawn_in = shown(provinces[here])
            counted_in[key] = (f" The office counts it in {there}; the boundary file "
                               f"draws it in {drawn_in}.")
            apart.setdefault(counted, []).append(
                f"{name}, which the office counts here, is drawn in {drawn_in}")
            apart.setdefault(here, []).append(
                f"{name}, drawn here, is counted by the office in {there}")
    by_key = {key: (unit, province) for unit, province, key in districts}
    for key, (linked, holding) in POINT_ELSEWHERE.items():
        unit, province = by_key[key]
        if province != linked:
            raise SystemExit(f"afghanistan_estimates: {key} is drawn in {province}, "
                             f"not {linked}")
        name = shown(unit)
        apart.setdefault(code_of_label[linked], []).append(
            f"the point of {name}, drawn here, falls inside "
            f"{shown(provinces[code_of_label[holding]])}'s polygon")
        apart.setdefault(code_of_label[holding], []).append(
            f"the point of {name}, drawn in {shown(provinces[code_of_label[linked]])}, "
            f"falls inside this one")
    return apart, counted_in


def drawn_sums(rows: dict[str, dict[str, Any]], units1: list[dict[str, Any]],
               units2: list[dict[str, Any]]) -> dict[str, tuple[int, int, list[str]] | str]:
    """Province code -> the office's females and males summed over the districts
    the boundary file draws in it, with their names; or why that sum is not the
    polygon's.

    The sum stands for a province only where the drawn districts are the
    polygon: no district point in it is linked elsewhere and none linked to it
    has its point elsewhere (``POINT_ELSEWHERE``), and no district drawn in it
    is one whose own count is refused (``SHIFTED``). Each district's figures
    are its own row's plus its temporary districts', as on its own record;
    both sexes are taken as females plus males, which is what every province's
    Total row prints, a misprinted row's head count included (``MISPRINTED``).
    """
    provinces = province_units(units1)
    code_of_label = {u["name"]: c for c, u in provinces.items()}
    touched = {code_of_label[p] for linked, holding in POINT_ELSEWHERE.values()
               for p in (linked, holding)}
    children: dict[str, list[str]] = {}
    for temp, parent in TEMPORARY_PARENT.items():
        children.setdefault(parent, []).append(temp)
    out: dict[str, tuple[int, int, list[str]] | str] = {}
    for unit, province, key in drawn_districts(units1, units2):
        code = code_of_label[province]
        if code in touched:
            out[code] = "touched"
            continue
        if key in SHIFTED:
            out[code] = f"refused:{shown(unit)}"
            continue
        if isinstance(out.get(code), str):
            continue
        parts = [rows[key]] + [rows[t] for t in children.get(key, ())]
        female = sum(sexes(p)[0] for p in parts)
        male = sum(sexes(p)[1] for p in parts)
        f, m, names = out.get(code, (0, 0, []))
        out[code] = (f + female, m + male, [*names, shown(unit)])
    return out


def province_records(placed: dict[str, dict[str, Any]], units1: list[dict[str, Any]],
                     apart: dict[str, list[str]],
                     sums: dict[str, tuple[int, int, list[str]] | str] | None = None
                     ) -> list[dict[str, Any]]:
    provinces = province_units(units1)
    sums = sums or {}
    out = []
    for code, block in sorted(placed.items()):
        unit = provinces[code]
        female, male, both = block["total"][6:9]
        fields: dict[str, Any]
        summed = sums.get(code)
        if code in apart and isinstance(summed, tuple):
            # Drawn otherwise than the office counts it, but drawn whole out of
            # districts that each carry their own row: the polygon is their sum.
            f, m, names = summed
            listed = ", ".join(sorted(names))
            said = (f"The statistics office's 1396 (2017-18) estimates of the settled "
                    f"population summed over the {len(names)} districts the boundary "
                    f"file draws in this province ({listed}): {f + m:,} ({m:,} males, "
                    f"{f:,} females). The office's own total for the province, "
                    f"{both:,}, is not this polygon's -- {'; '.join(apart[code])}. "
                    f"Afghanistan has had no census since 1979, and the {NOMADS:,} "
                    f"Kuchi nomads the office counts nationally are in no province.")
            fields = {
                "population": measure(f + m, year=YEAR, source=SOURCE),
                "population_note": said,
                "sex_ratio": measure(males_per_100(m, f), unit="males_per_100_females",
                                     year=YEAR, source=SOURCE),
                "sex_ratio_note": (f"1396 estimate, summed over the districts drawn "
                                   f"here: {m:,} males against {f:,} females.")}
        elif code in apart:
            reason = (f"Not written: the boundary file does not draw {shown(unit)} as the "
                      f"statistics office counts it -- {'; '.join(apart[code])} -- so the "
                      f"office's 1396 estimate for the province ({both:,} settled people, "
                      f"{male:,} males and {female:,} females) is not this polygon's. The "
                      f"districts drawn in it carry their own.")
            fields = {"population": gap(NOT_AVAILABLE, reason),
                      "sex_ratio": gap(NOT_AVAILABLE, reason)}
        else:
            fields = {
                "population": measure(both, year=YEAR, source=SOURCE),
                "population_note": (
                    f"The statistics office's estimate of the settled population for 1396 "
                    f"(2017-18), projected from the 2003-05 household listing: {both:,} "
                    f"({male:,} males, {female:,} females). Afghanistan has had no census "
                    f"since 1979. The {NOMADS:,} Kuchi nomads the office counts nationally "
                    f"are allocated to no province and are not in this figure."),
                "sex_ratio": measure(males_per_100(male, female), unit="males_per_100_females",
                                     year=YEAR, source=SOURCE),
                "sex_ratio_note": f"1396 estimate: {male:,} males against {female:,} females."}
        out.append(record(
            f"AFG-EST-{code}", unit["name"], level="admin1", parent="AFG", country="AFG",
            match_by="shape_id", shape_id=unit["id"],
            median_age=gap(NOT_AVAILABLE, AGE_GAP),
            sources=[{"field": "population/sex_ratio", "name": SOURCE, "url": URL,
                      "year": YEAR, "license": LICENCE}],
            **fields))
    return out


AGE_GAP = (
    "The statistics office publishes age only for the whole country -- its 1396 "
    "release's age workbook (\"گروپ سنین\") gives five-year groups by sex for the "
    "rural, urban and nomadic population of Afghanistan and for no province or "
    "district -- and Afghanistan has had no census since 1979. OCHA's 2021 "
    "provincial age table (cod-ps-afg) applies one national age structure to every "
    "province, so it measures nothing about any one of them.")


def temporary_note(names: list[str]) -> str:
    """What a drawn district's figures say about the temporary rows added in."""
    if not names:
        return ""
    # The sheet spells some in lower case ("zerko", "laja mangel").
    names = [n if any(c.isupper() for c in n) else n.title() for n in names]
    if len(names) == 1:
        return (f" Summed with {names[0]}, a temporary district the office counts "
                f"apart, cut from this one; the boundary file draws no polygon for it.")
    listed = ", ".join(names[:-1]) + " and " + names[-1]
    return (f" Summed with {listed}, temporary districts the office counts apart, "
            f"cut from this one; the boundary file draws no polygon for them.")


def district_records(rows: dict[str, dict[str, Any]], units1: list[dict[str, Any]],
                     units2: list[dict[str, Any]], counted_in: dict[str, str]
                     ) -> tuple[list[dict[str, Any]], dict[str, int]]:
    children: dict[str, list[str]] = {}
    for temp, parent in TEMPORARY_PARENT.items():
        if temp not in rows or not rows[temp]["temporary"]:
            raise SystemExit(f"afghanistan_estimates: {temp} is not a temporary district")
        children.setdefault(parent, []).append(temp)
    starred = {k for k, r in rows.items() if r["temporary"]}
    if starred - set(TEMPORARY_PARENT):
        raise SystemExit(f"afghanistan_estimates: temporary districts with no parent: "
                         f"{sorted(starred - set(TEMPORARY_PARENT))}")
    out = []
    tally = {"written": 0, "refused": 0}
    districts = drawn_districts(units1, units2)
    for unit, province, key in districts:
        if key not in rows:
            raise SystemExit(f"afghanistan_estimates: the 1396 table has no row {key}")
        parts = [rows[key]] + [rows[t] for t in children.get(key, ())]
        female = sum(sexes(p)[0] for p in parts)
        male = sum(sexes(p)[1] for p in parts)
        both = sum(sexes(p)[2] for p in parts)
        fields: dict[str, Any] = {}
        if key in SHIFTED:
            fields.update(population=gap(NOT_AVAILABLE, SHIFTED_NOTE),
                          sex_ratio=gap(NOT_AVAILABLE, SHIFTED_NOTE))
            tally["refused"] += 1
        else:
            said = (temporary_note([p["en"].strip() for p in parts[1:]])
                    + counted_in.get(key, ""))
            if key in MISPRINTED:
                fields["population"] = gap(NOT_AVAILABLE, "Not written: " + MISPRINTED[key])
            else:
                fields["population"] = measure(both, year=YEAR, source=SOURCE)
                fields["population_note"] = (
                    f"The statistics office's estimate of the settled population for 1396 "
                    f"(2017-18), projected from the 2003-05 household listing; Afghanistan "
                    f"has had no census since 1979.{said}")
            fields["sex_ratio"] = measure(males_per_100(male, female),
                                          unit="males_per_100_females", year=YEAR, source=SOURCE)
            fields["sex_ratio_note"] = (f"1396 estimate: {male:,} males against {female:,} "
                                        f"females.{said}")
            tally["written"] += 1
        out.append(record(
            f"AFG-EST-{key}", unit["name"], level="admin2", parent="AFG", country="AFG",
            match_by="shape_id", shape_id=unit["id"], parent_name=province,
            median_age=gap(NOT_AVAILABLE, AGE_GAP),
            sources=[{"field": "population/sex_ratio", "name": SOURCE, "url": URL,
                      "year": YEAR, "license": LICENCE}],
            **fields))
    left = sorted(set(rows) - {key for _u, _p, key in districts} - set(TEMPORARY_PARENT))
    if left:
        raise SystemExit(f"afghanistan_estimates: rows no polygon takes: {left}")
    return out, tally


def build(rows_: list[list[Any]], units1: list[dict[str, Any]],
          units2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary, blocks = read_sheet(rows_)
    placed = provinces_of(summary, blocks)
    rows = district_rows(placed)
    apart, counted_in = drawn_apart(units1, units2)
    sums = drawn_sums(rows, units1, units2)
    provinces = province_records(placed, units1, apart, sums)
    districts, tally = district_records(rows, units1, units2, counted_in)
    summed = sorted(code for code in apart if isinstance(sums.get(code), tuple))
    log(f"    {len(provinces) - len(apart)} provinces written as the office counts them, "
        f"{len(summed)} drawn otherwise written as the sum of the districts drawn in "
        f"them ({', '.join(summed)}), {len(apart) - len(summed)} not; "
        f"{tally['written']} districts written, {tally['refused']} refused with their reason")
    return provinces + districts


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    log("afghanistan_estimates: CSO estimated settled population 1396 (2017-18)")
    import openpyxl                                 # noqa: PLC0415
    blob = http_get(URL, binary=True)
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    if SHEET not in book.sheetnames:
        raise SystemExit(f"afghanistan_estimates: no sheet {SHEET!r}: {book.sheetnames}")
    rows_ = [list(r) for r in book[SHEET].iter_rows(values_only=True)]
    records = build(rows_, load_units("AFG", "admin1"), load_units("AFG", "admin2"))
    write_json(PROCESSED / OUT, records)
    log(f"  {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
