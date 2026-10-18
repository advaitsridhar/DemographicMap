"""São Tomé and Príncipe's 2012 census reports as the runner printed their pages (no network)."""

import unittest

from scripts.fetch_census import sao_tome_census as st

# The national report's Quadro 2: the district names are set sideways down
# each block, so they reach the text a letter or two at a time.
QUADRO_2 = 'Resultados Nacionais do IV Recenseamento Geral da População e da Habitação 2012\nQuadro 2: População recensea da segundo situação de residência e distrito por tipo de alojamento\nCondição Total Alojamentos particulares Alojamentos coletivos\nde residência Total Homem Mulher Total Homem Mulher Total Homem Mulher\nPopulação total recenseada\n(RP+RA+V) 73.091 35.632 37.459 72.312 35.079 37.233 779 553 226\ne\nd Residente Presente (RP) 66.722 32.009 34.713 66.430 31.814 34.616 292 195 97\nn\na\ng r Residente Ausentes (RA) 3.050 1.796 1.254 3.024 1.774 1.250 26 22 4\n- u a Visitas (Presente não Residente) (V) 3.319 1.827 1.492 2.858 1.491 1.367 461 336 125\ng\nÁ\nPopulação Residente (RP+RA) 69.772 33.805 35.967 69.454 33.588 35.866 318 217 101\n% População residente por sexo 100 48,5 51,5 100 48,4 51,6 100 68,2 31,8\nPopulação total recenseada\n(RP+RA+V) 20.007 10.233 9.774 19.950 10.177 9.773 57 56 212\nResidente Presente (RP) 18.772 9.447 9.325 18.723 9.398 9.325 49 49 1\na\nat\nResidente Ausentes (RA) 642 436 206 642 436 206 0 0 0\nb\no\nL Visitas (Presente não Residente) (V) 593 350 243 585 343 242 8 7 211\nPopulação Residente (RP+RA) 19.414 9.883 9.531 19.365 9.834 9.531 49 49 1\n% População residente por sexo 100 50,9 49,1 100 50,8 49,2 100 100,0 0,0\nPopulação total recenseada\n(RP+RA+V) 18.194 9.295 8.899 18.178 9.288 8.890 16 7 9\no Residente Presente (RP) 16.715 8.466 8.249 16.707 8.464 8.243 8 2 6\nal\na g Residente Ausentes (RA) 454 288 166 454 288 166 0 0 0\nnt\na Visitas (Presente não Residente) (V) 1.025 541 484 1.017 536 481 8 5 3\nC\nPopulação Residente (RP+RA) 17.169 8.754 8.415 17.161 8.752 8.409 8 2 6\n% População residente por sexo 100 51,0 49,0 100 51,0 49,0 100 25,0 75,0\nPopulação total recenseada\n(RP+RA+V) 15.370 8.004 7.366 15.323 7.980 7.343 47 24 23\nResidente Presente (RP) 14.197 7.265 6.932 14.173 7.250 6.923 24 15 9\ná\nm b Residente Ausentes (RA) 479 314 165 479 314 165 0 0 0\ne\nL Visitas (Presente não Residente) (V) 694 425 269 671 416 255 23 9 14\nPopulação Residente (RP+RA) 14.676 7.579 7.097 14.652 7.564 7.088 24 15 9\n% População residente por sexo 100 51,6 48,4 100 51,6 48,4 100 62,5 37,5\nPopulação total recenseada\n(RP+RA+V) 6.887 3.603 3.284 6.772 3.547 3.225 115 56 59\nResidente Presente (RP) 5.974 3.100 2.874 5.943 3.080 2.863 31 20 11\né\nu Residente Ausentes (RA) 88 54 34 88 54 34 0 0 0\na\nC\nVisitas (Presente não Residente) (V) 825 449 376 741 413 328 84 36 48\nPopulação Residente (RP+RA) 6.062 3.154 2.908 6.031 3.134 2.897 31 20 11\n% População residente por sexo 100 52,0 48,0 100 52,0 48,0 100 64,5 35,5\nPopulação total recenseada\n(RP+RA+V) 46.265 23.074 23.191 46.241 23.054 23.187 24 20 4\nhi Residente Presente (RP) 43.629 21.547 22.082 43.618 21.540 22.078 11 7 4\nc\nZ ó Residente Ausentes (RA) 1.134 710 424 1.134 710 424 0 0 0\nM\n-é\nVisitas (Presente não Residente) (V) 1.502 817 685 1.489 804 685 13 13 0\nPopulação Residente (RP+RA) 44.763 22.257 22.506 44.752 22.250 22.502 11 7 4\n% População residente por sexo 100 49,7 50,3 100 49,7 50,3 100 63,6 36,4\nPopulação total recenseada\n(RP+RA+V) 7.542 3.891 3.651 7.467 3.846 3.621 75 45 30\ne\nci p Residente Presente (RP) 7.171 3.654 3.517 7.152 3.645 3.507 19 9 10\nn\nrí Residente Ausentes (RA) 173 101 72 172 100 72 1 1 0\nP\nA. Visitas (Presente não Residente) (V) 198 136 62 143 101 42 55 35 20\nR.\nPopulação Residente (RP+RA) 7.344 3.755 3.589 7.324 3.745 3.579 20 10 10\n% População residente por sexo 100 51,1 48,9 100 51,1 48,9 100 50,0 50,0\nInstituto Nacional de Estatística de São Tomé e Príncipe, 2013 21'

