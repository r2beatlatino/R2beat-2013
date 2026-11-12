/* globo_combo.c — EL GLOBO DEL COMBO (14-oct-2026)
 *
 *   anonimo03: «el que está esperando para correr o ya corrió no ve los combos del de su equipo (¿como el espectador?)»
 *   → «como un globo de texto, pegado al char que corre, con su contador de combos · solamente cuando se está
 *   espectando o en modo relevo, no cuando uno mismo es el corredor».
 *
 *   Por qué no se ve hoy: el combo NO viaja. A los demás corredores el cliente los mueve con piloto automático (todo
 *   PERFECT) y el latido sólo dice «tiene 40 o más» (documentacion/ESPECTADOR_INVESTIGACION_SYNC_Y_COMBOS.md §3). El
 *   contador del HUD del que espera muestra ese combo falso, o nada. Lo que se hace acá:
 *
 *     1 · EL QUE CORRE LO MANDA: cada cuadro de carrera el juego atiende a cada corredor (0x500AB0, llamado desde
 *         0x4F97CB); en el MÍO se lee el combo que se ve ([cPlayer+0x190] xor [0x904210]) y, si cambió (como mucho
 *         cada GC_CADA ms) o cada GC_LATIDO ms, va por el FF4E de la carrera con un sub NUESTRO:
 *             0x5C7FB0(red = [0x9314D0], sub 0x70, A = 0x4743_00_asiento ('GC'), B = combo)
 *         El 0x70 no lo atiende el juego (0x4FCAD0 lo manda al «default», 0x5685F0, que sólo conoce 0x82..0x88): un
 *         cliente sin esta dll lo ignora. Si estoy esperando mi tramo o ya corrí (0x4F2F50) no mando nada.
 *         El server lo releva sólo a quien le sirve: a los sentados de una sala de RELEVO (lobby.py). Los NPC que
 *         corren mandan el suyo desde el server (npc_carrera.py).
 *         ★ El ESPECTADOR no lo necesita: con el modo transmisión (transmision.c) re-juzga las teclas de cada
 *           corredor, así que su copia del corredor ya tiene el combo de verdad, con el mismo retraso que lo que ve.
 *           El globo del espectador sale de ahí (salvo un NPC, que no aprieta teclas: ése sí manda el 0x70).
 *     2 · EL QUE MIRA LO GUARDA: 0x4FCAD0 (el receptor del FF4E) con un trampolín: el sub 0x70 con la firma 'GC' se
 *         anota en g_gc_combo[asiento] y no sigue; todo lo demás, como siempre.
 *     3 · EL GLOBO: el nombre sobre la cabeza lo pone 0x5009D0(cPlayer, x, y) (llamado desde 0x500C61, sólo para los
 *         que NO soy yo: x = el centro, y = arriba del nombre). Ahí, después del nombre: si es el corredor que sigue la
 *         cámara ([cGame+0x5D]), no soy yo, la carrera es de RELEVO ([cGame+0xC] & 0x40) o yo soy ESPECTADOR
 *         ([cGame+0xC01]), y hay noticias de su combo (si no llegan en GC_SIN_DATOS ms, o
 *         llega su «terminó», se apaga SUAVE; y si su nombre deja de dibujarse, el globo se desvanece donde estaba) ⇒ el globo con el número, con la colita
 *         apuntando al nombre. El globo está en la hoja de la carrera (sala12_carrera.tga, 4 piezas: se estira con
 *         las cifras), con una imagen propia (z: delante del nombre y detrás del HUD). ★ El CONTADOR de adentro es el
 *         del juego — su hoja y su animación, achicados (ver gc_globo).
 *
 *     4 · ★ EL «BREAK»: con el combo en 0 después de tenerlo, el «break» del juego (su mancha, su letrero y su «COMBO»,
 *         con su reloj); el que corre manda el corte EN EL ACTO (si no, el acierto siguiente lo tapa).
 *
 *   [globo] activo=0 lo apaga entero (no manda ni dibuja) · dy = cuánto baja la colita desde la y del nombre (10)
 *   · z (milésimas, 780: sólo si no se halla la de los números del HUD — el globo va justo debajo) · escala (milésimas del contador del juego, 380) · color (ARGB en hex:
 *   el tinte del globo) · apagar=1 (se desvanece como el del juego) · salto (% del «pop» del
 *   juego, 30) · ocultar_contador=0 (el espectador ve también el contador de arriba) · log=1 anota lo que manda y recibe.
 */
#define GCV(x) (g_gc_base + ((DWORD)(x) - 0x400000))
#define GC_SUB 0x70
#define GC_FIRMA 0x47430000u                                  /* 'G' 'C' en los 2 bytes altos de A */
#define GC_CADA 250                                           /* ms entre dos envíos por cambio (★ era 150: más barato) */
#define GC_LATIDO 1500                                        /* ms: aunque no cambie (si no, el globo se apaga) */
#define GC_FIN 0x80000000u                                    /* en B: «terminó su tramo» (el globo se apaga) */
#define GC_SIN_DATOS 2200                                     /* ms sin noticias: el globo empieza a apagarse */
#define GC_APAGA 600                                          /* ms del apagado suave */

static BYTE *g_gc_base = NULL;
static int g_gc_activo = 0;
static int g_gc_dy = 10, g_gc_log = 0;
static float g_gc_z = 0.78f;
static int g_gc_escala = 380, g_gc_apagar = 0, g_gc_salto = 30;   /* milésimas del contador · 1 = se desvanece · % del salto */
static DWORD g_gc_color = 0xFFFFFFFF;                         /* el tinte del globo (blanco = como está en la hoja) */
static int g_gc_ultimo[16];
static DWORD g_gc_t_cambio[16];
static DWORD g_gc_t_break[16];                                /* cuándo fue el último corte (de > 0 a 0) */
#define GC_BREAK_MIN 900                                      /* ms del «break» entero (aparece, se asienta, se desvanece) aunque vuelva a acertar */
static DWORD g_gc_fin[16];                                    /* cuándo llegó «terminó su tramo» (0 = no) */
static int g_gc_ex[16], g_gc_ey[16], g_gc_ef[16];             /* dónde y con qué opacidad se dibujó la última vez */
static DWORD g_gc_t_visto[16];                                /*   y cuándo (0 = no está a la vista) */
static int g_gc_ancla = -1;                                   /* el corredor desde el que se apagan los «huérfanos» */
/* ★ QA 14-oct · EL ESPECTADOR QUE SALTA: lo que llegó de cada asiento (el combo real, con su hora), para sembrar */
#define GC_HIST 32
static DWORD g_gc_h_t[16][GC_HIST];
static int g_gc_h_c[16][GC_HIST], g_gc_h_i[16];
static int g_gc_seguia = -1, g_gc_n_siembra = 0, g_gc_n_resiembra = 0;
static DWORD g_gc_t_desvio = 0;                               /* desde cuándo la copia se aparta del real */
static DWORD g_gc_t_salto = 0;                                /* cuándo cambió de corredor */
static BYTE *g_gc_juego_ant = NULL;

