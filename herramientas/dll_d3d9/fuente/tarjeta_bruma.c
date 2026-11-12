/* tarjeta_bruma.c — LAS TARJETAS DE NOMBRE «BRUMA»: el humo que da vueltas, fluido (17-oct-2026) · TARJETA_BRUMA.md
 *
 * Las hojas, los íconos y las tablas los arma `herramientas/bruma_crear.py` (paks rnr_ui_lt_bruma / rnr_item_bruma +
 * namecard.xml/shop.bin/shop_lt.txt en rnr_script). Acá va lo del exe.
 * Se INCLUYE desde d3d9_proxy.c (después de `escribir_bytes`).
 *
 *   cNameCard ([0x93433C]) guarda sus hojas en un vector [nc+0xC .. nc+0x10] (`<sprite>` de namecard.xml, en orden) y
 *   dibuja la tarjeta con `0x683FB0(hoja, x, y, recorte, 0)` desde CUATRO lugares, todos adentro de cNameCard:
 *       0x48196C  la sala (0x4818D0, desde 0x5987FC)            recorte = roomcut
 *       0x4819F0  la lista de la sala (0x481980, desde 0x592421)  recorte = chatcut
 *       0x481A70  la mensajería (0x481A00, desde 0x481AA7)        recorte = messengercut
 *       0x481BE5  el asiento con el apodo (0x481B50)              recorte = roomcut
 *   Esos 4 `call` van a bru_dibujar: si la hoja es una de las nuestras (BRU_HOJA0..BRU_HOJA0+9) y el recorte es el 1.º
 *   de una tanda (1, N+1, 2N+1), dibuja el cuadro de la hora y ENCIMA el siguiente con la transparencia de lo que falta
 *   (`0x64E710`, el color por recorte: alfa < 255 prende la mezcla) ⇒ se ve fluido a cualquier ritmo con N cuadros.
 *   Cualquier otra hoja (Nieve, Rubí…) pasa derecho.
 *
 *   ★ EL APODO EN BLANCO (las oscuras). En el asiento (0x481B50) el color del apodo sale de `0x484E90(crayón)`:
 *     sin crayón devuelve 0xFF505050 (gris oscuro), ilegible sobre negro. Sus 2 llamadas (0x481C8B y 0x481CBC, una u
 *     otra) van a bru_color: si lo último que se dibujó en ese asiento fue una bruma OSCURA y no hay crayón, blanco
 *     (el borde negro que le pone 0x63AC30 queda). Las hojas oscuras son las impares (bruma_crear: oscura, clara, …).
 *
 * §2 · EL «PACK DE SLOT MAZINO» (los ojos de la web, fondo del asiento; `herramientas/slot_mazino_crear.py`). Es un MARCO
 *   (slotpack.txt): el juego lo dibuja con recorte = BeginFrame + un contador (0..3) en TRES lugares, y antes busca la
 *   fila del marco por su número con `0x50F8C0(n)`:
 *       0x5AD730 busca · 0x5AD7F3 dibuja        0x5ADB17 busca · 0x5ADBF9 dibuja
 *       ★ 0x598499 busca · 0x59863F dibuja — EL ASIENTO DE LA SALA (0x598480; contador por asiento [sala+0x11F+n]).
 *         Faltaba en la 1.ª vuelta: anonimo03 vio los 4 cuadros de fábrica «a 1 o 2 por segundo». (0x5985BB es el de
 *         pareja, que lleva otra hoja: no se toca.)
 *   Las 3 búsquedas van a slm_fila (anota el número) y los 3 dibujos a slm_dibujar: si el número es uno de los nuestros
 *   (SLM_INDEX0.., el original y las 5 con la bruma de colores en el borde), el cuadro
 *   de la hora entre los SLM_N (recortes 1..SLM_N) y encima el siguiente, mezclado — como las brumas. Otro marco pasa
 *   derecho. Sin la dll se ven los cuadros 1..4 con el contador de fábrica (late a saltos, no rompe).
 *
 *   ⚠ Los números BRU_* y SLM_* los compara `pruebas/probar_bruma.py` con bruma_crear.py / slot_mazino_crear.py.
 *   [bruma] activo=0 en d3d9_proxy.ini lo apaga (se ve el cuadro 0 quieto, y el apodo gris). */

