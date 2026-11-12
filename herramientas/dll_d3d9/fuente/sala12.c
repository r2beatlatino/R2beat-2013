/* sala12.c — «MODO DE 12 JUGADORES» en la ventana de CREAR SALA (el 6vs6, 10-oct-2026)
 *
 *   anonimo03 (10-oct, con un paint): una tercera casilla en la caja de la derecha, debajo de «Modo de Ítem». Con
 *   Batalla en Equipo = el 6vs6; con Batalla Personal = 12 todos contra todos; ⛔ con Relevo no.
 *   Investigación: documentacion/MODO_6VS6.md §11. Lo que se VE lo arma herramientas/sala12_crear.py
 *   (rnr_ui_sala12.pak: el .rui con `Image_mode12` / `Image_check12` / `Base_mode12`, el fondo y el rótulo).
 *
 *   La ventana es cCreateRoomRegular (vtable 0x879694). Su entrada [3] (0x4BCB10, thiscall, ret 0x10) es la que
 *   atiende el mouse: hace el hit-test del diálogo (`0x686530(&msg 0x931198, &flags 0x9313B4)`, el control tocado
 *   queda en [0x9313BC]) y compara su NOMBRE (`0x688650`). Un nombre nuevo no lo atiende nadie ⇒ esta entrada se
 *   desvía a s12_mensaje, que:
 *     · clic en Base_mode12 → prende/apaga (al prender: si estaba Relevo pasa a Equipo `0x4BC560(0)`, y si estaba
 *       Colaboración o Jefe `[+0x14]` 4/5 pasa a Velocidad `0x4BC340(2)`)
 *     · ⛔ Relevo con el 12 prendido → se deshace en la misma vuelta (anonimo03: «que no se pueda marcar relevo»)
 *     · si después de todo quedó Colaboración o Jefe → el 12 se apaga
 *     · pinta la tilde (`0x686A10` visible) y el rótulo (`0x686A30` corte 1 encendido / 2 normal) en cada vuelta
 *   Los modos de la ventana: [+0x10] 0 equipo · 1 personal · 2 relevo · [+0x14] 1 ítem · 2 velocidad · 4 colab · 5 jefe.
 *
 *   EL AVISO AL SERVER: el FF10 lo arma 0x5C6AF0 (thiscall, 7 args, el 1.º = los flags del modo: 0x01 velocidad,
 *   0x02 equipo, 0x10 relevo — `0x46BC60`). El bit 0x80 no lo usa nadie: con el 12 prendido va 0x80 (las dos llamadas
 *   de la ventana, 0x4BC2BD y 0x4BC31F). El server lo saca del modo y prende la carrera grande de la sala.
 *   [sala12] activo=0 lo apaga.
 *
 *   ★ 15-oct · LOS 4 EQUIPOS (EQUIPOS_4.md). anonimo03: «el modo 12 jugadores pasará a ser el TÍTULO, y el check será elegir
 *   entre "2 equipos", "4 equipos"» · «agregar tercera casilla "solo": si el modo individual está marcado, esa también
 *   lo esté (es diseño de UI que veremos mañana)» · «el relevo sólo podrá marcar "4 equipos"» · el cooperativo, nada.
 *   La casilla única pasa a ser 3 casillas EXCLUYENTES (`g_s12`: 0 ninguna · 2 «2 equipos» · 4 «4 equipos» · 1 «solo»):
 *     · tocar una marcada la desmarca (sala de 6, como antes)
 *     · «2 equipos» / «4 equipos» con Batalla Personal marcada → pasa a Batalla en Equipo; «solo» → a Batalla Personal
 *     · con Relevo marcado sólo vale «4 equipos» (tocar las otras no hace nada)
 *     · y al revés, si el jugador cambia la columna de la izquierda: Personal → «solo» · Equipo con «solo» → «2 equipos»
 *       · Relevo → «4 equipos» · Colaboración / Jefe → ninguna
 *   Al server: 0x80 con cualquiera, y 0x40 con «4 equipos» (en relevo va igual: el relevo de 12 siempre es de 4).
 */
#include "sala12_datos.h"

#define S12V(x) (g_s12_base + ((DWORD)(x) - 0x400000))
#define S12_FLAG 0x80
#define S12_FLAG_CUATRO 0x40                /* ★ 15-oct: «4 equipos» */

static BYTE *g_s12_base = NULL;
static int   g_s12_relevo = 1;                /* ★ 14-oct: el relevo con el 12 prendido ([sala12] relevo) */
static int   g_s12 = 0;                    /* ★ 15-oct: la casilla marcada: 0 ninguna · 2 / 4 equipos · 1 solo */
static int   g_s12_item = 1;               /* ★ 13-oct: 12 + ÍTEM permitido ([sala12] item=0 lo vuelve a prohibir) */
static DWORD g_s12_orig = 0;               /* 0x4BCB10 */

