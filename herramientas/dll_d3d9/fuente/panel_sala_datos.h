/* panel_sala_datos.h — LO ESCRIBE herramientas/panel_sala.py: no se toca a mano.
 *   Las medidas con las que se armó el panel de la sala (px del panel: 0,0 = su esquina de arriba a la izquierda). */
#define PS_SUBE         56     /* el panel sube esto (0xB4 = 180 -> 124) */
#define PS_ALTO_NUEVO   92     /* filas metidas debajo de «Pista»: el Rcoin baja esto */
#define PS_ALTO         402    /* el corte 9 nuevo */
#define PS_INSET        3      /* la imagen va así de adentro del marco */
#define PS_OBST         22, 248, 98, 312   /* el marco de «Obstáculos» (x0, y0, x1, y1) */
#define PS_VICT         106, 248, 182, 312   /* el de «Victoria» */
#define PS_CORTE_VICT   18     /* el recuadro de «Victoria» en gr_1.spr (sólo en salas por equipos) */
#define PS_VICT_XY      100, 225   /* dónde va ese corte, en el panel */
/* ★ el COOPERATIVO: el mini-panel con «Pista» y «Obstáculos» (corte aparte, debajo de «Modo Cooperativo») */
#define PS_COOP_SUBE    50     /* la moneda gorila (su .rui, en el pak) y «Modo Cooperativo» suben esto */
#define PS_COOP_RCOIN   55     /* el Rcoin del cooperativo baja esto */
#define PS_CORTE_COOP   19     /* en gr_1.spr */
#define PS_COOP_Y       365    /* y en la pantalla (x = la del panel) · alto 104 */
#define PS_COOP_PISTA   22, 32, 98, 96   /* los marcos, en el mini-panel */
#define PS_COOP_OBST    106, 32, 182, 96
/* ★★ la versión COMPACTA (pantallas de menos de 1005 px de ancho): cortes 20 (panel), 21 («Victoria»), 22 (cooperativo) */
#define PS_ANGOSTA      1005
#define PS_C_CORTE      20       /* el panel compacto: 355 px, en 0xB4 (no sube) */
#define PS_C_PISTA_SUBE 6        /* lo de «Pista» (imagen, clic, «seleccionando») sube esto */
#define PS_C_RCOIN      45       /* el Rcoin baja esto */
#define PS_C_OBST       22, 237, 98, 272   /* el marco de «Obstáculos» en el compacto */
#define PS_C_VICT_XY    100, 218   /* el corte 21 */
#define PS_C_COOP_RCOIN 19       /* el Rcoin del cooperativo angosto baja esto */
#define PS_C_COOP_PISTA 22, 27, 98, 62   /* corte 22 (68 px) */
#define PS_C_COOP_OBST  106, 27, 182, 62
