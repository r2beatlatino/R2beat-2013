/* sala12_datos.h — GENERADO por herramientas/sala12_crear.py. No editar a mano. */
#define S12_TARJETAS_TGA "rnr_ui_lt/rnr_room/sala12_tarjetas.tga"
#define S12_CHICA_W 102
#define S12_CHICA_H 48
#define S12_GRANDE_W 154
#define S12_GRANDE_H 193
static const int S12_CORTES[][4] = { { 0, 0, 102, 48 }, { 104, 0, 102, 48 }, { 208, 0, 102, 48 }, { 312, 0, 102, 48 }, { 0, 52, 154, 193 }, { 160, 122, 58, 18 }, { 230, 122, 54, 17 }, { 160, 142, 102, 48 }, { 264, 142, 102, 48 } };
#define S12_CORTE_ROJO 0  /* (0,0) */
#define S12_CORTE_AZUL 1  /* (104,0) */
#define S12_CORTE_VIOLETA 2  /* (208,0) */
#define S12_CORTE_VACIO 3  /* (312,0) */
#define S12_CORTE_GRANDE 4  /* (0,52) */
#define S12_CORTE_LISTO 5  /* (160,122) */
#define S12_CORTE_ANFITRION 6  /* (230,122) */
#define S12_CORTE_VERDE 7  /* (160,142) */
#define S12_CORTE_NARANJA 8  /* (264,142) */
#define S12_INSIGNIA_W 22
#define S12_INSIGNIA_H 20
/* la fila de cada color en la hoja: rojo, azul, violeta (la insignia k está en x0 + k*(W+2)) */
#define S12_INSIGNIA_COLORES 5   /* rojo, azul, violeta, verde, naranja (★ 14-oct: +2) */
static const int S12_INSIGNIA_FILA[S12_INSIGNIA_COLORES][2] = { { 160, 52 }, { 160, 74 }, { 160, 96 }, { 160, 196 }, { 160, 218 } };
#define S12_RUI_ROTULO "Image_mode12"
#define S12_ROTULO_ENCENDIDO 1
#define S12_ROTULO_NORMAL    2
/* ★ 15-oct · las 3 casillas chicas (EQUIPOS_4.md): 0 «2 equipos» · 1 «4 equipos» · 2 «solo». Su rótulo:
 *   el corte S12_OPCION_ENCENDIDO + 2k (marcada) o + 1 (no) de la hoja del título */
#define S12_OPCIONES 3
static const char *const S12_RUI_BASE_OP[S12_OPCIONES] = { "Base_mode12_2", "Base_mode12_4", "Base_mode12_s" };
static const char *const S12_RUI_TILDE_OP[S12_OPCIONES] = { "Image_check12_2", "Image_check12_4", "Image_check12_s" };
static const char *const S12_RUI_ETIQ_OP[S12_OPCIONES] = { "Image_mode12_2", "Image_mode12_4", "Image_mode12_s" };
#define S12_OPCION_ENCENDIDO 3
/* ★ la carrera de 12 (carrera12.c): 0..5 = 7TH..12TH; 6 + col*6 + (asiento-6) = la insignia 7P..12P de la
 *   columna col (0 por asiento, 1 rojo, 2 azul: las de 01.tga en sus cortes asiento+4 / +0x43 / +0x49);
 *   ★ 14-oct: S12_MARCA_ROJO + k / S12_MARCA_AZUL + k = el marcador «k+1» de la barra de abajo (k = 0..11);
 *   S12_PUESTO_CHICO + p = el puesto chico «(p+1)TH» de las tarjetas */
#define S12_MARCA_ROJO 24
#define S12_MARCA_AZUL 36
#define S12_PUESTO_CHICO 48
/* ★ 14-oct · relevo de 12: marcadores VERDE / NARANJA (k = 0..11) e insignias 7P..12P verde / naranja */
#define S12_MARCA_VERDE 60
#define S12_MARCA_NARANJA 72
#define S12_INSIG_VERDE 84
#define S12_INSIG_NARANJA 90
/* ★ 14-oct · el GLOBO DEL COMBO (globo_combo.c): punta izq., medio (se estira), punta der., colita; los números
 *   y el «COMBO» son los del contador del juego (la hoja del HUD) */
