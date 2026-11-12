/* pausa.c — el 3er botón de la Pausa: «Repetir» (04-oct-2026)
 *
 *   anonimo03: el 3er botón de la Pausa, «Repetir», con la idea del cliente XYX — y la decisión:
 *   *"sólo jugando solo"*. Investigación entera: documentacion/PAUSA_REPETIR.md.
 *
 *   Se engancha en 4 lugares del exe, desde nuestra d3d9 (sin tocar el exe):
 *
 *     0x41F62E  la APERTURA de la Pausa (ventana 0x28)  -> si estás solo, arma el botón [obj+0x424]
 *                                                          con los cortes 15/14/13 y lo registra
 *     0x41B2B3  el DIBUJO de la Pausa                    -> el fondo ancho (corte 16) y los 3 botones
 *     0x4265A7  el `je` del clic en [obj+0x424]          -> en la Pausa NO va a «Salir»: repite
 *     0x41FE41  la apertura de la ventana 4 (el regalo)  -> le devuelve a [obj+0x424] sus cortes 6/7/8
 *               ⚠ esa ventana COMPARTE el botón y no lo rearma al abrirse: sin esto saldría «Repetir»
 *
 *   ★ «Repetir» = la función NATIVA 0x413760 sobre [0x9314CC]: pide de nuevo la escena de la carrera
 *     (`+0x49360`) con la transición del juego. El cliente vuelve a cargar y manda otro `FF25`; el server
 *     le contesta el `GO` sólo si está solo en la carrera (`lobby_carrera.h_31_ff25`).
 *   ★ La figurita (cortes 13..16) va en `R2Beat/rnr_ui_pausa.pak` (herramientas/pausa_repetir.py, que
 *     escribe pausa_datos.h). Si el pak NO está, la figurita trae 13 cortes y el botón no se pone: la
 *     Pausa queda como siempre.
 *   ⛔ [pausa] repetir=0 lo apaga.
 *   ★ Y la PRÁCTICA arranca con PD Valofe (`[practica] pd_valofe`, 1 de fábrica): ver `pau_practica`.
 */
#include "pausa_datos.h"

#define PV(x) (g_pau_base + ((DWORD)(x) - 0x400000))
#define TCP __attribute__((thiscall))

static BYTE *g_pau_base = NULL;
static int   g_pau_listo = 0;      /* 1 = el botón está armado en la Pausa abierta ahora      */
static int   g_pau_tocado = 0;     /* 1 = [obj+0x424] tiene NUESTROS cortes (hay que devolvérselos) */
static int   g_pau_aviso = 0;      /* el aviso de «figurita sin los cortes», una vez            */
static long  g_pau_veces = 0;      /* cuántas veces se repitió (para el log)                    */
static volatile DWORD g_pau_ret = 0;

typedef void (TCP *F_BOT_ARMAR)(void *btn, void *spr, int c1, int c2, int c3, int z, const char *t, int k);
typedef void (TCP *F_REGISTRAR)(void *ui, void *btn, int uno);
typedef void (TCP *F_POS)(void *btn, int x, int y);
typedef void (TCP *F_COLOR)(void *btn, int a, int b, int c);
typedef void (TCP *F_CORTE)(void *spr, int x, int y, int corte, int z);
typedef void (TCP *F_SONIDO)(void *snd, int id);
typedef void (TCP *F_THIS0)(void *self);

/* ── ¿estoy solo? el PADRÓN de la sala: el std::map de [0x931660] (head +0x18, tamaño +0x1C) ────
 *   ★ anonimo03: *"la Pausa sólo sale en modo práctica"* — o sea que abrir la Pausa ya es estar practicando.
 *     Esto queda de red, por si algún modo la abriera con gente.
 *   ⛔ NO sirven los cPlayer de [cGame+0xA14]: MEDIDO (04-oct, Frida, practicando solo) — están los 6
 *     armados, uno por asiento, aunque corras solo. La 1ª versión los contaba y el botón nunca salía. */
static int pau_estoy_solo(void)
{
    BYTE *pad = *(BYTE **)PV(0x931660);
    if (!pad) return 0;
    DWORD n = *(DWORD *)(pad + 0x1C);
    return n <= 1;
}

