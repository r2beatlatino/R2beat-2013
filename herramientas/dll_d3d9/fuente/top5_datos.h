/* top5_datos.h — LO ESCRIBE herramientas/top5_rank.py: no se toca a mano.
 *   Las medidas de la ventana «TOP 5 RANK» (px de la ventana, 512×332 = el fondo del coreano) y de las piezas en la
 *   hoja `top5.tga`. Las mismas con las que la herramienta armó `_trabajo/top5/vista.png`. */
#define T5_HOJA_TGA    "rnr_ui_lt/rnr_ui/room_music/top5.tga"
#define T5_LIENZO_TGA  "rnr_ui_lt/rnr_ui/room_music/top5_lienzo.tga"
#define T5_W           512
#define T5_H           332
#define T5_FILAS       5
static const int T5_FILA_Y[T5_FILAS] = { 116, 152, 186, 221, 255 };
#define T5_FILA_H      33
#define T5_MIO_Y       289
#define T5_MIO_H       35
#define T5_TITULO_Y    64      /* el nombre de la canción (centro) */
#define T5_COL_PUESTO  32      /* centros de las columnas */
#define T5_COL_APODO   112
#define T5_APODO_ANCHO 112
#define T5_COL_FECHA   218
#define T5_COL_TIEMPO  296
#define T5_COL_COMBO   360
#define T5_COL_PREC    440
#define T5_X_X         477     /* la X, en la ventana */
#define T5_X_Y         34
#define T5_X_TAM       28
#define T5_BARRA_X     500     /* la barrita de desplazamiento */
#define T5_BARRA_Y0    118
#define T5_BARRA_Y1    286
#define T5_BOTON_W     113
#define T5_BOTON_H     22
static const int T5_BOTON_CORTE[3][2] = { { 0, 340 }, { 118, 340 }, { 236, 340 } };   /* normal · encima · apretado */
static const int T5_X_CORTE[3][2] = { { 360, 340 }, { 392, 340 }, { 424, 340 } };
#define T5_BOTON_DLG_X 219     /* el botón, en el diálogo del picker */
#define T5_BOTON_DLG_Y 212
#define T5_VENTANA_DLG_X 122   /* la ventana, en el diálogo del picker (centrada) */
#define T5_VENTANA_DLG_Y 136
