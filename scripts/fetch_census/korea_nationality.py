#!/usr/bin/env python3
"""South Korea: nationality as ethnicity, by province and district, by the owner's decision.

Korea's census asks no ethnicity question, and for as long as this map
read only what a census asks the seventeen provinces and 228 districts said
so (``NOT_COLLECTED_POLICY``, "South Korea's census does not collect
ethnicity"). What the state does count is nationality: every Korean
national is on the resident register, and every foreigner staying more
than ninety days registers with the immigration office under the
Immigration Act, by country of nationality. On 19 September 2026 the map's
owner decided that Korea's ethnicity field should carry that count as a
real composition under ``ethnicity_basis: "nationality"``, the way Japan's
prefectures carry their census's nationality table. This module is that
decision. It is a count, not a model: nothing here estimates anything.

**What is read.** Two registers, both at 31 December 2023.

* The Ministry of Justice's *registered foreign residents by district and
  nationality* (시군구별 국적(지역)별 등록외국인 체류현황), published on
  data.go.kr (dataset 15108413) as a zip of two cp949 CSVs, 2022 and 2023.
  The 2023 file has 500 rows: 250 units (the 시군구, with the districts of
  a city that has them -- 수원시 장안구 -- listed separately) by sex, and
  201 columns: 시도, 시군구, 성별, a total, and 196 nationalities from
  한국계중국인 to 기타. The reader sums the sexes, sums a city's districts
  into the city, and checks that every row's nationalities add up to its
  printed total.
* The Ministry of the Interior and Safety's *resident registration
  population by district* (주민등록 인구통계), the register of Korean
  nationals, for the same month, which is the "Korean" row and the
  denominator.

**What the labels mean.** "Korean" is everyone on the resident register:
naturalised citizens and people of any ancestry included. "Korean-Chinese"
is the immigration statistics' own category 한국계 중국인 -- Chinese
nationals of Korean descent, the 조선족 -- which the Ministry lists apart
from other Chinese nationals and this map keeps apart, because folding it
into "Chinese" would hide the largest foreign community in the country;
"Chinese" is every other Chinese national. The nationalities named are
those with at least ``NAMED_MIN`` registered residents nationally; the rest
are "Other nationalities".

**What is not counted.** Registered foreigners are those who registered
under Article 31 of the Immigration Act. Overseas Koreans of foreign
nationality living in Korea on a domestic residence report (국내거소신고,
the F-4 visa) are a separate register and are not in this file, nor are
short-term visitors or anyone undocumented; the resident register counts
Koreans, not foreigners. So the foreign share here is of *registered*
foreign residents, and runs below the share of all foreigners present.

**Checks.** The reader refuses to write anything if a row's nationalities
do not sum to its printed total, if the provinces do not sum to the
national total, if a unit's shares do not make 100 within
``SUM_TOLERANCE``, if any district the shape file draws is not matched, or
if the national foreign share is more than ``NATIONAL_TOLERANCE`` points
from the Ministry's published national total (``PUBLISHED``).

**Getting the files.** Neither host answers a runner reliably: data.go.kr's
file endpoint times out about as often as it answers, and the resident
register's form drops a connection every few requests. So what a run reads
is kept under ``data/raw/korea`` -- the .gitignore admits it -- and a later
run reads the copy. ``--fetch-only`` asks for whatever is not there yet and
stops, so a run that reaches a host banks the file even if another host is
down that minute; the reader itself then needs no network at all.

Usage:
    python -m scripts.fetch_census.korea_nationality
    python -m scripts.fetch_census.korea_nationality --fetch-only         # bank the sources
    python -m scripts.fetch_census.korea_nationality --inspect            # the MOJ zip
    python -m scripts.fetch_census.korea_nationality --inspect <url>      # any zipped CSV
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import urllib.parse
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, RAW, download, http_get, log, measure, record, write_json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import slugify  # noqa: E402

OUT = "korea_nationality.json"
DECISION = "19 September 2026"
YEAR = 2023
AS_OF = "31 December 2023"

# --- the Ministry of Justice: registered foreigners by district ------------
MOJ_DATASET = "https://www.data.go.kr/data/15108413/fileData.do"
MOJ_URL = ("https://www.data.go.kr/cmm/cmm/fileDownload.do"
           "?atchFileId=FILE_000000002903067&fileDetailSn=1&insertDataPrcus=N")
MOJ_MEMBER = "2023"
# Both hosts answer a runner about one request in two, the rest ending in
# a connect timeout, so what a run reads is kept under data/raw/korea (the
# .gitignore admits it) and a later run reads the copy.
KEEP = RAW / "korea"
MOJ_FILE = KEEP / "moj_registered_foreigners_by_district_2022_2023.zip"
MOJ_SOURCE = ("Ministry of Justice (Korea Immigration Service), registered foreign residents "
              "by city/county/district and nationality at 31 December 2023 "
              "(시군구별 국적(지역)별 등록외국인 체류현황, data.go.kr dataset 15108413)")
MOJ_LICENCE = "Korea Open Government License Type 1 (공공누리 제1유형): attribution"
ENCODING = "cp949"
COL_SIDO, COL_SIGUNGU, COL_SEX, COL_TOTAL = "시도", "시군구", "성별", "총합계"

# --- the Ministry of the Interior and Safety: the resident register --------
# The Ministry's resident-register site serves its monthly table through a
# form: a dozen fields posted to downloadCsv.do come back as a cp949 CSV of
# "행정구역 (code)", 총인구수 and 세대수. One request with the province
# level set to "A" lists the seventeen provinces and the national row; one
# request per province lists its districts. The data.go.kr copy of the
# same table (dataset 3033301) is offered on application only.
MOIS_DATASET = "https://jumin.mois.go.kr/statMonth.do"
MOIS_URL = "https://jumin.mois.go.kr/downloadCsv.do?searchYearMonth=month&xlsStats=1"
MOIS_SOURCE = ("Ministry of the Interior and Safety, resident registration population by "
               "city/county/district at December 2023 (주민등록 인구통계, jumin.mois.go.kr, "
               "주민등록 인구 및 세대현황, 2023년 12월)")
MOIS_LICENCE = MOJ_LICENCE
REGISTER_YEAR, REGISTER_MONTH = "2023", "12"
ALL = "A"
DISTRICT_TYPE = "2"

# --- the Ministry of Justice's own national figure -------------------------
# The Ministry publishes registered foreigners by nationality and year for
# the whole country as one long cp949 CSV (년, 국적지역, 등록외국인 수; 2011
# to 2025, some 195 nationalities a year). The 2023 rows are the published
# national total the district file is checked against: the foreign share
# rebuilt from the 250 units must sit within NATIONAL_TOLERANCE points of
# the population of the one the Ministry prints, or the district file is
# the wrong thing; a smaller difference is published and stated on every
# row, by the owner's instruction.
MOJ_NATIONAL_DATASET = "https://www.data.go.kr/data/15100019/fileData.do"
# The portal offers the same file by two routes -- its file endpoint, and
# the download servlet the dataset page's own button calls -- and each times
# out about as often as it answers. Both are tried, shortest first, rather
# than spending five ninety-second waits on one of them.
MOJ_NATIONAL_URL = ("https://www.data.go.kr/cmm/cmm/fileDownload.do"
                    "?atchFileId=FILE_000000003669729&fileDetailSn=1&insertDataPrcus=N")
MOJ_NATIONAL_URLS = (
    MOJ_NATIONAL_URL,
    "https://www.data.go.kr/tcs/dss/selectFileDataDownload.do?publicDataPk=15100019"
    "&publicDataDetailPk=uddi:ca4a9b96-e429-4272-bfc9-b6e0ef198841",
)
MOJ_NATIONAL_FILE = KEEP / "moj_registered_foreigners_by_nationality_by_year.csv"
MOJ_NATIONAL_SOURCE = ("Ministry of Justice, registered foreign residents by nationality by "
                       "year (연도별 등록외국인 국적(지역)별 현황, data.go.kr dataset 15100019)")
COL_YEAR, COL_NATIONALITY, COL_COUNT = "년", "국적지역", "등록외국인"
TOTAL_ROWS = {"총계", "합계", "계", "총합계", "전체"}
NATIONAL_TOLERANCE = 0.5     # points of the total population
SUM_TOLERANCE = 0.3          # points, a unit's shares against 100
NAMED_MIN = 10_000           # registered residents nationally, to be named

# The provinces as the file writes them, 2022 and 2023 spellings both, and
# as the boundary file names them.
SIDO: dict[str, str] = {
    "서울특별시": "Seoul", "부산광역시": "Busan", "대구광역시": "Daegu",
    "인천광역시": "Incheon", "광주광역시": "Gwangju", "대전광역시": "Daejeon",
    "울산광역시": "Ulsan", "세종특별자치시": "Sejong", "경기도": "Gyeonggi",
    "강원도": "Gangwon", "강원특별자치도": "Gangwon",
    "충청북도": "North Chungcheong", "충청남도": "South Chungcheong",
    "전라북도": "North Jeolla", "전북특별자치도": "North Jeolla",
    "전라남도": "South Jeolla", "경상북도": "North Gyeongsang",
    "경상남도": "South Gyeongsang", "제주특별자치도": "Jeju",
}

# Every district the boundary file draws: (province, the 시군구 as the file
# writes it) -> (the shape's name, the province the boundary file draws it
# under when that is not its own). The Korean key is the first word of the
# file's 시군구, so the districts of a city that has them (수원시 장안구,
# 수원시 권선구, ...) sum into the city the boundary file draws.
#
# geoBoundaries CGAZ files twenty of the 228 under the wrong province:
# Seoul's Eunpyeong-gu, four of Incheon's ten, four of Gwangju's five,
# Busan's Gangseo-gu, Gijang-gun and Yeongdo-gu, Daegu's Dalseong-gun and
# Gunwi-gun, Daejeon's Dong-gu, Gyeongbuk's Uljin-gun, Jeonnam's Sinan-gun
# and Incheon's Ongjin-gun (the last three under the country itself). The
# row's parent_name is the province the shape is drawn under, because that
# is the only way the join finds a Dong-gu among six, and the note says
# which province the district is actually part of. Jeonnam's Yeonggwang-gun
# has no shape at all.
DRAWN_ELSEWHERE: dict[tuple[str, str], str] = {
    ("Seoul", "Eunpyeong-gu"): "Gyeonggi",
    ("Incheon", "Seo-gu [West District]"): "Gyeonggi",
    ("Incheon", "Gyeyang-gu"): "Gyeonggi",
    ("Incheon", "Ganghwa-gun"): "Gyeonggi",
    ("Incheon", "Ongjin-gun"): "",
    ("Busan", "Gangseo-gu"): "South Gyeongsang",
    ("Busan", "Gijang-gun"): "South Gyeongsang",
    ("Busan", "Yeongdo-gu"): "",
    ("Daegu", "Dalseong-gun"): "North Gyeongsang",
    ("Daegu", "Gunwi-gun"): "North Gyeongsang",
    ("Gwangju", "Dong-gu [East District]"): "South Jeolla",
    ("Gwangju", "Seo-gu [West District]"): "South Jeolla",
    ("Gwangju", "Nam-gu [South District]"): "South Jeolla",
    ("Gwangju", "Gwangsan-gu"): "South Jeolla",
    ("Daejeon", "Dong-gu"): "North Chungcheong",
    ("North Gyeongsang", "Uljin-gun"): "Gangwon",
    ("South Jeolla", "Sinan-gun"): "",
}

DISTRICTS: dict[str, dict[str, str]] = {
    "Seoul": {
        "종로구": "Jongno-gu", "중구": "Jung-gu [Central District]", "용산구": "Yongsan-gu",
        "성동구": "Seongdong-gu", "광진구": "Gwangjin-gu", "동대문구": "Dongdaemun-gu",
        "중랑구": "Jungnang-gu", "성북구": "Seongbuk-gu", "강북구": "Gangbuk-gu",
        "도봉구": "Dobong-gu", "노원구": "Nowon-gu", "은평구": "Eunpyeong-gu",
        "서대문구": "Seodaemun-gu", "마포구": "Mapo-gu", "양천구": "Yangcheon-gu",
        "강서구": "Gangseo-gu", "구로구": "Guro-gu", "금천구": "Geumcheon-gu",
        "영등포구": "Yeongdeungpo-gu", "동작구": "Dongjak-gu", "관악구": "Gwanak-gu",
        "서초구": "Seocho-gu", "강남구": "Gangnam-gu", "송파구": "Songpa-gu",
        "강동구": "Gangdong-gu",
    },
    "Busan": {
        "중구": "Jung-gu [Central District]", "서구": "Seo-gu [West District]",
        "동구": "Dong-gu [East District]", "영도구": "Yeongdo-gu", "부산진구": "Busanjin-gu",
        "동래구": "Dongnae-gu", "남구": "Nam-gu [South District]",
        "북구": "Buk-gu [North Distrikt]", "해운대구": "Haeundae-gu", "사하구": "Saha-gu",
        "금정구": "Geumjeong-gu", "강서구": "Gangseo-gu", "연제구": "Yeonje-gu",
        "수영구": "Suyeong-gu", "사상구": "Sasang-gu", "기장군": "Gijang-gun",
    },
    "Daegu": {
        "중구": "Jung-gu [Central District]", "동구": "Dong-gu",
        "서구": "Seo-gu [West District]", "남구": "Nam-gu [South District]",
        "북구": "Buk-gu [North Distrikt]", "수성구": "Suseong-gu", "달서구": "Dalseo-gu",
        "달성군": "Dalseong-gun", "군위군": "Gunwi-gun",
    },
    "Incheon": {
        "중구": "Jung-gu [Central District]", "동구": "Dong-gu [East District]",
        "미추홀구": "Michuhol-gu [Nam-gu]", "연수구": "Yeonsu-gu", "남동구": "Namdong-gu",
        "부평구": "Bupyeong-gu", "계양구": "Gyeyang-gu", "서구": "Seo-gu [West District]",
        "강화군": "Ganghwa-gun", "옹진군": "Ongjin-gun",
    },
    "Gwangju": {
        "동구": "Dong-gu [East District]", "서구": "Seo-gu [West District]",
        "남구": "Nam-gu [South District]", "북구": "Buk-gu", "광산구": "Gwangsan-gu",
    },
    "Daejeon": {
        "동구": "Dong-gu", "중구": "Jung-gu", "서구": "Seo-gu", "유성구": "Yuseong-gu",
        "대덕구": "Daedeok-gu",
    },
    "Ulsan": {
        "중구": "Jung-gu [Central District]", "남구": "Nam-gu [South District]",
        "동구": "Dong-gu [East District]", "북구": "Buk-gu", "울주군": "Ulju-gun",
    },
    # Sejong is a province that is one city: it has no 시군구 at all, so the
    # Ministry's file writes a bare "0" in that column and the register
    # repeats the province's own name a level down.
    "Sejong": {"세종특별자치시": "Sejong-si"},
    "Gyeonggi": {
        "수원시": "Suwon-si", "성남시": "Seongnam-si", "고양시": "Goyang-si",
        "용인시": "Yongin-si", "안산시": "Ansan-si", "안양시": "Anyang-si",
        "부천시": "Bucheon-si", "광명시": "Gwangmyeong-si", "평택시": "Pyeongtaek-si",
        "동두천시": "Dongducheon-si", "의정부시": "Uijeongbu-si", "과천시": "Gwacheon-si",
        "구리시": "Guri-si", "남양주시": "Namyangju-si", "오산시": "Osan-si",
        "시흥시": "Siheung-si", "군포시": "Gunpo-si", "의왕시": "Uiwang-si",
        "하남시": "Hanam-si", "파주시": "Paju-si", "이천시": "Icheon-si",
        "안성시": "Anseong-si", "김포시": "Gimpo-si", "화성시": "Hwaseong-si",
        "양주시": "Yangju-si", "포천시": "Pocheon-si", "여주시": "Yeoju",
        "연천군": "Yeoncheon-gun", "가평군": "Gapyeong-gun", "양평군": "Yangpyeong-gun",
        "광주시": "Gwangju-si",
    },
    "Gangwon": {
        "춘천시": "Chuncheon-si", "원주시": "Wonju-si", "강릉시": "Gangneung-si",
        "동해시": "Donghae-si", "태백시": "Taebaek-si", "속초시": "Sokcho-si",
        "삼척시": "Samcheok-si", "홍천군": "Hongcheon-gun", "횡성군": "Hoengseong-gun",
        "영월군": "Yeongwol-gun", "평창군": "Pyeongchang-gun", "정선군": "Jeongseon-gun",
        "철원군": "Cheorwon-gun", "화천군": "Hwacheon-gun", "양구군": "Yanggu-gun",
        "인제군": "Inje-gun", "고성군": "Goseong-gun", "양양군": "Yangyang-gun",
    },
    "North Chungcheong": {
        "청주시": "Cheongju-si", "충주시": "Chungju-si", "제천시": "Jecheon-si",
        "보은군": "Boeun-gun", "옥천군": "Okcheon-gun", "영동군": "Yeongdong-gun",
        "증평군": "Jeungpyeong-gun", "진천군": "Jincheon-gun", "괴산군": "Goesan-gun",
        "음성군": "Eumseong-gun", "단양군": "Danyang-gun",
    },
    "South Chungcheong": {
        "천안시": "Cheonan-si", "공주시": "Gongju-si", "보령시": "Boryeong-si",
        "아산시": "Asan-si", "서산시": "Seosan-si", "논산시": "Nonsan-si",
        "계룡시": "Gyeryong-si", "당진시": "Dangjin-si", "금산군": "Geumsan-gun",
        "부여군": "Buyeo-gun", "서천군": "Seocheon-gun", "청양군": "Cheongyang-gun",
        "홍성군": "Hongseong-gun", "예산군": "Yesan-gun", "태안군": "Taean-gun",
    },
    "North Jeolla": {
        "전주시": "Jeonju-si", "군산시": "Gunsan-si", "익산시": "Iksan-si",
        "정읍시": "Jeongeup-si", "남원시": "Namwon-si", "김제시": "Gimje-si",
        "완주군": "Wanju-gun", "진안군": "Jinan-gun", "무주군": "Muju-gun",
        "장수군": "Jangsu-gun", "임실군": "Imsil-gun", "순창군": "Sunchang-gun",
        "고창군": "Gochang-gun", "부안군": "Buan-gun",
    },
    "South Jeolla": {
        "목포시": "Mokpo-si", "여수시": "Yeosu-si", "순천시": "Suncheon-si",
        "나주시": "Naju-si", "광양시": "Gwangyang-si", "담양군": "Damyang-gun",
        "곡성군": "Gokseong-gun", "구례군": "Gurye-gun", "고흥군": "Goheung-gun",
        "보성군": "Boseong-gun", "화순군": "Hwasun-gun", "장흥군": "Jangheung-gun",
        "강진군": "Gangjin-gun", "해남군": "Haenam-gun", "영암군": "Yeongam-gun",
        "무안군": "Muan-gun", "함평군": "Hampyeong-gun", "장성군": "Jangseong-gun",
        "완도군": "Wando-gun", "진도군": "Jindo-gun", "신안군": "Sinan-gun",
    },
    "North Gyeongsang": {
        "포항시": "Pohang-si", "경주시": "Gyeongju-si", "김천시": "Gimcheon-si",
        "안동시": "Andong-si", "구미시": "Gumi-si", "영주시": "Yeongju-si",
        "영천시": "Yeongcheon-si", "상주시": "Sangju-si", "문경시": "Mungyeong-si",
        "경산시": "Gyeongsan-si", "의성군": "Uiseong-gun", "청송군": "Cheongsong-gun",
        "영양군": "Yeongyang-gun", "영덕군": "Yeongdeok-gun", "청도군": "Cheongdo-gun",
        "고령군": "Goryeong-gun", "성주군": "Seongju-gun", "칠곡군": "Chilgok-gun",
        "예천군": "Yecheon-gun", "봉화군": "Bonghwa-gun", "울진군": "Uljin-gun",
        "울릉군": "Ulleung-gun",
        # Gunwi-gun was Gyeongbuk's until 1 July 2023; the 2022 file lists it
        # here and the 2023 file under Daegu.
        "군위군": "Gunwi-gun",
    },
    "South Gyeongsang": {
        "창원시": "Changwon-si", "진주시": "Jinju-si", "통영시": "Tongyeong-si",
        "사천시": "Sacheon-si", "김해시": "Gimhae-si", "밀양시": "Miryang-si",
        "거제시": "Geoje-si", "양산시": "Yangsan-si", "의령군": "Uiryeong-gun",
        "함안군": "Haman-gun", "창녕군": "Changnyeong-gun", "고성군": "Goseong-gun",
        "남해군": "Namhae-gun", "하동군": "Hadong-gun", "산청군": "Sancheong-gun",
        "함양군": "Hamyang-gun", "거창군": "Geochang-gun", "합천군": "Hapcheon-gun",
    },
    "Jeju": {"제주시": "Jeju-si", "서귀포시": "Seogwipo-si"},
}

# Units the file lists that the boundary file does not draw. They count
# towards their province and are not written on their own.
UNDRAWN: dict[tuple[str, str], str] = {
    ("South Jeolla", "영광군"): "Yeonggwang-gun",
}

# The file's nationality columns, in the map's words. A column not listed
# here is folded into "Other nationalities"; one that is listed but absent
# from the file is a refusal, because a spelling the Ministry changed is
# not a nationality that vanished. Both spellings are given where the
# Ministry has used both.
NATIONALITIES: dict[str, str] = {
    "한국계중국인": "Korean-Chinese", "한국계 중국인": "Korean-Chinese",
    "중국": "Chinese", "베트남": "Vietnamese", "태국": "Thai", "타이": "Thai",
    "우즈베키스탄": "Uzbek", "네팔": "Nepalese", "필리핀": "Filipino",
    "캄보디아": "Cambodian", "인도네시아": "Indonesian", "미국": "American",
    "미얀마": "Burmese", "스리랑카": "Sri Lankan", "몽골": "Mongolian",
    "일본": "Japanese", "러시아": "Russian", "러시아(연방)": "Russian",
    "러시아연방": "Russian", "카자흐스탄": "Kazakh", "방글라데시": "Bangladeshi",
    "파키스탄": "Pakistani", "대만": "Taiwanese", "타이완": "Taiwanese",
    "키르기즈": "Kyrgyz", "키르기스스탄": "Kyrgyz", "키르기즈스탄": "Kyrgyz",
    "캐나다": "Canadian", "인도": "Indian", "말레이시아": "Malaysian",
    "동티모르": "East Timorese", "티모르민주공화국": "East Timorese", "라오스": "Lao",
    "호주": "Australian",
    "영국": "British", "홍콩": "Hong Konger", "프랑스": "French", "독일": "German",
    "우크라이나": "Ukrainian", "나이지리아": "Nigerian", "이란": "Iranian",
    "타지키스탄": "Tajik", "튀르키예": "Turkish", "터키": "Turkish",
    "뉴질랜드": "New Zealander", "이집트": "Egyptian", "가나": "Ghanaian",
    "브라질": "Brazilian", "남아프리카공화국": "South African",
    "싱가포르": "Singaporean", "아프가니스탄": "Afghan", "이탈리아": "Italian",
    "스페인": "Spanish", "폴란드": "Polish", "아일랜드": "Irish",
}
OTHER = "Other nationalities"
KOREAN = "Korean"


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def members(blob: bytes) -> dict[str, bytes]:
    """{member name decoded as cp949: bytes} for every CSV in a zip; a bare
    CSV comes back as one member called "-"."""
    if not zipfile.is_zipfile(io.BytesIO(blob)):
        return {"-": blob}
    archive = zipfile.ZipFile(io.BytesIO(blob))
    out: dict[str, bytes] = {}
    for info in archive.infolist():
        # zipfile decodes a name without the UTF-8 flag as cp437; the bytes
        # the Ministry wrote are cp949.
        raw = (info.filename.encode("utf-8") if info.flag_bits & 0x800
               else info.filename.encode("cp437", "replace"))
        name = raw.decode(ENCODING, "replace")
        if name.lower().endswith(".csv"):
            out[name] = archive.read(info)
    return out


def rows_of(data: bytes, encoding: str = ENCODING) -> list[list[str]]:
    text = data.decode(encoding, "replace").lstrip("﻿")
    return [[c.strip() for c in row] for row in csv.reader(io.StringIO(text, newline=""))]


def number(cell: str) -> int:
    cell = cell.replace(",", "").strip()
    if cell in ("", "-"):
        return 0
    return int(cell)


def column(header: list[str], name: str) -> int:
    hits = [i for i, h in enumerate(header) if h.replace(" ", "").startswith(name)]
    if len(hits) != 1:
        raise SystemExit(f"korea_nationality: {len(hits)} columns start with {name!r}: "
                         f"{header[:6]}")
    return hits[0]


def read_moj(table: list[list[str]]) -> dict[tuple[str, str], dict[str, int]]:
    """{(province, first word of the 시군구): {column: count}}, sexes summed.

    Every row's nationalities must add up to its printed total, and every
    province must be one the file is known to write; either failing is a
    different file from the one this was written for.
    """
    header = table[0]
    i_sido, i_gu, i_sex = column(header, COL_SIDO), column(header, COL_SIGUNGU), column(header, COL_SEX)
    i_total = column(header, COL_TOTAL)
    first = max(i_sido, i_gu, i_sex, i_total) + 1
    nationalities = header[first:]
    if nationalities[-1:] != ["기타"] or "한국계중국인" not in [n.replace(" ", "") for n in nationalities]:
        raise SystemExit(f"korea_nationality: {len(nationalities)} nationality columns after "
                         f"{header[:first]}, ending {nationalities[-3:]}; not the Ministry's file")
    out: dict[tuple[str, str], dict[str, int]] = {}
    for row in table[1:]:
        if len(row) < len(header) or not row[i_sido]:
            continue
        sido = row[i_sido].strip()
        if sido not in SIDO:
            raise SystemExit(f"korea_nationality: unknown province {sido!r}")
        counts = {n: number(c) for n, c in zip(nationalities, row[first:])}
        total = number(row[i_total])
        if sum(counts.values()) != total:
            raise SystemExit(f"korea_nationality: {sido} {row[i_gu]} {row[i_sex]}: nationalities "
                             f"sum to {sum(counts.values()):,} against a printed {total:,}")
        gu = row[i_gu].split()
        # Sejong has no 시군구 and the file writes a zero in that column; the
        # unit is the province itself, keyed by the province's name so that
        # the register's row for the same ground matches it.
        key = (SIDO[sido], gu[0] if gu and gu[0] != "0" else sido)
        unit = out.setdefault(key, Counter())
        unit.update(counts)
        unit["__total__"] += total
    return {k: dict(v) for k, v in out.items()}


AREA = re.compile(r"^(.*?)\s*\((\d{10})\)\s*$")


def register_rows(table: list[list[str]]) -> list[tuple[str, str, int]]:
    """(area name, ten-digit code, population) for every row of one of the
    register's CSVs, whose first column is "행정구역 (code)" and whose
    population is the column headed 총인구수."""
    header = table[0]
    i_area = next((i for i, h in enumerate(header) if "행정구역" in h), 0)
    totals = [i for i, h in enumerate(header) if "총인구수" in h]
    if not totals:
        raise SystemExit(f"korea_nationality: no 총인구수 column in {header[:6]}")
    out = []
    for row in table[1:]:
        if len(row) <= max(i_area, totals[0]):
            continue
        found = AREA.match(row[i_area].strip())
        if not found:
            continue
        out.append((" ".join(found.group(1).split()), found.group(2), number(row[totals[0]])))
    return out


def read_register(tables: list[list[list[str]]]) -> dict[tuple[str, str], int]:
    """{(province, district as the register writes it): Korean nationals},
    with the province's own row under (province, "") and the national row
    under ("", ""), from the register's province listing and its per-province
    listings.

    A city's own districts (수원시 장안구, code 4111100000) are listed beside
    the city (4111000000) and are skipped: the city's row already carries
    them, and it is the city the boundary file draws. They are told from an
    ordinary district by naming three levels -- province, city, district --
    where a district of a province names two, and Sejong, a province that is
    one city, names one. The codes do not say it: 증평군 is 4374500000, a
    county of its own with a non-zero fifth digit sitting beside 영동군 at
    4374000000, and reading the code as a parent's dropped a county of
    37,484 people out of North Chungcheong.
    """
    out: dict[tuple[str, str], int] = {}
    for table in tables:
        for area, code, count in register_rows(table):
            words = area.split()
            if code[2:] == "00000000":
                key = ("", "") if words[0] == "전국" else (SIDO[words[0]], "")
                if words[0] != "전국" and words[0] not in SIDO:
                    raise SystemExit(f"korea_nationality: unknown province {area!r}")
            else:
                if code[5:] != "00000":
                    continue                        # an 읍면동
                if len(words) > 2:
                    continue                        # a district of a city
                if words[0] not in SIDO:
                    raise SystemExit(f"korea_nationality: {area!r} names no province")
                # Sejong's one district is the city itself, and the register
                # writes the province's name again a level down rather than a
                # district name; every other district row names its province
                # and then itself.
                if len(words) < 2 and SIDO[words[0]] != "Sejong":
                    raise SystemExit(f"korea_nationality: {area!r} names no district")
                key = (SIDO[words[0]], words[1] if len(words) > 1 else words[0])
            if key in out and out[key] != count:
                raise SystemExit(f"korea_nationality: {area} appears twice in the register")
            out[key] = count
    return out


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------

def named(national: dict[str, int]) -> list[str]:
    """The file's columns that are named on the map: those in NATIONALITIES
    with at least NAMED_MIN registered residents nationally. A column in the
    table but absent from the file is a refusal."""
    columns = [c for c in national if c not in ("__total__", "koreans")]
    present = {c.replace(" ", "") for c in columns}
    missing = [k for k in ("한국계중국인", "중국", "베트남", "미국") if k not in present]
    if missing:
        raise SystemExit(f"korea_nationality: the file has no column for {missing}")
    out = [c for c in columns if c in NATIONALITIES and national[c] >= NAMED_MIN]
    unnamed = sorted(((national[c], c) for c in columns
                      if c not in NATIONALITIES and c != "기타" and national[c] >= NAMED_MIN),
                     reverse=True)
    if unnamed:
        raise SystemExit("korea_nationality: nationalities above the naming threshold with no "
                         f"label: {unnamed}")
    return out


def composition(foreign: dict[str, int], koreans: int, names: list[str]
                ) -> list[dict[str, Any]]:
    """Counts by label, Koreans first, shares to one decimal summing to 100.0
    by largest remainder, largest first, name breaking a tie; zero rows are
    dropped."""
    counts: dict[str, int] = {KOREAN: koreans}
    for col in names:
        label = NATIONALITIES[col]
        counts[label] = counts.get(label, 0) + foreign.get(col, 0)
    other = foreign["__total__"] - sum(foreign.get(col, 0) for col in names)
    if other < 0:
        raise SystemExit("korea_nationality: the named nationalities exceed the total")
    counts[OTHER] = other
    total = sum(counts.values())
    if total <= 0:
        return []
    items = [(g, c, c / total * 1000) for g, c in counts.items() if c > 0]
    floors = [int(v) for _, _, v in items]
    order = sorted(range(len(items)), key=lambda i: -(items[i][2] - floors[i]))
    for i in order[:1000 - sum(floors)]:
        floors[i] += 1
    out = [{"group": g, "pct": floors[i] / 10, "count": c} for i, (g, c, _) in enumerate(items)]
    out.sort(key=lambda r: (-r["pct"], r["group"]))
    return out


def check(units: dict[tuple[str, str], dict[str, int]], register: dict[tuple[str, str], int]
          ) -> tuple[dict[str, dict[str, int]], dict[str, int], dict[str, int]]:
    """The two files against each other and against the published total.

    Returns the provinces' foreign counts by column, the provinces' Korean
    counts, and the national row (foreign columns plus "koreans").
    """
    provinces: dict[str, dict[str, int]] = {}
    for (province, _), counts in units.items():
        row = provinces.setdefault(province, Counter())
        row.update(counts)
    if set(provinces) != set(SIDO.values()):
        raise SystemExit(f"korea_nationality: the file has {len(provinces)} provinces: "
                         f"{sorted(provinces)}")
    koreans: dict[str, int] = {}
    for province in provinces:
        if (province, "") not in register:
            raise SystemExit(f"korea_nationality: the register has no row for {province}")
        koreans[province] = register[(province, "")]
        parts = sum(register[k] for k in register if k[0] == province and k[1])
        if parts and abs(parts - koreans[province]) > 0:
            raise SystemExit(f"korea_nationality: {province}: the register's districts sum to "
                             f"{parts:,} against the province's own {koreans[province]:,}")
    national: dict[str, int] = dict(sum((Counter(v) for v in provinces.values()), Counter()))
    national["koreans"] = sum(koreans.values())
    if ("", "") in register and register[("", "")] != national["koreans"]:
        raise SystemExit(f"korea_nationality: the provinces' Koreans sum to "
                         f"{national['koreans']:,} against the register's national "
                         f"{register[('', '')]:,}")
    log(f"  national: {national['__total__']:,} registered foreigners against "
        f"{national['koreans']:,} Koreans "
        f"({national['__total__'] / (national['__total__'] + national['koreans']) * 100:.2f}%)")
    return {p: dict(v) for p, v in provinces.items()}, koreans, national


def read_national(table: list[list[str]], year: int = YEAR) -> dict[str, int]:
    """{nationality: registered foreigners} for ``year`` from the Ministry's
    national by-year table, total rows left out."""
    header = table[0]
    i_year = column(header, COL_YEAR)
    i_nat = column(header, COL_NATIONALITY)
    i_count = column(header, COL_COUNT)
    out: dict[str, int] = {}
    for row in table[1:]:
        if len(row) <= max(i_year, i_nat, i_count) or row[i_year].strip() != str(year):
            continue
        label = row[i_nat].strip()
        if label in TOTAL_ROWS:
            continue
        out[label] = out.get(label, 0) + number(row[i_count])
    if not out:
        raise SystemExit(f"korea_nationality: the national table has no rows for {year}")
    return out


def published_caveat(national: dict[str, int], published: dict[str, int]) -> str:
    """The district file's national row against the Ministry's published one.

    Refuses when the foreign share of the population they give differ by
    more than NATIONAL_TOLERANCE points. Returns the sentence that states a
    smaller difference, or "" when the two agree exactly.
    """
    koreans = national["koreans"]
    districts = national["__total__"]
    total = sum(published.values())
    share = districts / (districts + koreans) * 100
    printed = total / (total + koreans) * 100
    if abs(share - printed) > NATIONAL_TOLERANCE:
        raise SystemExit(f"korea_nationality: the district file's {districts:,} registered "
                         f"foreigners ({share:.2f}%) are {abs(share - printed):.2f} points from "
                         f"the Ministry's national {total:,} ({printed:.2f}%); not the same "
                         "register")
    by_label: dict[str, int] = {}
    for label, count in published.items():
        by_label[NATIONALITIES.get(label, OTHER)] = by_label.get(NATIONALITIES.get(label, OTHER), 0) + count
    ours: dict[str, int] = {}
    for col, count in national.items():
        if col in ("__total__", "koreans"):
            continue
        ours[NATIONALITIES.get(col, OTHER)] = ours.get(NATIONALITIES.get(col, OTHER), 0) + count
    drift = sorted(((abs(ours.get(k, 0) - v) / v, k, ours.get(k, 0), v)
                    for k, v in by_label.items() if v >= NAMED_MIN), reverse=True)
    log(f"  published: the Ministry's national table gives {total:,} registered foreigners "
        f"({printed:.2f}%) against the district file's {districts:,} ({share:.2f}%)")
    for rel, label, mine, theirs in drift[:5]:
        log(f"      {label:18} districts {mine:>9,}  national {theirs:>9,}  ({rel * 100:.1f}% apart)")
    if districts == total:
        return ""
    return (f"The Ministry's national table for the same date counts {total:,} registered "
            f"foreigners ({printed:.1f}% of the population) where the district file sums to "
            f"{districts:,} ({share:.1f}%), so the foreign share here runs about "
            f"{printed - share:.1f} points below the national figure.")


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

def note_for(name: str, province: str | None, drawn_under: str | None,
             caveat: str = "") -> str:
    where = ("this district" if province else "this province")
    placement = f" {caveat}" if caveat else ""
    if drawn_under is not None:
        under = drawn_under or "the country itself"
        placement += (f" The boundary file draws {name} under {under}; it is a district of "
                      f"{province}, and is counted in {province}'s row here.")
    return (
        f"Registered foreign residents by country of nationality at {AS_OF} (Ministry of "
        "Justice, 시군구별 국적(지역)별 등록외국인 체류현황) against the resident-registered "
        f"Korean population of the same date (Ministry of the Interior and Safety, 주민등록 "
        f"인구통계): NATIONALITY, not ethnicity, which Korea's census does not ask. 'Korean' "
        "is everyone on the resident register, naturalised citizens and people of any "
        "ancestry included; 'Korean-Chinese' is the immigration statistics' own category "
        "한국계 중국인, Chinese nationals of Korean descent, kept apart from other Chinese "
        "nationals as the Ministry lists them. Registered foreigners are those staying over "
        "ninety days who registered under the Immigration Act; overseas Koreans of foreign "
        "nationality on a domestic residence report (F-4), short-term visitors and the "
        f"undocumented are not counted, so the foreign share of {where} runs below the share "
        f"of all foreigners present.{placement} Written by the map owner's decision of "
        f"{DECISION}.")


def build(units: dict[tuple[str, str], dict[str, int]], register: dict[tuple[str, str], int],
          published: dict[str, int] | None = None) -> list[dict[str, Any]]:
    provinces, koreans, national = check(units, register)
    caveat = published_caveat(national, published) if published else ""
    names = named(national)
    log(f"  named: {', '.join(dict.fromkeys(NATIONALITIES[c] for c in names))}")
    sources = [{"field": "ethnicity", "name": MOJ_SOURCE, "url": MOJ_DATASET, "year": YEAR,
                "license": MOJ_LICENCE},
               {"field": "ethnicity", "name": MOIS_SOURCE, "url": MOIS_DATASET, "year": YEAR,
                "license": MOIS_LICENCE}]
    if published:
        sources.append({"field": "ethnicity", "name": MOJ_NATIONAL_SOURCE + ", the national "
                        "check", "url": MOJ_NATIONAL_DATASET, "year": YEAR,
                        "license": MOJ_LICENCE})
    records: list[dict[str, Any]] = []
    for province in SIDO.values():
        if any(r["name"] == province for r in records):
            continue
        shares = composition(provinces[province], koreans[province], names)
        total = sum(r["pct"] for r in shares)
        if abs(total - 100.0) > SUM_TOLERANCE:
            raise SystemExit(f"korea_nationality: {province}: shares sum to {total}")
        population = koreans[province] + provinces[province]["__total__"]
        records.append(record(
            f"KOR-{slugify(province)}", province, level="admin1", parent="KOR", country="KOR",
            sources=sources,
            population=measure(population, year=YEAR,
                               source="resident-registered Koreans plus registered foreigners"),
            ethnicity=shares, ethnicity_year=YEAR, ethnicity_basis="nationality",
            ethnicity_note=note_for(province, None, None, caveat)))
    matched: set[tuple[str, str]] = set()
    unmatched: list[str] = []
    for (province, word), counts in sorted(units.items()):
        shape = DISTRICTS.get(province, {}).get(word)
        if shape is None:
            if (province, word) in UNDRAWN:
                log(f"  {province} {word} ({UNDRAWN[(province, word)]}): no shape; counted in "
                    f"the province only")
                continue
            unmatched.append(f"{province} {word}")
            continue
        if (province, word) not in register:
            raise SystemExit(f"korea_nationality: the register has no row for {province} {word}")
        drawn_under = DRAWN_ELSEWHERE.get((province, shape))
        shares = composition(counts, register[(province, word)], names)
        total = sum(r["pct"] for r in shares)
        if abs(total - 100.0) > SUM_TOLERANCE:
            raise SystemExit(f"korea_nationality: {shape}: shares sum to {total}")
        population = register[(province, word)] + counts["__total__"]
        records.append(record(
            f"KOR-{slugify(province)}-{slugify(shape)}", shape, level="admin2",
            parent=f"KOR-{slugify(province)}",
            parent_name=(drawn_under if drawn_under else province) if drawn_under is not None
            else province,
            country="KOR", sources=sources,
            population=measure(population, year=YEAR,
                               source="resident-registered Koreans plus registered foreigners"),
            ethnicity=shares, ethnicity_year=YEAR, ethnicity_basis="nationality",
            ethnicity_note=note_for(shape, province, drawn_under, caveat)))
        matched.add((drawn_under if drawn_under is not None else province, shape))
    if unmatched:
        raise SystemExit(f"korea_nationality: units the boundary table does not know: {unmatched}")
    drawn = {(DRAWN_ELSEWHERE.get((p, s), p), s) for p, table in DISTRICTS.items()
             for s in table.values()}
    missing = sorted(drawn - matched)
    if missing:
        raise SystemExit(f"korea_nationality: shapes with no row in the file: {missing}")
    return records


# ---------------------------------------------------------------------------
# Inspection and entry point
# ---------------------------------------------------------------------------

def inspect(url: str, rows: int, width: int, encoding: str) -> None:
    blob = http_get(url, binary=True, cache=False)
    assert isinstance(blob, bytes)
    log(f"inspect: {url} ({len(blob):,} bytes)")
    for name, data in members(blob).items():
        table = rows_of(data, encoding)
        log(f"\n=== {name}: {len(table):,} rows, {len(table[0]) if table else 0} columns")
        if not table:
            continue
        header = table[0]
        log(f"  first columns: {header[:width]}")
        log(f"  last columns: {header[-6:]}")
        for row in table[1:rows + 1]:
            log(f"  {row[:width]} ... {row[-3:]}")
        for col in range(min(3, len(header))):
            values = Counter(r[col] for r in table[1:] if len(r) > col)
            log(f"  column {col} {header[col]!r}: {len(values)} distinct; "
                f"{list(values.items())[:70]}")


def fetch_moj() -> list[list[str]]:
    blob = download(MOJ_URL, MOJ_FILE, timeout=90).read_bytes()
    if not zipfile.is_zipfile(io.BytesIO(blob)):
        MOJ_FILE.unlink()
        raise SystemExit(f"korea_nationality: {MOJ_URL} answered {len(blob):,} bytes that are "
                         "not the zip; the copy is discarded")
    found = members(blob)
    name = next((n for n in found if MOJ_MEMBER in n), None)
    if name is None:
        raise SystemExit(f"korea_nationality: no {MOJ_MEMBER} member in {sorted(found)}")
    log(f"  {name}: {len(found[name]):,} bytes")
    return rows_of(found[name])


def register_fields(level1: str, level2: str = ALL, *, districts: bool = False
                    ) -> list[tuple[str, str]]:
    """The form's fields for one month, as its page posts them (the runner's
    probe of statMonth.do printed the inputs): the province level, the
    district level ("A" for every district of the province), the month at
    both ends of the range, and the register's default of every resident
    (sltUndefType blank). ``sltOrgType`` is the level the listing is made
    at: 1 lists provinces, DISTRICT_TYPE a province's districts."""
    return [
        ("tableId", "month"), ("category", "month"), ("searchYearMonth", "month"),
        ("sltOrgType", DISTRICT_TYPE if districts else "1"),
        ("sltOrgLvl1", level1), ("sltOrgLvl2", level2),
        ("searchYearStart", REGISTER_YEAR), ("searchMonthStart", REGISTER_MONTH),
        ("searchYearEnd", REGISTER_YEAR), ("searchMonthEnd", REGISTER_MONTH),
        ("sltUndefType", ""), ("sltOrderType", "1"), ("sltOrderValue", "ASC"),
        ("nowYear", "2026"),
    ]