/* ═══ ★ 14-oct · LA CALCULADORA DEL ESPECTADOR (documentacion/PAQUETES_ESPECTADOR.md) ═══════════════════════════════
 *   El que corre manda sus notas (0x71: hasta 4 por paquete, cada 4 o 400 ms) y cada 8 s la BASE (0x72: 7 partes con
 *   todo el conteo y el seq de la última tanda incluida). SÓLO si alguien mira ([cGame+0xC1C], lo prende el FFBB).
 *   El que mira guarda lo que llega en una fila por asiento, lo aplica `espera_ms` después de que LLEGÓ (alineado con
 *   la transmisión), y arma una calculadora por asiento: un hueco en el seq ⇒ «sin sincronizar» hasta la próxima base. */
#define GC_SUB_CALC 0x71
#define GC_SUB_BASE 0x72
#define GC_FIRMA_CALC 0x43u                                     /* 'C' en el byte alto de A */
#define GC_TANDA_MS 400
#define GC_BASE_MS 8000
#define GC_COLA 64
typedef struct { int caj[11]; int notas; long long suma; int seg, mejor; } GC_CALC;
typedef void (TCK *F_GC_MANDAR_C)(void *red, int sub, DWORD a, DWORD b);   /* 0x5C7FB0 (el mismo que F_GC_MANDAR) */
static BYTE *gc_juego(void);
static int g_gc_nb[4], g_gc_nn = 0, g_gc_mirar_ant = 0, g_gc_n_calc = 0;
static BYTE g_gc_seq = 0;
static DWORD g_gc_t_tanda = 0, g_gc_t_base = 0;
static GC_CALC g_gc_calc[16], g_gc_tmp[16];
static int g_gc_cseq[16], g_gc_csinc[16], g_gc_tmask[16], g_gc_tseq[16];
typedef struct { DWORD t, a, b; BYTE sub; } GC_PEND;
static GC_PEND g_gc_cola[16][GC_COLA];
static unsigned g_gc_cola_i[16], g_gc_cola_f[16];

static void gc_calc_al_juzgar(int p, int reinicio)              /* el que corre: lo llama calculadora.c */
{
    if (reinicio) { g_gc_nn = 0; g_gc_t_base = 0; return; }   /* canción nueva: la base sale ya */
    if (g_gc_nn >= 4) return;                                   /* (no pasa: se manda en el cuadro) */
    if (!g_gc_nn) g_gc_t_tanda = GetTickCount();
    g_gc_nb[g_gc_nn++] = p < 0 ? 0 : p > 100 ? 100 : p;
}

static void gc_calc_mandar(void *red, int asiento, int mirar)   /* el que corre, en cada cuadro */
{
    if (mirar && !g_gc_mirar_ant) g_gc_t_base = 0;              /* entró alguien a mirar: base ya */
    g_gc_mirar_ant = mirar;
    if (!mirar) { g_gc_nn = 0; return; }                        /* nadie mira: no se manda NADA */
    DWORD ahora = GetTickCount();
    F_GC_MANDAR_C mandar = (F_GC_MANDAR_C)GCV(0x5C7FB0);
    if (g_gc_nn == 4 || (g_gc_nn && ahora - g_gc_t_tanda >= GC_TANDA_MS)) {
        DWORD b = 0;
        for (int i = 0; i < g_gc_nn; i++) b |= (DWORD)g_gc_nb[i] << (8 * i);
        g_gc_seq++;
        mandar(red, GC_SUB_CALC, (GC_FIRMA_CALC << 24) | ((DWORD)g_gc_seq << 16) | ((DWORD)g_gc_nn << 8) | asiento, b);
        g_gc_nn = 0;
        g_gc_n_calc++;
    }
    if (!g_gc_t_base || ahora - g_gc_t_base >= GC_BASE_MS) {
        int bajo = g_calc_caj[0] + g_calc_caj[1] + g_calc_caj[2] + g_calc_caj[3] + g_calc_caj[4];
        DWORD v[7] = { (DWORD)(g_calc_notas & 0xFFFF) | ((DWORD)(g_calc_mejor & 0xFFFF) << 16), (DWORD)g_calc_suma,
                       (DWORD)g_calc_seguidas, (DWORD)(g_calc_caj[10] & 0xFFFF) | ((DWORD)(g_calc_caj[9] & 0xFFFF) << 16),
                       (DWORD)(g_calc_caj[8] & 0xFFFF) | ((DWORD)(g_calc_caj[7] & 0xFFFF) << 16),
                       (DWORD)(g_calc_caj[6] & 0xFFFF) | ((DWORD)(g_calc_caj[5] & 0xFFFF) << 16), (DWORD)bajo };
        for (int i = 0; i < 7; i++)
            mandar(red, GC_SUB_BASE, (GC_FIRMA_CALC << 24) | ((DWORD)g_gc_seq << 16) | ((DWORD)i << 8) | asiento, v[i]);
        g_gc_t_base = ahora | 1;
    }
}

static void gc_calc_nota(GC_CALC *c, int p)                     /* lo mismo que cuenta calculadora.c */
{
    int i = p >= 99 ? 10 : p / 10;
    c->caj[i <= 4 ? 0 : i]++;
    c->notas++;
    c->suma += p;
    if (p >= 99) { if (++c->seg > c->mejor) c->mejor = c->seg; }
    else c->seg = 0;
}

static void gc_calc_aplicar(GC_PEND *e, int k)                  /* el que mira: una tanda o una parte de la base */
{
    int seq = (e->a >> 16) & 0xFF, x = (e->a >> 8) & 0xFF;
    if (e->sub == GC_SUB_CALC) {
        if (!g_gc_csinc[k]) return;                             /* esperando la base */
        if (seq != ((g_gc_cseq[k] + 1) & 0xFF) || x < 1 || x > 4) { g_gc_csinc[k] = 0; return; }   /* hueco */
        for (int i = 0; i < x; i++) gc_calc_nota(&g_gc_calc[k], (int)((e->b >> (8 * i)) & 0xFF));
        g_gc_cseq[k] = seq;
        return;
    }
    if (x > 6) return;
    if (g_gc_tseq[k] != seq || !g_gc_tmask[k]) { ZeroMemory(&g_gc_tmp[k], sizeof(GC_CALC)); g_gc_tmask[k] = 0; g_gc_tseq[k] = seq; }
    GC_CALC *t = &g_gc_tmp[k];
    DWORD b = e->b, lo = b & 0xFFFF, hi = b >> 16;
    switch (x) {
    case 0: t->notas = (int)lo; t->mejor = (int)hi; break;
    case 1: t->suma = b; break;
    case 2: t->seg = (int)b; break;
    case 3: t->caj[10] = (int)lo; t->caj[9] = (int)hi; break;
    case 4: t->caj[8] = (int)lo; t->caj[7] = (int)hi; break;
    case 5: t->caj[6] = (int)lo; t->caj[5] = (int)hi; break;
    case 6: t->caj[0] = (int)b; break;
    }
    g_gc_tmask[k] |= 1 << x;
    if (g_gc_tmask[k] == 0x7F) {                                /* la base completa: re-sincronizado */
        g_gc_calc[k] = *t;
        g_gc_cseq[k] = seq;
        g_gc_csinc[k] = 1;
        g_gc_tmask[k] = 0;
    }
}

static void gc_calc_recibir(int sub, DWORD a, DWORD b)         /* el que mira: a la fila (se aplica con el atraso) */
{
    int k = a & 0xFF;
    if (k >= 16) return;
    if (g_gc_cola_f[k] - g_gc_cola_i[k] >= GC_COLA) { g_gc_cola_i[k]++; g_gc_csinc[k] = 0; }   /* llena: se pierde */
    GC_PEND *e = &g_gc_cola[k][g_gc_cola_f[k]++ % GC_COLA];
    e->t = GetTickCount(); e->a = a; e->b = b; e->sub = (BYTE)sub;
}