/* ── 0x41F62E: la apertura ── */
static int __cdecl pau_abrir(BYTE *obj)
{
    g_pau_listo = 0;
    BYTE *spr = *(BYTE **)(obj + 0x2ED8);
    if (!spr) return 0;
    if (*(DWORD *)(spr + 0xA0) < PAUSA_CORTES_MIN) {
        if (!g_pau_aviso++)
            apuntar("  [pausa] la figurita trae %u cortes (hacen falta %d): sin «Repetir». ¿Falta rnr_ui_pausa.pak?",
                    *(DWORD *)(spr + 0xA0), PAUSA_CORTES_MIN);
        return 0;
    }
    if (!pau_estoy_solo()) return 0;
    ((F_BOT_ARMAR)PV(0x685D90))(obj + 0x424, spr, PAUSA_C_NORMAL, PAUSA_C_ENCENDIDO, PAUSA_C_APRETADO,
                                0, (const char *)PV(0x873C99), -1);
    ((F_REGISTRAR)PV(0x647B80))(*(void **)PV(0x93156C), obj + 0x424, 1);
    g_pau_tocado = 1;
    g_pau_listo = 1;
    return 0;                                     /* sigue lo nativo (Continuar y Salir) */
}

/* ── 0x41B2B3: el dibujo. 1 = lo dibujé yo (salta al final del switch, 0x41BFE0) ── */
static int __cdecl pau_dibujar(BYTE *obj)
{
    if (!g_pau_listo) return 0;
    int cx = *(int *)PV(0x904084);
    ((F_CORTE)PV(0x683FB0))(*(void **)(obj + 0x2ED8), cx - 192, 0x49, PAUSA_C_FONDO, 0);
    struct { int off, dx; } b[3] = { { 0x354, -188 }, { 0x284, -62 }, { 0x424, 64 } };  /* Continuar · Salir · Repetir */
    for (int i = 0; i < 3; i++) {
        ((F_POS)PV(0x685900))(obj + b[i].off, cx + b[i].dx, 0x78);
        ((F_COLOR)PV(0x685920))(obj + b[i].off, 0, 0, 0xFF);
    }
    return 1;
}

/* ── 0x4265A7: el clic en [obj+0x424]. 1 = era nuestro «Repetir» (no ir a «Salir») ── */
static int __cdecl pau_clic(int ventana, BYTE *obj)
{
    if (ventana != 0x28 || !g_pau_listo || !pau_estoy_solo()) return 0;
    g_pau_listo = 0;
    ((F_SONIDO)PV(0x40B800))(*(void **)PV(0x9314E4), 1);       /* el clic, como Continuar/Salir */
    BYTE *esc = *(BYTE **)PV(0x9314CC);
    if (esc && *(DWORD *)(esc + 0xB000) == 0)                   /* sin cambio de escena pendiente */
        ((F_THIS0)PV(0x413760))(esc);                            /* ★ la carrera, de nuevo */
    ((F_THIS0)PV(0x417470))(obj);                                /* cierra la Pausa */
    apuntar("  [pausa] ★ Repetir (%ld)", ++g_pau_veces);
    return 1;
}

/* ── 0x41FE41: la ventana 4 (el regalo) usa el MISMO botón: devolverle sus cortes 6/7/8 ── */
static int __cdecl pau_regalo(BYTE *obj)
{
    if (g_pau_tocado && *(void **)(obj + 0x228)) {
        ((F_BOT_ARMAR)PV(0x685D90))(obj + 0x424, *(void **)(obj + 0x228), 6, 7, 8, 0, (const char *)PV(0x873C99), -1);
        g_pau_tocado = 0;
    }
    return 0;
}

/* ── ★ 0x5E2585: la PRÁCTICA arranca (04-oct) ──────────────────────────────────────────────────
 *   anonimo03: *"en modo práctica el pd inicial es el normal — hasta crear una sala recién cambia al
 *   Valofe — aquí no hay chat"*. El PD Valofe lo prende un byte al final del LOADGAME (FF25) de una
 *   SALA (`PD_VALOFE` = 1 byte en 0xA16B40, el cave de `armar_cave_pd_valofe.py`). La práctica no pasa
 *   por el LOADGAME: arranca acá, en el handler del FF3A (0x5E2510) con tipo 2 y estado > 0, justo antes
 *   de saltar a la escena de carrera. ⇒ La práctica quedaba con lo de fábrica (0, Normal) o con lo
 *   de la ÚLTIMA sala. Ahora arranca SIEMPRE con lo de `[practica] pd_valofe` (1 de fábrica).
 *   ★ Las salas no cambian: su LOADGAME vuelve a escribir el byte en cada carrera. */