#define S12_GLOBO_IZQ 96
#define S12_GLOBO_MEDIO 97
#define S12_GLOBO_DER 98
#define S12_GLOBO_COLA 99
#define S12_GLOBO_MONTA 3   /* la colita monta el borde de abajo */
#define S12_CARRERA_TGA "rnr_ui_lt/rnr_game/image/sala12_carrera.tga"
static const int S12_CARRERA_CORTES[][4] = { { 0, 0, 92, 50 }, { 94, 0, 103, 53 }, { 199, 0, 102, 53 }, { 0, 55, 127, 54 }, { 129, 55, 107, 54 }, { 238, 55, 117, 54 }, { 0, 112, 29, 31 }, { 31, 112, 29, 31 }, { 62, 112, 29, 31 }, { 93, 112, 29, 31 }, { 124, 112, 29, 31 }, { 155, 112, 29, 31 }, { 0, 145, 29, 31 }, { 31, 145, 29, 31 }, { 62, 145, 29, 31 }, { 93, 145, 29, 31 }, { 124, 145, 29, 31 }, { 155, 145, 29, 31 }, { 0, 178, 29, 31 }, { 31, 178, 29, 31 }, { 62, 178, 29, 31 }, { 93, 178, 29, 31 }, { 124, 178, 29, 31 }, { 155, 178, 29, 31 }, { 0, 213, 20, 20 }, { 21, 213, 20, 20 }, { 42, 213, 20, 20 }, { 63, 213, 20, 20 }, { 84, 213, 20, 20 }, { 105, 213, 20, 20 }, { 126, 213, 20, 20 }, { 147, 213, 20, 20 }, { 168, 213, 20, 20 }, { 189, 213, 20, 20 }, { 210, 213, 20, 20 }, { 231, 213, 20, 20 }, { 0, 235, 20, 20 }, { 21, 235, 20, 20 }, { 42, 235, 20, 20 }, { 63, 235, 20, 20 }, { 84, 235, 20, 20 }, { 105, 235, 20, 20 }, { 126, 235, 20, 20 }, { 147, 235, 20, 20 }, { 168, 235, 20, 20 }, { 189, 235, 20, 20 }, { 210, 235, 20, 20 }, { 231, 235, 20, 20 }, { 190, 112, 36, 25 }, { 228, 112, 44, 25 }, { 274, 112, 40, 25 }, { 316, 112, 44, 25 }, { 362, 112, 41, 25 }, { 405, 112, 42, 25 }, { 449, 112, 39, 25 }, { 190, 136, 44, 25 }, { 236, 136, 43, 25 }, { 281, 136, 54, 25 }, { 337, 136, 45, 25 }, { 384, 136, 50, 25 }, { 0, 260, 20, 20 }, { 21, 260, 20, 20 }, { 42, 260, 20, 20 }, { 63, 260, 20, 20 }, { 84, 260, 20, 20 }, { 105, 260, 20, 20 }, { 126, 260, 20, 20 }, { 147, 260, 20, 20 }, { 168, 260, 20, 20 }, { 189, 260, 20, 20 }, { 210, 260, 20, 20 }, { 231, 260, 20, 20 }, { 0, 282, 20, 20 }, { 21, 282, 20, 20 }, { 42, 282, 20, 20 }, { 63, 282, 20, 20 }, { 84, 282, 20, 20 }, { 105, 282, 20, 20 }, { 126, 282, 20, 20 }, { 147, 282, 20, 20 }, { 168, 282, 20, 20 }, { 189, 282, 20, 20 }, { 210, 282, 20, 20 }, { 231, 282, 20, 20 }, { 0, 306, 29, 31 }, { 31, 306, 29, 31 }, { 62, 306, 29, 31 }, { 93, 306, 29, 31 }, { 124, 306, 29, 31 }, { 155, 306, 29, 31 }, { 0, 339, 29, 31 }, { 31, 339, 29, 31 }, { 62, 339, 29, 31 }, { 93, 339, 29, 31 }, { 124, 339, 29, 31 }, { 155, 339, 29, 31 }, { 0, 374, 14, 58 }, { 16, 374, 4, 58 }, { 22, 374, 14, 58 }, { 38, 374, 20, 13 } };
/* ★ 14-oct · el cartel de 4 banderas (relevo de 12): 0 = el fondo, 1 = el marco de la elegida (gr_btn 0x1A),
 *   2 / 3 = la FLECHITA del cambio de lugar (01.tga 56 normal / 57 con el mouse encima).
 *   Casillero k en x = S12_BANDERAS_X0 + k*S12_BANDERAS_PASO del fondo */
#define S12_BANDERAS_TGA "rnr_ui_lt/rnr_room/sala12_banderas.tga"
#define S12_BANDERAS_PASO 112
#define S12_BANDERAS_X0 17
#define S12_BANDERAS_N 4
static const int S12_BANDERAS_CORTES[S12_BANDERAS_N][4] = { { 0, 0, 469, 140 }, { 0, 142, 110, 104 }, { 112, 142, 21, 21 }, { 135, 142, 21, 21 } };