static void gc_calc_al_dia(void)                                /* el que mira, una vez por cuadro */
{
    DWORD ahora = GetTickCount();
    for (int k = 0; k < 16; k++)
        while (g_gc_cola_i[k] != g_gc_cola_f[k]) {
            GC_PEND *e = &g_gc_cola[k][g_gc_cola_i[k] % GC_COLA];
            if (ahora - e->t < g_tx_espera_ms) break;
            gc_calc_aplicar(e, k);
            g_gc_cola_i[k]++;
        }
}

static void gc_calc_mostrar(void)                               /* antes de que calculadora.c dibuje */
{
    BYTE *g = gc_juego();
    if (!g_gc_activo || !g || !g[0xC01]) return;
    int k = g[0x5D];
    if (k >= 16) return;
    GC_CALC *c = &g_gc_calc[k];
    for (int i = 0; i < 11; i++) g_calc_caj[i] = c->caj[i];
    g_calc_notas = c->notas; g_calc_suma = c->suma; g_calc_seguidas = c->seg; g_calc_mejor = c->mejor;
}

static void gc_calc_limpiar(void)
{
    ZeroMemory(g_gc_calc, sizeof g_gc_calc); ZeroMemory(g_gc_tmask, sizeof g_gc_tmask);
    ZeroMemory(g_gc_csinc, sizeof g_gc_csinc); ZeroMemory(g_gc_cola_i, sizeof g_gc_cola_i);
    ZeroMemory(g_gc_cola_f, sizeof g_gc_cola_f);
}
static DWORD g_gc_t_ancla = 0;
static void *g_gc_orig_ff4e = NULL;                           /* trampolín de 0x4FCAD0 */
static void *g_gc_orig_cont[2] = { NULL, NULL };              /* trampolines del contador del HUD (0x54B670 / 0x54B920) */
static int g_gc_ocultar = 1;                                  /* [globo] ocultar_contador: el espectador sólo ve el globo */
static int g_gc_combo[16];
static DWORD g_gc_t[16];                                      /* GetTickCount de cuando llegó (0 = nunca) */
static int g_gc_enviado = -1;
static DWORD g_gc_t_env = 0;
static int g_gc_n_env = 0, g_gc_n_rec = 0, g_gc_n_dib = 0;
static BYTE g_gc_hoja[0x100];                                 /* el c2DImage nuestro (la clase ocupa 0x40) */
static int g_gc_estado = 0;                                   /* 0 sin cargar · 1 lista · -1 no está la hoja */

typedef void  (TCK *F_GC_JUGADOR)(void *p, float t);                         /* 0x500AB0, ret 4 */
typedef void  (TCK *F_GC_ETIQUETA)(void *p, int x, int y);                   /* 0x5009D0, ret 8 */
typedef void  (TCK *F_GC_FF4E)(void *g, int sub, DWORD a, DWORD b);           /* 0x4FCAD0, ret 0xC */
typedef void  (TCK *F_GC_MANDAR)(void *red, int sub, DWORD a, DWORD b);       /* 0x5C7FB0, ret 0xC */
typedef int   (TCK *F_GC_ESPERA)(void *g, int k);                            /* 0x4F2F50, ret 4 */
typedef void *(TCK *F_GC_CREAR)(void *self);                                 /* 0x64E560 */
typedef int   (TCK *F_GC_CARGAR)(void *self, const char *ruta, const char *prefijo);   /* 0x64E1E0 */
typedef void  (TCK *F_GC_RECORTE)(void *self, float x, float y, int u, int v, int w, int h, float z);  /* 0x64EC40 */
typedef void  (TCK *F_GC_POS)(void *spr, int corte, int x, int y);           /* 0x64D990, ret 0xC */
typedef void  (TCK *F_GC_DIB)(void *spr, int corte, int banderas);           /* 0x64EE40, ret 8 */
typedef void  (TCK *F_GC_TAM)(void *spr, int corte, int w, int h);           /* 0x64DB90, ret 0xC */
typedef void  (TCK *F_GC_COLOR)(void *spr, int corte, DWORD argb);           /* 0x64E710, ret 8 */

static int gc_escribir(DWORD va, const void *b, int n)
{
    DWORD viejo = 0;
    if (!VirtualProtect(GCV(va), n, PAGE_EXECUTE_READWRITE, &viejo)) return 0;
    CopyMemory(GCV(va), b, n);
    VirtualProtect(GCV(va), n, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), GCV(va), n);
    return 1;
}

static int gc_llama_a(DWORD sitio, DWORD destino)             /* ¿el call de `sitio` va a `destino`? */
{
    BYTE *p = GCV(sitio);
    return p[0] == 0xE8 && (DWORD)(p + 5 + *(int *)(p + 1)) == (DWORD)GCV(destino);
}

static void gc_desviar(DWORD sitio, void *a)
{
    int rel = (int)((DWORD)a - ((DWORD)GCV(sitio) + 5));
    gc_escribir(sitio + 1, &rel, 4);
}

static BYTE *gc_juego(void) { return *(BYTE **)GCV(0x9314C8); }

static int gc_mi_asiento(void)
{
    BYTE *padron = *(BYTE **)GCV(0x931660);
    return padron ? padron[0x40] : -1;
}

static int gc_combo_de(BYTE *p)                               /* el combo que se VE (el del HUD) */
{
    return (int)(*(DWORD *)(p + 0x190) ^ *(DWORD *)GCV(0x904210));
}

static void gc_globo(int k, int x, int y, int combo, int f, float esc);
static float g_gc_eesc[16];                                   /* el tamaño con que se dibujó cada globo (huérfanos) */
#define GC_CHICO 0.75f                                        /* ★ los globos de los que NO sigo (espectador): 75 % */

/* ★ el apagado suave (anonimo03: «el globo debe desaparecer al final suavemente»): si el nombre de un corredor deja de
 *   dibujarse (terminó, la cámara pasó al siguiente, fin de la carrera) su globo se desvanece donde estaba, en GC_APAGA
 *   ms. Se dibuja desde un corredor «ancla» (el primero que atiende el juego en cada cuadro). */
static void gc_huerfanos(int asiento)
{
    DWORD ahora = GetTickCount();
    if (g_gc_ancla < 0 || ahora - g_gc_t_ancla > 200) g_gc_ancla = asiento;
    if (asiento != g_gc_ancla) return;
    g_gc_t_ancla = ahora;
    for (int k = 0; k < 16; k++) {
        if (!g_gc_t_visto[k]) continue;
        DWORD fuera = ahora - g_gc_t_visto[k];
        if (fuera < 60) continue;                               /* se sigue dibujando con su nombre */
        int f = g_gc_ef[k] - (int)((fuera - 60) * 256 / GC_APAGA);
        if (f <= 0) {
            g_gc_t_visto[k] = 0;
            continue;
        }
        DWORD t_v = g_gc_t_visto[k];
        gc_globo(k, g_gc_ex[k], g_gc_ey[k], g_gc_ultimo[k], f, g_gc_eesc[k] > 0 ? g_gc_eesc[k] : 1.0f);
        g_gc_t_visto[k] = t_v;                                  /* gc_globo lo pone en «ahora»: no es un nombre */
    }
}