static int g_pau_pd_practica = 1;
static long g_pau_practicas = 0;
static int __cdecl pau_practica(BYTE *obj)
{
    (void)obj;
    *(BYTE *)PV(0xA16B40) = (BYTE)(g_pau_pd_practica ? 1 : 0);
    if (++g_pau_practicas <= 3)
        apuntar("  [practica] arranca con PD %s", g_pau_pd_practica ? "Valofe" : "Normal");
    return 0;
}

/* ── los saltos, armados en memoria (como caras.c) ─────────────────────────────────────────────
 *   pushad · pushfd · [push edi(16)] · push esi · call f · add esp · mov [g_pau_ret],eax · popfd · popad
 *   y después: si g_pau_ret != 0 -> `si_uno`; si no -> lo original (+ volver), o `si_cero`.        */
static BYTE *g_pau_cueva = NULL;
static int   g_pau_usado = 0;

static BYTE *pau_emitir(const void *b, int n) { BYTE *p = g_pau_cueva + g_pau_usado; CopyMemory(p, b, n); g_pau_usado += n; return p; }
static void  pau_rel(BYTE op, DWORD destino)    /* E8/E9 rel32 */
{
    BYTE *p = g_pau_cueva + g_pau_usado;
    p[0] = op; *(DWORD *)(p + 1) = destino - (DWORD)(p + 5); g_pau_usado += 5;
}
static void  pau_jne(DWORD destino)
{
    BYTE *p = g_pau_cueva + g_pau_usado;
    p[0] = 0x0F; p[1] = 0x85; *(DWORD *)(p + 2) = destino - (DWORD)(p + 6); g_pau_usado += 6;
}

/* llamar `f` y: si devuelve != 0 -> saltar a `si_uno`; si no -> los `n` bytes originales y volver */
static BYTE *pau_cueva_llamar(void *f, int con_ventana, DWORD sitio, int n, DWORD si_uno, DWORD si_cero)
{
    BYTE *ini = g_pau_cueva + g_pau_usado;
    static const BYTE guardar[] = { 0x60, 0x9C };                         /* pushad, pushfd */
    pau_emitir(guardar, 2);
    static const BYTE esi[] = { 0x56 };                                   /* push esi: el ÚLTIMO argumento */
    pau_emitir(esi, 1);
    if (con_ventana) { static const BYTE v[] = { 0x0F, 0xB7, 0xC7, 0x50 }; pau_emitir(v, 4); }  /* movzx eax,di; push eax = el 1º */
    pau_rel(0xE8, (DWORD)f);
    BYTE limpiar[] = { 0x83, 0xC4, (BYTE)(con_ventana ? 8 : 4) };
    pau_emitir(limpiar, 3);
    BYTE guardar_ret[5] = { 0xA3 }; *(DWORD *)(guardar_ret + 1) = (DWORD)&g_pau_ret;
    pau_emitir(guardar_ret, 5);
    static const BYTE volver[] = { 0x9D, 0x61 };                          /* popfd, popad */
    pau_emitir(volver, 2);
    BYTE cmp[7] = { 0x83, 0x3D }; *(DWORD *)(cmp + 2) = (DWORD)&g_pau_ret; cmp[6] = 0;
    pau_emitir(cmp, 7);
    pau_jne(si_uno);
    if (si_cero) pau_rel(0xE9, si_cero);
    else {
        pau_emitir((void *)sitio, n);                                     /* lo original (sin saltos relativos) */
        pau_rel(0xE9, sitio + n);
    }
    return ini;
}

static int pau_poner_salto(DWORD sitio, int n, BYTE *destino)
{
    DWORD viejo = 0;
    if (!VirtualProtect((void *)sitio, n, PAGE_EXECUTE_READWRITE, &viejo)) return 0;
    BYTE *s = (BYTE *)sitio;
    s[0] = 0xE9;
    *(DWORD *)(s + 1) = (DWORD)destino - (sitio + 5);
    for (int i = 5; i < n; i++) s[i] = 0x90;
    VirtualProtect((void *)sitio, n, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), s, n);
    return 1;
}