#define BRU_N 24                 /* cuadros por tanda (bruma_crear.N_CUADROS)                    */
#define BRU_MS 3000              /* lo que dura la vuelta (bruma_crear.SEGUNDOS_VUELTA)            */
#define BRU_HOJA0 1              /* la 1.ª hoja nuestra en el vector (bruma_crear.PRIMERA_HOJA)    */
#define BRU_HOJAS 12             /* 6 colores × oscura/clara (bruma_crear.items()) */
/* ★ la de la sala es MÁS GRANDE que la de fábrica (106×51 contra 98×41) para TAPAR el recuadro del equipo (102×47):
 *   el juego la pone a (+2, +3) del recuadro en los dos dibujos del asiento ⇒ se corre (−2−M, −3−M), M = 2
 *   (bruma_crear.SALA_MARGEN; anonimo03, 17-oct: «que cubra el slot de color rojo "equipo"»). Se probó 102 de ancho
 *   alineada con el fondo del asiento y anonimo03 la revirtió. */
#define BRU_SALA_DX (-4)
#define BRU_SALA_DY (-5)
/* §3 · las «FLAMA» (`herramientas/flama_crear.py`, la imagen de anonimo03 animada, 23-oct): 8 hojas más, DESPUÉS de las
 *   brumas (FLA_HOJA0..), los mismos BRU_N cuadros y la misma vuelta. Son oscuras (el apodo en blanco). La de la sala
 *   SOBRESALE (anonimo03: «el marco tapa el slot y las flamas sobresalen»): el recorte es más grande y la línea del marco
 *   cae sobre el cuerpo de la bruma ⇒ se corre (FLA_SALA_DX, FLA_SALA_DY) = flama_crear.SALA_DX/DY. */
#define FLA_HOJA0 13             /* flama_crear.PRIMERA_HOJA (= BRU_HOJA0 + BRU_HOJAS)            */
#define FLA_HOJAS 8              /* len(flama_crear.COLORES)                                         */
/* ★ la de la SALA va SIN MEZCLA, con FLA_N_SALA cuadros (flama_crear.N_SALA): mezclar es dibujar el cuadro y ENCIMA el
 *   siguiente medio transparente, y la luz de afuera de la flama es semitransparente ⇒ a mitad de cada paso queda más
 *   opaca y late (anonimo03, 23-oct: «un parpadeo no deseado, como una sombra»). Charla y mensajería (opacas): mezcladas,
 *   BRU_N cuadros desde FLA_N_SALA+1 y FLA_N_SALA+BRU_N+1. */
#define FLA_N_SALA 56
/* §4 · «CORAZONES» (`herramientas/corazon_crear.py`, 23-oct): la misma hoja que una flama (tamaños, 56 cuadros sin mezcla
 *   en la sala, el mismo corrimiento), DESPUÉS de las 8 flamas ⇒ la dll la trata como una flama más. */
#define COR_HOJAS 1              /* corazon_crear: 1 hoja, la FLA_HOJA0 + FLA_HOJAS (= corazon_crear.PRIMERA_HOJA)  */
/* dónde está la LÍNEA del marco en el recorte de la sala de una flama / corazón (flama_crear: SALA 142×76, la línea de
 *   MARCO_X0 19 / MARCO_Y0 13,5, de 103×48) — para estirarlo a otra caja (la tarjeta grande de la sala de 12) */
#define FLA_CORTE_W 142
#define FLA_CORTE_H 76
#define FLA_LINEA_X 19.0f
#define FLA_LINEA_Y 13.5f
#define FLA_LINEA_W 103.0f
#define FLA_LINEA_H 48.0f
#define FLA_SALA_DX (-20)
#define FLA_SALA_DY (-17)
#define SLM_INDEX0 41            /* el número del 1.er marco (slot_mazino_crear.INDEX0; el 40 se retiró) */
#define SLM_CANT 6               /* las 6 con bruma, la roja incluida (len(VARIANTES))    */
#define SLM_N 32                 /* sus cuadros (slot_mazino_crear.N_CUADROS)              */
#define SLM_MS 3600              /* lo que dura el latido (slot_mazino_crear.SEGUNDOS)     */
/* §5 · «CORAZÓN ELÉCTRICO» (`herramientas/corazon_electrico_crear.py`, 24-oct): la TARJETA va como una flama más (hojas
 *   CEL_HOJAS después de la de corazones) y el FONDO DEL ASIENTO (el túnel de corazones del GIF de anonimo03 + la enredadera)
 *   es un marco más grande que el de fábrica —la enredadera ASOMA E px a los costados y arriba—: se dibuja corrido
 *   (SLT_DX, SLT_DY), con sus SLT_N cuadros en SLT_MS (2 vueltas del GIF), mezclados. */