/* ★ QA 14-oct (anonimo03: «en los espectadores saltarás de asiento, viendo si el combo se actualiza según el jugador que
 *   cambiamos a espectar»). MEDIDO (qa_mirar.py, 34 saltos): la cámara cambia bien, pero el combo que ve es «desde que lo
 *   empezó a mirar» (12, 44, 78… contra 1.100 del corredor): el modo transmisión re-juzga las teclas SÓLO del que sigue.
 *   ⇒ al cambiar de corredor se le SIEMBRA a su copia el combo real de hace `espera_ms` (lo que el que mira está viendo
 *   ahora: la transmisión va ese tiempo atrás) — desde ahí sigue re-juzgando. El 0x70 se lo pasa el server. */
/* el combo del asiento k de hace `espera_ms` (lo que el espectador está viendo ahora: la transmisión va ese tiempo
 * atrás) — -1 si no hay noticias; *edad = hace cuánto llegó ése */
static int gc_historia(int k, DWORD *edad)
{
    DWORD ahora = GetTickCount(), hasta = ahora - g_tx_espera_ms;
    int mejor = -1;
    DWORD mt = 0;
    for (int i = 0; i < GC_HIST; i++) {
        DWORD t = g_gc_h_t[k][i];
        if (t && (long)(hasta - t) >= 0 && (mejor < 0 || (long)(t - mt) > 0)) { mejor = i; mt = t; }
    }
    if (edad) *edad = mejor < 0 ? 0 : ahora - mt;
    return mejor < 0 ? -1 : g_gc_h_c[k][mejor];
}

/* ★ 17-oct · LOS TROPIEZOS FALSOS DEL QUE MIRA (anonimo03: «el modo espectador sigue dando falsos tropiezos visualmente
 *   aunque el combo no se haya roto»). MEDIDO (sonda en 0x50ACD0, _trabajo/qa/sonda_tropiezos.py, 3 carreras de 12): en
 *   el que mira, la copia de algunos corredores pone la animación de nota FALLADA (0x65..0x70 = 101..112) 60–80 veces
 *   por carrera; en el juego de ese mismo corredor, CERO. Todas desde el tick 0x50C490: 0x50ADD0 da la nota por pasada
 *   sin tecla → 0x502DA0 la marca → 0x50C4D7.. tropiezo (0x50ACD0), empujón (0x502BD0(5,0)) y se apagan las auras
 *   «불»/«천사» (0x52E4F0) → 0x50C520. En la copia la tecla del FF98 llega tarde respecto del reloj que le corrigen
 *   (latido / repetición): la nota «pasa» antes de la tecla.
 *   ⇒ en el que mira, antes del tropiezo se le pregunta al combo REAL de ese corredor (el sub 0x70, que manda los cortes
 *   en el acto): si alrededor de lo que se está viendo (hace espera_ms, ± GC_TROPIEZO_MS) el real NO se cortó, la nota
 *   queda marcada pero sin tropiezo, sin empujón y sin apagar las auras. Si se cortó (o no hay noticias), como siempre. */
#define GC_TROPIEZO_MS 700
static int g_gc_trop_si = 0, g_gc_trop_no = 0;

static int gc_real_se_corto(int k)                            /* 1 = se cortó de verdad (o no sé) · 0 = venía sumando */
{
    if (k < 0 || k >= 16) return 1;
    DWORD ahora = GetTickCount(), centro = ahora - g_tx_espera_ms;
    DWORD desde = centro - GC_TROPIEZO_MS, hasta = centro + GC_TROPIEZO_MS;
    int base = -1, hay = 0;
    DWORD tb = 0;
    for (int i = 0; i < GC_HIST; i++) {                       /* la última noticia ANTES de la ventana: el punto de partida */
        DWORD t = g_gc_h_t[k][i];
        if (t && (long)(desde - t) > 0 && (base < 0 || (long)(t - tb) > 0)) { base = i; tb = t; }
    }
    int previo = base >= 0 ? g_gc_h_c[k][base] : -1;
    for (;;) {                                                /* las de la ventana, en orden */
        int sig = -1;
        DWORD ts = 0;
        for (int i = 0; i < GC_HIST; i++) {
            DWORD t = g_gc_h_t[k][i];
            if (!t || (long)(t - desde) < 0 || (long)(t - hasta) > 0) continue;
            if (hay && (long)(t - tb) <= 0) continue;
            if (sig < 0 || (long)(t - ts) < 0) { sig = i; ts = t; }
        }
        if (sig < 0) break;
        int c = g_gc_h_c[k][sig];
        if (c <= 2 || (previo >= 0 && c < previo)) return 1;  /* un corte de verdad */
        previo = c;
        tb = ts;
        hay = 1;
    }
    if (previo < 0) return 1;                                 /* sin noticias de ese corredor: lo de fábrica */
    return previo <= 2;
}

/* la llama la cueva de 0x50C4D7 (con el cPlayer); != 0 ⇒ sin tropiezo */
static int __cdecl gc_tropiezo_falso(BYTE *p)
{
    BYTE *g = gc_juego();
    if (!g_gc_activo || !p || !g || !g[0xC01]) return 0;     /* sólo en el que mira */
    if (gc_real_se_corto(p[0x49])) { g_gc_trop_si++; return 0; }
    if (g_gc_log && g_gc_trop_no < 5) apuntar("  [globo] tropiezo FALSO del asiento %d: el real venía sumando (no se muestra)", p[0x49]);
    g_gc_trop_no++;
    return 1;
}

static void gc_tropiezo_instalar(void)
{
    static const BYTE e[5] = { 0xD9, 0xEE, 0x6A, 0x01, 0x51 };   /* 0x50C4D7  fldz · push 1 · push ecx */
    if (memcmp(GCV(0x50C4D7), e, 5) != 0 || !gc_llama_a(0x50C4E6, 0x50ACD0)) {
        apuntar("  [globo] ⚠ el tropiezo del tick (0x50C4D7) no es el esperado: los tropiezos quedan de fábrica");
        return;
    }
    BYTE *k = (BYTE *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!k) return;
    int i = 0, a;
    k[i++] = 0x60;                                                                  /* pushad */
    k[i++] = 0x56;                                                                  /* push esi (el cPlayer) */
    k[i++] = 0xE8; *(int *)(k + i) = (int)((DWORD)gc_tropiezo_falso - (DWORD)(k + i + 4)); i += 4;
    k[i++] = 0x83; k[i++] = 0xC4; k[i++] = 0x04;                                    /* add esp,4 */
    k[i++] = 0x85; k[i++] = 0xC0;                                                   /* test eax,eax */
    k[i++] = 0x61;                                                                  /* popad (no toca las banderas) */
    k[i++] = 0x75; a = i++;                                                         /* jnz sin_tropiezo */
    CopyMemory(k + i, e, 5); i += 5;                                                /* lo de fábrica */
    k[i++] = 0xE9; *(int *)(k + i) = (int)((DWORD)GCV(0x50C4DC) - (DWORD)(k + i + 4)); i += 4;
    k[a] = (BYTE)(i - (a + 1));
    k[i++] = 0xE9; *(int *)(k + i) = (int)((DWORD)GCV(0x50C520) - (DWORD)(k + i + 4)); i += 4;   /* sin_tropiezo */
    BYTE s[5] = { 0xE9, 0, 0, 0, 0 };
    *(int *)(s + 1) = (int)((DWORD)k - ((DWORD)GCV(0x50C4D7) + 5));
    gc_escribir(0x50C4D7, s, 5);
    apuntar("  [globo] los tropiezos del que mira se comparan con el combo real (±%d ms)", GC_TROPIEZO_MS);
}

