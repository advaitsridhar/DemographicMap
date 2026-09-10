"""Mali's RGPH5 annex tables are landscape pages stored upside down: every
cell comes out of pdfplumber mirrored, wrapped cells come out in fragments,
and the rows come out bottom-up with a region's name in the row of its
figures or the row after. These fixtures are the cells exactly as the runner
printed them for Tableau 5 (ethnie), Tableau 6 (langue maternelle) and the
page after it that carries Tableau 6's populations.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import mali  # noqa: E402


def rows(block: str) -> list[list[str]]:
    # The runner printed each row as its cells joined by " | ", so a row whose
    # first cell is empty starts with " | " and the pipes must not be stripped.
    return [[c.strip() for c in line.split("|")] for line in block.strip("\n").splitlines()]


TABLEAU_5 = """
ecnedisér⏎ed⏎noigéR |  |  | 39,53 | 24,8 | 38,21 | 97,4 | 71,8 | 71,1 | 30,4 | 90,6 | 60,1 | 19,3 | 61,2 | 74,0 | 53,5 | 60,0 | 56,0 | 09,1 | 06,0 | 73,0 | 83,0 | 33,0 | 71,1 | 61,0 | 00,001 | 100212 81 |
 | mesnE | elb |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  | 28,24 | 89,9 | 05,21 | 09,3 | 02,01 | 58,0 | 06,2 | 35,5 | 76,0 | 43,0 | 40,2 | 47,0 | 05,2 | 50,0 | 33,0 | 14,1 | 50,0 | 73,0 | 26,0 | 14,0 | 76,1 | 24,0 | 00,001 | 47614 69 |
 | amaB | ok |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  | 68,2 | 40,0 | 01,0 | 69,4 | 20,0 | 00,0 | 10,0 | 12,0 | 74,0 | 76,27 | 01,0 | 10,0 | 20,0 | 58,0 | 60,0 | 20,0 | 64,2 | 10,0 | 40,0 | 97,0 | 32,41 | 70,0 | 0,001 0 | 53422 3 |
 | anéM | ak |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  | 33,3 | 20,0 | 80,0 | 49,2 | 10,0 | 20,0 | 40,0 | 90,0 | 12,13 | 58,01 | 50,0 | 10,0 | 00,0 | 40,0 | 40,0 | 40,0 | 39,05 | 50,0 | 42,0 | 00,0 | 10,0 | 00,0 | 00,001 | 85299 |
 | éduoaT | tin |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 | ladiK |  | 45,5 | 30,0 | 20,0 | 83,1 | 50,0 | 10,0 | 30,0 | 52,0 | 66,3 | 1,68 8 | 50,0 | 00,0 | 00,0 | 10,0 | 00,0 | 00,0 | 22,2 | 00,0 | 14,0 | 00,0 | 41,0 | 20,0 | ,001 00 | 6575 9 |
 | oaG |  | 55,3 | 90,0 | 50,2 | 01,45 | 90,0 | 20,0 | 80,0 | 02,0 | 82,0 | 17,23 | 50,0 | 00,0 | 40,0 | 21,0 | 70,0 | 05,0 | 08,5 | 30,0 | 01,0 | 10,0 | 80,0 | 30,0 | 0,001 0 | 9276 20 |
 |  |  | 05,4 | 11,0 | 23,4 | 87,93 | 12,0 | 50,0 | 40,0 | 32,0 | 97,1 | 83,34 | 50,0 | 10,0 | 30,0 | 80,0 | 10,0 | 22,1 | 17,3 | 90,0 | 11,0 | 30,0 | 32,0 | 20,0 | 00,001 | 442196 |
 | tcuobmoT | uo |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  | 03,01 | 03,0 | 96,22 | 55,7 | 54,0 | 60,0 | 90,0 | 30,05 | 53,0 | 46,5 | 50,0 | 10,0 | 80,0 | 50,0 | 40,0 | 14,0 | 82,0 | 95,0 | 40,0 | 20,0 | 39,0 | 40,0 | 00,001 | 097641 |
 | tneuoD | az |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  | 82,3 | 80,0 | 96,0 | 23,0 | 22,0 | 10,0 | 41,0 | 83,39 | 90,0 | 41,0 | 50,0 | 60,0 | 60,0 | 30,0 | 01,0 | 51,0 | 00,0 | 11,1 | 00,0 | 10,0 | 70,0 | 10,0 | 00,001 | 376617 |
 | gaidnaB | ara |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 | itpoM |  | 69,91 | 04,2 | 33,82 | 72,9 | 20,4 | 51,0 | 93,0 | 18,7 | 91,0 | 56,3 | 28,0 | 13,0 | 15,0 | 41,0 | 44,0 | 81,81 | 60,0 | 70,1 | 70,0 | 09,0 | 22,1 | 11,0 | 0,001 0 | 8638 56 |
 | naS |  | 43,13 | 08,1 | 69,5 | 18,0 | 74,2 | 40,0 | 84,0 | 33,4 | 31,0 | 13,0 | 99,82 | 85,4 | 83,51 | 40,0 | 41,0 | 35,1 | 20,0 | 25,0 | 51,0 | 72,0 | 06,0 | 11,0 | 0,001 0 | 7218 32 |
 | uogéS |  | 27,55 | 54,2 | 76,21 | 37,1 | 46,5 | 11,0 | 85,0 | 57,2 | 95,0 | 10,1 | 80,1 | 23,0 | 91,5 | 70,0 | 33,0 | 88,4 | 20,0 | 62,1 | 23,0 | 01,1 | 20,2 | 61,0 | 00,001 | 89912 89 |
 |  |  | 29,02 | 46,2 | 00,6 | 46,0 | 33,1 | 80,0 | 95,1 | 40,2 | 71,0 | 61,0 | 17,4 | 96,0 | 00,75 | 50,0 | 52,0 | 84,0 | 10,0 | 22,0 | 40,0 | 70,0 | 08,0 | 11,0 | 00,001 | 59411 08 |
 | aituoK | al |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  | 05,46 | 94,5 | 13,12 | 23,0 | 97,0 | 50,0 | 63,1 | 68,1 | 70,0 | 60,0 | 73,0 | 70,0 | 37,1 | 10,0 | 80,0 | 50,1 | 10,0 | 70,0 | 30,0 | 90,0 | 16,0 | 70,0 | 00,001 | 080651 7 |
 | oguoB | inu |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  | 64,72 | 77,1 | 61,11 | 77,0 | 01,1 | 51,0 | 66,24 | 98,1 | 90,0 | 21,0 | 99,0 | 13,0 | 50,3 | 30,0 | 56,6 | 74,0 | 00,0 | 21,0 | 40,0 | 31,0 | 39,0 | 11,0 | 00,001 | 48151 18 |
 | sakiS | os |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 | araN |  | 78,91 | 41,1 | 40,12 | 13,0 | 24,14 | 51,0 | 01,0 | 21,0 | 38,41 | 90,0 | 50,0 | 30,0 | 21,0 | 40,0 | 10,0 | 90,0 | 00,0 | 20,0 | 42,0 | 20,0 | 82,0 | 30,0 | 00,001 | 377672 |
 |  |  | 44,17 | 96,1 | 66,81 | 63,0 | 69,1 | 60,0 | 75,0 | 94,1 | 62,0 | 90,0 | 92,0 | 41,0 | 85,0 | 10,0 | 50,0 | 72,0 | 10,0 | 90,0 | 81,0 | 71,0 | 94,1 | 41,0 | 0,001 0 | 3376 23 |
 | lioiD | a |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  | 38,85 | 80,41 | 30,01 | 51,1 | 34,6 | 42,0 | 97,0 | 53,2 | 75,0 | 21,0 | 00,1 | 61,0 | 01,1 | 20,0 | 21,0 | 36,0 | 20,0 | 61,0 | 17,0 | 34,0 | 29,0 | 41,0 | 00,001 | 336322 4 |
 | okiluoK | or |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 | oroiN |  | 79,71 | 76,1 | 82,52 | 73,0 | 64,34 | 05,2 | 61,0 | 51,0 | 54,6 | 90,0 | 50,0 | 90,0 | 41,0 | 30,0 | 30,0 | 01,0 | 20,0 | 21,0 | 79,0 | 20,0 | 22,0 | 11,0 | 0,001 0 | 2566 20 |
 | atiK |  | 91,52 | 50,94 | 95,51 | 72,0 | 39,2 | 55,0 | 24,0 | 12,0 | 54,0 | 60,0 | 51,0 | 51,0 | 17,1 | 10,0 | 20,0 | 32,0 | 00,0 | 80,0 | 29,1 | 40,0 | 09,0 | 70,0 | 0,001 0 | 0976 41 |
 | seyaK |  | 48,41 | 33,52 | 64,61 | 14,0 | 35,72 | 87,9 | 55,0 | 94,0 | 44,1 | 70,0 | 12,0 | 60,0 | 68,0 | 50,0 | 90,0 | 06,0 | 00,0 | 21,0 | 82,0 | 11,0 | 65,0 | 61,0 | 00,001 | 84181 52 |