typedef int  (__fastcall *F_S12_MSG)(BYTE *self, void *nada, int a, int b, int c, int d);
typedef int  (__fastcall *F_S12_HIT)(BYTE *dlg, void *nada, void *msg, void *flags);
typedef BYTE (__fastcall *F_S12_ES)(void *ctl, void *nada, const char *nombre);
typedef void (__fastcall *F_S12_INT)(void *self, void *nada, int v);
typedef void (__fastcall *F_S12_NOMBRE)(void *dlg, void *nada, const char *nombre, int v);
typedef void (__fastcall *F_S12_FF10)(void *red, void *nada, int flags, int a1, int a2, int a3, int a4, int a5, int a6);

static int s12_tocado(const char *nombre)
{
    void *ctl = *(void **)S12V(0x9313BC);
    return ctl && ((F_S12_ES)S12V(0x688650))(ctl, NULL, nombre);
}

static const int S12_VALOR_OP[S12_OPCIONES] = { 2, 4, 1 };      /* la casilla k → g_s12 */

static void s12_pintar(BYTE *self)
{
    BYTE *dlg = self + 0xDC;
    for (int k = 0; k < S12_OPCIONES; k++) {
        int si = g_s12 == S12_VALOR_OP[k];
        ((F_S12_NOMBRE)S12V(0x686A10))(dlg, NULL, S12_RUI_TILDE_OP[k], si);
        ((F_S12_NOMBRE)S12V(0x686A30))(dlg, NULL, S12_RUI_ETIQ_OP[k], S12_OPCION_ENCENDIDO + 2 * k + (si ? 0 : 1));
    }
    ((F_S12_NOMBRE)S12V(0x686A30))(dlg, NULL, S12_RUI_ROTULO, g_s12 ? S12_ROTULO_ENCENDIDO : S12_ROTULO_NORMAL);
}

/* ★ 15-oct: la casilla tiene que cuadrar con la columna de la izquierda ([+0x10] 0 equipo · 1 personal · 2 relevo) */
static void s12_acomodar(BYTE *self)
{
    int lado = *(int *)(self + 0x10), m = *(int *)(self + 0x14);
    if (m == 4 || m == 5) { g_s12 = 0; return; }                                 /* colaboración / jefe: sin 12 */
    if (!g_s12) return;
    if (lado == 1) g_s12 = 1;                                                    /* personal → «solo» */
    else if (lado == 2) g_s12 = g_s12_relevo ? 4 : 0;                             /* relevo → «4 equipos» */
    else if (g_s12 == 1) g_s12 = 2;                                              /* equipo con «solo» → «2 equipos» */
}

/* ⛔ 1.ª vuelta (anonimo03, 10-oct): «sí marca, pero quedé atascado, sin poder cancelar». Hacía el hit-test del diálogo
 *   YO, antes que el juego, y el juego lo volvía a hacer: los BOTONES (OK / Cancelar) manejan su apretado/soltado en
 *   el hit-test, y dos veces por vuelta se les perdía el clic. ⇒ Ahora NO se toca el hit-test: se deja trabajar al
 *   juego y DESPUÉS se mira qué tocó ([0x9313BC] y el bit 2 de [0x9313B4], que el propio hit-test pone en 0 al
 *   empezar: si no tocó nada de esta ventana, el bit no está). El relevo con el 12 prendido se DESHACE (se vuelve
 *   al equipo de antes) en vez de bloquearse antes.
 *   Y el «arranca apagado» ya no va por tiempo (sin mover el mouse no llegan mensajes y se apagaba solo): va en la
 *   APERTURA de la ventana (`0x4A15E0: jmp 0x4BC8B0`, ver s12_abrir). */
static int __fastcall s12_mensaje(BYTE *self, void *nada, int a, int b, int c, int d)
{
    (void)nada;
    int r = ((F_S12_MSG)g_s12_orig)(self, NULL, a, b, c, d);
    int clic = (*(BYTE *)S12V(0x9313B4) & 2) != 0;
    int k = -1;
    for (int q = 0; clic && q < S12_OPCIONES && k < 0; q++)
        if (s12_tocado(S12_RUI_BASE_OP[q])) k = q;
    if (k >= 0) {
        int v = S12_VALOR_OP[k], lado = *(int *)(self + 0x10);
        if (lado == 2 && v != 4) {
            apuntar("  [sala12] con Relevo sólo vale «4 equipos»");                /* anonimo03 */
        } else if (lado == 2 && !g_s12_relevo) {
            apuntar("  [sala12] relevo de 12 apagado ([sala12] relevo=0)");
        } else {
            ((F_S12_INT)S12V(0x40B800))(*(void **)S12V(0x9314E4), NULL, 3);      /* el sonido del clic */
            g_s12 = g_s12 == v ? 0 : v;
            if (g_s12 == 1 && lado != 1) ((F_S12_INT)S12V(0x4BC560))(self, NULL, 1);           /* → personal */
            if ((g_s12 == 2 || g_s12 == 4) && lado == 1) ((F_S12_INT)S12V(0x4BC560))(self, NULL, 0); /* → equipo */
            if (g_s12) {
                int m = *(int *)(self + 0x14);
                if (m == 4 || m == 5 || (m == 1 && !g_s12_item)) ((F_S12_INT)S12V(0x4BC340))(self, NULL, 2);
            }
            apuntar("  [sala12] modo de 12 jugadores: %s", g_s12 == 2 ? "2 EQUIPOS" : g_s12 == 4 ? "4 EQUIPOS" :
                    g_s12 == 1 ? "SOLO" : "apagado");
        }
    }
    s12_acomodar(self);
    /* ⛔ 12 + ÍTEM: «empieza sin audio y crashea a los segundos» (anonimo03, 10-oct). Los ítems tienen sus propios «6»
     *   (pendiente, MODO_6VS6.md §11): hasta resolverlo, con el 12 prendido el modo es VELOCIDAD. */
    if (g_s12 && *(int *)(self + 0x14) == 1 && !g_s12_item) ((F_S12_INT)S12V(0x4BC340))(self, NULL, 2);
    s12_pintar(self);
    return r;
}

