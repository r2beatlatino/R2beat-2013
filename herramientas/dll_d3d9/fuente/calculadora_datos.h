/* calculadora_datos.h — GENERADO. ⛔ NO EDITAR A MANO.
 *
 *   Lo escribe  herramientas/calculadora/generar_datos_dll.py  (repo Servidor R2Beat 2013)
 *   desde       herramientas/calculadora/posicion_de_fabrica.json
 *               _trabajo/calculadora/cortes.json   (lo escribe armar_textura.py)
 *   Para cambiar un numero: cambiar el origen y volver a generar. */
#pragma once

/* las posiciones de fabrica, ordenadas por ALTO: {ancho, alto, x, y} */
static const int CALC_FABRICA[][4] = {
    {  800,  600,  111,  311 },   /* 800x600 */
    { 1024,  768,   53,  448 },   /* 1024x768 */
    { 1600,  900,   82,  591 },   /* 1600x900 */
    { 1920, 1080,   64,  719 },   /* 1920x1080 */
};
#define CALC_N_FABRICA 4

/* la figurita: recortes de la fila de carteles (x, y, ancho, alto en la textura) */
#define CALC_FILA_X 146
#define CALC_FILA_Y 110
#define CALC_FILA_W 216
#define CALC_FILA_H 30
#define CALC_VER_X  146
#define CALC_VER_Y  160
#define CALC_CARTEL_1 199   /* la fila, medida desde el borde de arriba del panel */
#define CALC_PD_Y     9   /* el numero del PD, idem */

/* las piezas SUELTAS que la DLL copia al lienzo: {x, y, ancho, alto} en la textura */
static const int CALC_P_DIG_BLANCO[4] = { 150, 64, 9, 16 };
static const int CALC_P_ROT_ACHICAR[4] = { 293, 6, 10, 18 };
static const int CALC_P_ROT_AGRANDAR[4] = { 279, 6, 10, 18 };
static const int CALC_P_ROT_FIJADO[4] = { 235, 6, 40, 18 };
static const int CALC_P_ROT_FIJAR[4] = { 202, 6, 29, 18 };
static const int CALC_P_TECLA_I[4] = { 150, 6, 13, 13 };
static const int CALC_P_TECLA_O[4] = { 166, 6, 13, 13 };
static const int CALC_P_TECLA_P[4] = { 182, 6, 13, 13 };
#define CALC_HAY_PIEZAS 1
#define CALC_F9_X 140   /* la tecla F9 dentro de la fila: los botones van encima */
#define CALC_F9_W 27