einhtE |  |  | arabmaB/nanamaB | éknilaM/eknilaM | hlueP | Z/iahrnoS/yahgnoS⏎amra | élokaraS/ékninoS | eknossahK | ofuonéS | nogoD | eruaM/akaruoS | gerauoT/qehsamaT | oboB/awB/oB | gnifaD | aknainiM/alamaM | assuoaH | ogomaS | ozoB | ebarA | issoM | olokaK | onomoS | ilaM⏎ud⏎einhte⏎ertuA | non⏎einhte⏎enneilam⏎ertuA | % |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | itceffE | f
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | lbmesnE⏎e |  |
"""

TABLEAU_6 = """
ecnedisér⏎ed⏎noigéR | latoT |  | 09,94 | 01,7 | 91,8 | 85,4 | 35,6 | 01,1 | 38,2 | 34,5 | 29,0 | 58,3 | 39,1 | 10,0 | 13,0 | 80,4 | 50,0 | 23,0 | 35,0 | 14,1 | 24,0 | 12,0 | 11,0 | 11,0 | 80,0
 |  |  | 84,66 | 19,5 | 06,6 | 50,3 | 76,6 | 45,0 | 50,1 | 71,4 | 91,0 | 62,0 | 25,1 | 10,0 | 93,0 | 21,1 | 30,0 | 02,0 | 71,0 | 57,0 | 20,0 | 51,0 | 62,0 | 03,0 | 61,0
 | amaB | ok |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  | 49,2 | 52,0 | 81,0 | 55,4 | 20,0 | 10,0 | 00,0 | 02,0 | 55,0 | 58,47 | 31,0 | 10,0 | 10,0 | 20,0 | 58,0 | 00,0 | 14,0 | 12,0 | 32,2 | 92,01 | 01,2 | 60,0 | 31,0
 | néM | aka |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  | 03,4 | 52,0 | 80,0 | 23,3 | 20,0 | 10,0 | 20,0 | 21,0 | 67,44 | 46,41 | 60,0 | 30,0 | 40,0 | 10,0 | 30,0 | 10,0 | 92,2 | 30,0 | 83,92 | 20,0 | 45,0 | 40,0 | 00,0
 | duoaT | tiné |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  | 54,6 | 61,0 | 40,0 | 04,1 | 25,1 | 30,0 | 30,0 | 02,0 | 70,5 | 9,28 3 | 41,0 | 10,0 | 00,0 | 10,0 | 00,0 | 00,0 | 11,0 | 10,0 | 67,1 | 10,0 | 10,0 | 30,0 | 80,0
 | diK | la |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 | oaG |  | 68,3 | 92,0 | 88,0 | 39,45 | 90,0 | 40,0 | 40,0 | 92,0 | 96,0 | 16,23 | 01,0 | 10,0 | 00,0 | 50,0 | 41,0 | 60,0 | 63,0 | 84,0 | 97,4 | 50,0 | 61,0 | 60,0 | 20,0
 |  |  | 07,4 | 22,0 | 99,3 | 86,14 | 71,0 | 40,0 | 20,0 | 81,0 | 60,2 | 65,24 | 90,0 | 10,0 | 20,0 | 40,0 | 70,0 | 51,0 | 52,0 | 48,0 | 67,2 | 50,0 | 20,0 | 70,0 | 10,0
 | uobmoT | uotc |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  | 70,21 | 85,0 | 91,42 | 63,7 | 83,0 | 50,0 | 70,0 | 48,74 | 23,0 | 35,5 | 90,0 | 10,0 | 20,0 | 40,0 | 42,0 | 14,0 | 50,0 | 83,0 | 12,0 | 80,0 | 40,0 | 20,0 | 20,0
 | euoD | aztn |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  | 42,5 | 21,0 | 99,0 | 92,0 | 52,0 | 10,0 | 90,0 | 59,09 | 11,0 | 41,0 | 50,0 | 10,0 | 22,0 | 20,0 | 40,0 | 20,1 | 60,0 | 03,0 | 00,0 | 40,0 | 20,0 | 10,0 | 20,0
 | aidnaB | arag |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  | 01,72 | 23,1 | 80,92 | 90,9 | 83,1 | 80,0 | 91,0 | 45,6 | 81,0 | 13,3 | 95,0 | 20,0 | 81,0 | 61,0 | 80,0 | 62,1 | 82,0 | 17,81 | 70,0 | 62,0 | 80,0 | 30,0 | 10,0
 | tpoM | i |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 | naS |  | 74,34 | 37,1 | 98,3 | 05,0 | 25,0 | 20,0 | 71,0 | 07,3 | 40,0 | 62,0 | 41,82 | 90,0 | 35,3 | 97,21 | 20,0 | 23,0 | 60,0 | 05,0 | 10,0 | 11,0 | 20,0 | 50,0 | 60,0
 |  |  | 57,97 | 59,0 | 16,6 | 61,1 | 78,1 | 50,0 | 71,0 | 07,1 | 32,0 | 18,0 | 37,0 | 10,0 | 02,0 | 58,1 | 20,0 | 90,1 | 01,0 | 74,2 | 10,0 | 70,0 | 50,0 | 50,0 | 50,0
 | ogéS | u |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  | 07,13 | 34,3 | 47,3 | 94,0 | 37,0 | 50,0 | 09,0 | 46,1 | 60,0 | 11,0 | 64,4 | 50,0 | 44,0 | 13,15 | 40,0 | 71,0 | 02,0 | 82,0 | 00,0 | 50,0 | 30,0 | 40,0 | 80,0
 | ituoK | ala |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  | 87,28 | 39,4 | 53,6 | 52,0 | 62,0 | 30,0 | 48,0 | 27,1 | 30,0 | 40,0 | 23,0 | 00,0 | 50,0 | 32,1 | 10,0 | 90,0 | 40,0 | 19,0 | 00,0 | 10,0 | 20,0 | 50,0 | 40,0
 | guoB | inuo |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  | 58,64 | 62,1 | 49,5 | 26,0 | 65,0 | 70,0 | 85,33 | 06,1 | 40,0 | 90,0 | 08,0 | 00,0 | 81,0 | 59,1 | 20,0 | 21,0 | 37,5 | 03,0 | 00,0 | 70,0 | 50,0 | 80,0 | 90,0
 | sakiS | os |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 | araN |  | 88,91 | 47,0 | 45,02 | 03,0 | 11,24 | 31,0 | 70,0 | 01,0 | 55,51 | 80,0 | 70,0 | 30,0 | 50,0 | 50,0 | 80,0 | 40,0 | 00,0 | 60,0 | 30,0 | 20,0 | 40,0 | 20,0 | 10,0
 |  |  | 58,98 | 48,0 | 28,5 | 22,0 | 39,0 | 30,0 | 51,0 | 13,1 | 40,0 | 70,0 | 42,0 | 00,0 | 30,0 | 52,0 | 10,0 | 30,0 | 20,0 | 50,0 | 00,0 | 10,0 | 10,0 | 60,0 | 30,0
 | lioiD | a |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  | 87,86 | 80,31 | 14,7 | 58,0 | 67,4 | 51,0 | 23,0 | 39,1 | 52,0 | 01,0 | 28,0 | 10,0 | 01,0 | 75,0 | 20,0 | 31,0 | 70,0 | 73,0 | 20,0 | 80,0 | 50,0 | 70,0 | 60,0
 | kiluoK | oro |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  | 95,02 | 91,1 | 26,42 | 14,0 | 94,34 | 95,2 | 01,0 | 01,0 | 37,5 | 81,0 | 40,0 | 00,0 | 80,0 | 80,0 | 40,0 | 12,0 | 20,0 | 80,0 | 10,0 | 81,0 | 20,0 | 71,0 | 70,0
 | roiN | o |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 | atiK |  | 42,24 | 30,84 | 83,5 | 61,0 | 14,1 | 64,0 | 02,0 | 31,0 | 21,0 | 30,0 | 01,0 | 00,0 | 01,0 | 63,1 | 10,0 | 10,0 | 10,0 | 80,0 | 00,0 | 60,0 | 10,0 | 50,0 | 50,0
 |  |  | 32,91 | 63,42 | 28,41 | 73,0 | 61,72 | 59,9 | 13,0 | 04,0 | 32,1 | 50,0 | 71,0 | 00,0 | 40,0 | 76,0 | 70,0 | 81,0 | 50,0 | 54,0 | 00,0 | 42,0 | 70,0 | 90,0 | 90,0
 | eyaK | s |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