#define CEL_HOJAS 9              /* len(corazon_electrico_crear.COLORES)                       */
#define DOJ_HOJAS 1              /* dojo_tarjeta_crear: la tarjeta Dojo, después de las del Corazón Eléctrico (§7) */
#define SLT_INDEX0 47            /* corazon_electrico_crear.MARCO0                              */
#define SLT_CANT 9               /* len(corazon_electrico_crear.COLORES)                       */
#define SLT_N 38                 /* corazon_electrico_crear.N_ASIENTO                           */
#define SLT_MS 1900              /* corazon_electrico_crear.MS_ASIENTO                          */
#define SLT_DX (-8)              /* −corazon_electrico_crear.E                                  */
#define SLT_DY (-8)
/* §6 · «PACK DE SLOT DOJO» (`herramientas/bonsai_cobra_crear.py`, 24-oct): el bonsái de Miyagi-Do (con brisa) y la cobra
 *   de Cobra Kai; el mismo formato que el del Corazón Eléctrico (asoma E px), su propio ritmo. */
#define SLB_INDEX0 56            /* bonsai_cobra_crear.MARCO                                     */
#define SLB_CANT 1
#define SLB_N 48                 /* bonsai_cobra_crear.N                                         */
#define SLB_MS 3200              /* bonsai_cobra_crear.MS                                        */
#define SLB_DX (-8)              /* −bonsai_cobra_crear.E                                        */
#define SLB_DY (-8)
/* §8 · «LLUVIA DE ESTRELLAS» (`herramientas/estrellas_crear.py`, 24-oct): la TARJETA va como una flama más (EST_HOJAS
 *   después de la Dojo) y el FONDO DEL ASIENTO es otro marco que asoma E px —acá también abajo: las estrellitas de las
 *   esquinas—, corrido (SLE_DX, SLE_DY), con sus SLE_N cuadros en SLE_MS, mezclados. */
#define EST_HOJAS 1              /* estrellas_crear: la tarjeta, después de la Dojo                 */
#define SLE_INDEX0 57            /* estrellas_crear.MARCO                                          */
#define SLE_CANT 1
#define SLE_N 64                 /* estrellas_crear.N                                              */
#define SLE_MS 3200              /* estrellas_crear.MS                                             */
#define SLE_DX (-8)              /* −estrellas_crear.E                                             */
#define SLE_DY (-8)
/* §9 · «RAYO» (`herramientas/rayo_tarjeta_crear.py`, 25-oct): el marco eléctrico del video de anonimo03, 2 colores; tarjetas
 *   como una flama más, después de la de las estrellas. ★ 29-oct: rehechas con el video 1 a 1 (24 cuadros/s, 324 en
 *   una hoja de 2048×2048). */
#define RAY_HOJAS 2              /* len(rayo_tarjeta_crear.COLORES)                                 */
/* ★ (anonimo03: «movimiento más lento») el rayo tiene su PROPIA vuelta: RAY_N_SALA cuadros sin mezcla en RAY_MS (la sala)
 *   y sus charla/mensajería (BRU_N cuadros) también en RAY_MS; las hojas del rayo son las ÚLTIMAS de la cuenta. */
#define RAY_N_SALA 324           /* rayo_tarjeta_crear.N_SALA                                        */
#define RAY_MS 13500             /* rayo_tarjeta_crear.MS                                            */
#define RAY_HOJA0 (FLA_HOJA0 + FLA_HOJAS + COR_HOJAS + CEL_HOJAS + DOJ_HOJAS + EST_HOJAS)
/* §10 · «ONDAS» (`herramientas/ondas_crear.py`, 29-oct): la imagen de anonimo03 con sus cintas animadas al estilo XMB. La
 *   TARJETA va como una flama más, DESPUÉS de las del rayo, con su propia vuelta (OND_N_SALA sin mezcla en OND_MS; charla y
 *   mensajería, BRU_N mezclados en OND_MS); el FONDO DEL ASIENTO es otro marco, que asoma E px por lado (tapa el de fábrica), con sus
 *   SLO_N cuadros en SLO_MS, mezclados. Las dos con la MISMA vuelta (una cinta baja de una a la otra). */
