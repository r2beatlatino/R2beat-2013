/* picker_datos.h — LO ESCRIBE herramientas/picker_bpm.py: no se toca a mano.
 *   Las posiciones de la lista del picker (px desde su borde izquierdo), las MISMAS con las que se
 *   pintaron las rayas de rnr_ui_picker.pak. Si cambian acá, cambian las dos cosas juntas. */
#define PK_CORRE        10     /* título y corazón, a la izquierda */
#define PK_CORAZON      185    /* era 195 (0xC3) */
#define PK_ARTISTA      211    /* era 221 (0xDD) */
#define PK_ARTISTA_W    84     /* era 80 (0x50) */
#define PK_RAYA_BPM     297
#define PK_BPM_CENTRO   311
/* la barra del volumen (picker_volumen.tga): x, y, ancho, alto de cada pieza */
#define PK_VOL_TGA      "rnr_ui_lt/rnr_ui/room_music/picker_volumen.tga"
#define PK_VOL_RIEL     0, 0, 69, 9
#define PK_VOL_TIRA     70, 0, 1, 13
#define PK_VOL_PERILLA  72, 0, 7, 13
/* el panel: los NÚMEROS, al lado de los rótulos pintados en host01 (px desde la lista; y desde su 1ª fila) */
#define PK_INFO_COL_X   -121   /* «Duracion» y «BPM» EMPIEZAN acá (debajo de «Puesto») */
#define PK_PUESTO_CORRE 4     /* «Puesto N (…)», que lo escribe el exe: tantos px a la izquierda */
#define PK_INFO_BPM_Y   7
#define PK_INFO_DUR_Y   -9
/* ★ (129) la fila «Noter»: el valor, en la columna del título y el género (px desde la lista y su 1ª fila) */
#define PK_NOTER_X      (-283)
#define PK_NOTER_Y      51
#define PK_NOTER_W      261
/* el menú de orden: los cortes de «Orden por BPM» (normal / encendido) en music_select_host04.spr */
#define PK_MENU_CORTE_N 44
#define PK_MENU_CORTE_E 45
/* «BPM : nnn» en la SALA (sala_bpm.tga): las piezas 0..9 = las cifras, 10 = «BPM :».
 *   u, v (el borde) · u2 (el relleno, misma v) · w, h · dx, dy desde la pluma y la LÍNEA DE BASE · avance · tinta izq/der */
#define PK_SALA_TGA      "rnr_ui_lt/rnr_room/sala_bpm.tga"
#define PK_SALA_PALABRA  10
#define PK_SALA_FIN      176    /* px del panel: la tinta TERMINA acá (4 px adentro del borde del cuadro) */
#define PK_SALA_BASE     22     /* la línea de base de «Música», px del panel */
static const short PK_SALA_PIEZA[11][10] = {
    {   0,  0,  18, 17, 21,  -4, -15, 10,  1,  9 }   /* «0» */,
    {  36,  0,  50, 13, 21,  -2, -15, 10,  2,  6 }   /* «1» */,
    {  64,  0,  81, 16, 21,  -3, -15, 10,  1,  9 }   /* «2» */,
    {  98,  0, 114, 15, 21,  -3, -15, 10,  2,  8 }   /* «3» */,
    { 130,  0, 148, 17, 21,  -4, -15, 10,  1,  9 }   /* «4» */,
    { 166,  0, 183, 16, 21,  -3, -15, 10,  2,  8 }   /* «5» */,
    { 200,  0, 217, 16, 21,  -3, -15, 10,  1,  9 }   /* «6» */,
    {   0, 22,  17, 16, 21,  -3, -15, 10,  1,  9 }   /* «7» */,
    {  34, 22,  51, 16, 21,  -3, -15, 10,  1,  8 }   /* «8» */,
    {  68, 22,  85, 16, 21,  -3, -15, 10,  1,  8 }   /* «9» */,
    { 102, 22, 150, 47, 21,  -3, -15, 46,  1, 40 }   /* «BPM :» */
};
