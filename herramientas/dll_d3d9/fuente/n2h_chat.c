/* n2h_chat.c — ★ 19-nov · LA LECTURA DEL CHAT DE Ñ2HOCK, DENTRO DE LA DLL (SÓLO LECTURA)
 *
 *   Port a C de la pestaña «Chat» de Ñ2Hock (ChatReader.cs, ChatSettings.cs, Form1.Chat.cs y el dibujo de
 *   Form1.GameOverlay.cs). Ñ2Hock abre el proceso desde afuera (PROCESS_VM_READ); acá ya estamos adentro y se
 *   lee la memoria del propio proceso. ⛔ NO SE ESCRIBE NADA EN EL EXE: ni un byte, ni un gancho.
 *
 *   Se incluye dentro de herramienta.c, justo antes de `#include "n2h_ventana.c"`: usa g_ht_base / HT_VA /
 *   HT_TC (herramienta.c), F_PINTAR / calc_pantalla (calculadora.c) e id_leer / g_id_mb2wc (idiomas.c).
 *
 * ── EL MAPA (el de ChatReader.cs, con la misma firma que comprueba Ñ2Hock) ──────────────────────────────────
 *   [0x9314E8]            cChatWindow (0 = todavía no existe)
 *     +0x93C / +0x940     vector de pestañas (begin / end), 0x40 bytes cada una
 *     +0xA24              índice de la pestaña elegida en el juego
 *   pestaña +0x00         std::string nombre ("" = General)      +0x3C  la lista de mensajes (puntero, 0 = vacía)
 *   lista   +0x14         cabeza del std::list                   +0x18  cuántos nodos
 *   nodo    +0 sig · +4 ant · +8 std::string texto · +8+0x1C color ARGB
 *   std::string (MSVC)    +4 texto en línea (capacidad < 16) o puntero · +0x14 largo · +0x18 capacidad
 *   Firma (si algún byte no está, no se lee nada): 0x4ED786 · 0x45DF0E · 0x45E009 · 0x65CA58 · 0x65C91C.
 *   Para dibujar: [0x93149C] + 0x63A640 (el pintor, F_PINTAR), [0x931568] + 0x635350 (medir, thiscall),
 *   [0x931498] (+4 ancho, +8 alto de la pantalla: calc_pantalla).
 *
 * ── CÓMO SE LEE ──────────────────────────────────────────────────────────────────────────────────────────
 *   Con ReadProcessMemory sobre el PROPIO proceso (nc_leer), no con punteros a pelo: el hilo del juego agrega y
 *   borra nodos mientras la ventana lee desde su hilo, y un nodo liberado entre «¿existe?» (ht_memoria_ok) y la
 *   lectura sería una violación de acceso. ReadProcessMemory nunca revienta: si la memoria no está, falla y listo.
 *   Para no recorrer las listas 20 veces por segundo, cada pestaña tiene una «huella» (lista, cabeza, primero,
 *   último, cuenta): sólo se relee si cambió (y igual, una vez por segundo). Si la huella cambia DURANTE la lectura,
 *   se descarta y se reintenta en el próximo tick.
 *   El historial guarda los BYTES del juego (no el texto ya convertido): cambiar la codificación re-decodifica todo
 *   sin duplicar (Ñ2Hock volvía a meter las líneas que seguían en pantalla). Nada se escribe en disco.
 *
 * ── LA API (todo static) ─────────────────────────────────────────────────────────────────────────────────
 *   Hilo de la ventana (todas toman el mismo candado, no se llaman entre sí):
 *     void nc_tick(void)                                   cada 50 ms: lee el juego y junta las líneas nuevas
 *     int  nc_version(void)                                cambia cuando hay que redibujar el historial
 *     int  nc_lineas(void)                                 cuántas líneas tiene el canal que se muestra
 *     int  nc_linea(int i, wchar_t *texto, int n, COLORREF *color)   1 = ok (texto con el 0 final, color RGB)
 *     COLORREF nc_color_legible(COLORREF c, COLORREF fondo, COLORREF texto)  el ajuste de DrawChatLine
 *     int  nc_version_canales(void)                        cambia cuando aparece un canal nuevo
 *     int  nc_canales(wchar_t nombres[][NCH_NOMBRE_W], int max)       0 = «Canal seleccionado en el juego»,
 *                                                          después los canales vistos («General» = sin nombre)
 *     void nc_elegir_canal(int i)   ·  int nc_canal_actual(void)
 *     int  nc_codificaciones(const wchar_t **nombres, int max)        las de Ñ2Hock, en su orden
 *     void nc_elegir_codificacion(int i)  ·  int nc_codificacion_actual(void)
 *     void nc_conservar_diez(int on)       «Conservar últimas 10 entradas» (si no, 500 por canal)
 *     void nc_vaciar(void)                 «Vaciar historial» (lo que sigue en pantalla del juego NO vuelve)
 *     int  nc_estado(wchar_t *s, int n)    el texto de estado de Ñ2Hock; devuelve 1 bien · 0 neutro · -1 error
 *     void nc_en_juego(int on, int solo_carrera)   «Ver el chat dentro del juego» / «Solo durante la carrera»
 *   Hilo del juego:
 *     void nc_por_cuadro(void)             desde ht_por_cuadro (el HUD de carrera): las últimas 8 líneas abajo a
 *                                          la derecha (98,5 % del ancho, 80 % del alto), con la letra del juego
 *
 *   «Español / occidental» usa la regla del juego (idiomas.c: UTF-8 si lo es, si no 1252), que para 1252 da lo
 *   mismo. Las demás, MultiByteToWideChar con su página (si Windows no la tiene, 1252). Dentro del juego el texto
 *   va con sus bytes tal cual: lo convierte el propio juego (con la regla de idiomas.c), como su ventana de chat.
 *
 *   ⚠ «Solo durante la carrera»: nc_por_cuadro sólo corre en la carrera (lo llama el HUD), así que hoy da igual
 *     prendido o apagado. Ñ2Hock, fuera de la carrera, dibuja con su dinput8.dll en el Present (o con una ventana
 *     transparente encima del juego); acá haría falta un dibujo propio en el EndScene/Present de d3d9_proxy.c.
 */

