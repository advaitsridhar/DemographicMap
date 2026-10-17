"""Burkina Faso's 2019 census monograph of the Boucle du Mouhoun as the runner
printed its page (one token a line), and its list of tables."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import burkina_provinces as bp  # noqa: E402

CONTENTS = 'Tableau 2.3: Répartition (%) des effectifs de la population par province selon le sexe\n................................ 13\n'

PAGE = 'La répartition des effectifs de population\npar\nprovince indique que l\na province du\nMouhoun est la\nplus peuplée avec 391 561 habitants\n,\ntandis que le Nayala demeure la moins peuplée avec 223 151\nhabitants.\nA l’image de la région,\nles femmes sont plus nombreuses que les hommes au niveau des différentes\nprovinces à l’exception de la Kossi où le rapport de masculinité indique 103 hommes pour 100\nfemmes.\nLa province du Sourou compte autant d’hommes que de femmes.\nAu niveau régional, ce\nrapport est de 99 hommes pour 100 femmes (tableau 2.3).\nTableau\n2\n.\n3\n: Répartition (%) des effectifs de la population par province selon le sexe\nProvince\nSexe\nPoids de chaque\nProvince (%)\nRapport de\nmasculini\nté\nHomme\nFemme\nEnsemble\nBalé\n148\n040\n149\n428\n297\n468\n15,6\n99\nBanwa\n169\n820\n177\n169\n346\n989\n18,3\n96\nKossi\n180\n802\n176\n287\n357\n089\n18,8\n103\nMouhoun\n194\n617\n196\n944\n391\n561\n20,6\n99\nNayala\n110\n674\n112\n477\n223\n151\n11,7\n98\nSourou\n142\n230\n142\n781\n285\n011\n15,0\n100\nEnsemble\n946\n183\n955\n086\n1\n901\n269\n100\n99\nAu niveau des communes, Solenzo demeure la plus peuplée avec une proportion de 8,4% de la\npopulation\nde\nla région. Elle est suivie de Dédougou avec 6,5% de la population. Son\no\net Madouba\nsont les communes les moins peuplées de la région\navec un poids démographique de 0,5%.\nLes rapports de masculinité varient d’une commune à l’autre et se situent à 99 hommes pour 100\nfemmes dans l’ensemble de la région (tableau 2.4).\n\n'


class BurkinaProvinces(unittest.TestCase):
    def test_table(self):
        names = ["Bale", "Banwa", "Kossi", "Mouhoun", "Nayala", "Sourou"]
        table = bp.province_table(CONTENTS + PAGE, names)
        self.assertEqual(table["Bale"], (148_040, 149_428, 297_468))
        self.assertEqual(table["Sourou"], (142_230, 142_781, 285_011))
        self.assertEqual(sum(v[2] for v in table.values()), 1_901_269)

    def test_missing_province(self):
        with self.assertRaises(SystemExit):
            bp.province_table(PAGE, ["Bale", "Tapoa"])


if __name__ == "__main__":
    unittest.main()