ellenretam⏎eugnaL |  |  | namaB/arabmaB⏎nakna | akninaM/éknilaM⏎nak | edlufluF/hlueP | yohgnoS/iahrnoS⏎amraZ/ | kninooS/elokaraS⏎e | sahX/éknossahK⏎nakaknos | araneyS/ofuonéS | ôsôgôD/nogoD | ayinasaH/eruaM | qehsamaT | umoB/oboB | erebanuK | gnifaD | ramaM/aknainiM⏎a | assuoaH | éroM/issoM | oognuD/ogomaS⏎am | okayT/ozoB | ebarA | ud⏎eugnal⏎ertuA⏎ilaM | eugnal⏎eniacirfa⏎ertuA | eugnal⏎erègnarté⏎ertuA | non⏎eugnal⏎eniacirfa⏎ertuA
"""

TABLEAU_6_TOTALS = """
ecnedisér⏎ed⏎noigéR | latoT |  | 00,001 | 44191 336
 | amaB⏎ok |  | 0,001 0 | 7973 994
 | néM aka |  | 0,001 0 | 4302 11
 | duoaT⏎tiné |  | 00,001 | 35329
 | diK⏎la |  | ,001 00 | 127 36
 | oaG |  | 0,001 0 | 6906 70
 | uobmoT | uotc | 00,001 | 668436
 |  |  |  |
 |  |  | 0,001 0 | 1431 72
 | euoD | aztn |  |
 | aidnaB⏎arag |  | 00,001 | 63646 9
 | tpoM⏎i |  | 0,001 0 | 3367 97
 | naS |  | 0,001 0 | 7437 80
 | ogéS⏎u |  | 0,001 0 | 5891 507
 | ituoK⏎ala |  | 0,001 0 | 7201 992
 | guoB⏎inuo |  | 00,001 | 0931 311
 | sakiS⏎os |  | 0,001 0 | 0631 446
 | araN |  | 0,001 0 | 5742 94
 | lioiD⏎a |  | 0,001 0 | 1606 20
 | kiluoK⏎oro |  | 00,001 | 4002 853
 | roiN⏎o |  | 0,001 0 | 5695 83
 | atiK |  | 0,001 0 | 2995 48
 | eyaK⏎s |  | 0,001 0 | 8361 855