/* ── el mapa ── */
#define NCH_VENTANA         0x009314E8
#define NCH_PEST_INI        0x93C
#define NCH_PEST_FIN        0x940
#define NCH_PEST_ELEGIDA    0xA24
#define NCH_PEST_TAM        0x40
#define NCH_PEST_LISTA      0x3C
#define NCH_LISTA_CABEZA    0x14
#define NCH_LISTA_CUENTA    0x18
#define NCH_NODO_VALOR      8
#define NCH_LINEA_COLOR     0x1C
#define NCH_PINTOR_OBJ      0x0093149C
#define NCH_PINTOR          0x0063A640
#define NCH_MEDIR_OBJ       0x00931568
#define NCH_MEDIR           0x00635350

/* ── los límites (los de Ñ2Hock) ── */
#define NCH_MAX_PEST        32          /* pestañas del juego                          */
#define NCH_MAX_LINEAS      1000        /* nodos de una lista                          */
#define NCH_MAX_TEXTO       1024        /* bytes de un texto                           */
#define NCH_HISTORIAL       500         /* ChatHistoryLimit                            */
#define NCH_CORTO           10          /* ChatShortLimit                              */
#define NCH_MAX_CANALES     48          /* canales recordados (índice + nombre)        */
#define NCH_MAX_NOMBRE      64          /* bytes del nombre de un canal                */
#define NCH_NOMBRE_W        72          /* wchar de un nombre para la lista            */
#define NCH_RELEER_MS       1000        /* relectura completa aunque la huella no cambie */
#define NCH_JUEGO_LINEAS    8           /* InGameChatLines                             */
#define NCH_JUEGO_FILAS     (NCH_JUEGO_LINEAS + 4)
#define NCH_JUEGO_ANCHO     440         /* el recuadro de RenderChatOverlay            */
#define NCH_JUEGO_MARGEN    8
#define NCH_JUEGO_ALTO_FILA 16          /* la letra del juego es más chica que la Segoe 13 px de Ñ2Hock */

typedef int (HT_TC *NC_F_MEDIR)(void *mgr, const char *s, int fuente);

/* ═══ 1 · LEER LA MEMORIA DEL PROPIO PROCESO, SIN REVENTAR ═══════════════════════════════════════════════ */
static int nc_leer(DWORD dir, void *dst, int n)
{
    SIZE_T leidos = 0;
    if (!dir || n <= 0) return 0;
    return ReadProcessMemory(GetCurrentProcess(), (LPCVOID)(ULONG_PTR)dir, dst, (SIZE_T)n, &leidos) && leidos == (SIZE_T)n;
}

static int nc_u32(DWORD dir, DWORD *v) { return nc_leer(dir, v, 4); }

/* un std::string de MSVC a partir de su cabecera (0x1C bytes ya leídos): los bytes, sin el 0. -1 = no se pudo. */
static int nc_cadena_de(const BYTE *cab, char *out, int cap)
{
    int largo = *(const int *)(cab + 0x14), capac = *(const int *)(cab + 0x18);
    if (largo <= 0) return 0;
    if (largo > NCH_MAX_TEXTO) largo = NCH_MAX_TEXTO;
    if (largo > cap) largo = cap;
    if (capac < 16) {
        if (largo > 15) largo = 15;
        CopyMemory(out, cab + 4, largo);
        return largo;
    }
    return nc_leer(*(const DWORD *)(cab + 4), out, largo) ? largo : -1;
}

static int nc_cadena(DWORD dir, char *out, int cap)
{
    BYTE cab[0x1C];
    if (!nc_leer(dir, cab, sizeof(cab))) return -1;
    return nc_cadena_de(cab, out, cap);
}

/* ═══ 2 · LISTAS DE LÍNEAS (bytes del juego + color), EN UN SOLO BLOQUE ═══════════════════════════════════
 *   línea i en d + ini[i]: DWORD color · int largo · los bytes */
typedef struct { char *d; int usado, cap; int *ini; int nl, capl; } NC_LISTA;

static void *nc_crecer(void *p, int bytes)
{
    return p ? HeapReAlloc(GetProcessHeap(), 0, p, bytes) : HeapAlloc(GetProcessHeap(), 0, bytes);
}

static int nc_lista_poner(NC_LISTA *l, const char *t, int n, DWORD color)
{
    int hace_falta = l->usado + 8 + n;
    if (hace_falta > l->cap) {
        int cap = hace_falta * 2 + 1024;
        char *d = (char *)nc_crecer(l->d, cap);
        if (!d) return 0;
        l->d = d; l->cap = cap;
    }
    if (l->nl >= l->capl) {
        int capl = l->capl * 2 + 64;
        int *ini = (int *)nc_crecer(l->ini, capl * (int)sizeof(int));
        if (!ini) return 0;
        l->ini = ini; l->capl = capl;
    }
    char *p = l->d + l->usado;
    *(DWORD *)p = color;
    *(int *)(p + 4) = n;
    if (n > 0) CopyMemory(p + 8, t, n);
    l->ini[l->nl++] = l->usado;
    l->usado = hace_falta;
    return 1;
}