#define OND_HOJAS 9              /* len(ondas_crear.COLORES): las tarjetas, las últimas hojas         */
#define OND_N_SALA 140           /* ondas_crear.N_SALA                                               */
#define OND_MS 8500              /* ondas_crear.MS                                                   */
#define OND_HOJA0 (RAY_HOJA0 + RAY_HOJAS)
#define SLO_INDEX0 58            /* ondas_crear.MARCO                                                */
#define SLO_CANT 9               /* len(ondas_crear.COLORES)                                         */
#define SLO_N 80                 /* ondas_crear.N                                                    */
#define SLO_MS 8500              /* ondas_crear.MS                                                   */
#define SLO_DX (-3)              /* −ondas_crear.E: asoma 3 px por lado (tapa el asiento de fábrica)   */
#define SLO_DY (-3)
/* §11 · «PACK DE SLOT RAYO» (`herramientas/rayo_slot_crear.py`, 03-nov): el asiento de la tarjeta «Rayo» (§9), el mismo
 *   marco eléctrico sobre el borde del asiento, 2 colores; asoma SLR_DX/DY px por lado, SLR_N cuadros mezclados en la
 *   MISMA vuelta que su tarjeta (RAY_MS): el tramo brillante da la vuelta a la vez en las dos piezas. */
#define SLR_INDEX0 67            /* rayo_slot_crear.MARCO                                            */
#define SLR_CANT 7               /* len(rayo_slot_crear.COLORES) + 4 de rayo_aurora_crear (§12) + 1 de reflejo_estelar_crear (§13), seguidos */
#define SLR_N 162                /* rayo_slot_crear.N                                                */
#define SLR_MS 13500             /* rayo_slot_crear.MS (= RAY_MS)                                    */
#define SLR_DX (-5)              /* −rayo_slot_crear.E                                               */
#define SLR_DY (-5)
/* §12 · «RAYO AURORA / BOREAL» (`herramientas/rayo_aurora_crear.py`, 03-nov): los dos rayos (fino y fuego) con la aurora
 *   del círculo R2FrienDz de RELLENO, en el color del rayo (jugadorX) y en el del video (Boreal). Los ASIENTOS son 4 marcos
 *   más de la §11 (misma forma y vuelta: SLR_CANT); las TARJETAS van como una flama más, DESPUÉS de las de las Ondas, con
 *   la vuelta del rayo (RAY_N_SALA sin mezcla en RAY_MS). */
#define AUR_HOJAS 5              /* len(rayo_aurora_crear.items()) + 1 de reflejo_estelar_crear (§13) */
#define AUR_HOJA0 (OND_HOJA0 + OND_HOJAS)
/* §13 · «REFLEJO ESTELAR» (`herramientas/reflejo_estelar_crear.py`, 05-nov): la imagen de anonimo03 (la pareja, la luz, el
 *   cielo que cae, el agua) animada en capas. Misma forma y vuelta que el Rayo jugadorX: el ASIENTO es un marco más de la
 *   §11 (SLR_CANT) y la TARJETA una hoja más de la §12 (AUR_HOJAS). Sólo cambian esas dos cuentas. */

typedef void  (__attribute__((thiscall)) *F_BRU_DIBUJAR)(void *hoja, int x, int y, int corte, int banderas); /* 0x683FB0 */
typedef void  (__attribute__((thiscall)) *F_BRU_COLOR)(void *hoja, int corte, DWORD argb);                   /* 0x64E710 */
typedef void  (__attribute__((thiscall)) *F_BRU_Z)(void *hoja, int corte, float z);                         /* 0x683F60 */
typedef DWORD (__stdcall *F_BRU_CRAYON)(DWORD crayon);                                                      /* 0x484E90 */

static BYTE *g_bru_base = NULL;
static int   g_bru_oscura = 0;   /* el último dibujo del ASIENTO fue una bruma oscura (lo consume bru_color) */
static LARGE_INTEGER g_bru_hz;
#define BRUV(x) (g_bru_base + ((DWORD)(x) - 0x400000))