# Água Grande's report: Quadro 5 (page 27), Quadro 6 (pages 28-30) and
# Quadro 10 (pages 36-38), rows rebuilt from the words' positions.
AGUA_GRANDE = ['Resultado Distrital do IV Recenseamento Geral da População e da Habitação 2012\nQuadro 5: Repartição da população residente segundo sexo por grupos etários quinquenais\nGrupos Água-Grande\nEtários Total Homem Mulher\nTotal 69.454 33.588 35.866\n0-4 anos 10.463 5.265 5.198\n5-9 anos 9.218 4.649 4.569\n10-14 anos 7.939 3.850 4.089\n15-19 anos 7.004 3.417 3.587\n20-24 anos 6.430 3.049 3.381\n25-29 anos 6.241 2.933 3.308\n30-34 anos 5.175 2.488 2.687\n35-39 anos 3.843 1.840 2.003\n40-44 anos 3.155 1.537 1.618\n45-49 anos 2.610 1.240 1.370\n50-54 anos 2.277 1.059 1.218\n55-59 anos 1.633 745 888\n60-64 anos 1.050 522 528\n65-69 anos 727 329 398\n70-74 anos 655 266 389\n75-79 anos 470 196 274\n80 e + anos 564 203 361\nInstituto Nacional de Estatística de São Tomé e Príncipe, 2013\n27', 'Resultado Distrital do IV Recenseamento Geral da População e da Habitação 2012\nQuadro 6: Repartição da população residente segundo sexo e grupos etários por Religião\nGrupos Religião\nAssembléia Católica Apostólica Deus é\nTotal Adventista Jeová Maná\nEtários de Deus Romana amor\nTotal de Água-\nGrande 69.454 3.241 1.752 39.888 651 1.030 2.094\n0-4 anos 10.463 505 270 5.070 130 115 339\n5-9 anos 9.218 469 221 5.085 105 138 271\n10-14 anos 7.939 393 217 4.723 70 146 224\n15-19 anos 7.004 393 195 3.989 67 110 235\n20-24 anos 6.430 414 190 3.401 61 96 233\n25-29 anos 6.241 325 172 3.401 65 91 225\n30-34 anos 5.175 218 112 3.019 42 73 184\n35-39 anos 3.843 149 91 2.364 28 66 96\n40-44 anos 3.155 98 77 1.994 29 44 81\n45-49 anos 2.610 61 59 1.713 25 31 69\n50-54 anos 2.277 60 49 1.502 11 35 50\n55-59 anos 1.633 49 29 1.149 5 19 35\n60-64 anos 1.050 21 18 743 5 10 19\n65-69 anos 727 26 13 523 1 9 11\n70-74 anos 655 22 14 483 3 14 7\n75-79 anos 470 21 14 327 3 9 6\n80 e + anos 564 17 11 402 1 24 9\nTotal Homem 33.588 1.592 824 18.390 295 483 892\n0-4 anos 5.265 269 134 2.523 58 58 162\n5-9 anos 4.649 227 117 2.565 53 68 131\n10-14 anos 3.850 200 104 2.181 29 65 102\n15-19 anos 3.417 180 74 1.827 33 66 113\n20-24 anos 3.049 217 95 1.497 29 40 91\n25-29 anos 2.933 165 85 1.437 27 40 83\n30-34 anos 2.488 94 55 1.351 22 32 72\n35-39 anos 1.840 72 45 1.056 11 30 36\n40-44 anos 1.537 49 36 928 9 18 32\n45-49 anos 1.240 29 24 786 14 14 27\n50-54 anos 1.059 25 17 666 4 18 14\n55-59 anos 745 18 11 512 0 6 10\n60-64 anos 522 9 8 364 2 6 8\n65-69 anos 329 13 6 232 1 3 4\n70-74 anos 266 6 4 197 2 4 3\n75-79 anos 196 14 5 128 1 4 1\n80 e + anos 203 5 4 140 0 11 3\nInstituto Nacional de Estatística de São Tomé e Príncipe, 2013\n28', 'Resultado Distrital do IV Recenseamento Geral da População e da Habitação 2012\nQuadro 6: Repartição da população residente segundo sexo e grupos etários por Religião (continuação…)\nGrupos Religião\nAssembléia Católica Apostólica Deus é\nTotal Adventista Jeová Maná\nEtários de Deus Romana amor\nTotal Mulher 35.866 1.649 928 21.498 356 547 1.202\n0-4 anos 5.198 236 136 2.547 72 57 177\n5-9 anos 4.569 242 104 2.520 52 70 140\n10-14 anos 4.089 193 113 2.542 41 81 122\n15-19 anos 3.587 213 121 2.162 34 44 122\n20-24 anos 3.381 197 95 1.904 32 56 142\n25-29 anos 3.308 160 87 1.964 38 51 142\n30-34 anos 2.687 124 57 1.668 20 41 112\n35-39 anos 2.003 77 46 1.308 17 36 60\n40-44 anos 1.618 49 41 1.066 20 26 49\n45-49 anos 1.370 32 35 927 11 17 42\n50-54 anos 1.218 35 32 836 7 17 36\n55-59 anos 888 31 18 637 5 13 25\n60-64 anos 528 12 10 379 3 4 11\n65-69 anos 398 13 7 291 0 6 7\n70-74 anos 389 16 10 286 1 10 4\n75-79 anos 274 7 9 199 2 5 5\n80 e + anos 361 12 7 262 1 13 6\nGrupos Religião\nNova Messiânica Igreja Universal Não\nOutras Não sabe Não tem\nEtários Apostólica Mundial do Reino de Deus declarou\nTotal de Água-\nGrande 618 431 2.104 3.966 164 517 12.998\n0-4 anos 84 55 346 543 16 47 2.943\n5-9 anos 77 46 301 539 7 49 1.910\n10-14 anos 71 38 234 451 8 34 1.330\n15-19 anos 81 36 232 382 14 46 1.224\n20-24 anos 70 31 225 389 21 68 1.231\n25-29 anos 72 23 222 410 16 85 1.134\n30-34 anos 35 44 158 315 18 45 912\n35-39 anos 25 24 111 249 11 32 597\n40-44 anos 22 24 75 172 12 34 493\n45-49 anos 28 33 75 137 14 23 342\n50-54 anos 18 33 52 121 7 22 317\n55-59 anos 13 14 28 61 4 13 214\n60-64 anos 10 14 19 59 8 5 119\n65-69 anos 5 9 7 43 2 5 73\n70-74 anos 1 3 12 34 2 3 57\n75-79 anos 3 0 5 33 1 3 45\n80 e + anos 3 4 2 28 3 3 57\nInstituto Nacional de Estatística de São Tomé e Príncipe, 2013\n29', 'Resultado Distrital do IV Recenseamento Geral da População e da Habitação 2012\nQuadro 6: Repartição da população residente segundo sexo e grupos etários por Religião (continuação…)\nGrupos Religião\nNova Messiânica Igreja Universal Não\nOutras Não sabe Não tem\nEtários Apostólica Mundial do Reino de Deus declarou\nTotal\nHomem 312 150 874 1.887 95 346 7.448\n0-4 anos 44 23 188 264 10 25 1.507\n5-9 anos 42 18 137 252 5 26 1.008\n10-14 anos 34 14 108 205 5 22 781\n15-19 anos 43 17 83 187 4 32 758\n20-24 anos 33 12 96 183 14 46 696\n25-29 anos 39 7 82 192 11 64 701\n30-34 anos 12 13 67 134 13 34 589\n35-39 anos 13 11 32 133 4 21 376\n40-44 anos 10 4 31 94 3 23 300\n45-49 anos 14 6 20 69 10 16 211\n50-54 anos 7 11 9 62 6 17 203\n55-59 anos 6 4 5 27 3 9 134\n60-64 anos 8 8 6 26 2 5 70\n65-69 anos 5 1 3 18 1 4 38\n70-74 anos 0 1 4 14 1 1 29\n75-79 anos 1 0 3 16 1 1 21\n80 e + anos 1 0 0 11 2 0 26\nTotal\nMulher 306 281 1.230 2.079 69 171 5.550\n0-4 anos 40 32 158 279 6 22 1.436\n5-9 anos 35 28 164 287 2 23 902\n10-14 anos 37 24 126 246 3 12 549\n15-19 anos 38 19 149 195 10 14 466\n20-24 anos 37 19 129 206 7 22 535\n25-29 anos 33 16 140 218 5 21 433\n30-34 anos 23 31 91 181 5 11 323\n35-39 anos 12 13 79 116 7 11 221\n40-44 anos 12 20 44 78 9 11 193\n45-49 anos 14 27 55 68 4 7 131\n50-54 anos 11 22 43 59 1 5 114\n55-59 anos 7 10 23 34 1 4 80\n60-64 anos 2 6 13 33 6 0 49\n65-69 anos 0 8 4 25 1 1 35\n70-74 anos 1 2 8 20 1 2 28\n75-79 anos 2 0 2 17 0 2 24\n80 e + anos 2 4 2 17 1 3 31\nInstituto Nacional de Estatística de São Tomé e Príncipe, 2013\n30', 'Resultado Distrital do IV Recenseamento Geral da População e da Habitação 2012\n1. EDUCAÇÃO\nQuadro 10: População residente segundo sexo e grupos etários por língua falada\nGrupos Português Fôrro Angolar Lunguié\nEtários Total Sim Não Total Sim Não Total Sim Não Total Sim Não\nTotal de Água-\nGrande 67.295 66.359 936 67.295 24.745 42.550 67.295 2.426 64.869 67.295 783 66.512\n1-4 anos 8.304 7.556 748 8.304 168 8.136 8.304 11 8.293 8.304 2 8.302\n5-9 anos 9.218 9.208 10 9.218 552 8.666 9.218 33 9.185 9.218 4 9.214\n10-14 anos 7.939 7.931 8 7.939 1.137 6.802 7.939 52 7.887 7.939 9 7.930\n15-19 anos 7.004 6.992 12 7.004 2.118 4.886 7.004 167 6.837 7.004 43 6.961\n20-24 anos 6.430 6.417 13 6.430 2.669 3.761 6.430 252 6.178 6.430 91 6.339\n25-29 anos 6.241 6.220 21 6.241 3.179 3.062 6.241 299 5.942 6.241 116 6.125\n30-34 anos 5.175 5.161 14 5.175 2.938 2.237 5.175 299 4.876 5.175 106 5.069\n35-39 anos 3.843 3.830 13 3.843 2.337 1.506 3.843 248 3.595 3.843 90 3.753\n40-44 anos 3.155 3.147 8 3.155 2.101 1.054 3.155 221 2.934 3.155 77 3.078\n45-49 anos 2.610 2.592 18 2.610 1.806 804 2.610 189 2.421 2.610 75 2.535\n50-54 anos 2.277 2.269 8 2.277 1.694 583 2.277 199 2.078 2.277 62 2.215\n55-59 anos 1.633 1.625 8 1.633 1.274 359 1.633 144 1.489 1.633 33 1.600\n60-64 anos 1.050 1.040 10 1.050 844 206 1.050 110 940 1.050 27 1.023\n65-69 anos 727 719 8 727 595 132 727 63 664 727 21 706\n70-74 anos 655 646 9 655 517 138 655 52 603 655 12 643\n75-79 anos 470 461 9 470 361 109 470 38 432 470 6 464\n80 e + anos 564 545 19 564 455 109 564 49 515 564 9 555\nTotal Homem 32.462 31.976 486 32.462 11.391 21.071 32.462 1.110 31.352 32.462 376 32.086\n1-4 anos 4.139 3.755 384 4.139 82 4.057 4.139 8 4.131 4.139 1 4.138\n5-9 anos 4.649 4.643 6 4.649 287 4.362 4.649 13 4.636 4.649 1 4.648\n10-14 anos 3.850 3.848 2 3.850 522 3.328 3.850 27 3.823 3.850 3 3.847\n15-19 anos 3.417 3.411 6 3.417 970 2.447 3.417 60 3.357 3.417 11 3.406\n20-24 anos 3.049 3.042 7 3.049 1.223 1.826 3.049 107 2.942 3.049 41 3.008\n25-29 anos 2.933 2.919 14 2.933 1.489 1.444 2.933 118 2.815 2.933 51 2.882\n30-34 anos 2.488 2.477 11 2.488 1.389 1.099 2.488 138 2.350 2.488 52 2.436\n35-39 anos 1.840 1.828 12 1.840 1.068 772 1.840 120 1.720 1.840 49 1.791\n40-44 anos 1.537 1.531 6 1.537 989 548 1.537 114 1.423 1.537 44 1.493\n45-49 anos 1.240 1.228 12 1.240 834 406 1.240 99 1.141 1.240 38 1.202\n50-54 anos 1.059 1.055 4 1.059 777 282 1.059 91 968 1.059 33 1.026\n55-59 anos 745 739 6 745 563 182 745 67 678 745 17 728\n60-64 anos 522 514 8 522 411 111 522 58 464 522 14 508\n65-69 anos 329 326 3 329 267 62 329 31 298 329 10 319\n70-74 anos 266 265 1 266 211 55 266 25 241 266 5 261\n75-79 anos 196 194 2 196 143 53 196 14 182 196 3 193\n80 e + anos 203 201 2 203 166 37 203 20 183 203 3 200\nInstituto Nacional de Estatística de São Tomé e Príncipe, 2013\n36', 'Resultado Distrital do IV Recenseamento Geral da População e da Habitação 2012\nQuadro 10: População residente segundo sexo e grupos etários por língua falada (continuação…)\nGrupos Português Fôrro Angolar Lunguié\nEtários Total Sim Não Total Sim Não Total Sim Não Total Sim Não\nTotal Mulher 34.833 34.383 450 34.833 13.354 21.479 34.833 1.316 33.517 34.833 407 34.426\n1-4 anos 4.165 3.801 364 4.165 86 4.079 4.165 3 4.162 4.165 1 4.164\n5-9 anos 4.569 4.565 4 4.569 265 4.304 4.569 20 4.549 4.569 3 4.566\n10-14 anos 4.089 4.083 6 4.089 615 3.474 4.089 25 4.064 4.089 6 4.083\n15-19 anos 3.587 3.581 6 3.587 1.148 2.439 3.587 107 3.480 3.587 32 3.555\n20-24 anos 3.381 3.375 6 3.381 1.446 1.935 3.381 145 3.236 3.381 50 3.331\n25-29 anos 3.308 3.301 7 3.308 1.690 1.618 3.308 181 3.127 3.308 65 3.243\n30-34 anos 2.687 2.684 3 2.687 1.549 1.138 2.687 161 2.526 2.687 54 2.633\n35-39 anos 2.003 2.002 1 2.003 1.269 734 2.003 128 1.875 2.003 41 1.962\n40-44 anos 1.618 1.616 2 1.618 1.112 506 1.618 107 1.511 1.618 33 1.585\n45-49 anos 1.370 1.364 6 1.370 972 398 1.370 90 1.280 1.370 37 1.333\n50-54 anos 1.218 1.214 4 1.218 917 301 1.218 108 1.110 1.218 29 1.189\n55-59 anos 888 886 2 888 711 177 888 77 811 888 16 872\n60-64 anos 528 526 2 528 433 95 528 52 476 528 13 515\n65-69 anos 398 393 5 398 328 70 398 32 366 398 11 387\n70-74 anos 389 381 8 389 306 83 389 27 362 389 7 382\n75-79 anos 274 267 7 274 218 56 274 24 250 274 3 271\n80 e + anos 361 344 17 361 289 72 361 29 332 361 6 355\nOutra(s) língua(s)\nGrupos Cabo verdiano Francês Inglês\n(inclusive sinais)\nEtários Total Sim Não Total Sim Não Total Sim Não Total Sim Não\nTotal de Água-\nGrande 67.295 3.637 63.658 67.295 7.308 59.987 67.295 5.782 61.513 67.295 2.034 65.261\n1-4 anos 8.304 10 8.294 8.304 20 8.284 8.304 16 8.288 8.304 69 8.235\n5-9 anos 9.218 35 9.183 9.218 50 9.168 9.218 31 9.187 9.218 44 9.174\n10-14 anos 7.939 99 7.840 7.939 401 7.538 7.939 217 7.722 7.939 53 7.886\n15-19 anos 7.004 261 6.743 7.004 929 6.075 7.004 793 6.211 7.004 101 6.903\n20-24 anos 6.430 471 5.959 6.430 965 5.465 6.430 864 5.566 6.430 180 6.250\n25-29 anos 6.241 536 5.705 6.241 915 5.326 6.241 872 5.369 6.241 244 5.997\n30-34 anos 5.175 508 4.667 5.175 886 4.289 5.175 821 4.354 5.175 249 4.926\n35-39 anos 3.843 380 3.463 3.843 750 3.093 3.843 607 3.236 3.843 191 3.652\n40-44 anos 3.155 323 2.832 3.155 600 2.555 3.155 414 2.741 3.155 164 2.991\n45-49 anos 2.610 300 2.310 2.610 585 2.025 2.610 366 2.244 2.610 198 2.412\n50-54 anos 2.277 237 2.040 2.277 549 1.728 2.277 354 1.923 2.277 233 2.044\n55-59 anos 1.633 134 1.499 1.633 338 1.295 1.633 221 1.412 1.633 160 1.473\n60-64 anos 1.050 105 945 1.050 169 881 1.050 105 945 1.050 61 989\n65-69 anos 727 50 677 727 80 647 727 53 674 727 29 698\n70-74 anos 655 78 577 655 43 612 655 28 627 655 28 627\nInstituto Nacional de Estatística de São Tomé e Príncipe, 2013\n37', 'Resultado Distrital do IV Recenseamento Geral da População e da Habitação 2012\nQuadro 10: População residente segundo sexo e grupos etários por língua falada (continuação…)\nOutra(s) língua(s)\nCabo verdiano Francês Inglês\nGrupos (inclusive sinais)\nEtários Total Sim Não Total Sim Não Total Sim Não Total Sim Não\n75-79 anos 470 71 399 470 19 451 470 14 456 470 15 455\n80 e + anos 564 39 525 564 9 555 564 6 558 564 15 549\nTotal Homem 32.462 1.654 30.808 32.462 4.175 28.287 32.462 3.715 28.747 32.462 1.296 31.166\n1-4 anos 4.139 5 4.134 4.139 11 4.128 4.139 8 4.131 4.139 38 4.101\n5-9 anos 4.649 18 4.631 4.649 20 4.629 4.649 16 4.633 4.649 16 4.633\n10-14 anos 3.850 34 3.816 3.850 189 3.661 3.850 108 3.742 3.850 21 3.829\n15-19 anos 3.417 84 3.333 3.417 419 2.998 3.417 385 3.032 3.417 56 3.361\n20-24 anos 3.049 203 2.846 3.049 521 2.528 3.049 507 2.542 3.049 94 2.955\n25-29 anos 2.933 241 2.692 2.933 488 2.445 2.933 522 2.411 2.933 140 2.793\n30-34 anos 2.488 245 2.243 2.488 478 2.010 2.488 535 1.953 2.488 165 2.323\n35-39 anos 1.840 192 1.648 1.840 462 1.378 1.840 430 1.410 1.840 136 1.704\n40-44 anos 1.537 149 1.388 1.537 401 1.136 1.537 322 1.215 1.537 119 1.418\n45-49 anos 1.240 141 1.099 1.240 363 877 1.240 274 966 1.240 130 1.110\n50-54 anos 1.059 109 950 1.059 338 721 1.059 262 797 1.059 155 904\n55-59 anos 745 62 683 745 237 508 745 184 561 745 123 622\n60-64 anos 522 61 461 522 133 389 522 86 436 522 48 474\n65-69 anos 329 21 308 329 57 272 329 37 292 329 17 312\n70-74 anos 266 38 228 266 33 233 266 22 244 266 16 250\n75-79 anos 196 36 160 196 17 179 196 13 183 196 14 182\n80 e + anos 203 15 188 203 8 195 203 4 199 203 8 195\nTotal Mulher 34.833 1.983 32.850 34.833 3.133 31.700 34.833 2.067 32.766 34.833 738 34.095\n1-4 anos 4.165 5 4.160 4.165 9 4.156 4.165 8 4.157 4.165 31 4.134\n5-9 anos 4.569 17 4.552 4.569 30 4.539 4.569 15 4.554 4.569 28 4.541\n10-14 anos 4.089 65 4.024 4.089 212 3.877 4.089 109 3.980 4.089 32 4.057\n15-19 anos 3.587 177 3.410 3.587 510 3.077 3.587 408 3.179 3.587 45 3.542\n20-24 anos 3.381 268 3.113 3.381 444 2.937 3.381 357 3.024 3.381 86 3.295\n25-29 anos 3.308 295 3.013 3.308 427 2.881 3.308 350 2.958 3.308 104 3.204\n30-34 anos 2.687 263 2.424 2.687 408 2.279 2.687 286 2.401 2.687 84 2.603\n35-39 anos 2.003 188 1.815 2.003 288 1.715 2.003 177 1.826 2.003 55 1.948\n40-44 anos 1.618 174 1.444 1.618 199 1.419 1.618 92 1.526 1.618 45 1.573\n45-49 anos 1.370 159 1.211 1.370 222 1.148 1.370 92 1.278 1.370 68 1.302\n50-54 anos 1.218 128 1.090 1.218 211 1.007 1.218 92 1.126 1.218 78 1.140\n55-59 anos 888 72 816 888 101 787 888 37 851 888 37 851\n60-64 anos 528 44 484 528 36 492 528 19 509 528 13 515\n65-69 anos 398 29 369 398 23 375 398 16 382 398 12 386\n70-74 anos 389 40 349 389 10 379 389 6 383 389 12 377\n75-79 anos 274 35 239 274 2 272 274 1 273 274 1 273\n80 e + anos 361 24 337 361 1 360 361 2 359 361 7 354\nInstituto Nacional de Estatística de São Tomé e Príncipe, 2013\n38']