static const char *nc_lista_texto(const NC_LISTA *l, int i, int *n, DWORD *color)
{
    const char *p = l->d + l->ini[i];
    if (color) *color = *(const DWORD *)p;
    *n = *(const int *)(p + 4);
    return p + 8;
}

static void nc_lista_vaciar(NC_LISTA *l) { l->usado = 0; l->nl = 0; }

/* quita las k primeras (el juego y el historial sueltan por adelante) */
static void nc_lista_quitar(NC_LISTA *l, int k)
{
    if (k <= 0) return;
    if (k >= l->nl) { nc_lista_vaciar(l); return; }
    int corte = l->ini[k];
    MoveMemory(l->d, l->d + corte, l->usado - corte);
    l->usado -= corte;
    for (int i = k; i < l->nl; i++) l->ini[i - k] = l->ini[i] - corte;
    l->nl -= k;
}

static int nc_misma(const NC_LISTA *a, int i, const NC_LISTA *b, int j)
{
    int na, nb;
    DWORD ca, cb;
    const char *ta = nc_lista_texto(a, i, &na, &ca), *tb = nc_lista_texto(b, j, &nb, &cb);
    if (na != nb || ca != cb) return 0;
    for (int k = 0; k < na; k++) if (ta[k] != tb[k]) return 0;
    return 1;
}

/* ChatReader.NewLines: desde qué línea de `ahora` son nuevas (el juego agrega al final y suelta por adelante) */
static int nc_nuevas(const NC_LISTA *antes, const NC_LISTA *ahora)
{
    for (int suelta = 0; suelta <= antes->nl; suelta++) {
        int junta = antes->nl - suelta;
        if (junta > ahora->nl) continue;
        int igual = 1;
        for (int i = 0; i < junta && igual; i++) igual = nc_misma(antes, suelta + i, ahora, i);
        if (igual) return junta;
    }
    return 0;
}

/* ═══ 3 · LAS CODIFICACIONES (ChatEncodings.All) ═════════════════════════════════════════════════════════ */
static const struct { const wchar_t *nombre; UINT pagina; } NCH_COD[] = {
    { L"Español / occidental", 1252 }, { L"Coreano", 949 }, { L"Japonés", 932 },
    { L"Chino simplificado", 936 }, { L"Chino tradicional", 950 }, { L"Tailandés", 874 },
};
#define NCH_N_COD ((int)(sizeof(NCH_COD) / sizeof(NCH_COD[0])))

/* bytes del juego -> UTF-16 con la codificación `cod`. Devuelve las WCHAR escritas (sin contar el 0, que pone). */
static int nc_decodificar(int cod, const char *s, int n, wchar_t *w, int cap)
{
    WCHAR tmp[NCH_MAX_TEXTO + 2];
    int nw = 0;
    if (!w || cap < 1) return 0;
    if (n > NCH_MAX_TEXTO) n = NCH_MAX_TEXTO;
    if (n > 0) {
        if (cod <= 0 || cod >= NCH_N_COD) {               /* la regla del juego: UTF-8 si lo es, si no 1252 */
            if (!g_id_mb2wc) g_id_mb2wc = (ID_MB2WC)GetProcAddress(GetModuleHandleA("kernel32.dll"), "MultiByteToWideChar");
            nw = g_id_mb2wc ? id_leer((const BYTE *)s, n, tmp, NULL) : 0;
        } else {
            nw = MultiByteToWideChar(NCH_COD[cod].pagina, 0, s, n, tmp, NCH_MAX_TEXTO + 1);
            if (nw <= 0) nw = MultiByteToWideChar(1252, 0, s, n, tmp, NCH_MAX_TEXTO + 1);
        }
        if (nw < 0) nw = 0;
    }
    if (nw > cap - 1) nw = cap - 1;
    CopyMemory(w, tmp, nw * sizeof(WCHAR));
    w[nw] = 0;
    return nw;
}

/* ═══ 4 · EL ESTADO ════════════════════════════════════════════════════════════════════════════════════ */
typedef struct {
    int indice;                         /* la pestaña del juego (la clave de Ñ2Hock es «índice:nombre») */
    char nombre[NCH_MAX_NOMBRE];
    int nn;
    int abierto;                        /* está en el juego ahora                                       */
    NC_LISTA hist, visto;               /* el historial de la sesión · lo que el juego mostraba         */
    DWORD huella[5];                    /* lista, cabeza, primero, último, cuenta                       */
    int con_huella;
} NC_CANAL;

static SRWLOCK g_nc_candado = SRWLOCK_INIT;           /* hilo de la ventana                                  */
static NC_CANAL g_nc_c[NCH_MAX_CANALES];
static int g_nc_nc = 0;
static NC_LISTA g_nc_tmp;
static volatile LONG g_nc_version = 1, g_nc_version_canales = 1;
static int g_nc_mostrado = -1;                         /* el canal (g_nc_c) del historial que se ve            */
static int g_nc_seleccionado = 1;                      /* 1 = «Canal seleccionado en el juego»                 */
static char g_nc_elegido[NCH_MAX_NOMBRE];
static int g_nc_elegido_n = 0;
static int g_nc_cod = 0;
static int g_nc_diez = 0;
static int g_nc_firma = 0;                             /* 0 sin mirar · 1 bien · -1 este exe no es             */
static DWORD g_nc_firma_va = 0;
static DWORD g_nc_ult_completa = 0;
static wchar_t g_nc_estado[160] = L"Carga el juego y conecta la cuenta para leer el chat.";
static int g_nc_estado_tipo = 0;
static int g_nc_aviso = 0;                             /* «Historial vaciado.» hasta el próximo cambio          */