ellenretam⏎eugnaL |  |  | elbmesnE | fitceffE
"""

TABLEAU_2_03 = """INSTAT-BCR-Résultats du RGPH5
Tableau 2.03 : Répartition (effectif & en %) de la population résidente par religion
selon la région
Musulman Chrétien Animiste Sans
religion
Kayes 98,75 0,70 0,03 0,42 0,10 100,00 1 826 564
Kita 98,80 0,86 0,04 0,27 0,03 100,00 680 380
Nioro 99,70 0,11 0,01 0,14 0,04 100,00 668 966
Koulikoro 95,32 2,14 0,74 1,44 0,36 100,00 2 246 154
Dioïla 98,48 1,08 0,03 0,39 0,02 100,00 674 419
Nara 99,65 0,19 0,15 0,01 0,00 100,00 278 904
Sikasso 96,30 1,50 0,93 1,04 0,23 100,00 1 528 398
Bougouni 98,89 0,93 0,04 0,11 0,03 100,00 1 567 533
Koutiala 91,57 4,32 3,14 0,62 0,35 100,00 1 153 375
Ségou 98,52 1,29 0,04 0,13 0,02 100,00 2 208 847
San 70,10 16,99 8,33 3,65 0,93 100,00 815 185
Mopti 99,10 0,84 0,01 0,04 0,01 100,00 842 209
Bandiagara 93,96 5,99 0,04 0,00 0,01 100,00 720 279
Douentza 99,64 0,34 0,01 0,00 0,01 100,00 147 229
Tombouctou 99,67 0,31 0,00 0,02 0,00 100,00 693 719
Gao 99,51 0,47 0,01 0,00 0,01 100,00 679 911
Kidal 99,64 0,29 0,01 0,02 0,04 100,00 79 324
Taoudenni 99,81 0,18 0,00 0,00 0,01 100,00 99 499
Ménaka 99,67 0,30 0,02 0,00 0,01 100,00 225 223
Bamako 97,58 2,32 0,01 0,06 0,03 100,00 4 211 468
Ensemble 96,45 2,27 0,65 0,50 0,13 100,00 21 347 587
"""


class MirroredCellsReadTheRightWayRound(unittest.TestCase):
    def test_flip(self):
        self.assertEqual(mali.flip("8361 855"), "1638558")
        self.assertEqual(mali.flip("0,001 0"), "100,00")
        self.assertEqual(mali.flip(",001 00"), "100,00")
        self.assertEqual(mali.flip("1,68 8"), "86,18")
        self.assertEqual(mali.flip("arabmaB/nanamaB"), "Bamanan/Bambara")
        self.assertEqual(mali.flip("ilaM⏎ud⏎einhte⏎ertuA"), "MaliduethnieAutre")
        self.assertEqual(mali.key("ilaM⏎ud⏎einhte⏎ertuA"), mali.key("Autre ethnie du Mali"))


class AnnexTablesAreReadBottomUp(unittest.TestCase):
    def test_ethnicity_table(self):
        got = mali.read_annex(rows(TABLEAU_5), mali.ETHNICITIES)
        self.assertEqual(len(got), 21)                      # 20 regions + Ensemble
        pop, pcts = got["Kayes"]
        self.assertEqual(pop, 1814825)
        self.assertEqual(pcts["Bambara"], 14.84)
        self.assertEqual(pcts["Khassonke"], 9.78)
        self.assertEqual(got["Kidal"][1]["Tuareg"], 86.18)  # the wrapped "1,68 8"
        self.assertEqual(got["Kidal"][0], 57569)      # "6575 9"
        self.assertEqual(got["Bamako"][0], 4167496)
        self.assertEqual(got["Ensemble"][0], 21200118)
        self.assertEqual(got["Tombouctou"][1]["Songhai/Zarma"], 39.78)
        checked = mali.checked("ethnicity", got)
        self.assertEqual(len(checked), 20)

    def test_language_table_and_its_populations(self):
        got = mali.read_annex(rows(TABLEAU_6), mali.LANGUAGES)
        self.assertEqual(len(got), 21)
        self.assertIsNone(got["Kayes"][0])
        self.assertEqual(got["Kayes"][1]["Bambara"], 19.23)
        self.assertEqual(got["Kidal"][1]["Tamasheq"], 82.93)  # the wrapped "9,28 3"
        totals = mali.read_annex(rows(TABLEAU_6_TOTALS), {})
        self.assertEqual(totals["Kayes"][0], 1638558)
        self.assertEqual(totals["Douentza"][0], 134127)
        self.assertEqual(totals["Ensemble"][0], 19144633)
        for region in got:
            got[region] = (totals[region][0], got[region][1])
        checked = mali.checked("language", got)
        self.assertEqual(len(checked), 20)

    def test_a_population_in_the_wrong_cell_is_refused(self):
        got = mali.read_annex(rows(TABLEAU_5), mali.ETHNICITIES)
        got["Bamako"] = (416749, got["Bamako"][1])            # a digit dropped
        with self.assertRaises(SystemExit):
            mali.checked("ethnicity", got)


class TwentyRegionsSumIntoNineShapes(unittest.TestCase):
    def test_build(self):
        text = "front matter\f" + TABLEAU_2_03
        religion = mali.checked("religion", dict(mali.religion_rows(text)))
        ethnicity = mali.checked("ethnicity", mali.read_annex(rows(TABLEAU_5), mali.ETHNICITIES))
        language = mali.read_annex(rows(TABLEAU_6), mali.LANGUAGES)
        totals = mali.read_annex(rows(TABLEAU_6_TOTALS), {})
        for region in list(language):
            language[region] = (totals[region][0], language[region][1])
        language = mali.checked("language", language)
        records = mali.build({"religion": religion, "ethnicity": ethnicity,
                              "language": language})
        self.assertEqual([r["name"] for r in records],
                         ["Bamako", "Gao", "Kayes", "Kidal", "Koulikoro", "Mopti",
                          "Sikasso", "Ségou", "Tombouctou"])
        by = {r["name"]: r for r in records}
        self.assertEqual(by["Koulikoro"]["aliases"], ["Koulikouro"])
        kayes = by["Kayes"]
        self.assertAlmostEqual(sum(b["count"] for b in kayes["religion"]),
                               1826564 + 680380 + 668966, delta=5)
        self.assertEqual(kayes["religion"][0]["group"], "Islam")
        self.assertEqual(kayes["ethnicity"][0]["group"], "Soninke")
        self.assertEqual(by["Kidal"]["ethnicity"][0], {"group": "Tuareg", "pct": 86.2, "count": 49612})
        self.assertIn("Kayes, Kita, Nioro", kayes["ethnicity_note"])
        self.assertNotIn("This shape is", by["Kidal"]["language_note"])
        self.assertEqual(by["Ségou"]["language"][0]["group"], "Bambara")


if __name__ == "__main__":
    unittest.main()