static void gc_sembrar(BYTE *p, int k)
{
    DWORD mt;
    int c = gc_historia(k, &mt);
    if (c < 0) return;                                          /* sin noticias de ese corredor: queda como está */
    DWORD clave = *(DWORD *)GCV(0x904210);
    *(DWORD *)(p + 0x190) = (DWORD)c ^ clave;                     /* el combo que se ve (el HUD y el globo) */
    *(DWORD *)(p + 0x254) = (DWORD)c ^ clave;                     /*   y su pareja */
    if (g_gc_log && g_gc_n_siembra < 8) apuntar("  [globo] espectador: al seguir al asiento %d le siembro su combo %d"
                                                " (el de hace %lu ms)", k, c, (unsigned long)mt);
    g_gc_n_siembra++;
}

/* 1 · 0x4F97CB → 0x500AB0 (por corredor, por cuadro): en el mío, mandar el combo */
static void __fastcall gc_jugador(BYTE *p, void *nada, float t)
{
    (void)nada;
    ((F_GC_JUGADOR)GCV(0x500AB0))(p, t);
    BYTE *g = gc_juego();
    if (g_gc_activo && p && g) gc_huerfanos(p[0x49]);
    if (g_gc_activo && g && g != g_gc_juego_ant) {              /* otra carrera: la historia de la anterior no vale */
        g_gc_juego_ant = g;
        g_gc_seguia = -1;
        ZeroMemory(g_gc_h_t, sizeof g_gc_h_t);
        gc_calc_limpiar();
    }
    if (g_gc_activo && p && g && g[0xC01] && p[0x49] == g_gc_ancla) gc_calc_al_dia();   /* una vez por cuadro */
    if (g_gc_activo && p && g && g[0xC01] && p[0x49] == g[0x5D] && p[0x49] < 16) {   /* ★ el espectador cambió de corredor */
        if (g_gc_seguia != p[0x49]) { gc_sembrar(p, p[0x49]); g_gc_t_desvio = 0; g_gc_t_salto = GetTickCount(); }
        g_gc_seguia = p[0x49];
        /* ★ QA 14-oct (personal + ítem, 28 de 192 saltos): la copia re-juzgada SE DESVÍA (con hielos y golpes el que mira
         *   la juzga distinto: 0 contra 250 del corredor) y no volvía hasta el salto siguiente. ⇒ si se aparta del combo
         *   real (el de hace espera_ms) por más de 2 durante 1 s seguido, se la vuelve a sembrar. */
        int real = gc_historia(p[0x49], NULL), copia = gc_combo_de(p);
        if (g_tx_en_vivo && real >= 0 && copia != real) gc_sembrar(p, p[0x49]);   /* ★ en vivo: el HUD con el real, siempre */
        else if (real >= 0 && (copia - real > 2 || real - copia > 2)) {
            /* ★ QA jefe: justo después del salto el juego tarda un instante en pasarle la transmisión al nuevo y le
             *   pisa la copia (0): en el primer 1,5 s se re-siembra EN EL ACTO */
            if (GetTickCount() - g_gc_t_salto < 1500) { gc_sembrar(p, p[0x49]); g_gc_t_desvio = 0; }
            else if (!g_gc_t_desvio) g_gc_t_desvio = GetTickCount() | 1;
            else if (GetTickCount() - g_gc_t_desvio >= 1000) { gc_sembrar(p, p[0x49]); g_gc_t_desvio = 0; g_gc_n_resiembra++; }
        } else g_gc_t_desvio = 0;
    }
    if (!g_gc_activo || !p || !g || g[0xC01] || p[0x49] != gc_mi_asiento()) return;   /* el espectador no corre */
    void *red = *(void **)GCV(0x9314D0);
    if (!red) return;
    int mirar = g[0xC1C] != 0, relevo = (*(WORD *)(g + 0xC) & 0x40) != 0;
    gc_calc_mandar(red, p[0x49], mirar);                        /* ★ la calculadora: sólo si alguien mira */
    if (!mirar && !relevo) { g_gc_enviado = -1; return; }       /* ★ el globo: sólo relevo o con espectadores */
    if (relevo && ((F_GC_ESPERA)GCV(0x4F2F50))(g, p[0x49])) {    /* relevo: no es mi tramo */
        if (g_gc_enviado >= 0)                                  /* ★ terminó mi tramo: el aviso de «fin» */
            ((F_GC_MANDAR)GCV(0x5C7FB0))(red, GC_SUB, GC_FIRMA | p[0x49], (DWORD)g_gc_enviado | GC_FIN);
        g_gc_enviado = -1;
        return;
    }
    int c = gc_combo_de(p);
    if (c < 0 || c > 99999) return;
    DWORD ahora = GetTickCount();
    /* ★ un CORTE (el combo baja) va en el acto: si no, el próximo acierto lo tapa y el que mira no ve el «break» */
    int corte = g_gc_enviado > 0 && c < g_gc_enviado;
    if (!corte && (c == g_gc_enviado ? ahora - g_gc_t_env < GC_LATIDO : ahora - g_gc_t_env < GC_CADA)) return;
    ((F_GC_MANDAR)GCV(0x5C7FB0))(red, GC_SUB, GC_FIRMA | p[0x49], (DWORD)c);
    g_gc_enviado = c;
    g_gc_t_env = ahora;
    if (g_gc_log && g_gc_n_env < 5) apuntar("  [globo] mandé mi combo %d (asiento %d)", c, p[0x49]);
    g_gc_n_env++;
}

/* 2 · 0x4FCAD0 (el receptor del FF4E): el sub 0x70 con la firma es nuestro */
static void __fastcall gc_ff4e(BYTE *g, void *nada, int sub, DWORD a, DWORD b)
{
    (void)nada;
    if (((sub & 0xFF) == GC_SUB_CALC || (sub & 0xFF) == GC_SUB_BASE) && (a >> 24) == GC_FIRMA_CALC) {
        if (g[0xC01]) gc_calc_recibir(sub & 0xFF, a, b);     /* sólo el que mira */
        return;
    }
    if ((sub & 0xFF) == GC_SUB && (a & 0xFFFF0000u) == GC_FIRMA) {
        int k = a & 0xFF;
        if (k < 16) {
            g_gc_combo[k] = (int)(b & ~GC_FIN);
            g_gc_t[k] = GetTickCount() | 1;
            g_gc_fin[k] = (b & GC_FIN) ? g_gc_t[k] : 0;
            int i = g_gc_h_i[k]++ % GC_HIST;                        /* la historia, para sembrar al espectador */
            g_gc_h_t[k][i] = g_gc_t[k];
            g_gc_h_c[k][i] = g_gc_combo[k];
        }
        if (g_gc_log && g_gc_n_rec < 5) apuntar("  [globo] llegó el combo %d del asiento %d%s", (int)(b & ~GC_FIN), k,
                                                (b & GC_FIN) ? " (terminó)" : "");
        g_gc_n_rec++;
        return;
    }
    ((F_GC_FF4E)g_gc_orig_ff4e)(g, sub, a, b);
}