/* lo que dibuja el hilo del juego: una copia, con su propio candado (se tiene por un CopyMemory) */
typedef struct {
    int nl, version;
    int n[NCH_JUEGO_LINEAS];
    DWORD color[NCH_JUEGO_LINEAS];
    char t[NCH_JUEGO_LINEAS][NCH_MAX_TEXTO + 1];
} NC_CUADRO;
static SRWLOCK g_nc_candado_cuadro = SRWLOCK_INIT;
static NC_CUADRO g_nc_cuadro;
static volatile LONG g_nc_en_juego = 1, g_nc_solo_carrera = 1;   /* los de fábrica de ChatSettings */
static int g_nc_cuadro_version = -1;

static void nc_poner_estado(int tipo, const wchar_t *s)
{
    g_nc_estado_tipo = tipo;
    lstrcpynW(g_nc_estado, s, (int)(sizeof(g_nc_estado) / sizeof(g_nc_estado[0])));
}

static int nc_limite(void) { return g_nc_diez ? NCH_CORTO : NCH_HISTORIAL; }

static void nc_recortar(NC_LISTA *l) { if (l->nl > nc_limite()) nc_lista_quitar(l, l->nl - nc_limite()); }

static int nc_mismo_nombre(const NC_CANAL *c, const char *s, int n)
{
    if (c->nn != n) return 0;
    for (int k = 0; k < n; k++) if (c->nombre[k] != s[k]) return 0;
    return 1;
}

/* el canal de esa pestaña (índice + nombre); lo crea si no estaba. -1 si ya no hay lugar. */
static int nc_canal_de(int indice, const char *nombre, int nn)
{
    for (int i = 0; i < g_nc_nc; i++)
        if (g_nc_c[i].indice == indice && nc_mismo_nombre(&g_nc_c[i], nombre, nn)) return i;
    if (g_nc_nc >= NCH_MAX_CANALES) return -1;
    int nuevo = 1;                                      /* ¿un nombre que la lista no tenía? */
    for (int i = 0; i < g_nc_nc; i++) if (nc_mismo_nombre(&g_nc_c[i], nombre, nn)) nuevo = 0;
    NC_CANAL *c = &g_nc_c[g_nc_nc];
    ZeroMemory(c, sizeof(*c));
    c->indice = indice;
    CopyMemory(c->nombre, nombre, nn);
    c->nn = nn;
    if (nuevo) InterlockedIncrement(&g_nc_version_canales);
    return g_nc_nc++;
}

/* la lista de nombres que ve la ventana: los distintos, en el orden en que aparecieron (+ el elegido) */
static int nc_nombres(const char **p, int *n, int max)
{
    int k = 0, elegido_esta = g_nc_seleccionado;
    for (int i = 0; i < g_nc_nc && k < max; i++) {
        int repetido = 0;
        for (int j = 0; j < k && !repetido; j++) repetido = nc_mismo_nombre(&g_nc_c[i], p[j], n[j]);
        if (repetido) continue;
        if (!elegido_esta && nc_mismo_nombre(&g_nc_c[i], g_nc_elegido, g_nc_elegido_n)) elegido_esta = 1;
        p[k] = g_nc_c[i].nombre; n[k] = g_nc_c[i].nn; k++;
    }
    if (!elegido_esta && k < max) { p[k] = g_nc_elegido; n[k] = g_nc_elegido_n; k++; }
    return k;
}

/* ═══ 5 · LEER UNA PESTAÑA ════════════════════════════════════════════════════════════════════════════
 *   La huella: [lista, cabeza, cabeza->sig, cabeza->ant, cuenta]. 0 = no se pudo leer. */
static int nc_huella(DWORD lista, DWORD h[5])
{
    BYTE cab[0x1C];
    DWORD nodo[2];
    ZeroMemory(h, 5 * sizeof(DWORD));
    h[0] = lista;
    if (!lista) return 1;
    if (!nc_leer(lista, cab, sizeof(cab))) return 0;
    h[1] = *(DWORD *)(cab + NCH_LISTA_CABEZA);
    h[4] = *(DWORD *)(cab + NCH_LISTA_CUENTA);
    if (!h[1] || h[4] > NCH_MAX_LINEAS || !nc_leer(h[1], nodo, 8)) return 0;
    h[2] = nodo[0]; h[3] = nodo[1];
    return 1;
}

/* las líneas de la lista en `out`. 1 = bien. */
static int nc_leer_lineas(const DWORD h[5], NC_LISTA *out)
{
    char texto[NCH_MAX_TEXTO];
    nc_lista_vaciar(out);
    if (!h[0]) return 1;
    DWORD cabeza = h[1], nodo = h[2];
    for (DWORD i = 0; i < h[4] && nodo != cabeza && nodo; i++) {
        BYTE b[NCH_NODO_VALOR + NCH_LINEA_COLOR + 4];     /* sig, ant, la cadena y el color: UNA lectura */
        if (!nc_leer(nodo, b, sizeof(b))) return 0;
        int n = nc_cadena_de(b + NCH_NODO_VALOR, texto, sizeof(texto));
        if (n < 0) return 0;
        nc_lista_poner(out, texto, n, *(DWORD *)(b + NCH_NODO_VALOR + NCH_LINEA_COLOR));
        nodo = *(DWORD *)b;
    }
    return 1;
}