/* la hoja `h` es nuestra: su número en el vector de cNameCard, o -1 */
static int bru_cual(void *h)
{
    BYTE *nc = *(BYTE **)BRUV(0x93433C);
    if (!nc || !h) return -1;
    void **ini = *(void ***)(nc + 0xC), **fin = *(void ***)(nc + 0x10);
    if (!ini || fin < ini) return -1;
    int n = (int)(fin - ini);
    for (int k = BRU_HOJA0; k < BRU_HOJA0 + BRU_HOJAS && k < n; k++)
        if (ini[k] == h) return k;
    for (int k = FLA_HOJA0; k < FLA_HOJA0 + FLA_HOJAS + COR_HOJAS + CEL_HOJAS + DOJ_HOJAS + EST_HOJAS + RAY_HOJAS + OND_HOJAS + AUR_HOJAS && k < n; k++)  /* §3..§12 */
        if (ini[k] == h) return k;
    return -1;
}

static void bru_mezclar(void *h, int x, int y, int primero, int zde, int n, int ms_vuelta, int banderas, int mezclar);

/* cuántos recortes tiene la hoja (lista de 0x50 B en [h+0x18 .. h+0x1C]) */
static int bru_cortes(void *h) { return (int)((*(DWORD *)((BYTE *)h + 0x1C) - *(DWORD *)((BYTE *)h + 0x18)) / 0x50); }

static void bru_pintar(void *h, int x, int y, int corte, int banderas, int asiento)
{
    F_BRU_DIBUJAR dib = (F_BRU_DIBUJAR)BRUV(0x683FB0);
    int k = bru_cual(h);
    int flama = k >= FLA_HOJA0;
    if (asiento) g_bru_oscura = (k >= 0 && (flama || ((k - BRU_HOJA0) & 1) == 0));
    if (flama) {                                               /* §3: sus tandas son 1 / FLA_N_SALA+1 / +BRU_N */
        int rayo = k >= RAY_HOJA0;                             /* §9: su propia vuelta */
        int nsala = rayo ? RAY_N_SALA : FLA_N_SALA, vuelta = rayo ? RAY_MS : BRU_MS;
        if (k >= OND_HOJA0) { nsala = OND_N_SALA; vuelta = OND_MS; }                       /* §10: la suya */
        if (k >= AUR_HOJA0) { nsala = RAY_N_SALA; vuelta = RAY_MS; }                       /* §12: la del rayo */
        int sala = corte == 1, otra = corte == nsala + 1 || corte == nsala + BRU_N + 1;
        if ((!sala && !otra) || bru_cortes(h) < nsala + 2 * BRU_N + 1) {
            dib(h, x, y, corte, banderas);
            return;
        }
        if (sala)
            bru_mezclar(h, x + FLA_SALA_DX, y + FLA_SALA_DY, 1, 1, nsala, vuelta, banderas, 0);
        else
            bru_mezclar(h, x, y, corte, corte, BRU_N, vuelta, banderas, 1);
        return;
    }
    int base0 = corte - 1;                                     /* 0, N o 2N si es el 1.º de una tanda */
    if (k < 0 || base0 < 0 || base0 % BRU_N != 0 || base0 / BRU_N > 2 || bru_cortes(h) < corte + BRU_N) {
        dib(h, x, y, corte, banderas);
        return;
    }
    if (base0 == 0) { x += BRU_SALA_DX; y += BRU_SALA_DY; }    /* la de la sala: sobre el recuadro del equipo */
    bru_mezclar(h, x, y, corte, corte, BRU_N, BRU_MS, banderas, 1);
}

/* dibuja la tanda [primero .. primero+n) según la hora, el cuadro de ahora y (si `mezclar`) ENCIMA el siguiente con la
 * transparencia de lo que falta; la z, la del recorte `zde` (la que le puso el juego antes de llamar) */
static void bru_mezclar(void *h, int x, int y, int primero, int zde, int n, int ms_vuelta, int banderas, int mezclar)
{
    F_BRU_DIBUJAR dib = (F_BRU_DIBUJAR)BRUV(0x683FB0);
    LARGE_INTEGER t;
    QueryPerformanceCounter(&t);
    long long ms = g_bru_hz.QuadPart ? (t.QuadPart * 1000 / g_bru_hz.QuadPart) : (long long)GetTickCount();
    int fase = (int)((ms % ms_vuelta) * n * 256 / ms_vuelta);      /* en 256avos de cuadro */
    int f = fase >> 8, resto = fase & 0xFF;
    int c1 = primero + f, c2 = primero + (f + 1) % n;
    float z = *(float *)(*(BYTE **)((BYTE *)h + 0x18) + zde * 0x50 + 0x10);
    F_BRU_Z pz = (F_BRU_Z)BRUV(0x683F60);
    F_BRU_COLOR col = (F_BRU_COLOR)BRUV(0x64E710);
    pz(h, c1, z);
    col(h, c1, 0xFFFFFFFF);
    dib(h, x, y, c1, banderas);
    if (mezclar && resto > 2) {
        pz(h, c2, z);
        col(h, c2, ((DWORD)resto << 24) | 0xFFFFFF);
        dib(h, x, y, c2, banderas);
    }
}

