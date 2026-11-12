/* cartel12_datos.h — LO ESCRIBE herramientas/cartel12_crear.py: no se toca a mano.
 *   El cartel de resultado de la carrera de 12 (800×600, la maqueta_K_final de anonimo03): dónde va cada pieza en la
 *   hoja `cartel12.tga` y dónde se pega en el cartel. Las mismas con las que la herramienta armó
 *   `_trabajo/cartel12/vista.png`. Doc: documentacion/MODO_6VS6.md §17.
 *   ★ Las MEDIDAS son lógicas (el cartel de 800×600); las PIEZAS (K12_P_*) están en px de la hoja, que va al
 *   doble (K12_ESC): la dll arma el cartel al tamaño de la pantalla re-muestreando desde ahí. */
#define K12_HOJA_TGA   "rnr_ui_lt/rnr_game/image/cartel12.tga"
#define K12_LIENZO_TGA "rnr_ui_lt/rnr_game/image/cartel12_lienzo.tga"
#define K12_W 800
#define K12_H 600
#define K12_ESC 2
#define K12_LIENZO_W 2048
#define K12_LIENZO_H 1536
#define K12_P_FONDO 0, 0, 1600, 1200
#define K12_FILA_X0 212
#define K12_FILA_W 574
#define K12_FILA_H 30
static const int K12_FILA_Y[12] = { 166, 197, 229, 260, 292, 323, 355, 386, 418, 449, 481, 512 };
/* las columnas: x del borde DERECHO y el juego de cifras (0 = «a», las de exp/rcoin · 1 = «b») */
static const int K12_COL_X[6] = { 450, 514, 578, 642, 708, 770 };
static const int K12_COL_JUEGO[6] = { 0, 1, 1, 1, 1, 0 };
#define K12_TIEMPO_CX 364     /* ★ 17-oct: el tiempo de llegada (mm:ss:cc), centrado */
#define K12_PISTA_X 20
#define K12_PISTA_CY 176
#define K12_CANCION_X 20
#define K12_CANCION_CY 227
#define K12_ESTRELLAS_X 14
#define K12_ESTRELLAS_Y 245
#define K12_ESTRELLAS_DX 15
#define K12_ESTRELLAS_N 10
#define K12_PODIO_X 22
static const int K12_PODIO_CY[3] = { 342, 426, 510 };
#define K12_GANADOR_X 261
#define K12_GANADOR_CY 117
/* lo del marcador que se escribe sólo en modo equipo */
static const int K12_MARC_X[3] = { 420, 540, 660 };
#define K12_MARC_CY 106
#define K12_LEYENDA_X 540
#define K12_LEYENDA_CY 128
static const int K12_SCORE_XY[2][2] = { { 480, 104 }, { 600, 104 } };
#define K12_ROJO 0xFFEB555F
#define K12_AZUL 0xFF5587F5
#define K12_AMARILLO 0xFFFFFFA0
/* las piezas en la hoja: x, y, w, h */
#define K12_P_FILA_ROJA 0, 1276, 1148, 60
#define K12_P_FILA_AZUL 0, 1338, 1148, 60
#define K12_P_FILA_GRIS 0, 1524, 1148, 60
#define K12_P_FILA_VERDE 0, 1400, 1148, 60
#define K12_P_FILA_NARANJA 0, 1462, 1148, 60
#define K12_P_YO 0, 1202, 1160, 72
#define K12_P_ESTRELLA_VACIA 1901, 1798, 30, 32
#define K12_P_PODIO 1602, 0, 286, 528
#define K12_P_PODIO_VACIO 1602, 530, 286, 528
#define K12_P_EMBLEMA0 0, 1586, 194, 210
#define K12_P_EMBLEMA1 196, 1586, 194, 210
#define K12_P_EMBLEMA2 392, 1586, 194, 210
#define K12_P_EMBLEMA3 588, 1586, 194, 210
#define K12_P_EMBLEMA4 784, 1586, 194, 210
#define K12_P_ESTRELLA_LLENA0 1581, 1798, 30, 32
#define K12_P_ESTRELLA_LLENA1 1613, 1798, 30, 32
#define K12_P_ESTRELLA_LLENA2 1645, 1798, 30, 32
#define K12_P_ESTRELLA_LLENA3 1677, 1798, 30, 32
#define K12_P_ESTRELLA_LLENA4 1709, 1798, 30, 32
#define K12_P_ESTRELLA_MEDIA0 1741, 1798, 30, 32
#define K12_P_ESTRELLA_MEDIA1 1773, 1798, 30, 32
#define K12_P_ESTRELLA_MEDIA2 1805, 1798, 30, 32
#define K12_P_ESTRELLA_MEDIA3 1837, 1798, 30, 32
#define K12_P_ESTRELLA_MEDIA4 1869, 1798, 30, 32
#define K12_P_PUESTO1 980, 1586, 78, 46
#define K12_P_PUESTO2 0, 1798, 88, 44
#define K12_P_PUESTO3 1384, 1586, 84, 46
#define K12_P_PUESTO4 1470, 1586, 86, 46
#define K12_P_PUESTO5 1558, 1586, 84, 46
#define K12_P_PUESTO6 1644, 1586, 82, 46
#define K12_P_PUESTO7 1728, 1586, 82, 46
#define K12_P_PUESTO8 1812, 1586, 82, 46
#define K12_P_PUESTO9 1896, 1586, 84, 46
#define K12_P_PUESTO10 1060, 1586, 110, 46
#define K12_P_PUESTO11 1172, 1586, 102, 46
#define K12_P_PUESTO12 1276, 1586, 106, 46
#define K12_P_INSIG0 90, 1798, 38, 42
#define K12_P_INSIG1 130, 1798, 38, 42
#define K12_P_INSIG2 250, 1798, 38, 42
#define K12_P_INSIG3 290, 1798, 38, 42
#define K12_P_INSIG4 330, 1798, 38, 42
#define K12_P_INSIG5 370, 1798, 38, 42
#define K12_P_INSIG6 410, 1798, 38, 42
#define K12_P_INSIG7 450, 1798, 38, 42
#define K12_P_INSIG8 490, 1798, 38, 42
#define K12_P_INSIG9 530, 1798, 38, 42
#define K12_P_INSIG10 170, 1798, 38, 42
#define K12_P_INSIG11 210, 1798, 38, 42
#define K12_P_INSIGV6 1130, 1798, 38, 42
#define K12_P_INSIGV7 1170, 1798, 38, 42
#define K12_P_INSIGV8 1210, 1798, 38, 42
#define K12_P_INSIGV9 1250, 1798, 38, 42
#define K12_P_INSIGV10 1050, 1798, 38, 42
#define K12_P_INSIGV11 1090, 1798, 38, 42
#define K12_P_INSIGN6 890, 1798, 38, 42
#define K12_P_INSIGN7 930, 1798, 38, 42
#define K12_P_INSIGN8 970, 1798, 38, 42
#define K12_P_INSIGN9 1010, 1798, 38, 42
#define K12_P_INSIGN10 810, 1798, 38, 42
#define K12_P_INSIGN11 850, 1798, 38, 42
#define K12_P_INSIGA0 570, 1798, 38, 42
#define K12_P_INSIGA1 610, 1798, 38, 42
#define K12_P_INSIGA2 650, 1798, 38, 42
#define K12_P_INSIGA3 690, 1798, 38, 42
#define K12_P_INSIGA4 730, 1798, 38, 42
#define K12_P_INSIGA5 770, 1798, 38, 42
#define K12_P_A0 1290, 1798, 29, 32
#define K12_P_A1 1933, 1798, 20, 31
#define K12_P_A2 1955, 1798, 27, 31
#define K12_P_A3 1321, 1798, 27, 32
#define K12_P_A4 1984, 1798, 29, 31
#define K12_P_A5 1350, 1798, 26, 32
#define K12_P_A6 1378, 1798, 26, 32
#define K12_P_A7 2015, 1798, 27, 31
#define K12_P_A8 0, 1844, 27, 31
#define K12_P_A9 1406, 1798, 27, 32
#define K12_P_B0 1435, 1798, 29, 32
#define K12_P_B1 29, 1844, 20, 31
#define K12_P_B2 51, 1844, 27, 31
#define K12_P_B3 1466, 1798, 27, 32
#define K12_P_B4 80, 1844, 29, 31
#define K12_P_B5 1495, 1798, 26, 32
#define K12_P_B6 1523, 1798, 27, 32
#define K12_P_B7 111, 1844, 26, 31
#define K12_P_B8 139, 1844, 27, 31
#define K12_P_B9 1552, 1798, 27, 32
static const int K12_EMBLEMA[5][4] = { { K12_P_EMBLEMA0 }, { K12_P_EMBLEMA1 }, { K12_P_EMBLEMA2 }, { K12_P_EMBLEMA3 }, { K12_P_EMBLEMA4 } };
static const int K12_ESTRELLA_LLENA[5][4] = { { K12_P_ESTRELLA_LLENA0 }, { K12_P_ESTRELLA_LLENA1 }, { K12_P_ESTRELLA_LLENA2 }, { K12_P_ESTRELLA_LLENA3 }, { K12_P_ESTRELLA_LLENA4 } };
static const int K12_ESTRELLA_MEDIA[5][4] = { { K12_P_ESTRELLA_MEDIA0 }, { K12_P_ESTRELLA_MEDIA1 }, { K12_P_ESTRELLA_MEDIA2 }, { K12_P_ESTRELLA_MEDIA3 }, { K12_P_ESTRELLA_MEDIA4 } };
#define K12_EMBLEMA_X 34
#define K12_EMBLEMA_Y 11
/* 0 novato · 1 estrella · 2 luna · 3 violeta · 4 sol */
static const int K12_PUESTO[12][4] = { { K12_P_PUESTO1 }, { K12_P_PUESTO2 }, { K12_P_PUESTO3 }, { K12_P_PUESTO4 }, { K12_P_PUESTO5 }, { K12_P_PUESTO6 }, { K12_P_PUESTO7 }, { K12_P_PUESTO8 }, { K12_P_PUESTO9 }, { K12_P_PUESTO10 }, { K12_P_PUESTO11 }, { K12_P_PUESTO12 } };
static const int K12_INSIG[12][4] = { { K12_P_INSIG0 }, { K12_P_INSIG1 }, { K12_P_INSIG2 }, { K12_P_INSIG3 }, { K12_P_INSIG4 }, { K12_P_INSIG5 }, { K12_P_INSIG6 }, { K12_P_INSIG7 }, { K12_P_INSIG8 }, { K12_P_INSIG9 }, { K12_P_INSIG10 }, { K12_P_INSIG11 } };
/* ★ 14-oct · relevo de 12: 7P..12P verde (V) y naranja (N), índice = asiento − 6 */
static const int K12_INSIG_V[6][4] = { { K12_P_INSIGV6 }, { K12_P_INSIGV7 }, { K12_P_INSIGV8 }, { K12_P_INSIGV9 }, { K12_P_INSIGV10 }, { K12_P_INSIGV11 } };
static const int K12_INSIG_N[6][4] = { { K12_P_INSIGN6 }, { K12_P_INSIGN7 }, { K12_P_INSIGN8 }, { K12_P_INSIGN9 }, { K12_P_INSIGN10 }, { K12_P_INSIGN11 } };
/* ★ 15-oct · 4 equipos: 1P..6P AZUL (A), índice = asiento (el azul del equipo de 4 / relevo de 12 es 4-6) */
static const int K12_INSIG_A[6][4] = { { K12_P_INSIGA0 }, { K12_P_INSIGA1 }, { K12_P_INSIGA2 }, { K12_P_INSIGA3 }, { K12_P_INSIGA4 }, { K12_P_INSIGA5 } };
static const int K12_CIFRA[2][10][4] = { { { K12_P_A0 }, { K12_P_A1 }, { K12_P_A2 }, { K12_P_A3 }, { K12_P_A4 }, { K12_P_A5 }, { K12_P_A6 }, { K12_P_A7 }, { K12_P_A8 }, { K12_P_A9 } }, { { K12_P_B0 }, { K12_P_B1 }, { K12_P_B2 }, { K12_P_B3 }, { K12_P_B4 }, { K12_P_B5 }, { K12_P_B6 }, { K12_P_B7 }, { K12_P_B8 }, { K12_P_B9 } } };
/* los nombres de las pistas (stage_lt.txt, cp1252): el server manda el número */
#define K12_PISTAS 104
static const char *const K12_PISTA[K12_PISTAS] = {
    "Random",
    "LA MONTA\x3F"" MUSHROOM",
    "Escuela Mushroom",
    "PARQUE WEIMAR",
    "CLUB SEED",
    "VAQUERO ESPACIAL",
    "TUNEL TINTOY",
    "AUTOPISTA ESTRELLA",
    "COLINA FUNGUS",
    "PARQUE WEIMAR - Oeste",
    "OCTUBRE",
    "MARAVILLA ESPACIAL",
    "CAMPO DE INVIERNO",
    "",
    "LA CIUDAD DULCE",
    "CAMINO ROSA",
    "",
    "",
    "",
    "PUERTO  CARIBE",
    "",
    "\xC6""\xE3""\xB0""\xC5""\xBD""\xBA"" \xC5""\xB8""\xBF""\xEE""",
    "Abismo semi oscuro",
    "",
    "",
    "Puente Neblinoso",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "Glitch Land",
    "",
    "",
    "",
    "",
    "ESTADIO PERU BOLIVIA",
    "",
    "",
    "Pista exclusiva de Miku",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "AKB48\xC7""\xEF""\xD2""\xB6""\xD4""\xAD""\xBE""\xE7""\xB3""\xA1""",
    "",
    "",
    "",
    "",
    "Abismo sin fin",
    "",
    "",
    "",
    "",
};