/* ═══ 6 · EL TICK ═══════════════════════════════════════════════════════════════════════════════════════ */
static const struct { DWORD va; int n; BYTE b[8]; } NCH_FIRMA[] = {
    { 0x004ED786, 6, { 0x8B, 0x0D, 0xE8, 0x14, 0x93, 0x00 } },          /* mov ecx, [ventana del chat]   */
    { 0x0045DF0E, 6, { 0x8B, 0xB5, 0x3C, 0x09, 0x00, 0x00 } },          /* mov esi, [this+0x93C]         */
    { 0x0045E009, 6, { 0x39, 0x8B, 0x24, 0x0A, 0x00, 0x00 } },          /* cmp [this+0xA24], ecx         */
    { 0x0065CA58, 6, { 0x8B, 0x46, 0x18, 0x3B, 0x46, 0x24 } },          /* la cuenta en +0x18            */
    { 0x0065C91C, 7, { 0xC7, 0x46, 0x18, 0x0F, 0x00, 0x00, 0x00 } },    /* capacidad del string en +0x18 */
};

static int nc_mirar_firma(void)
{
    for (int i = 0; i < (int)(sizeof(NCH_FIRMA) / sizeof(NCH_FIRMA[0])); i++) {
        BYTE v[8];
        if (!nc_leer((DWORD)(ULONG_PTR)HT_VA(NCH_FIRMA[i].va), v, NCH_FIRMA[i].n)) { g_nc_firma_va = NCH_FIRMA[i].va; return -1; }
        for (int k = 0; k < NCH_FIRMA[i].n; k++)
            if (v[k] != NCH_FIRMA[i].b[k]) { g_nc_firma_va = NCH_FIRMA[i].va; return -1; }
    }
    return 1;
}

/* qué canal se muestra (RefreshChatView): el elegido en el juego, o el de ese nombre (abierto primero) */
static int nc_cual_mostrar(int elegida_juego)
{
    int i;
    if (g_nc_seleccionado) {
        for (i = 0; i < g_nc_nc; i++) if (g_nc_c[i].abierto && g_nc_c[i].indice == elegida_juego) return i;
        return -1;
    }
    for (i = 0; i < g_nc_nc; i++) if (g_nc_c[i].abierto && nc_mismo_nombre(&g_nc_c[i], g_nc_elegido, g_nc_elegido_n)) return i;
    if (g_nc_elegido_n == 0) return -1;                 /* Ñ2Hock: el historial de un canal cerrado, sólo con nombre */
    for (i = 0; i < g_nc_nc; i++) if (nc_mismo_nombre(&g_nc_c[i], g_nc_elegido, g_nc_elegido_n)) return i;
    return -1;
}

/* copia las últimas líneas del canal que se ve para el hilo del juego */
static void nc_publicar_cuadro(void)
{
    static NC_CUADRO nuevo;
    nuevo.nl = 0;
    nuevo.version = (int)g_nc_version;
    if (g_nc_mostrado >= 0) {
        const NC_LISTA *h = &g_nc_c[g_nc_mostrado].hist;
        int desde = h->nl > NCH_JUEGO_LINEAS ? h->nl - NCH_JUEGO_LINEAS : 0;
        for (int i = desde; i < h->nl; i++) {
            int n;
            DWORD color;
            const char *t = nc_lista_texto(h, i, &n, &color);
            if (n > NCH_MAX_TEXTO) n = NCH_MAX_TEXTO;
            CopyMemory(nuevo.t[nuevo.nl], t, n);
            nuevo.t[nuevo.nl][n] = 0;
            nuevo.n[nuevo.nl] = n;
            nuevo.color[nuevo.nl] = color;
            nuevo.nl++;
        }
    }
    AcquireSRWLockExclusive(&g_nc_candado_cuadro);
    CopyMemory(&g_nc_cuadro, &nuevo, sizeof(nuevo));
    ReleaseSRWLockExclusive(&g_nc_candado_cuadro);
}

static void nc_refrescar(int elegida_juego, int leyo)
{
    int m = nc_cual_mostrar(elegida_juego);
    if (m != g_nc_mostrado) { g_nc_mostrado = m; InterlockedIncrement(&g_nc_version); }
    if (g_nc_cuadro_version != (int)g_nc_version) { g_nc_cuadro_version = (int)g_nc_version; nc_publicar_cuadro(); }
    if (!leyo || g_nc_aviso) return;
    int abierto = m >= 0 && g_nc_c[m].abierto;
    if (!abierto) { nc_poner_estado(1, L"Ese canal no está abierto en el juego ahora."); return; }
    wchar_t nombre[NCH_NOMBRE_W], s[160];
    if (g_nc_c[m].nn == 0) lstrcpyW(nombre, TR(L"General"));
    else nc_decodificar(g_nc_cod, g_nc_c[m].nombre, g_nc_c[m].nn, nombre, NCH_NOMBRE_W);
    wsprintfW(s, TR(L"Leyendo «%s» · %d entrada(s)."), nombre, g_nc_c[m].hist.nl);
    nc_poner_estado(1, s);
}