static void __fastcall bru_dibujar(void *h, void *nada, int x, int y, int corte, int banderas)
{
    (void)nada;
    bru_pintar(h, x, y, corte, banderas, 0);
}

static void __fastcall bru_dibujar_asiento(void *h, void *nada, int x, int y, int corte, int banderas)
{
    (void)nada;
    bru_pintar(h, x, y, corte, banderas, 1);
}

static DWORD __stdcall bru_color(DWORD crayon)
{
    DWORD c = ((F_BRU_CRAYON)BRUV(0x484E90))(crayon);
    if ((crayon & 0xFF) == 0 && g_bru_oscura) c = 0xFFFFFFFF;
    g_bru_oscura = 0;
    return c;
}

/* ── §2 · el Pack de Slot Mazino ── */
typedef void *(__attribute__((thiscall)) *F_SLM_FILA)(void *mgr, DWORD n);                                 /* 0x50F8C0 */
static int g_slm_ultimo = -1;    /* el número del marco que se acaba de buscar (lo consume slm_dibujar) */

static void *__fastcall slm_fila(void *mgr, void *nada, DWORD n)
{
    (void)nada;
    g_slm_ultimo = (int)(n & 0xFF);
    return ((F_SLM_FILA)BRUV(0x50F8C0))(mgr, n);
}

static void __fastcall slm_dibujar(void *h, void *nada, int x, int y, int corte, int banderas)
{
    (void)nada;
    int mio = g_slm_ultimo >= SLM_INDEX0 && g_slm_ultimo < SLM_INDEX0 + SLM_CANT;
    int tunel = g_slm_ultimo >= SLT_INDEX0 && g_slm_ultimo < SLT_INDEX0 + SLT_CANT;       /* §5 */
    int dojo = g_slm_ultimo >= SLB_INDEX0 && g_slm_ultimo < SLB_INDEX0 + SLB_CANT;        /* §6 */
    int estrellas = g_slm_ultimo >= SLE_INDEX0 && g_slm_ultimo < SLE_INDEX0 + SLE_CANT;   /* §8 */
    int ondas = g_slm_ultimo >= SLO_INDEX0 && g_slm_ultimo < SLO_INDEX0 + SLO_CANT;       /* §10 */
    int rayo = g_slm_ultimo >= SLR_INDEX0 && g_slm_ultimo < SLR_INDEX0 + SLR_CANT;        /* §11 */
    g_slm_ultimo = -1;
    if (rayo && h && bru_cortes(h) > SLR_N && corte >= 1 && corte <= SLR_N) {
        bru_mezclar(h, x + SLR_DX, y + SLR_DY, 1, corte, SLR_N, SLR_MS, banderas, 1);
        return;
    }
    if (ondas && h && bru_cortes(h) > SLO_N && corte >= 1 && corte <= SLO_N) {
        bru_mezclar(h, x + SLO_DX, y + SLO_DY, 1, corte, SLO_N, SLO_MS, banderas, 1);
        return;
    }
    if (dojo && h && bru_cortes(h) > SLB_N && corte >= 1 && corte <= SLB_N) {
        bru_mezclar(h, x + SLB_DX, y + SLB_DY, 1, corte, SLB_N, SLB_MS, banderas, 1);
        return;
    }
    if (estrellas && h && bru_cortes(h) > SLE_N && corte >= 1 && corte <= SLE_N) {
        bru_mezclar(h, x + SLE_DX, y + SLE_DY, 1, corte, SLE_N, SLE_MS, banderas, 1);
        return;
    }
    if (mio && h && bru_cortes(h) > SLM_N && corte >= 1 && corte <= SLM_N)
        bru_mezclar(h, x, y, 1, corte, SLM_N, SLM_MS, banderas, 1);
    else if (tunel && h && bru_cortes(h) > SLT_N && corte >= 1 && corte <= SLT_N)
        bru_mezclar(h, x + SLT_DX, y + SLT_DY, 1, corte, SLT_N, SLT_MS, banderas, 1);
    else
        ((F_BRU_DIBUJAR)BRUV(0x683FB0))(h, x, y, corte, banderas);
}