def post_csv(url: str, fields: list[tuple[str, str]], *, keep: Path | None = None,
             retries: int = 3, timeout: int = 45) -> list[list[str]]:
    """POST a form and read the CSV it answers with, cp949 as the site writes
    it whatever its header claims. A body that is not a CSV (the site's
    error page is HTML) is a refusal, printed. With ``keep``, the answer is
    written there and a file already there is read instead of asking."""
    import time
    import urllib.request
    from common import USER_AGENT
    if keep is not None and keep.exists() and keep.stat().st_size > 0:
        return rows_of(keep.read_bytes())
    data = urllib.parse.urlencode(fields).encode()
    delay = 3.0
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers={
                "User-Agent": USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                blob = resp.read()
                ctype = resp.headers.get("Content-Type", "")
            break
        except Exception as exc:  # pragma: no cover - network shape varies
            last = exc
            if attempt < retries:
                log(f"  retry {attempt + 1}/{retries} after {delay:.0f}s :: {last}")
                time.sleep(delay)
                delay *= 2
    else:
        raise SystemExit(f"korea_nationality: the register did not answer: {last}")
    if b"<html" in blob[:400].lower() or "html" in ctype:
        text = blob.decode(ENCODING, "replace")
        reason = re.findall(r"<li>([^<]{0,120})</li>", text)
        raise SystemExit(f"korea_nationality: the register answered a page, not a CSV: "
                         f"{reason[-1:] or text[:200]!r}")
    table = rows_of(blob)
    if keep is not None and register_rows(table):
        keep.parent.mkdir(parents=True, exist_ok=True)
        keep.write_bytes(blob)
    return table


def kept(name: str) -> Path:
    return KEEP / f"jumin_{REGISTER_YEAR}{REGISTER_MONTH}_{name}.csv"


def fetch_register(url: str) -> list[list[list[str]]]:
    """The province listing, then every province's district listing."""
    provinces = post_csv(url, register_fields(ALL), keep=kept("provinces"))
    listed = [(area, code) for area, code, _ in register_rows(provinces) if area != "전국"]
    log(f"  register: {len(listed)} provinces listed")
    if len(listed) != 17:
        raise SystemExit(f"korea_nationality: the register lists {len(listed)} provinces: "
                         f"{[a for a, _ in listed]}")
    tables = [provinces]
    for area, code in listed:
        table = post_csv(url, register_fields(code, districts=True),
                         keep=kept(f"districts_{code}"))
        rows = register_rows(table)
        if len(rows) < 2:
            raise SystemExit(f"korea_nationality: the register lists no districts for {area}")
        log(f"    {area}: {len(rows)} rows")
        tables.append(table)
    return tables


def fetch_national() -> list[list[str]]:
    """The Ministry's national by-year table, from the kept copy or from
    whichever of the portal's two download routes answers.

    The file is 53 KB and both routes time out about half the time, so each
    is given a short wait and the other is tried rather than one being
    waited on five times over. What answers is kept, and a later run reads
    the copy.
    """
    if MOJ_NATIONAL_FILE.exists() and MOJ_NATIONAL_FILE.stat().st_size > 0:
        log(f"  cached {MOJ_NATIONAL_FILE.name} "
            f"({MOJ_NATIONAL_FILE.stat().st_size / 1e3:.0f} kB)")
        return rows_of(MOJ_NATIONAL_FILE.read_bytes())
    last = ""
    for url in MOJ_NATIONAL_URLS:
        try:
            blob = http_get(url, binary=True, cache=False, retries=2, timeout=45)
        except Exception as exc:  # pragma: no cover - network shape varies
            log(f"  {url.split('?')[0]} did not answer: {exc}")
            last = str(exc)
            continue
        assert isinstance(blob, bytes)
        table = rows_of(blob)
        if not table or COL_YEAR not in table[0][0]:
            log(f"  {url.split('?')[0]} answered {len(blob):,} bytes that are not the "
                f"national table: {table[0][:4] if table else blob[:60]!r}")
            last = "not the national table"
            continue
        MOJ_NATIONAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        MOJ_NATIONAL_FILE.write_bytes(blob)
        log(f"  fetched {MOJ_NATIONAL_FILE.name} ({len(blob):,} bytes)")
        return table
    raise SystemExit("korea_nationality: neither download route served the Ministry's "
                     f"national table: {last}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inspect", nargs="?", const=MOJ_URL, default=None, metavar="URL",
                    help="print the shape of a zipped or bare CSV release and stop")
    ap.add_argument("--rows", type=int, default=8)
    ap.add_argument("--width", type=int, default=8)
    ap.add_argument("--encoding", default=ENCODING)
    ap.add_argument("--register", default=MOIS_URL, help="the resident register's form URL")
    ap.add_argument("--fetch-only", action="store_true",
                    help="fetch whatever is not yet under data/raw/korea and stop")
    args = ap.parse_args()
    if args.inspect:
        inspect(args.inspect, args.rows, args.width, args.encoding)
        return 0
    if args.fetch_only:
        # Each source on its own, so one host being down this minute does not
        # throw away what another just answered: the runner commits
        # data/raw either way, and the next run reads the copies.
        failed = []
        for what, fetch in (("the Ministry of Justice's district file", fetch_moj),
                            ("the resident register", lambda: fetch_register(args.register)),
                            ("the Ministry's national table", fetch_national)):
            try:
                fetch()
                log(f"  have {what}")
            except Exception as exc:
                log(f"  {what} did not answer: {exc}")
                failed.append(what)
        if failed:
            raise SystemExit(f"korea_nationality: still missing {', '.join(failed)}")
        return 0
    log(f"korea_nationality: {MOJ_SOURCE}")
    units = read_moj(fetch_moj())
    log(f"  {len(units)} units in 17 provinces")
    register = read_register(fetch_register(args.register))
    log(f"  register: {len(register)} rows, {register.get(('', ''), 0):,} nationally")
    published = read_national(fetch_national())
    log(f"  published: {len(published)} nationalities for {YEAR}")
    records = build(units, register, published)
    log(f"  {sum(1 for r in records if r['level'] == 'admin1')} provinces, "
        f"{sum(1 for r in records if r['level'] == 'admin2')} districts")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    sys.exit(main())