static void nc_tick_adentro(void)
{
    int i;
    if (!g_ht_base) return;
    if (!g_nc_firma) {
        g_nc_firma = nc_mirar_firma();
        if (g_nc_firma < 0) {
            wchar_t s[160];
            wsprintfW(s, TR(L"Esta versión del juego no coincide con el lector de chat (+0x%X)."), (unsigned)(g_nc_firma_va - 0x400000));
            nc_poner_estado(-1, s);
            apuntar("  [chat] ⛔ el exe no es el esperado en 0x%08X: el chat no se lee", (unsigned)g_nc_firma_va);
        }
    }
    if (g_nc_firma < 0) return;

    for (i = 0; i < g_nc_nc; i++) g_nc_c[i].abierto = 0;
    DWORD ventana = 0, ini = 0, fin = 0, elegida = (DWORD)-1;
    if (!nc_u32((DWORD)(ULONG_PTR)HT_VA(NCH_VENTANA), &ventana) || !ventana) {
        nc_refrescar(-1, 0);
        if (!g_nc_aviso) nc_poner_estado(0, L"Carga el juego y conecta la cuenta para leer el chat.");
        return;
    }
    if (!nc_u32(ventana + NCH_PEST_INI, &ini) || !nc_u32(ventana + NCH_PEST_FIN, &fin)
        || !nc_u32(ventana + NCH_PEST_ELEGIDA, &elegida)
        || fin < ini || (fin - ini) % NCH_PEST_TAM || (fin - ini) / NCH_PEST_TAM > NCH_MAX_PEST) {
        nc_refrescar(-1, 0);
        nc_poner_estado(-1, L"La lista de canales del chat no es válida.");
        return;
    }
    DWORD ahora = GetTickCount();
    int completa = ahora - g_nc_ult_completa >= NCH_RELEER_MS;
    if (completa) g_nc_ult_completa = ahora;
    int error = 0;
    for (DWORD p = ini, k = 0; p < fin; p += NCH_PEST_TAM, k++) {
        char nombre[NCH_MAX_NOMBRE];
        DWORD lista = 0, h[5], h2[5];
        int nn = nc_cadena(p, nombre, sizeof(nombre));
        if (nn < 0 || !nc_u32(p + NCH_PEST_LISTA, &lista)) { error = 1; continue; }
        int c = nc_canal_de((int)k, nombre, nn);
        if (c < 0) continue;
        NC_CANAL *ca = &g_nc_c[c];
        ca->abierto = 1;
        if (!nc_huella(lista, h)) { error = 1; continue; }
        if (!completa && ca->con_huella && !memcmp(h, ca->huella, sizeof(h))) continue;
        if (!nc_leer_lineas(h, &g_nc_tmp)) { error = 1; continue; }
        if (!nc_huella(lista, h2) || memcmp(h, h2, sizeof(h))) continue;   /* el juego la tocó mientras: otra vez */
        CopyMemory(ca->huella, h, sizeof(h));
        ca->con_huella = 1;
        int desde = nc_nuevas(&ca->visto, &g_nc_tmp);
        if (desde < g_nc_tmp.nl) {
            for (i = desde; i < g_nc_tmp.nl; i++) {
                int n;
                DWORD color;
                const char *t = nc_lista_texto(&g_nc_tmp, i, &n, &color);
                nc_lista_poner(&ca->hist, t, n, color);
            }
            nc_recortar(&ca->hist);
            InterlockedIncrement(&g_nc_version);
            g_nc_aviso = 0;
        }
        NC_LISTA cambio = ca->visto;                     /* lo leído pasa a ser lo visto (sin copiar) */
        ca->visto = g_nc_tmp;
        g_nc_tmp = cambio;
    }
    nc_refrescar((int)elegida, !error);
    if (error) nc_poner_estado(-1, L"La lista de mensajes del chat no es válida.");
}

/* ═══ 7 · LA API DE LA VENTANA ═══════════════════════════════════════════════════════════════════════════ */
static void nc_tick(void)
{
    AcquireSRWLockExclusive(&g_nc_candado);
    nc_tick_adentro();
    ReleaseSRWLockExclusive(&g_nc_candado);
}

static int nc_version(void) { return (int)g_nc_version; }
static int nc_version_canales(void) { return (int)g_nc_version_canales; }

static int nc_lineas(void)
{
    AcquireSRWLockShared(&g_nc_candado);
    int n = g_nc_mostrado >= 0 ? g_nc_c[g_nc_mostrado].hist.nl : 0;
    ReleaseSRWLockShared(&g_nc_candado);
    return n;
}