/* los `call` de una lista, a sus nuevos destinos: si alguno no es el esperado no se toca ninguno */
static int bru_mirar(const DWORD *va, const DWORD *dst, int n, const char *que)
{
    for (int i = 0; i < n; i++) {
        BYTE *c = BRUV(va[i]);
        if (c[0] != 0xE8 || (DWORD)(c + 5 + *(int *)(c + 1)) != (DWORD)BRUV(dst[i])) {
            apuntar("  [bruma] ⛔ %s: la llamada de 0x%06X no es la esperada: no se toca nada", que, va[i]);
            return 0;
        }
    }
    return 1;
}

/* `call destino` en va → `call nuevo`, con guarda */
static int bru_desviar(DWORD va, DWORD destino, void *nuevo, const char *que)
{
    BYTE esp[5] = { 0xE8 }, nue[5] = { 0xE8 };
    DWORD r1 = destino - (va + 5);
    DWORD r2 = (DWORD)nuevo - (DWORD)(BRUV(va) + 5);
    for (int i = 0; i < 4; i++) { esp[1 + i] = (BYTE)(r1 >> (8 * i)); nue[1 + i] = (BYTE)(r2 >> (8 * i)); }
    return escribir_bytes(va, esp, nue, 5, que);
}

/* ★ la TARJETA GRANDE de la sala de 12 (sala12_vista.c) estira el recorte de la sala a su barra (x, y, w, h). Con una
 *   flama / corazón (recorte de 142×76 con la línea adentro) quedaba chico y corrido (anonimo03, 23-oct: «el slot de id
 *   falla en el formato de 12 jugadores, la zona del mini char») ⇒ se estira para que la LÍNEA cubra la barra (el
 *   brillo asoma por fuera) y el recorte es el cuadro de la hora (sin mezcla, como en el asiento). 1 si lo cambió. */
static int bru_ajustar_grande(void *h, int *x, int *y, int *w, int *alto, int *corte)
{
    int k = g_bru_base ? bru_cual(h) : -1;
    int nsala = k >= RAY_HOJA0 ? RAY_N_SALA : FLA_N_SALA, vuelta = k >= RAY_HOJA0 ? RAY_MS : BRU_MS;   /* §9 */
    if (k >= OND_HOJA0) { nsala = OND_N_SALA; vuelta = OND_MS; }                                       /* §10 */
    if (k >= AUR_HOJA0) { nsala = RAY_N_SALA; vuelta = RAY_MS; }                                       /* §12 */
    if (!g_bru_base || k < FLA_HOJA0 || *corte != 1 || bru_cortes(h) <= nsala) return 0;
    float sx = *w / FLA_LINEA_W, sy = *alto / FLA_LINEA_H;
    *x -= (int)(FLA_LINEA_X * sx + 0.5f);
    *y -= (int)(FLA_LINEA_Y * sy + 0.5f);
    *w = (int)(FLA_CORTE_W * sx + 0.5f);
    *alto = (int)(FLA_CORTE_H * sy + 0.5f);
    LARGE_INTEGER t;
    QueryPerformanceCounter(&t);
    long long ms = g_bru_hz.QuadPart ? (t.QuadPart * 1000 / g_bru_hz.QuadPart) : (long long)GetTickCount();
    *corte = 1 + (int)((ms % vuelta) * nsala / vuelta);
    return 1;
}

/* ★ y lo de la Bruma y el Slot Mazino en la tarjeta grande de la sala de 12 (anonimo03, 23-oct: «sólo se anima el set
 *   nuevo, el Mazino anterior no»): la tarjeta grande es nuestra y los dibuja directo (un cuadro / el contador de 4 de
 *   fábrica). Éstas le dicen qué par de cuadros mezclar a esta hora, como bru_mezclar. 1 si es nuestro. */
static void bru_par(int primero, int n, int ms_vuelta, int *c1, int *c2, int *resto)
{
    LARGE_INTEGER t;
    QueryPerformanceCounter(&t);
    long long ms = g_bru_hz.QuadPart ? (t.QuadPart * 1000 / g_bru_hz.QuadPart) : (long long)GetTickCount();
    int fase = (int)((ms % ms_vuelta) * n * 256 / ms_vuelta);
    *c1 = primero + (fase >> 8);
    *c2 = primero + ((fase >> 8) + 1) % n;
    *resto = fase & 0xFF;
}