def d(n: int) -> str:
    """A figure as the reports print it, thousands after a dot."""
    return f"{n:,}".replace(",", ".")


def synthetic(name: str, ordinary: int) -> list[str]:
    """A district report's Quadros 5, 6 and 10 that add up, for build()."""
    groups = [ordinary // 17] * 17
    groups[0] += ordinary - sum(groups)
    labels = [f"{lo}-{lo + 4} anos" for lo in range(0, 80, 5)] + ["80 e + anos"]
    q5 = ["Quadro 5: Repartição da população residente segundo sexo por grupos etários quinquenais",
          f"Total {d(ordinary)} {d(ordinary // 2)} {d(ordinary - ordinary // 2)} 0 0 0 0 0 0"]
    for label, people in zip(labels, groups):
        q5.append(f"{label} {d(people)} {d(people // 2)} {d(people - people // 2)} 0 0 0 0 0 0")
    first = [ordinary // 2, 10, 20, 30, 40, 50]
    rest = ordinary - sum(first)
    second = [1, 2, 3, 4, 5, 6, rest - 21]
    q6 = ["Quadro 6: Repartição da população residente segundo sexo e grupos etários por Religião",
          f"Total de {name} {d(ordinary)} " + " ".join(map(d, first)),
          " ".join(map(d, second))]
    asked = ordinary - 100
    q10 = ["Quadro 10: População residente segundo sexo e grupos etários por língua falada",
           f"{name} " + " ".join(f"{d(asked)} {d(yes)} {d(asked - yes)}"
                                  for yes in (asked - 50, asked // 3, 40, 30)),
           f"{name} " + " ".join(f"{d(asked)} {d(yes)} {d(asked - yes)}"
                                  for yes in (20, 300, 200, 10))]
    return ["\n".join(q5), "\n".join(q6), "\n".join(q10)]


class Quadro2(unittest.TestCase):
    def test_sideways_names(self):
        self.assertEqual(st.letters("Mé-Zóchi"), st.letters("hi c Z ó M -é"))
        table = st.residents([QUADRO_2])
        self.assertEqual(set(table), set(st.DISTRICTS))
        self.assertEqual(table["Água Grande"], (69_772, 33_805, 35_967, 69_454))
        self.assertEqual(table["Lembá"], (14_676, 7_579, 7_097, 14_652))
        self.assertEqual(table["Príncipe"], (7_344, 3_755, 3_589, 7_324))
        self.assertEqual(sum(v[0] for v in table.values()), 179_200)

    def test_contents_page_is_not_the_table(self):
        self.assertEqual(st.residents(["Quadro 2: População recenseada ....... 21"]), {})


class AguaGrande(unittest.TestCase):
    def test_ages(self):
        total, groups = st.ages(AGUA_GRANDE)
        self.assertEqual(total, 69_454)
        self.assertEqual(groups[0], [0, 4, 10_463])
        self.assertEqual(groups[-1], [80, None, 564])

    def test_religion(self):
        rel = st.religion(AGUA_GRANDE, 69_454)
        self.assertEqual(sum(rel.values()), 69_454)
        self.assertEqual(rel["Catholic"], 39_888)
        self.assertEqual(rel["No religion"], 12_998)
        self.assertEqual(rel["Universal Church of the Kingdom of God"], 2_104)

    def test_languages(self):
        asked, speakers = st.languages(AGUA_GRANDE)
        self.assertEqual(asked, 67_295)
        self.assertEqual(speakers["Portuguese"], 66_359)
        self.assertEqual(speakers["Forro"], 24_745)
        self.assertEqual(speakers["Cape Verdean Creole"], 3_637)
        self.assertEqual(speakers["Other languages"], 2_034)

    def test_fields(self):
        fields = st.fields((69_772, 33_805, 35_967), st.ages(AGUA_GRANDE),
                           st.religion(AGUA_GRANDE, 69_454), "Água Grande district",
                           st.languages(AGUA_GRANDE))
        self.assertEqual(fields["median_age"]["value"], 20.1)
        self.assertEqual(fields["sex_ratio"]["value"], 940)
        self.assertEqual(fields["language"][0], {"group": "Portuguese", "pct": 98.6, "count": 66_359})
        self.assertEqual(fields["language_basis"], "languages spoken (multi-response)")
        self.assertGreater(sum(r["pct"] for r in fields["language"]), 100)
        self.assertEqual(fields["religion"][0]["group"], "Catholic")
        for note in (fields["language_note"], fields["religion_note"], fields["median_age_note"]):
            self.assertNotRegex(note, r"\.pdf|read|fetch")


class Build(unittest.TestCase):
    def test_build_adds_up(self):
        table = st.residents([QUADRO_2])
        reports = {name: synthetic(name, table[name][3]) for name in st.DISTRICTS}
        reports["Água Grande"] = AGUA_GRANDE
        national = [QUADRO_2, "Quadro 1: População\nPopulação Residente (RP+RA) 179.200 89.187 90.013"]
        records, report = st.build(national, reports)
        self.assertEqual(len(records), 9)
        by_name = {(r["level"], r["name"]): r for r in records}
        tome = by_name[("admin1", "São Tomé")]
        self.assertEqual(tome["population"]["value"], 171_856)
        self.assertEqual(by_name[("admin1", "Príncipe")]["population"]["value"], 7_344)
        self.assertEqual(by_name[("admin2", "Água Grande")]["median_age"]["value"], 20.1)
        self.assertTrue(all(r["match_by"] == "shape_id" for r in records))

    def test_records_keep_the_polygons_own_names(self):
        table = st.residents([QUADRO_2])
        reports = {name: synthetic(name, table[name][3]) for name in st.DISTRICTS}
        reports["Água Grande"] = AGUA_GRANDE
        national = [QUADRO_2, "Quadro 1: População\nPopulação Residente (RP+RA) 179.200 89.187 90.013"]
        labels = {st.DISTRICTS["Mé-Zóchi"][1]: "Mé-zóxi",
                  st.PROVINCES["São Tomé"][0]: "São Tomé Province"}
        records, _ = st.build(national, reports, None, labels)
        names = {r["name"] for r in records}
        self.assertIn("Mé-zóxi", names)
        self.assertIn("São Tomé Province", names)
        self.assertNotIn("Mé-Zóchi", names)

    def test_districts_must_make_the_country(self):
        table = st.residents([QUADRO_2])
        reports = {name: synthetic(name, table[name][3]) for name in st.DISTRICTS}
        national = [QUADRO_2, "Quadro 1: População\nPopulação Residente (RP+RA) 180.000 90.000 90.000"]
        with self.assertRaises(SystemExit):
            st.build(national, reports)


if __name__ == "__main__":
    unittest.main()