/* la línea i (0 = la más vieja) del canal que se ve. color = el del juego, en RGB (sin alfa). */
static int nc_linea(int i, wchar_t *texto, int n, COLORREF *color)
{
    int ok = 0;
    if (texto && n > 0) texto[0] = 0;
    AcquireSRWLockShared(&g_nc_candado);
    if (g_nc_mostrado >= 0 && i >= 0 && i < g_nc_c[g_nc_mostrado].hist.nl) {
        int nb;
        DWORD c;
        const char *t = nc_lista_texto(&g_nc_c[g_nc_mostrado].hist, i, &nb, &c);
        if (texto && n > 0) nc_decodificar(g_nc_cod, t, nb, texto, n);
        if (color) *color = RGB((c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF);
        ok = 1;
    }
    ReleaseSRWLockShared(&g_nc_candado);
    return ok;
}

/* DrawChatLine: si el color del juego casi no se distingue del fondo, va el del texto */
static int nc_brillo(COLORREF c)              /* Color.GetBrightness * 1000 */
{
    int r = GetRValue(c), g = GetGValue(c), b = GetBValue(c);
    int mx = r > g ? (r > b ? r : b) : (g > b ? g : b), mn = r < g ? (r < b ? r : b) : (g < b ? g : b);
    return (mx + mn) * 1000 / 510;
}

static COLORREF nc_color_legible(COLORREF c, COLORREF fondo, COLORREF texto)
{
    int d = nc_brillo(c) - nc_brillo(fondo);
    return (d < 350 && d > -350) ? texto : c;
}

static int nc_canales(wchar_t nombres[][NCH_NOMBRE_W], int max)
{
    const char *p[NCH_MAX_CANALES + 1];
    int n[NCH_MAX_CANALES + 1];
    if (max <= 0) return 0;
    AcquireSRWLockShared(&g_nc_candado);
    lstrcpynW(nombres[0], TR(L"Canal seleccionado en el juego"), NCH_NOMBRE_W);
    int k = nc_nombres(p, n, NCH_MAX_CANALES + 1), total = 1;
    for (int i = 0; i < k && total < max; i++, total++) {
        if (n[i] == 0) lstrcpynW(nombres[total], TR(L"General"), NCH_NOMBRE_W);
        else nc_decodificar(g_nc_cod, p[i], n[i], nombres[total], NCH_NOMBRE_W);
    }
    ReleaseSRWLockShared(&g_nc_candado);
    return total;
}

static void nc_elegir_canal(int i)
{
    const char *p[NCH_MAX_CANALES + 1];
    int n[NCH_MAX_CANALES + 1];
    AcquireSRWLockExclusive(&g_nc_candado);
    int k = nc_nombres(p, n, NCH_MAX_CANALES + 1);
    if (i <= 0 || i > k) { g_nc_seleccionado = 1; g_nc_elegido_n = 0; }
    else {
        g_nc_seleccionado = 0;
        g_nc_elegido_n = n[i - 1];
        MoveMemory(g_nc_elegido, p[i - 1], n[i - 1]);      /* p puede ser el propio g_nc_elegido */
    }
    g_nc_aviso = 0;
    InterlockedIncrement(&g_nc_version);
    InterlockedIncrement(&g_nc_version_canales);
    ReleaseSRWLockExclusive(&g_nc_candado);
}

static int nc_canal_actual(void)
{
    const char *p[NCH_MAX_CANALES + 1];
    int n[NCH_MAX_CANALES + 1], r = 0;
    AcquireSRWLockShared(&g_nc_candado);
    if (!g_nc_seleccionado) {
        int k = nc_nombres(p, n, NCH_MAX_CANALES + 1);
        for (int i = 0; i < k; i++) if (p[i] == g_nc_elegido || (n[i] == g_nc_elegido_n && !memcmp(p[i], g_nc_elegido, n[i]))) { r = i + 1; break; }
    }
    ReleaseSRWLockShared(&g_nc_candado);
    return r;
}

static int nc_codificaciones(const wchar_t **nombres, int max)
{
    int k;
    for (k = 0; k < NCH_N_COD && k < max; k++) nombres[k] = NCH_COD[k].nombre;
    return k;
}

static void nc_elegir_codificacion(int i)
{
    AcquireSRWLockExclusive(&g_nc_candado);
    g_nc_cod = (i >= 0 && i < NCH_N_COD) ? i : 0;
    InterlockedIncrement(&g_nc_version);                /* el historial se re-decodifica: nada se duplica */
    InterlockedIncrement(&g_nc_version_canales);
    ReleaseSRWLockExclusive(&g_nc_candado);
}

static int nc_codificacion_actual(void) { return g_nc_cod; }

static void nc_conservar_diez(int on)
{
    AcquireSRWLockExclusive(&g_nc_candado);
    g_nc_diez = on != 0;
    for (int i = 0; i < g_nc_nc; i++) nc_recortar(&g_nc_c[i].hist);
    InterlockedIncrement(&g_nc_version);
    ReleaseSRWLockExclusive(&g_nc_candado);
}

/* «visto» se queda: lo que sigue en la pantalla del juego no tiene que volver */
static void nc_vaciar(void)
{
    AcquireSRWLockExclusive(&g_nc_candado);
    for (int i = 0; i < g_nc_nc; i++) nc_lista_vaciar(&g_nc_c[i].hist);
    InterlockedIncrement(&g_nc_version);
    g_nc_aviso = 1;
    nc_poner_estado(0, L"Historial vaciado.");
    ReleaseSRWLockExclusive(&g_nc_candado);
}

static int nc_estado(wchar_t *s, int n)
{
    AcquireSRWLockShared(&g_nc_candado);
    if (s && n > 0) lstrcpynW(s, g_nc_estado, n);
    int t = g_nc_estado_tipo;
    ReleaseSRWLockShared(&g_nc_candado);
    return t;
}

static void nc_en_juego(int on, int solo_carrera)
{
    InterlockedExchange(&g_nc_en_juego, on != 0);
    InterlockedExchange(&g_nc_solo_carrera, solo_carrera != 0);
}

/* ═══ 8 · DENTRO DEL JUEGO (hilo del juego, una vez por cuadro de la carrera) ═════════════════════════════ */

/* Form1.Wrap: corta `s` en filas de `ancho` px (por espacios; si no hay, por letras sin partir una UTF-8).
 * Devuelve las filas (ini/largo en bytes de `s`). medir(texto con 0 final, ctx) = px. */
static int nc_partir(const char *s, int n, int ancho, int (*medir)(const char *, void *), void *ctx,
                     int *ini, int *largo, int max)
{
    char tmp[NCH_MAX_TEXTO + 1];
    int filas = 0, p = 0;
    if (n > NCH_MAX_TEXTO) n = NCH_MAX_TEXTO;
    while (p < n && filas < max) {
        int cabe = n - p;
        for (;;) {
            if (cabe <= 1) break;
            CopyMemory(tmp, s + p, cabe);
            tmp[cabe] = 0;
            if (medir(tmp, ctx) <= ancho) break;
            int esp = -1;
            for (int k = cabe - 1; k >= 0; k--) if (s[p + k] == ' ') { esp = k; break; }
            if (esp > 0) cabe = esp;
            else {
                cabe--;
                while (cabe > 1 && ((BYTE)s[p + cabe] & 0xC0) == 0x80) cabe--;    /* no partir una letra UTF-8 */
            }
        }
        int fin = cabe;
        while (fin > 0 && (s[p + fin - 1] == ' ' || s[p + fin - 1] == '\t' || s[p + fin - 1] == '\r' || s[p + fin - 1] == '\n')) fin--;
        ini[filas] = p; largo[filas] = fin; filas++;
        p += cabe;
        while (p < n && (s[p] == ' ' || s[p] == '\t' || s[p] == '\r' || s[p] == '\n')) p++;
    }
    return filas;
}

static int nc_medir_juego(const char *s, void *mgr)
{
    int w = mgr ? ((NC_F_MEDIR)HT_VA(NCH_MEDIR))(mgr, s, 0) : 0;
    return (w > 0 && w < 4000) ? w : lstrlenA(s) * 7;
}

/* los grises del juego se aclaran a medio camino del blanco (RenderChatOverlay) */
static DWORD nc_color_juego(DWORD c)
{
    int r = (c >> 16) & 0xFF, g = (c >> 8) & 0xFF, b = c & 0xFF;
    if (nc_brillo(RGB(r, g, b)) < 600) { r = (r + 255) / 2; g = (g + 255) / 2; b = (b + 255) / 2; }
    return 0xFF000000u | ((DWORD)r << 16) | ((DWORD)g << 8) | (DWORD)b;
}

static void nc_por_cuadro(void)
{
    static NC_CUADRO c;                                 /* la copia de este hilo                    */
    static int fila_linea[NCH_JUEGO_FILAS], fila_ini[NCH_JUEGO_FILAS], fila_n[NCH_JUEGO_FILAS];
    static int filas = 0, armado_version = -1, armado_w = -1;
    if (!g_ht_base || !g_nc_en_juego) return;

    AcquireSRWLockShared(&g_nc_candado_cuadro);
    int cambio = g_nc_cuadro.version != c.version || armado_version < 0;
    if (cambio) CopyMemory(&c, &g_nc_cuadro, sizeof(c));
    ReleaseSRWLockShared(&g_nc_candado_cuadro);
    if (c.nl <= 0) return;

    void *obj = NULL, *mgr = NULL;
    if (!ht_memoria_ok(HT_VA(NCH_PINTOR_OBJ), 4, 0) || !(obj = *(void **)HT_VA(NCH_PINTOR_OBJ))) return;
    if (ht_memoria_ok(HT_VA(NCH_MEDIR_OBJ), 4, 0)) mgr = *(void **)HT_VA(NCH_MEDIR_OBJ);
    int W = calc_pantalla(4), H = calc_pantalla(8);
    if (W <= 0 || H <= 0) return;
    int ancho = NCH_JUEGO_ANCHO;
    if (ancho > W / 2) ancho = W / 2;
    int util = ancho - NCH_JUEGO_MARGEN * 2;

    if (cambio || armado_version != c.version || armado_w != W) {   /* se arma sólo cuando cambia */
        int ini[NCH_JUEGO_FILAS], lar[NCH_JUEGO_FILAS];
        int todas_l[NCH_JUEGO_LINEAS * NCH_JUEGO_FILAS], todas_i[NCH_JUEGO_LINEAS * NCH_JUEGO_FILAS], todas_n[NCH_JUEGO_LINEAS * NCH_JUEGO_FILAS];
        int t = 0;
        for (int l = 0; l < c.nl; l++) {
            int k = nc_partir(c.t[l], c.n[l], util, nc_medir_juego, mgr, ini, lar, NCH_JUEGO_FILAS);
            for (int j = 0; j < k; j++) { todas_l[t] = l; todas_i[t] = ini[j]; todas_n[t] = lar[j]; t++; }
        }
        int desde = t > NCH_JUEGO_FILAS ? t - NCH_JUEGO_FILAS : 0;
        filas = 0;
        for (int j = desde; j < t; j++) {
            fila_linea[filas] = todas_l[j]; fila_ini[filas] = todas_i[j]; fila_n[filas] = todas_n[j]; filas++;
        }
        armado_version = c.version; armado_w = W;
    }

    F_PINTAR pintar = (F_PINTAR)HT_VA(NCH_PINTOR);
    int x = W * 985 / 1000 - ancho + NCH_JUEGO_MARGEN;
    int y = H * 80 / 100 - NCH_JUEGO_MARGEN - filas * NCH_JUEGO_ALTO_FILA;
    for (int j = 0; j < filas; j++, y += NCH_JUEGO_ALTO_FILA) {
        char t[NCH_MAX_TEXTO + 1];
        CopyMemory(t, c.t[fila_linea[j]] + fila_ini[j], fila_n[j]);
        t[fila_n[j]] = 0;
        if (!t[0]) continue;
        pintar(obj, x + 1, y + 1, (int)0xFF000000, 0, "%s", t);                     /* sombra */
        pintar(obj, x, y, (int)nc_color_juego(c.color[fila_linea[j]]), 0, "%s", t);
    }
}