static int bru_par_tarjeta(void *h, int corte, int *c1, int *c2, int *resto)        /* una Bruma, recorte de la sala */
{
    int k = g_bru_base ? bru_cual(h) : -1;
    if (k < BRU_HOJA0 || k >= BRU_HOJA0 + BRU_HOJAS || corte != 1 || bru_cortes(h) <= BRU_N) return 0;
    bru_par(1, BRU_N, BRU_MS, c1, c2, resto);
    return 1;
}

static int bru_par_marco(int marco, void *h, int *c1, int *c2, int *resto)        /* un Pack de Slot Mazino */
{
    if (!g_bru_base || marco < SLM_INDEX0 || marco >= SLM_INDEX0 + SLM_CANT || !h || bru_cortes(h) <= SLM_N) return 0;
    bru_par(1, SLM_N, SLM_MS, c1, c2, resto);
    return 1;
}

static void tarjeta_bruma_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    g_bru_base = (BYTE *)GetModuleHandleA(NULL);
    if (!GetPrivateProfileIntA("bruma", "activo", 1, ini)) {
        apuntar("  [bruma] APAGADA ([bruma] activo=0): las brumas quedan quietas");
        return;
    }
    QueryPerformanceFrequency(&g_bru_hz);
    /* §2 primero (independiente): las 3 búsquedas y los 3 dibujos (de soltero) del marco del asiento */
    static const DWORD SLM_VA[6] = { 0x5AD730, 0x5ADB17, 0x598499, 0x5AD7F3, 0x5ADBF9, 0x59863F };
    static const DWORD SLM_DST[6] = { 0x50F8C0, 0x50F8C0, 0x50F8C0, 0x683FB0, 0x683FB0, 0x683FB0 };
    if (bru_mirar(SLM_VA, SLM_DST, 6, "slot Mazino")) {
        int ok2 = 1;
        for (int i = 0; i < 6; i++)
            ok2 = ok2 && bru_desviar(SLM_VA[i], SLM_DST[i], i < 3 ? (void *)slm_fila : (void *)slm_dibujar,
                                     i < 3 ? "slot Mazino: búsqueda del marco" : "slot Mazino: dibujo del marco");
        if (ok2) apuntar("  [bruma] ★ los Pack de Slot Mazino (marcos %d..%d) laten (%d cuadros, %d ms, mezclados)"
                         " y el Corazón Eléctrico (marco %d..%d, %d cuadros, %d ms, corrido %d,%d)",
                         SLM_INDEX0, SLM_INDEX0 + SLM_CANT - 1, SLM_N, SLM_MS, SLT_INDEX0, SLT_INDEX0 + SLT_CANT - 1,
                         SLT_N, SLT_MS, SLT_DX, SLT_DY);
    }
    /* las brumas: los 6 se miran primero */
    static const DWORD DIB[4] = { 0x48196C, 0x4819F0, 0x481A70, 0x481BE5 };
    static const DWORD COL[2] = { 0x481C8B, 0x481CBC };
    static const DWORD DIB_DST[4] = { 0x683FB0, 0x683FB0, 0x683FB0, 0x683FB0 };
    static const DWORD COL_DST[2] = { 0x484E90, 0x484E90 };
    if (!bru_mirar(DIB, DIB_DST, 4, "bruma") || !bru_mirar(COL, COL_DST, 2, "bruma")) return;
    int ok = 1;
    for (int i = 0; i < 3; i++) ok &= bru_desviar(DIB[i], 0x683FB0, (void *)bru_dibujar, "bruma: dibujo de la tarjeta");
    ok &= bru_desviar(DIB[3], 0x683FB0, (void *)bru_dibujar_asiento, "bruma: dibujo del asiento");
    for (int i = 0; i < 2; i++) ok &= bru_desviar(COL[i], 0x484E90, (void *)bru_color, "bruma: color del apodo");
    if (ok) apuntar("  [bruma] ★ las tarjetas Bruma (hojas %d..%d) y Flama (%d..%d) se mueven (%d cuadros, vuelta de %d ms,"
                    " mezclados) y el apodo va en blanco sobre las oscuras", BRU_HOJA0, BRU_HOJA0 + BRU_HOJAS - 1,
                    FLA_HOJA0, FLA_HOJA0 + FLA_HOJAS - 1, BRU_N, BRU_MS);
}