static void gc_cargar(void)
{
    g_gc_estado = -1;
    ((F_GC_CREAR)GCV(0x64E560))(g_gc_hoja);
    if (!((F_GC_CARGAR)GCV(0x64E1E0))(g_gc_hoja, S12_CARRERA_TGA, NULL)) {
        apuntar("  [globo] ⛔ no encontré %s (¿falta rnr_ui_sala12.pak?): sin globo del combo", S12_CARRERA_TGA);
        return;
    }
    F_GC_RECORTE rec = (F_GC_RECORTE)GCV(0x64EC40);
    int nc = (int)(sizeof(S12_CARRERA_CORTES) / sizeof(S12_CARRERA_CORTES[0]));
    if (nc <= S12_GLOBO_COLA) {
        apuntar("  [globo] ⛔ la hoja de la carrera no trae el globo (%d cortes)", nc);
        return;
    }
    /* ★ la z: el globo va JUSTO DETRÁS de los números del contador del juego (medido: con la nuestra fija, 0,78, el
     *   globo opaco los tapaba: en este juego la z más BAJA se dibuja encima — 1ST 0,1, nombres 0,8). Se halla dónde guarda la z un corte (una marca en el nuestro) y se lee la del corte 0
     *   de la hoja del HUD; sin HUD, la del ini. */
    const float MARCA = 0.4321f;
    for (int i = 0; i < nc; i++)
        rec(g_gc_hoja, 0, 0, S12_CARRERA_CORTES[i][0], S12_CARRERA_CORTES[i][1], S12_CARRERA_CORTES[i][2],
            S12_CARRERA_CORTES[i][3], MARCA);
    BYTE *nuestros = *(BYTE **)(g_gc_hoja + 0x18);
    BYTE *hud = *(BYTE **)GCV(0x931670);
    BYTE *nums = hud ? *(BYTE **)(hud + 0x18 + 0x18) : NULL;
    int o = -1;
    for (int k = 0; nuestros && k < 0x50; k += 4)
        if (*(float *)(nuestros + k) == MARCA) { o = k; break; }
    float z = g_gc_z;
    if (o >= 0 && nums) {
        float zn = *(float *)(nums + o);
        if (zn > 0.0f && zn < 0.99f) z = zn + 0.004f;            /* MEDIDO: la z más BAJA va adelante (los números 0,3) */
    }
    for (int i = 0; o >= 0 && i < nc; i++)
        *(float *)(nuestros + i * 0x50 + o) = i == S12_GLOBO_COLA ? z - 0.002f : z;     /* la colita tapa el borde */
    g_gc_z = z;
    g_gc_estado = 1;
    apuntar("  [globo] ★ el globo del combo cargado (z=%d/1000, escala %d/1000)", (int)(g_gc_z * 1000), g_gc_escala);
}

/* dibuja el corte con tamaño, tinte y lugar; y le DEVUELVE lo que tenía (tamaño en corte+0x14/+0x18, cortes de 0x50 en
 * [spr+0x18]; el tinte lo pone 0x64E710): la hoja de los números es la del HUD, que la usa en el mismo cuadro */
static float g_gc_z_pieza = 0;                                /* > 0: la z de la próxima pieza (y se devuelve) */
static void gc_pieza(void *spr, int corte, int x, int y, int w, int h, DWORD argb)
{
    BYTE *c = *(BYTE **)((BYTE *)spr + 0x18) + corte * 0x50;
    float w0 = *(float *)(c + 0x14), h0 = *(float *)(c + 0x18), z0 = *(float *)(c + 0x10);
    if (g_gc_z_pieza > 0) *(float *)(c + 0x10) = g_gc_z_pieza;
    if (w > 0) ((F_GC_TAM)GCV(0x64DB90))(spr, corte, w, h);
    ((F_GC_COLOR)GCV(0x64E710))(spr, corte, argb);
    ((F_GC_POS)GCV(0x64D990))(spr, corte, x, y);
    ((F_GC_DIB)GCV(0x64EE40))(spr, corte, 0);
    *(float *)(c + 0x14) = w0;
    *(float *)(c + 0x18) = h0;
    *(float *)(c + 0x10) = z0;
    g_gc_z_pieza = 0;
    if (spr != g_gc_hoja) ((F_GC_COLOR)GCV(0x64E710))(spr, corte, 0xFFFFFFFF);
}

/* el reloj del contador, como el del juego (0x54B670: [hud+0x9D2] += 15 por cuadro hasta 810, y vuelve a 0 con cada
 * combo nuevo) — acá por asiento y con el reloj de Windows (15 por cuadro de 60 = 0,9 por ms) */
static int gc_reloj(int k, int combo)
{
    DWORD ahora = GetTickCount();
    if (combo != g_gc_ultimo[k]) {
        if (combo == 0 && g_gc_ultimo[k] > 0) g_gc_t_break[k] = ahora | 1;
        g_gc_ultimo[k] = combo;
        g_gc_t_cambio[k] = ahora;
    }
    DWORD t = (ahora - g_gc_t_cambio[k]) * 9 / 10;
    return t > 810 ? 810 : (int)t;
}

/* ★ 2.ª vuelta (anonimo03: «que adentro esté el mismo estilo, textura y funcionamiento del contador normal, pequeñito»):
 *   el contador ES el del juego — su hoja (la del HUD, [0x931670]+0x18: cortes 0..9 los números, 10 «COMBO») y su
 *   cuenta (0x54B670), achicados a g_gc_escala y centrados en el globo:
 *     reloj t <= 555: a = min(t, 255), c = a/2 -> los números (50+e)x(65+e) con e = 128-c, paso 178-c, y = 55-e/2;
 *                     «COMBO» (101+e)x(29+e) en y = 120-e/2; transparencia a  => nace GRANDE y transparente y se
 *                     asienta en ~0,3 s
 *     t > 555:        se desvanece hasta 810 (0,9 s sin acertar) — en el globo NO, salvo [globo] apagar=1: el globo
 *                     queda con el número quieto mientras el que corre siga (no se apaga a cada pausa)
 *   ★ 3.ª vuelta (anonimo03: «la textura/animación del combo BREAK cuando el que miramos falle»): con el combo en 0 (después
 *   de tenerlo) el juego dibuja, con el MISMO reloj (0x54B864): la mancha [hud+0x14] corte 2, (397−e)×(204−e) en
 *   (cx + e/2 − 196, e/2 − 22); el letrero [hud+0x18] corte 18, (302+e)×(92+e) en (cx − e/2 − 151, 34 − e/2); y el
 *   «COMBO» de siempre. Ése SÍ se desvanece (555 → 810) y con él el globo.
 *   f = la opacidad del apagado suave (256 = entero). */