/* la ventana se abre (0x4A15E0 hace `jmp 0x4BC8B0` con ecx = la ventana): arranca con el 12 apagado */
typedef void (__fastcall *F_S12_ABRIR)(BYTE *self);
static void __fastcall s12_abrir(BYTE *self)
{
    g_s12 = 0;
    ((F_S12_ABRIR)S12V(0x4BC8B0))(self);
    s12_pintar(self);
}

/* las dos llamadas al FF10 de la ventana (0x4BC2BD sin clave, 0x4BC31F con clave) */
static void __fastcall s12_ff10(void *red, void *nada, int flags, int a1, int a2, int a3, int a4, int a5, int a6)
{
    (void)nada;
    if (g_s12) {
        apuntar("  [sala12] crear sala: modo 0x%02X + 0x80 (12 jugadores)%s", flags & 0xFF,
                g_s12 == 4 ? " + 0x40 (4 equipos)" : "");
        flags |= S12_FLAG;
        if (g_s12 == 4) flags |= S12_FLAG_CUATRO;
    }
    g_s12 = 0;
    ((F_S12_FF10)S12V(0x5C6AF0))(red, NULL, flags, a1, a2, a3, a4, a5, a6);
}

static int s12_escribir(DWORD va, const void *b, int n)
{
    DWORD viejo = 0;
    if (!VirtualProtect(S12V(va), n, PAGE_EXECUTE_READWRITE, &viejo)) return 0;
    CopyMemory(S12V(va), b, n);
    VirtualProtect(S12V(va), n, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), S12V(va), n);
    return 1;
}

static void sala12_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("sala12", "activo", 1, ini)) {
        apuntar("  [sala12] apagado ([sala12] activo=0)");
        return;
    }
    g_s12_base = (BYTE *)GetModuleHandleA(NULL);
    g_s12_item = (int)GetPrivateProfileIntA("sala12", "item", 1, ini);
    /* ★ 14-oct: el RELEVO DE 12 (4 equipos de 3, RELEVO_12.md) — el server arma la sala con DOCE_RELEVO */
    g_s12_relevo = (int)GetPrivateProfileIntA("sala12", "relevo", 1, ini);
    static const DWORD LLAMA_FF10[2] = { 0x4BC2BD, 0x4BC31F };
    /* la guarda: la entrada [3] de la vtable, los nombres de la ventana y las dos llamadas al FF10 */
    if (*(DWORD *)S12V(0x8796A0) != (DWORD)S12V(0x4BCB10) || lstrcmpA((const char *)S12V(0x879760), "Base_relay") != 0) {
        apuntar("  [sala12] ⛔ la ventana de crear sala no es la esperada: no se toca nada");
        return;
    }
    for (int i = 0; i < 2; i++) {
        BYTE *c = S12V(LLAMA_FF10[i]);
        if (c[0] != 0xE8 || (DWORD)(c + 5 + *(int *)(c + 1)) != (DWORD)S12V(0x5C6AF0)) {
            apuntar("  [sala12] ⛔ la llamada al FF10 (0x%06X) no es la esperada: no se toca nada", LLAMA_FF10[i]);
            return;
        }
    }
    {
        BYTE *c = S12V(0x4A15E0);
        if (c[0] != 0xE9 || (DWORD)(c + 5 + *(int *)(c + 1)) != (DWORD)S12V(0x4BC8B0)) {
            apuntar("  [sala12] ⛔ la apertura de la ventana (0x4A15E0) no es la esperada: no se toca nada");
            return;
        }
    }
    g_s12_orig = (DWORD)S12V(0x4BCB10);
    {
        int rel = (int)((DWORD)s12_abrir - ((DWORD)S12V(0x4A15E0) + 5));
        s12_escribir(0x4A15E0 + 1, &rel, 4);
    }
    DWORD p = (DWORD)s12_mensaje;
    s12_escribir(0x8796A0, &p, 4);
    for (int i = 0; i < 2; i++) {
        int rel = (int)((DWORD)s12_ff10 - ((DWORD)S12V(LLAMA_FF10[i]) + 5));
        s12_escribir(LLAMA_FF10[i] + 1, &rel, 4);
    }
    apuntar("  [sala12] listo: «Modo de 12 jugadores» de crear sala — 2 equipos / 4 equipos / solo (vtable 0x8796A0,"
            " FF10 con 0x80, y 0x40 con 4 equipos)");
}
