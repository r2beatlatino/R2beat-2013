/* GENERADO por herramientas/poses_pareja_crear.py — no se edita a mano. */
/* coupleaction.xml del VFUN, con NUESTROS efectos y Fx. Orden de los 6: ReadyS ReadyN WinS WinN LoseS LoseN. */
#define PAR_FILAS 4
typedef struct { int id, efecto, simetria; unsigned char tipo[6]; unsigned short fx[2][6]; } PAR_FILA;
static const PAR_FILA PAR_TABLA[PAR_FILAS] = {
    { 0, 0, 1, {3, 3, 1, 1, 1, 1}, {{0, 0, 0, 0, 0, 0}, {0, 0, 0, 0, 0, 0}} },   /* toda pareja (sin ítem) */
    { 1, 3282, 0, {3, 3, 1, 1, 1, 1}, {{801, 800, 800, 800, 802, 802}, {0, 803, 803, 803, 802, 802}} },   /* 1000962 «Pose de Pareja: El Mejor Amor» */
    { 2, 3283, 0, {3, 3, 1, 1, 1, 1}, {{805, 804, 804, 804, 802, 802}, {0, 806, 806, 806, 802, 802}} },   /* 1000961 «Pose de Pareja: Amor de Mil Años» */
    { 3, 3281, 0, {3, 3, 1, 1, 1, 1}, {{925, 924, 932, 931, 928, 927}, {0, 926, 934, 933, 930, 929}} },   /* 1000963 «Pose de Pareja: Encuentro Romántico» */
};