static void gc_globo(int k, int x, int y, int combo, int f, float esc)
{
    if (!g_gc_estado) gc_cargar();
    BYTE *hud = *(BYTE **)GCV(0x931670);
    if (g_gc_estado != 1 || !hud) return;
    void *nums = hud + 0x18, *mancha = *(void **)(hud + 0x14);
    int t = gc_reloj(k, combo);
    /* el «break»: con el combo en 0 después de un corte, y al menos GC_BREAK_MIN ms aunque ya vuelva a acertar (el
     *   acierto siguiente lo tapaba al instante: en un globo chico no se llegaba a ver) — con su reloj desde el corte */
    DWORD desde_corte = g_gc_t_break[k] ? GetTickCount() - g_gc_t_break[k] : 0xFFFFFFFF;
    int rompe = (combo == 0 && g_gc_t_break[k]) || desde_corte < GC_BREAK_MIN;
    if (combo == 0 && !rompe) return;                           /* un 0 que no es un corte (el arranque): nada */
    if (rompe && !mancha) return;
    if (rompe) {
        t = (int)(desde_corte * 9 / 10);
        if (t > 810) t = 810;
    }
    if (t > 555 && !g_gc_apagar && !rompe) t = 555;
    int a, e;
    if (t <= 555) {
        a = t < 255 ? t : 255;
        e = 128 - a / 2;
    } else {
        a = (0x2A - t) & 0xFF;
        e = 0;
    }
    if (t >= 810 || (t > 555 && a == 0)) return;
    /* ★ MEDIDO en vivo: acertando seguido, cada combo nuevo vuelve el reloj a 0 y el número vive «saltando» (grande y
     *   transparente, como el del juego) — en el globo se salía del borde. Mismo latido, más corto: el salto a
     *   g_gc_salto % y nunca menos de 140 de opacidad */
    e = e * g_gc_salto / 100;
    int paso = 50 + e;
    if (t <= 555) a = 140 + a * 115 / 255;
    int a_globo = t > 555 ? a : 255;
    a = a * f / 256;
    a_globo = a_globo * f / 256;
    float s = g_gc_escala / 1000.0f * esc, sb = s * 0.7f;      /* el «break» es grande: a 0,7 */
    char txt[12];
    int n = wsprintfA(txt, "%d", combo);
    int punta = (int)(S12_CARRERA_CORTES[S12_GLOBO_IZQ][2] * esc), alto = (int)(S12_CARRERA_CORTES[S12_GLOBO_IZQ][3] * esc);
    /* el globo: lo que MIDE el contador dibujado (en vivo, 14-oct: ~76 «del juego» por cifra con su salto; el
     *   «COMBO» 101; el letrero del break 302) + 15 de cada lado (anonimo03: «más grande la burbuja») */
    int ancho = rompe ? (int)(302 * sb + 30 * esc) : (int)((n * 76 > 101 ? n * 76 : 101) * s + 30 * esc);
    if (ancho < 2 * punta + 4) ancho = 2 * punta + 4;
    const int *cola = S12_CARRERA_CORTES[S12_GLOBO_COLA];
    int cw = (int)(cola[2] * esc), ch = (int)(cola[3] * esc), monta = (int)(S12_GLOBO_MONTA * esc + 0.5f);
    int by = y + g_gc_dy - ch + monta - alto, bx = x - ancho / 2;
    DWORD ta = (g_gc_color >> 24) * (DWORD)a_globo / 255;
    DWORD tinte = (ta << 24) | (g_gc_color & 0xFFFFFF);
    gc_pieza(g_gc_hoja, S12_GLOBO_IZQ, bx, by, punta, alto, tinte);
    gc_pieza(g_gc_hoja, S12_GLOBO_MEDIO, bx + punta, by, ancho - 2 * punta, alto, tinte);
    gc_pieza(g_gc_hoja, S12_GLOBO_DER, bx + ancho - punta, by, punta, alto, tinte);
    gc_pieza(g_gc_hoja, S12_GLOBO_COLA, x - cw / 2, by + alto - monta, cw, ch, tinte);
    DWORD col = ((DWORD)a << 24) | 0xFFFFFF;
    g_gc_ex[k] = x;
    g_gc_ey[k] = y;
    g_gc_ef[k] = f;
    g_gc_eesc[k] = esc;
    g_gc_t_visto[k] = GetTickCount() | 1;
    if (rompe) {
        /* el break: las cuentas del juego con origen en el letrero (y 34) y el pie del «COMBO» (149) = 115 de alto */
        float arriba = by + (alto - 115 * sb) / 2;
#define GC_Y(Y) ((int)(arriba + ((Y) - 34) * sb))
        /* MEDIDO: la mancha va en z 0,55 y el letrero en 0,5 — DETRÁS del globo (que va detrás de los números, 0,3):
         *   mientras se dibujan se les pone una z justo delante del globo (y se les devuelve la suya) */
        g_gc_z_pieza = g_gc_z - 0.0015f;
        gc_pieza(mancha, 2, x + (int)((e / 2 - 196) * sb), GC_Y(e / 2 - 22), (int)((397 - e) * sb), (int)((204 - e) * sb), col);
        g_gc_z_pieza = g_gc_z - 0.003f;
        gc_pieza(nums, 18, x - (int)((e / 2 + 151) * sb), GC_Y(34 - e / 2), (int)((302 + e) * sb), (int)((92 + e) * sb), col);
        gc_pieza(nums, 10, x - (int)((101 + e) * sb / 2), GC_Y(120 - e / 2), (int)((101 + e) * sb), (int)((29 + e) * sb), col);
#undef GC_Y
        return;
    }
    /* el contador: las cuentas del juego en su escala. MEDIDO en vivo (14-oct): con la escala 0,34 el contador dibujado
     * mide 35 px de alto (los números arrancan ~4 px más arriba de su y y el «COMBO» baja más de su 29) ⇒ 103 de alto
     * «del juego» y 12 de corrimiento */
    int arriba = by + (alto - (int)(103 * s)) / 2 + (int)(12 * s);
    float nx = x - n * paso * s / 2;
    for (int i = 0; i < n; i++)
        gc_pieza(nums, txt[i] - '0', (int)(nx + i * paso * s), arriba - (int)(e / 2 * s), (int)((50 + e) * s),
                 (int)((65 + e) * s), col);
    gc_pieza(nums, 10, x - (int)((101 + e) * s / 2), arriba + (int)((65 - e / 2) * s), (int)((101 + e) * s),
             (int)((29 + e) * s), col);
}

/* ★ QA 14-oct (anonimo03: «ahora tenemos 2 combos al espectar, el original de arriba y el nuevo · quedarnos con el nuevo»):
 *   el contador de arriba lo dibuja el HUD por un puntero ([hud+0xCF4] = 0x54B670, o 0x54B920 con la bandera 0x400 del
 *   modo, 0x5588xx). Siendo ESPECTADOR no se dibuja: queda el globo, que es el mismo contador. El que corre, como siempre. */
typedef void (TCK *F_GC_CONTADOR)(void *hud);
static void __fastcall gc_contador0(BYTE *hud, void *nada)
{
    (void)nada;
    BYTE *g = gc_juego();
    if (g_gc_activo && g_gc_ocultar && g && g[0xC01]) return;
    ((F_GC_CONTADOR)g_gc_orig_cont[0])(hud);
}
static void __fastcall gc_contador1(BYTE *hud, void *nada)
{
    (void)nada;
    BYTE *g = gc_juego();
    if (g_gc_activo && g_gc_ocultar && g && g[0xC01]) return;
    ((F_GC_CONTADOR)g_gc_orig_cont[1])(hud);
}