static void practica_iniciar(const char *ini)
{
    g_pau_pd_practica = GetPrivateProfileIntA("practica", "pd_valofe", 1, ini) ? 1 : 0;
    static const BYTE espera[6] = { 0x8B, 0x0D, 0xE4, 0x14, 0x93, 0x00 };   /* mov ecx,[0x9314E4] */
    BYTE *s = PV(0x5E2585);
    for (int j = 0; j < 6; j++)
        if (s[j] != espera[j]) { apuntar("  [practica] ⛔ 0x5E2585 no tiene los bytes esperados: no se toca"); return; }
    if (!g_pau_cueva) g_pau_cueva = (BYTE *)VirtualAlloc(NULL, 512, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!g_pau_cueva) return;
    DWORD sitio = (DWORD)s;
    BYTE *c = pau_cueva_llamar((void *)pau_practica, 0, sitio, 6, sitio + 6, 0);   /* siempre sigue */
    if (pau_poner_salto(sitio, 6, c))
        apuntar("  [practica] ok: la práctica arranca con PD %s ([practica] pd_valofe=%d)",
                g_pau_pd_practica ? "Valofe" : "Normal", g_pau_pd_practica);
}

static void pausa_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    g_pau_base = (BYTE *)GetModuleHandleA(NULL);
    practica_iniciar(ini);
    if (!GetPrivateProfileIntA("pausa", "repetir", 1, ini)) {
        apuntar("  [pausa] «Repetir» apagado ([pausa] repetir=0)");
        return;
    }
    /* ⛔ los 4 lugares, con los bytes que esperamos (los mismos en el pristino, el de prod y el local) */
    static const struct { DWORD va; BYTE b[6]; int n; const char *que; } SITIOS[4] = {
        { 0x41F62E, { 0x8B, 0x96, 0xD8, 0x2E, 0x00, 0x00 }, 6, "la apertura de la Pausa" },
        { 0x41B2B3, { 0xA1, 0x84, 0x40, 0x90, 0x00 },       5, "el dibujo de la Pausa" },
        { 0x4265A7, { 0x0F, 0x84, 0xC6, 0x00, 0x00, 0x00 }, 6, "el clic del 3er botón (je a Salir)" },
        { 0x41FE41, { 0xA1, 0x88, 0x40, 0x90, 0x00 },       5, "la apertura del regalo" },
    };
    for (int i = 0; i < 4; i++) {
        BYTE *s = PV(SITIOS[i].va);
        for (int j = 0; j < SITIOS[i].n; j++)
            if (s[j] != SITIOS[i].b[j]) {
                apuntar("  [pausa] ⛔ %s (0x%08X) no tiene los bytes esperados: no se toca nada",
                        SITIOS[i].que, SITIOS[i].va);
                return;
            }
    }
    if (!g_pau_cueva) g_pau_cueva = (BYTE *)VirtualAlloc(NULL, 512, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!g_pau_cueva) { apuntar("  [pausa] ⛔ sin memoria para los saltos"); return; }

    DWORD abrir = (DWORD)PV(0x41F62E), dibujo = (DWORD)PV(0x41B2B3), je = (DWORD)PV(0x4265A7),
          regalo = (DWORD)PV(0x41FE41);
    BYTE *c_abrir  = pau_cueva_llamar((void *)pau_abrir, 0, abrir, 6, abrir + 6, 0);       /* siempre sigue */
    BYTE *c_dibujo = pau_cueva_llamar((void *)pau_dibujar, 0, dibujo, 5, (DWORD)PV(0x41BFE0), 0);
    BYTE *c_regalo = pau_cueva_llamar((void *)pau_regalo, 0, regalo, 5, regalo + 5, 0);
    /* el clic: reemplaza `je 0x426673` (relativo: NO se copia). eax == 3 -> preguntar; si es nuestro,
     * al final del manejo (0x4267CC, donde terminan Continuar y Salir); si no, a «Salir» como siempre. */
    BYTE *c_clic = g_pau_cueva + g_pau_usado;
    static const BYTE cmp3[] = { 0x83, 0xF8, 0x03 };                      /* cmp eax,3 */
    pau_emitir(cmp3, 3);
    pau_jne(je + 6);                                                      /* no es un clic: sigue */
    pau_cueva_llamar((void *)pau_clic, 1, 0, 0, (DWORD)PV(0x4267CC), (DWORD)PV(0x426673));

    if (!pau_poner_salto(abrir, 6, c_abrir) || !pau_poner_salto(dibujo, 5, c_dibujo) ||
        !pau_poner_salto(je, 6, c_clic) || !pau_poner_salto(regalo, 5, c_regalo)) {
        apuntar("  [pausa] ⛔ VirtualProtect falló a mitad: la Pausa puede quedar rara");
        return;
    }
    apuntar("  [pausa] ok: «Repetir» enganchado (sólo jugando solo; %d B de saltos)", g_pau_usado);
}