/* 3 · 0x500C61 → 0x5009D0 (el nombre sobre la cabeza de otro corredor): y el globo */
static void __fastcall gc_etiqueta(BYTE *p, void *nada, int x, int y)
{
    (void)nada;
    ((F_GC_ETIQUETA)GCV(0x5009D0))(p, x, y);
    BYTE *g = gc_juego();
    if (!g_gc_activo || !p || !g) return;
    int k = p[0x49], esp = g[0xC01] != 0;
    if (k >= 16 || (!esp && (k != g[0x5D] || k == gc_mi_asiento()))) return;
    if (!(*(WORD *)(g + 0xC) & 0x40) && !esp) return;            /* sólo en el relevo o si soy espectador */
    DWORD ahora = GetTickCount();
    int combo, f = 256;
    float esc = 1.0f;
    if (esp && k == g[0x5D]) {
        combo = gc_combo_de(p);                    /* ★ el que sigo: su copia re-juzgada (sembrada al cambiar) */
        if (g_tx_en_vivo && gc_historia(k, NULL) >= 0) combo = gc_historia(k, NULL);   /* ★ en vivo: el real */
        /* ★ QA sala de 12: el latido del juego le pisa la copia con 0 un instante (la re-siembra la repone al cuadro
         *   siguiente): un 0 con el real > 2 no es un corte — se muestra el real (y no dispara un BREAK falso) */
        int real = gc_historia(k, NULL);
        if (combo == 0 && real > 2) combo = real;
    }
    else if (esp) {
        /* ★ 14-oct (anonimo03: «¿las burbujas de todos todo el tiempo?»): los que NO sigo, al 75 %, con el combo que mandan
         *   tomado de hace espera_ms — alineado con lo que se ve (impulsores y golpes van con ese mismo atraso) */
        DWORD edad;
        combo = gc_historia(k, &edad);
        if (combo < 0) return;
        if (edad > GC_SIN_DATOS + g_tx_espera_ms) {             /* sin noticias hace rato: se apaga suave */
            f = 256 - (int)((edad - GC_SIN_DATOS - g_tx_espera_ms) * 256 / GC_APAGA);
        }
        esc = GC_CHICO;
    } else if (g_gc_t[k]) {
        /* ★ el apagado suave: «terminó su tramo» (lo avisa su juego) o sin noticias hace rato (un NPC que llegó) */
        DWORD desde = g_gc_fin[k] ? g_gc_fin[k] : g_gc_t[k] + GC_SIN_DATOS;
        if (ahora > desde) f = 256 - (int)((ahora - desde) * 256 / GC_APAGA);
        combo = g_gc_combo[k];
    } else return;
    if (f <= 0) {
        g_gc_t_visto[k] = 0;                                    /* ya se apagó: que no lo «resucite» el huérfano */
        return;
    }
    if (combo < 0 || combo > 99999) return;
    gc_globo(k, x, y, combo, f, esc);
    if (g_gc_log && g_gc_n_dib++ == 0) apuntar("  [globo] el 1.er globo: asiento %d, combo %d, en (%d, %d)", k,
                                                combo, x, y);
}

static void globo_combo_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("globo", "activo", 1, ini)) {
        apuntar("  [globo] apagado ([globo] activo=0)");
        return;
    }
    g_gc_base = (BYTE *)GetModuleHandleA(NULL);
    g_gc_dy = GetPrivateProfileIntA("globo", "dy", 10, ini);
    g_gc_z = GetPrivateProfileIntA("globo", "z", 780, ini) / 1000.0f;
    g_gc_log = GetPrivateProfileIntA("globo", "log", 0, ini);
    g_gc_escala = GetPrivateProfileIntA("globo", "escala", 380, ini);
    g_gc_apagar = GetPrivateProfileIntA("globo", "apagar", 0, ini);
    g_gc_salto = GetPrivateProfileIntA("globo", "salto", 30, ini);
    g_gc_ocultar = GetPrivateProfileIntA("globo", "ocultar_contador", 1, ini);
    {
        char c[16];
        GetPrivateProfileStringA("globo", "color", "FFFFFFFF", c, sizeof(c), ini);
        g_gc_color = 0;
        for (char *q = c; *q; q++) {
            int lo = *q | 0x20;
            int v = *q >= '0' && *q <= '9' ? *q - '0' : lo >= 'a' && lo <= 'f' ? lo - 'a' + 10 : -1;
            if (v >= 0) g_gc_color = (g_gc_color << 4) | (DWORD)v;
        }
    }
    /* la guarda: las dos llamadas y el comienzo del receptor, de fábrica */
    static const BYTE e_ff4e[7] = { 0x83, 0xEC, 0x08, 0x8B, 0x44, 0x24, 0x10 };
    if (!gc_llama_a(0x4F97CB, 0x500AB0) || !gc_llama_a(0x500C61, 0x5009D0) || memcmp(GCV(0x4FCAD0), e_ff4e, 7) != 0) {
        apuntar("  [globo] ⛔ los sitios no son los de fábrica: no se toca nada");
        return;
    }
    BYTE *c = (BYTE *)VirtualAlloc(NULL, 32, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!c) return;
    CopyMemory(c, e_ff4e, 7);                                   /* el trampolín: lo de fábrica + jmp de vuelta */
    c[7] = 0xE9;
    *(int *)(c + 8) = (int)((DWORD)GCV(0x4FCAD7) - (DWORD)(c + 12));
    g_gc_orig_ff4e = c;
    BYTE s[7] = { 0xE9, 0, 0, 0, 0, 0x90, 0x90 };
    *(int *)(s + 1) = (int)((DWORD)gc_ff4e - ((DWORD)GCV(0x4FCAD0) + 5));
    gc_escribir(0x4FCAD0, s, 7);
    gc_desviar(0x4F97CB, (void *)gc_jugador);
    {   /* el contador de arriba: sub esp,0x20 · mov eax,[0x91B270] (8 bytes, sin nada relativo) → trampolín */
        static const BYTE e_cont[8] = { 0x83, 0xEC, 0x20, 0xA1, 0x70, 0xB2, 0x91, 0x00 };
        static const DWORD sitio[2] = { 0x54B670, 0x54B920 };
        void *mio[2] = { (void *)gc_contador0, (void *)gc_contador1 };
        for (int i = 0; i < 2; i++) {
            if (memcmp(GCV(sitio[i]), e_cont, 8) != 0) {
                apuntar("  [globo] ⚠ el contador 0x%06lX no es el esperado: queda de fábrica", (unsigned long)sitio[i]);
                continue;
            }
            BYTE *t = (BYTE *)VirtualAlloc(NULL, 32, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
            if (!t) continue;
            CopyMemory(t, e_cont, 8);
            t[8] = 0xE9;
            *(int *)(t + 9) = (int)((DWORD)GCV(sitio[i] + 8) - (DWORD)(t + 13));
            g_gc_orig_cont[i] = t;
            BYTE j[8] = { 0xE9, 0, 0, 0, 0, 0x90, 0x90, 0x90 };
            *(int *)(j + 1) = (int)((DWORD)mio[i] - ((DWORD)GCV(sitio[i]) + 5));
            gc_escribir(sitio[i], j, 8);
        }
    }
    gc_desviar(0x500C61, (void *)gc_etiqueta);
    if (GetPrivateProfileIntA("globo", "tropiezos_falsos", 1, ini)) gc_tropiezo_instalar();   /* ★ 17-oct */
    g_calc_al_juzgar = gc_calc_al_juzgar;                      /* ★ la calculadora del espectador */
    g_calc_antes_de_dibujar = gc_calc_mostrar;
    g_calc_ajena = 1;
    g_gc_activo = 1;
    apuntar("  [globo] ★ el globo del combo: mando el mío (FF4E sub 0x%02X), recibo el de los demás y lo dibujo sobre"
            " el que sigue la cámara (relevo o espectador) · dy=%d", GC_SUB, g_gc_dy);
}
