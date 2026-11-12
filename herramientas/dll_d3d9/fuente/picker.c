/* picker.c — el PICKER con BPM, TIME y corazones (07-oct-2026)
 *
 *   anonimo03, mirando el picker del cliente coreano de hoy: *"lograr meter entre esas divisiones de filas
 *   un nuevo renglón de BPM … y el estilo de la textura acomodado · time (tiempo que dura) / bpm ·
 *   cambiamos la notita por corazón"*. Investigación y medidas: documentacion/PICKER_BPM.md.
 *
 *   El exe 2013 no sabe nada de BPM, y las columnas de la lista NO las arma el .rui: las dibuja
 *   `0x5B8EB0` (el Render de cMusicList) en posiciones FIJAS. Así que:
 *
 *     0x40DBE8  la lectura del `music_lt.txt` (el atributo `Bgm`, el último que lee el exe)
 *               -> además leemos `Index`, `BPM` y `BPMCnt` del mismo nodo y los guardamos acá
 *               (los pone en el catálogo taller/importador2013/poner_bpm.py, sacados de cada chart)
 *     0x5B9245  la llamada que escribe la DIFICULTAD de cada fila (5.5, 7.0…)
 *               -> después, el BPM de esa fila, centrado en su columna
 *     bytes     el título 10 px más corto, el corazón 10 px a la izquierda (el dibujo Y el clic),
 *               el artista corrido y de 64 px: las MISMAS medidas con las que herramientas/picker_bpm.py
 *               pintó las rayas en rnr_ui_picker.pak (picker_datos.h)
 *     vtable    el Render de la lista (0x882F3C) -> después, «BPM» y «TIME» en el panel de la izquierda,
 *               de la canción que muestra el panel ([[0x9314EC]+4])
 *
 *   ★ Sin rnr_ui_picker.pak la lista se ve corrida contra las rayas viejas: el pak y la dll van JUNTOS.
 *   ⛔ [picker] activo=0 lo apaga entero (ni engancha). Las posiciones del panel se ajustan con
 *      [picker] info_x / info_y (sin recompilar), por si en otra resolución quedan corridas.
 */
#include "picker_datos.h"

#define PKV(x) (g_pk_base + ((DWORD)(x) - 0x400000))
#define TCK __attribute__((thiscall))

static BYTE *g_pk_base = NULL;
static WORD  g_pk_bpm[65536];            /* el BPM de cada canción (Index), 0 = no tiene */
static BYTE  g_pk_cnt[65536];            /* BPMCnt: cuántas marcas de ritmo (1 = fijo) */
static char *g_pk_noter[65536];          /* ★ (129) el atributo `Noter` de cada canción (NULL = no tiene) */
static WORD  g_pk_min[65536], g_pk_max[65536];   /* ★ (129) `BPMMin`/`BPMMax`: el rango si el ritmo VARÍA (0 = fijo) */
static long  g_pk_leidas = 0;
static volatile BYTE *g_pk_fila = NULL;  /* la fila que se está dibujando (la pone el salto) */
static BYTE *g_pk_cueva = NULL;

/* el panel: desplazamientos desde el borde izquierdo de la LISTA y desde el texto de su 1ª fila */
static int   g_pk_info_x = 0, g_pk_info_y = 0;
static DWORD g_pk_col_valor = 0xFFFFFFFF;    /* blanco, como el título y el género */

typedef const char *(TCK *F_ATRIB)(void *nodo, void *cadena);           /* 0x678160, ret 4 */
typedef int         (TCK *F_LISTA_DIBUJAR)(void *lista, int dx, int dy); /* 0x5B8EB0, ret 8 */
typedef int (__cdecl *F_PINTAR_PK)(void *obj, int x, int y, int color, int estilo, const char *fmt, ...);

static F_ATRIB         g_pk_atrib_real;
static F_LISTA_DIBUJAR g_pk_lista_real;

/* ── un std::string de MSVC 2008, armado a mano para preguntarle al nodo XML ──────────────────────
 *   Medido en el propio lector (0x40D931..): el objeto es de 0x1C: +4 el texto corto (16), +0x14 el
 *   largo, +0x18 la capacidad (15 = texto corto). +0 no lo usa nadie en el find del map. */
typedef struct { DWORD nada; char txt[16]; DWORD largo; DWORD cap; } CADENA_MS;

static const char *pk_atrib(void *nodo, const char *clave)
{
    CADENA_MS c;
    ZeroMemory(&c, sizeof(c));
    lstrcpynA(c.txt, clave, 16);
    c.largo = (DWORD)lstrlenA(c.txt);
    c.cap = 15;
    return g_pk_atrib_real(nodo, &c);
}

static int pk_entero(const char *s)
{
    int n = 0, signo = 1;
    if (!s) return 0;
    while (*s == ' ') s++;
    if (*s == '-') { signo = -1; s++; }
    while (*s >= '0' && *s <= '9') n = n * 10 + (*s++ - '0');
    return n * signo;
}

/* ── 0x40DBE8: el exe lee `Bgm`; nosotros, además, Index/BPM/BPMCnt del mismo nodo ── */
static const char *TCK pk_mi_atrib(void *nodo, void *cadena)
{
    const char *r = g_pk_atrib_real(nodo, cadena);
    const char *i = pk_atrib(nodo, "Index"), *b = pk_atrib(nodo, "BPM");
    /* ★ (129) el noter: su propio atributo (antes iba pegado al género, «Vocaloid | Noter: …», y pisaba el botón) */
    const char *nt = pk_atrib(nodo, "Noter");
    if (i && nt && *nt) {
        int idx = pk_entero(i), n = lstrlenA(nt);
        if (idx >= 0 && idx < 65536 && n < 200 && !g_pk_noter[idx]) {
            char *copia = (char *)HeapAlloc(GetProcessHeap(), 0, n + 1);
            if (copia) { lstrcpyA(copia, nt); g_pk_noter[idx] = copia; }
        }
    }
    if (i && b) {
        int idx = pk_entero(i), bpm = pk_entero(b);
        if (idx >= 0 && idx < 65536 && bpm > 0 && bpm < 10000) {
            int cnt = pk_entero(pk_atrib(nodo, "BPMCnt"));
            g_pk_bpm[idx] = (WORD)bpm;
            g_pk_cnt[idx] = (BYTE)(cnt < 1 ? 1 : cnt > 255 ? 255 : cnt);
            int mn = pk_entero(pk_atrib(nodo, "BPMMin")), mx = pk_entero(pk_atrib(nodo, "BPMMax"));
            if (mn > 0 && mx > mn && mx < 10000) { g_pk_min[idx] = (WORD)mn; g_pk_max[idx] = (WORD)mx; }
            g_pk_leidas++;
        }
    }
    return r;
}

static BYTE *pk_cancion(BYTE *envoltorio)       /* la fila de la lista -> la canción del catálogo */
{
    return envoltorio ? *(BYTE **)envoltorio : NULL;
}

static int pk_ancho_digitos(int n) { return n * 7; }   /* la letra del juego: 7 px por cifra (calculadora.c) */

/* el ancho en px de un texto con la letra del juego: 0x635350 (thiscall sobre [0x931568], ret 8) —
 *   la que usa 0x442790 para recortar los títulos de la lista. */
typedef int (TCK *F_PK_ANCHO)(void *mgr, const char *s, int fuente);
static int pk_ancho_texto(const char *s)
{
    void *mgr = *(void **)PKV(0x931568);
    int w = mgr ? ((F_PK_ANCHO)PKV(0x635350))(mgr, s, 0) : 0;
    return (w > 0 && w < 2000) ? w : lstrlenA(s) * 7;
}

/* ★ (129) `s` cortado con «..» para que entre en `ancho` px (la letra del juego), sin partir una letra UTF-8 */
static void pk_cortar(const char *s, int ancho, char *out, int cap)
{
    lstrcpynA(out, s, cap);
    if (pk_ancho_texto(out) <= ancho) return;
    int n = lstrlenA(out);
    while (n > 0) {
        n--;
        while (n > 0 && ((BYTE)out[n] & 0xC0) == 0x80) n--;      /* al comienzo de una letra */
        if (n + 3 > cap) continue;
        out[n] = '.'; out[n + 1] = '.'; out[n + 2] = 0;
        if (pk_ancho_texto(out) <= ancho) return;
    }
    lstrcpynA(out, "..", cap);
}

/* ── 0x5B9245: la dificultad de la fila; y después, su BPM ── */
static int __cdecl pk_nivel(void *obj, int x, int y, int color, int estilo, const char *fmt, double nivel)
{
    F_PINTAR_PK pintar = (F_PINTAR_PK)PKV(0x63A640);
    int r = pintar(obj, x, y, color, estilo, fmt, nivel);
    BYTE *c = pk_cancion((BYTE *)g_pk_fila);
    if (c && obj) {
        int bpm = g_pk_bpm[*(WORD *)(c + 0x594)];
        if (bpm) {
            char t[8];
            int n = wsprintfA(t, "%d", bpm);
            int lista_x = x - 0x15E;                              /* x = lista + 0x15E (0x5B922B) */
            pintar(obj, lista_x + PK_BPM_CENTRO - pk_ancho_digitos(n) / 2, y, color, estilo, "%s", t);
        }
    }
    return r;
}

/* ═══ ★ LA BARRA DEL VOLUMEN DEL PREVIEW (la del coreano: riel, tira naranja y perilla) ═══════════
 *   El preview lo arranca 0x5BCE10 y lo sube de a poco en 0x5BFC90: cada cuadro pone el volumen
 *   [sel+0x310] (0 -> 1, y a los 28 s baja) con el método +0x1C del sonido (0x5BFD19).
 *   ⇒ En 0x5BFD07 (`fld [esi+0x310]`, lo que se le pasa) se multiplica por NUESTRO factor: la subida y
 *     la bajada de siempre, a la escala que eligió el jugador. Y como al llegar a 1 el juego deja de
 *     llamarlo, al mover la barra se le pone el volumen nosotros (pk_vol_aplicar).
 *   El mouse se lee acá mismo (en el Render): el cursor de Windows llevado a las coordenadas del juego. */
static float g_pk_vol = 1.0f;                   /* 0..1, [picker] volumen=0..100 */
static int   g_pk_vol_x = 237, g_pk_vol_y = 357;   /* el riel, desde el texto de la 1ª fila de la lista */
static BYTE  g_pk_vimg[0x100];                  /* el c2DImage (la clase ocupa 0x40) */
static int   g_pk_vimg_estado = 0;              /* 0 sin cargar · 1 cargada · -1 fallo */
static int   g_pk_arrastre = 0, g_pk_boton_antes = 0;
/* ⛔ la profundidad: 1ª vuelta en 0.5 y NO se veía; se pasó a 0 creyendo que el fondo estaba en 0 — ⛔ FALSO:
 *   medido el 09-oct (top5.c, el volcado de la cola), lo visible del picker va en 0.32 (íconos), 0.9 (fondos) y
 *   0.1 (la banda de arriba), y en 0 no se ve nada. [picker] volumen_z en milésimas, por si acaso. */
static float g_pk_vol_z = 0.1f;    /* ⛔ 09-oct: en 0 ni en 0.05 se ve (top5.c); 0.1 = la de la banda de arriba */

typedef void *(TCK *F_PK_C2D_CREAR)(void *self);
typedef int   (TCK *F_PK_C2D_CARGAR)(void *self, const char *ruta, const char *prefijo);
typedef void  (TCK *F_PK_C2D_RECORTE)(void *self, float x, float y, int u, int v, int w, int h, float z);
typedef void  (TCK *F_PK_C2D_POS)(void *self, int n, int x, int y);
typedef void  (TCK *F_PK_C2D_COLOR)(void *self, int n, DWORD argb);
typedef void  (TCK *F_PK_C2D_TAMANO)(void *self, int n, int ancho, int alto);
typedef void  (TCK *F_PK_C2D_DIBUJAR)(void *self, int n, int banderas);
typedef BYTE *(TCK *F_PK_SONIDO)(void *mgr, DWORD h);
typedef void  (TCK *F_PK_SON_VOL)(void *son, float v);

enum { PKV_RIEL, PKV_TIRA, PKV_PERILLA, PKV_TOTAL };

static void pk_vol_cargar(void)
{
    static const int cortes[PKV_TOTAL][4] = { { PK_VOL_RIEL }, { PK_VOL_TIRA }, { PK_VOL_PERILLA } };
    ((F_PK_C2D_CREAR)PKV(0x64E560))(g_pk_vimg);
    if (!((F_PK_C2D_CARGAR)PKV(0x64E1E0))(g_pk_vimg, PK_VOL_TGA, NULL)) {
        g_pk_vimg_estado = -1;
        apuntar("  [picker] ⛔ no encontré la barra del volumen (¿falta rnr_ui_picker.pak?): no la dibujo");
        return;
    }
    for (int i = 0; i < PKV_TOTAL; i++)
        ((F_PK_C2D_RECORTE)PKV(0x64EC40))(g_pk_vimg, 0, 0, cortes[i][0], cortes[i][1], cortes[i][2], cortes[i][3], g_pk_vol_z);
    int n = (int)((*(DWORD *)(g_pk_vimg + 0x1c) - *(DWORD *)(g_pk_vimg + 0x18)) / 0x50);
    g_pk_vimg_estado = (n == PKV_TOTAL) ? 1 : -1;
    apuntar("  [picker] barra del volumen: %d recortes%s · volumen %d %%", n, n == PKV_TOTAL ? "" : "  ⛔ NO DIBUJO",
            (int)(g_pk_vol * 100 + 0.5f));
}

static void pk_vol_pieza(int n, int x, int y, int w, int h)
{
    if (w >= 0) ((F_PK_C2D_TAMANO)PKV(0x64DB90))(g_pk_vimg, n, w, h);
    ((F_PK_C2D_POS)PKV(0x64D990))(g_pk_vimg, n, x, y);
    ((F_PK_C2D_COLOR)PKV(0x64E710))(g_pk_vimg, n, 0xFFFFFFFF);
    ((F_PK_C2D_DIBUJAR)PKV(0x64EE40))(g_pk_vimg, n, 0);
}

/* el volumen, YA, al preview que está sonando (el juego sólo lo pone mientras sube o baja) */
static void pk_vol_aplicar(BYTE *sel)
{
    DWORD h = *(DWORD *)(sel + 8);
    void *mgr = *(void **)PKV(0x931578);
    if (!h || !mgr || !*(BYTE *)(sel + 0x314)) return;
    BYTE *s = ((F_PK_SONIDO)PKV(0x413000))(mgr, h);
    if (!s) return;
    void *son = *(void **)(s + 0x1C);
    if (!son) return;
    F_PK_SON_VOL f = (F_PK_SON_VOL)(*(void ***)son)[0x1C / 4];
    f(son, *(float *)(sel + 0x310) * g_pk_vol);
}

/* [picker] volumen=NN en d3d9_proxy.ini, sin reescribir lo demás (el escritor de herramienta.c) */
static void pk_vol_guardar(void)
{
    if (!g_ht_ini[0]) return;
    EnterCriticalSection(&g_ht_cs);
    HT_BUF x = { NULL, 0, 0 };
    HANDLE h = CreateFileA(g_ht_ini, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL);
    if (h != INVALID_HANDLE_VALUE) {
        DWORD tam = GetFileSize(h, NULL), leidos = 0;
        if (tam != INVALID_FILE_SIZE && tam < (1u << 20) && ht_buf_reservar(&x, (int)tam + 1))
            if (ReadFile(h, x.b, tam, &leidos, NULL)) x.n = (int)leidos;
        CloseHandle(h);
    }
    if (ht_buf_reservar(&x, 64)) {
        const char *eol = "\r\n";
        for (int i = 0; i + 1 < x.n; i++) if (x.b[i] == '\n') { eol = (i > 0 && x.b[i - 1] == '\r') ? "\r\n" : "\n"; break; }
        char v[16];
        wsprintfA(v, "%d", (int)(g_pk_vol * 100 + 0.5f));
        ht_buf_poner_sec(&x, "[picker]", "volumen", v, eol);
        h = CreateFileA(g_ht_ini, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
        if (h != INVALID_HANDLE_VALUE) {
            DWORD esc = 0;
            WriteFile(h, x.b, (DWORD)x.n, &esc, NULL);
            CloseHandle(h);
        }
    }
    if (x.b) HeapFree(GetProcessHeap(), 0, x.b);
    LeaveCriticalSection(&g_ht_cs);
}

/* el cursor de Windows, en las coordenadas del juego (el backbuffer); 0 si no se puede */
static int pk_raton(int *mx, int *my)
{
    POINT p;
    RECT r;
    if (!g_ventana || !GetCursorPos(&p) || !ScreenToClient(g_ventana, &p) || !GetClientRect(g_ventana, &r)) return 0;
    if (r.right <= 0 || r.bottom <= 0) return 0;
    *mx = g_ancho ? (int)((LONGLONG)p.x * (LONGLONG)g_ancho / r.right) : p.x;
    *my = g_alto ? (int)((LONGLONG)p.y * (LONGLONG)g_alto / r.bottom) : p.y;
    return 1;
}

static void pk_vol_dibujar(BYTE *sel, int lx, int ly)
{
    if (g_pk_vimg_estado == 0) pk_vol_cargar();
    if (g_pk_vimg_estado != 1) return;
    static const int riel[4] = { PK_VOL_RIEL }, tira[4] = { PK_VOL_TIRA }, per[4] = { PK_VOL_PERILLA };
    int x = lx + g_pk_vol_x, y = ly + g_pk_vol_y;
    int w = riel[2], h = riel[3];
    /* el mouse: apretar ARRIBA de la barra (con un margen) la agarra; mientras siga apretado, la mueve */
    int mx, my, boton = (GetAsyncKeyState(VK_LBUTTON) & 0x8000) != 0;
    if (GetForegroundWindow() != g_ventana) boton = 0;
    if (pk_raton(&mx, &my)) {
        if (boton && !g_pk_boton_antes && mx >= x - 4 && mx <= x + w + 4 && my >= y - 5 && my <= y + h + 5)
            g_pk_arrastre = 1;
        if (g_pk_arrastre && boton) {
            float v = (float)(mx - x) / (float)w;
            v = v < 0 ? 0 : v > 1 ? 1 : v;
            if (v != g_pk_vol) { g_pk_vol = v; pk_vol_aplicar(sel); }
        }
    }
    if (g_pk_arrastre && !boton) { g_pk_arrastre = 0; pk_vol_guardar(); }
    g_pk_boton_antes = boton;

    int lleno = (int)(g_pk_vol * w + 0.5f);
    pk_vol_pieza(PKV_RIEL, x, y, -1, 0);
    if (lleno > 0) pk_vol_pieza(PKV_TIRA, x, y + (h - tira[3]) / 2, lleno, tira[3]);
    pk_vol_pieza(PKV_PERILLA, x + lleno - per[2] / 2, y + (h - per[3]) / 2, -1, 0);
}

/* ★ TOP 5 RANK (top5.c, incluido DESPUÉS): el botón y la ventana se dibujan desde acá */
static int  top5_abierto(void);
static int  top5_tapa_lista(void);
static void top5_cuadro(BYTE *c, int dx, int dy);
static void top5_diag_fase(int fase);

/* ── el Render de la lista; y después, «BPM» y «TIME» en el panel de la izquierda ── */
static int TCK pk_lista(void *lista, int dx, int dy)
{
    BYTE *sel = *(BYTE **)PKV(0x9314EC);
    int del_picker = sel && *(void **)(sel + 0x304) == lista;     /* sólo LA lista del picker */
    if (del_picker) top5_diag_fase(1);
    /* ★ con TOP 5 RANK abierto y [top5] ocultar_lista=1 la lista NO se dibuja (por si sus títulos asomaran por
     *   encima de la ventana). De fábrica SÍ se dibuja: la ventana va adelante (z 0.1), como en el coreano.
     *   (0x5B8EB0 no devuelve nada que se use: el eax de su salida es basura) */
    if (del_picker && top5_tapa_lista()) {
        top5_cuadro(pk_cancion(*(BYTE **)(sel + 4)), dx, dy);
        return 0;
    }
    int r = g_pk_lista_real(lista, dx, dy);
    if (!del_picker) return r;
    static int dicho = 0;
    if (!dicho++) apuntar("  [picker] la 1ª vez que se abre: %ld canciones trajeron BPM del catálogo", g_pk_leidas);
    /* la lista: x = [+0x10]+dx, y del texto de su 1ª fila = [+0x14]+dy+1 (0x5B8F12 / 0x5B8F21) */
    int lx = *(int *)((BYTE *)lista + 0x10) + dx;
    int ly = *(int *)((BYTE *)lista + 0x14) + dy + 1;
    if (g_pk_vol_x != -9999) pk_vol_dibujar(sel, lx, ly);
    BYTE *c = pk_cancion(*(BYTE **)(sel + 4));                    /* la canción del panel (0x5BCFF1) */
    top5_cuadro(c, dx, dy);                                       /* el botón «TOP 5 RANK» */
    void *obj = *(void **)PKV(0x93149C);
    /* ⛔ con TOP 5 RANK abierto, «Duracion» y «BPM» NO: se escriben DESPUÉS de la ventana y quedaban encima de ella
     *   (anonimo03, 10-oct: «bpm duración se está sobreponiendo al cartel»); los de la lista y «Puesto» sí quedan tapados */
    if (!c || !obj || top5_abierto()) return r;
    F_PINTAR_PK pintar = (F_PINTAR_PK)PKV(0x63A640);
    /* ★ 4ª vuelta (anonimo03, 09-oct, con su paint: «el orden que quiero · ya no quiero la cápsula»): «Duracion mm:ss»
     *   y «BPM nnn» EN COLUMNA debajo de «Puesto N (…)» (que lo escribe el exe), alineados a la izquierda con él;
     *   BPM en la fila del título. (La 3ª vuelta los centraba en la píldora / los alineaba a la derecha.)
     *   [picker] info_x / info_y los corren todos juntos (de fábrica 0). */
    int x = lx + g_pk_info_x, y = ly + g_pk_info_y;
    char t1[32];
    int bpm = g_pk_bpm[*(WORD *)(c + 0x594)];
    if (bpm) {
        /* ★ (129) anonimo03: «cuando hay 50-600 es una música con bpm variable, es correcto que salga "50-600"» */
        WORD mn = g_pk_min[*(WORD *)(c + 0x594)], mx = g_pk_max[*(WORD *)(c + 0x594)];
        if (mn && mx > mn) wsprintfA(t1, "BPM %d-%d", mn, mx);
        else wsprintfA(t1, "BPM %d", bpm);
        pintar(obj, x + PK_INFO_COL_X, y + PK_INFO_BPM_Y, (int)g_pk_col_valor, 0, "%s", t1);
    }
    DWORD t = *(DWORD *)(c + 0x588);                              /* `Time`, en 1/60 s (+0x588) */
    if (t > 0 && t < 60u * 60 * 60) {
        DWORD s = t / 60;
        /* ⛔ SIN tilde: con Windows en coreano (la PC de anonimo03) la «ó» sale «?» (09-oct: «Duraci? 02:22»):
         *   el pintor la convierte con la página de códigos del sistema */
        wsprintfA(t1, "Duracion %02u:%02u", s / 60, s % 60);
        pintar(obj, x + PK_INFO_COL_X, y + PK_INFO_DUR_Y, (int)g_pk_col_valor, 0, "%s", t1);
    }
    /* ★ (129) «Noter : …» (el rótulo está pintado en host01): el de la canción, o «R2Beat» si no tiene (anonimo03: «sino
     *   hay noter, solo poner R2beat como placeholder»). Cortado con «..» para no pisar el botón TOP 5 RANK; el corte
     *   se guarda por canción (medir cada cuadro serían ~30 llamadas a GDI). */
    {
        static int ultima = -1;
        static char cortado[256];
        int idx = *(WORD *)(c + 0x594);
        if (idx != ultima) {
            pk_cortar(g_pk_noter[idx] ? g_pk_noter[idx] : "R2Beat", PK_NOTER_W, cortado, sizeof(cortado));
            ultima = idx;
        }
        pintar(obj, x + PK_NOTER_X, y + PK_NOTER_Y, (int)g_pk_col_valor, 0, "%s", cortado);
    }
    return r;
}

/* ═══ ★ «BPM : nnn» EN LA SALA (08-oct, anonimo03: «como la 2ª captura, con la misma fuente»; a la derecha, su maqueta) ═
 *   El panel de la sala («Música» / «Pista» / Rcoin / EXP) lo dibuja 0x58F360: el corte 9 de gr_1.spr en
 *   x = ancho − 0xD2 (esi), y 0xB4 (0x58F3CA). Cuando hay canción de verdad (no «aleatoria» ni los dibujos de
 *   los modos) pone su portada y DESPUÉS sus estrellas con 0x413980 — en dos sitios, anfitrión (0x58F4F3) e
 *   invitado (0x58F643), los dos con ebp = la canción del catálogo (la misma estructura que la del picker:
 *   +0x574 el nivel, +0x594 el Index).
 *   ⇒ Esas dos llamadas pasan por un salto que guarda ebp y siguen en pk_sala_estrellas: las estrellas de
 *     siempre y, encima, «BPM : nnn» armado con las piezas de sala_bpm.tga (la letra de «Música»).
 *   Las piezas: todos los BORDES primero y todos los RELLENOS después (si no, el borde blanco de una cifra le
 *   tapa el relleno a la de al lado). Cada cifra tiene sus propios recortes POR POSICIÓN (4 lugares × 10
 *   cifras): «200» dibuja el «0» dos veces, y así no depende de si la cola guarda la posición o el recorte.
 *   [picker] sala_bpm=0 la apaga · sala_x / sala_y la corren (px). */
static volatile BYTE *g_pk_sala_cancion = NULL;    /* la pone el salto: ebp en la llamada a las estrellas */
static BYTE  g_pk_simg[0x100];                      /* el c2DImage de sala_bpm.tga */
static int   g_pk_simg_estado = 0;                  /* 0 sin cargar · 1 cargada · -1 fallo */
static int   g_pk_sala_x = 0, g_pk_sala_y = 0;
static float g_pk_sala_z = 0.32f;                  /* por si no se puede leer la de la portada */
#define PK_SALA_LUGARES 4                           /* hasta 4 cifras (BPM 1..9999) */
#define PK_SALA_ESTRELLAS_Y 0x10B                   /* la y de las estrellas (0x58F4E4 / 0x58F63A) ... */
#define PK_SALA_PANEL_Y     0xB4                    /* ... y la del panel (0x58F3C4): la guarda las controla */
#define PK_SALA_ESTRELLAS_X 0x1C                    /* las estrellas van en panel + 0x1C (0x58F4E9 / 0x58F63F) */

typedef void (TCK *F_PK_ESTRELLAS)(void *self, int x, int y, int nivel, int a, int b, int c);   /* ret 0x18 */

/* el recorte de cada cosa: la palabra (borde 0, relleno 1) y la cifra d en el lugar l (borde/relleno) */
static int pk_sala_corte(int pieza, int lugar, int relleno)
{
    if (pieza == PK_SALA_PALABRA) return relleno;
    return 2 + (lugar * 10 + pieza) * 2 + relleno;
}

static void pk_sala_cargar(void)
{
    ((F_PK_C2D_CREAR)PKV(0x64E560))(g_pk_simg);
    if (!((F_PK_C2D_CARGAR)PKV(0x64E1E0))(g_pk_simg, PK_SALA_TGA, NULL)) {
        g_pk_simg_estado = -1;
        apuntar("  [picker] ⛔ no encontré sala_bpm.tga (¿falta rnr_ui_selector.pak?): la sala va sin BPM");
        return;
    }
    F_PK_C2D_RECORTE recorte = (F_PK_C2D_RECORTE)PKV(0x64EC40);
    const short *w = PK_SALA_PIEZA[PK_SALA_PALABRA];
    recorte(g_pk_simg, 0, 0, w[0], w[1], w[3], w[4], 0.0f);           /* 0: la palabra, borde */
    recorte(g_pk_simg, 0, 0, w[2], w[1], w[3], w[4], 0.0f);           /* 1: la palabra, relleno */
    for (int l = 0; l < PK_SALA_LUGARES; l++)
        for (int d = 0; d < 10; d++) {
            const short *p = PK_SALA_PIEZA[d];
            recorte(g_pk_simg, 0, 0, p[0], p[1], p[3], p[4], 0.0f);
            recorte(g_pk_simg, 0, 0, p[2], p[1], p[3], p[4], 0.0f);
        }
    int n = (int)((*(DWORD *)(g_pk_simg + 0x1c) - *(DWORD *)(g_pk_simg + 0x18)) / 0x50);
    int esperados = 2 + PK_SALA_LUGARES * 20;
    g_pk_simg_estado = (n == esperados) ? 1 : -1;
    apuntar("  [picker] sala: %d recortes de «BPM : nnn»%s", n, n == esperados ? "" : "  ⛔ NO DIBUJO");
}

static void pk_sala_bpm(int px, int py, int bpm, float z)
{
    if (g_pk_simg_estado == 0) pk_sala_cargar();
    if (g_pk_simg_estado != 1 || bpm <= 0 || bpm > 9999) return;
    int cif[PK_SALA_LUGARES], n = 0;
    char t[8];
    wsprintfA(t, "%d", bpm);
    for (; t[n] && n < PK_SALA_LUGARES; n++) cif[n] = t[n] - '0';
    /* las plumas: la palabra en 0, cada cifra donde terminó la anterior (la cuenta de picker_bpm.sala_armar) */
    int pluma[1 + PK_SALA_LUGARES], pieza[1 + PK_SALA_LUGARES], k = 0, p = 0;
    pieza[k] = PK_SALA_PALABRA; pluma[k++] = 0; p = PK_SALA_PIEZA[PK_SALA_PALABRA][7];
    for (int i = 0; i < n; i++) { pieza[k] = cif[i]; pluma[k++] = p; p += PK_SALA_PIEZA[cif[i]][7]; }
    int der = pluma[k - 1] + PK_SALA_PIEZA[pieza[k - 1]][9];
    int x0 = px + PK_SALA_FIN - der + g_pk_sala_x;            /* alineado a la DERECHA (la maqueta de anonimo03) */
    int y0 = py + PK_SALA_BASE + g_pk_sala_y;
    for (int relleno = 0; relleno < 2; relleno++)
        for (int i = 0; i < k; i++) {
            const short *q = PK_SALA_PIEZA[pieza[i]];
            int c = pk_sala_corte(pieza[i], i - 1, relleno);
            *(float *)(*(BYTE **)(g_pk_simg + 0x18) + c * 0x50 + 0x10) = z;   /* la z del recorte */
            ((F_PK_C2D_POS)PKV(0x64D990))(g_pk_simg, c, x0 + pluma[i] + q[5], y0 + q[6]);
            ((F_PK_C2D_COLOR)PKV(0x64E710))(g_pk_simg, c, 0xFFFFFFFF);
            ((F_PK_C2D_DIBUJAR)PKV(0x64EE40))(g_pk_simg, c, 0);
        }
}

static void TCK pk_sala_estrellas(void *self, int x, int y, int nivel, int a, int b, int c)
{
    ((F_PK_ESTRELLAS)PKV(0x413980))(self, x, y, nivel, a, b, c);
    BYTE *cancion = (BYTE *)g_pk_sala_cancion;
    g_pk_sala_cancion = NULL;
    if (!cancion) return;
    static int dicho = 0;
    int idx = *(WORD *)(cancion + 0x594), bpm = g_pk_bpm[idx];
    if (!dicho++) apuntar("  [picker] sala: la 1ª canción en el panel es la %d (BPM %d, nivel %d)", idx, bpm, nivel);
    /* ⛔ la PROFUNDIDAD: en z 0 (la del picker) NO se veía. Medido el 08-oct con la entrada de la portada, que sí
     *   se ve: está en z 0,32 (y la nuestra en 0, todo lo demás igual: posición, tamaño, uv, color). ⇒ se usa la
     *   z de la portada de esta misma canción, leída en cada cuadro ([portada+0x18] = sus recortes, de 0x50; la z
     *   en +0x10); si no se puede leer, [picker] sala_z (milésimas, de fábrica 320). */
    float z = g_pk_sala_z;
    BYTE *portada = *(BYTE **)cancion;
    if (portada) {
        BYTE *v0 = *(BYTE **)(portada + 0x18), *v1 = *(BYTE **)(portada + 0x1C);
        if (v0 && v1 >= v0 + 2 * 0x50) {
            float zp = *(float *)(v0 + 0x50 + 0x10);
            if (zp >= 0.0f && zp <= 1.0f) z = zp;
        }
    }
    static int dicho_z = 0;
    if (!dicho_z++) apuntar("  [picker] sala: dibujo en z %d/1000 (la de la portada)", (int)(z * 1000 + 0.5f));
    if (bpm) pk_sala_bpm(x - PK_SALA_ESTRELLAS_X, y - PK_SALA_ESTRELLAS_Y + PK_SALA_PANEL_Y, bpm, z);
}

/* ═══ ★ «ORDEN POR BPM»: la 7ª fila del menú de orden (2ª vuelta, anonimo03 07-oct) ═══════════════════════
 *   El menú lo dibuja 0x5BA170 y lo maneja 0x5BDF70; elegir una fila llama 0x5BDEB0(0, fila, 1), que guarda
 *   [sel+0x31C] y ordena con 0x5BD7C0(modo, &[sel+0x8C], 1) — 6 modos por tabla de saltos (0x5BDB40).
 *     0x5BA208  cuántas filas dibuja el anfitrión: 6 -> 7 (el invitado sigue en 5)
 *     0x5BDFA4  cuántas filas atiende el mouse: `add edx,5` (5 + soy anfitrión) -> 5 + 2·(soy anfitrión)
 *     0x5BA1B9  el texto de ARRIBA (el modo elegido): con el modo 6 el exe pediría el corte 19 (= 7+2·6, que
 *               es de la búsqueda) -> el nuestro (PK_MENU_CORTE_N)
 *     0x5BA29C  el texto de cada FILA: la 7ª pediría 19/20 -> los nuestros (normal / encendido)
 *     0x5BD7C0  el ordenador: el modo 6 lo hacemos acá (por BPM; 1er clic de lento a rápido, el 2º al revés)
 *   El fondo de 7 filas y los dos textos nuevos están en music_select_host04 de rnr_ui_selector.pak. */
typedef void (TCK *F_PK_CORTE)(void *spr, int x, int y, int corte, int banderas);   /* 0x683FB0, ret 0x10 */
typedef void (TCK *F_PK_ORDENAR)(BYTE *sel, int modo, BYTE *vec, int clic);        /* 0x5BD7C0, ret 0xC  */
static F_PK_ORDENAR g_pk_ordenar_real;

static void TCK pk_menu_cabecera(void *spr, int x, int y, int corte, int banderas)
{
    BYTE *sel = *(BYTE **)PKV(0x9314EC);
    if (sel && *(int *)(sel + 0x31C) == 6 && corte == 7 + 2 * 6) corte = PK_MENU_CORTE_N;
    ((F_PK_CORTE)PKV(0x683FB0))(spr, x, y, corte, banderas);
}

static void TCK pk_menu_fila(void *spr, int x, int y, int corte, int banderas)
{
    if (corte == 7 + 2 * 6) corte = PK_MENU_CORTE_N;          /* sólo la 7ª fila pide 19/20 en este lazo */
    else if (corte == 8 + 2 * 6) corte = PK_MENU_CORTE_E;
    ((F_PK_CORTE)PKV(0x683FB0))(spr, x, y, corte, banderas);
}

static int pk_bpm_de(BYTE *envoltorio)
{
    BYTE *c = envoltorio ? *(BYTE **)envoltorio : NULL;
    return c ? g_pk_bpm[*(WORD *)(c + 0x594)] : 0;
}

/* orden ESTABLE (a igual BPM queda el orden que traía) — una mezcla con un arreglo de paso */
static void pk_mezclar(BYTE **a, BYTE **tmp, int n, int sube)
{
    if (n < 2) return;
    int m = n / 2;
    pk_mezclar(a, tmp, m, sube);
    pk_mezclar(a + m, tmp, n - m, sube);
    int i = 0, j = m, k = 0;
    while (i < m && j < n) {
        int bi = pk_bpm_de(a[i]), bj = pk_bpm_de(a[j]);
        if (sube ? (bj < bi) : (bj > bi)) tmp[k++] = a[j++];
        else tmp[k++] = a[i++];
    }
    while (i < m) tmp[k++] = a[i++];
    while (j < n) tmp[k++] = a[j++];
    CopyMemory(a, tmp, n * sizeof(BYTE *));
}

static void TCK pk_ordenar(BYTE *sel, int modo, BYTE *vec, int clic)
{
    if (modo != 6) { g_pk_ordenar_real(sel, modo, vec, clic); return; }
    /* lo mismo que hace el exe con [+0x3C] (el modo) y [+0x40] (el sentido) al entrar (0x5BD7D2..0x5BD7ED) */
    if (*(int *)(sel + 0x3C) == 6) { if (clic) sel[0x40] = (BYTE)(sel[0x40] == 0); }
    else sel[0x40] = 1;
    *(int *)(sel + 0x3C) = 6;
    BYTE **ini = *(BYTE ***)(vec + 0xC), **fin = *(BYTE ***)(vec + 0x10);    /* (el vector: 0x446C30/60) */
    int n = (ini && fin > ini) ? (int)(fin - ini) : 0;
    if (n < 2 || n > 100000) return;
    BYTE **tmp = (BYTE **)HeapAlloc(GetProcessHeap(), 0, n * sizeof(BYTE *));
    if (!tmp) return;
    pk_mezclar(ini, tmp, n, sel[0x40] != 0);
    HeapFree(GetProcessHeap(), 0, tmp);
}

/* ── los bytes del exe, con lo que esperamos encontrar ── */
typedef struct { DWORD va; BYTE esp[6]; BYTE nue[6]; int n; const char *que; } PK_PARCHE;

static int pk_iguales(DWORD va, const BYTE *b, int n)
{
    BYTE *s = PKV(va);
    for (int i = 0; i < n; i++) if (s[i] != b[i]) return 0;
    return 1;
}

static int pk_escribir(DWORD va, const void *b, int n)
{
    BYTE *s = PKV(va);
    DWORD viejo = 0;
    if (!VirtualProtect(s, n, PAGE_EXECUTE_READWRITE, &viejo)) return 0;
    CopyMemory(s, b, n);
    VirtualProtect(s, n, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), s, n);
    return 1;
}

static int pk_rel(DWORD sitio_va, DWORD destino_va)               /* el rel32 de un E8 en `sitio` */
{
    return (int)(destino_va - ((DWORD)PKV(sitio_va) + 5));
}

/* «BPM : nnn» en la sala: aparte del resto (si su guarda falla, el picker sigue igual). Usa la tabla del BPM
 *   que llena el lector del catálogo, así que sólo se engancha si el picker quedó enganchado. */
typedef struct { DWORD va; BYTE esp[6]; int n; const char *que; } PK_GUARDA;

static void pk_sala_iniciar(const char *ini)
{
    if (!GetPrivateProfileIntA("picker", "sala_bpm", 1, ini)) {
        apuntar("  [picker] sala sin BPM ([picker] sala_bpm=0)");
        return;
    }
    g_pk_sala_x = GetPrivateProfileIntA("picker", "sala_x", 0, ini);
    g_pk_sala_y = GetPrivateProfileIntA("picker", "sala_y", 0, ini);
    g_pk_sala_z = (float)GetPrivateProfileIntA("picker", "sala_z", 320, ini) / 1000.0f;
    static const PK_GUARDA G[] = {
        { 0x58F3C4, { 0x68, 0xB4, 0, 0, 0 }, 5, "y del panel de la sala" },
        { 0x58F4E4, { 0x68, 0x0B, 0x01, 0, 0 }, 5, "y de las estrellas (anfitrión)" },
        { 0x58F4E9, { 0x8D, 0x4E, 0x1C }, 3, "x de las estrellas (anfitrión)" },
        { 0x58F63A, { 0x68, 0x0B, 0x01, 0, 0 }, 5, "y de las estrellas (invitado)" },
        { 0x58F63F, { 0x8D, 0x46, 0x1C }, 3, "x de las estrellas (invitado)" },
        { 0x58F474, { 0x8B, 0xE8 }, 2, "ebp = la canción (anfitrión)" },
        { 0x58F5C4, { 0x8B, 0xE8 }, 2, "ebp = la canción (invitado)" },
    };
    for (int i = 0; i < (int)(sizeof(G) / sizeof(G[0])); i++)
        if (!pk_iguales(G[i].va, G[i].esp, G[i].n)) {
            apuntar("  [picker] ⛔ sala: %s (0x%08X) no tiene los bytes esperados: la sala va sin BPM", G[i].que, G[i].va);
            return;
        }
    static const DWORD sitios[2] = { 0x58F4F3, 0x58F643 };          /* call 0x413980 (las estrellas) */
    for (int i = 0; i < 2; i++) {
        BYTE e[5] = { 0xE8 };
        *(int *)(e + 1) = pk_rel(sitios[i], (DWORD)PKV(0x413980));
        if (!pk_iguales(sitios[i], e, 5)) {
            apuntar("  [picker] ⛔ sala: la llamada a las estrellas (0x%08X) no es la esperada: la sala va sin BPM", sitios[i]);
            return;
        }
    }
    /* el salto: mov [g_pk_sala_cancion],ebp · jmp pk_sala_estrellas (la pila y ecx, intactos) */
    BYTE *ks = g_pk_cueva + 112;
    ks[0] = 0x89; ks[1] = 0x2D; *(DWORD *)(ks + 2) = (DWORD)&g_pk_sala_cancion;
    ks[6] = 0xE9; *(int *)(ks + 7) = (int)((DWORD)pk_sala_estrellas - (DWORD)(ks + 11));
    int ok = 1;
    for (int i = 0; i < 2; i++) {
        BYTE n[5] = { 0xE8 };
        *(int *)(n + 1) = pk_rel(sitios[i], (DWORD)ks);
        ok &= pk_escribir(sitios[i], n, 5);
    }
    apuntar(ok ? "  [picker] sala: «BPM : nnn» junto a «Música» (corrido %d,%d)"
               : "  [picker] ⛔ sala: VirtualProtect falló a mitad", g_pk_sala_x, g_pk_sala_y);
}

static void picker_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("picker", "activo", 1, ini)) {
        apuntar("  [picker] apagado ([picker] activo=0)");
        return;
    }
    g_pk_base = (BYTE *)GetModuleHandleA(NULL);
    g_pk_info_x = GetPrivateProfileIntA("picker", "info_x", 0, ini);     /* correcciones finas, de fábrica 0 */
    g_pk_info_y = GetPrivateProfileIntA("picker", "info_y", 0, ini);
    g_pk_vol_x = GetPrivateProfileIntA("picker", "volumen_x", 237, ini);   /* -9999 = sin barra */
    g_pk_vol_y = GetPrivateProfileIntA("picker", "volumen_y", 357, ini);
    g_pk_vol_z = (float)GetPrivateProfileIntA("picker", "volumen_z", 100, ini) / 1000.0f;
    int vol = GetPrivateProfileIntA("picker", "volumen", 100, ini);
    g_pk_vol = (float)(vol < 0 ? 0 : vol > 100 ? 100 : vol) / 100.0f;

    const BYTE C = (BYTE)PK_CORRE;
    PK_PARCHE P[] = {
        /* el TÍTULO, 10 px más corto en sus tres casos (sin «New», con «New», con «Event/Hot») */
        { 0x5B90B8, { 0xB8, 0xA5, 0, 0, 0 }, { 0xB8, (BYTE)(0xA5 - C), 0, 0, 0 }, 5, "ancho del título" },
        { 0x5B90EB, { 0x8D, 0x45, 0x44 }, { 0x8D, 0x45, (BYTE)(0x44 - C) }, 3, "ancho del título (2)" },
        { 0x5B9111, { 0x8D, 0x45, 0x44 }, { 0x8D, 0x45, (BYTE)(0x44 - C) }, 3, "ancho del título (4)" },
        { 0x5B912F, { 0xB8, 0x85, 0, 0, 0 }, { 0xB8, (BYTE)(0x85 - C), 0, 0, 0 }, 5, "ancho del título (New)" },
        { 0x5B9134, { 0x8D, 0x68, 0xB4 }, { 0x8D, 0x68, (BYTE)(0xB4 + C) }, 3, "x del título (New)" },
        /* el CORAZÓN: el dibujo (preferida / no) y el clic que lo cambia (0x5B8C90) */
        { 0x5B908B, { 0x8D, 0x87, 0xC3, 0, 0, 0 }, { 0x8D, 0x87, PK_CORAZON, 0, 0, 0 }, 6, "x del corazón" },
        { 0x5B909A, { 0x8D, 0x97, 0xC3, 0, 0, 0 }, { 0x8D, 0x97, PK_CORAZON, 0, 0, 0 }, 6, "x del corazón (2)" },
        { 0x5B8DEC, { 0x8D, 0x95, 0xC5, 0, 0, 0 }, { 0x8D, 0x95, (BYTE)(0xC5 - C), 0, 0, 0 }, 6, "clic del corazón (desde)" },
        { 0x5B8DF6, { 0x8D, 0x95, 0xD9, 0, 0, 0 }, { 0x8D, 0x95, (BYTE)(0xD9 - C), 0, 0, 0 }, 6, "clic del corazón (hasta)" },
        /* el ARTISTA */
        { 0x5B91C5, { 0x8D, 0x97, 0xDD, 0, 0, 0 }, { 0x8D, 0x97, PK_ARTISTA, 0, 0, 0 }, 6, "x del artista" },
        { 0x5B918A, { 0x6A, 0x50 }, { 0x6A, PK_ARTISTA_W }, 2, "ancho del artista" },
        /* «Puesto N (…)» y sus partes (0x5BC860): el juego los escribe en NEGRO; con el cuadro oscuro del
         * coreano no se verían -> blanco (los 6 `push 0xFF000000` de esa función) */
        { 0x5BC9E5, { 0x68, 0, 0, 0, 0xFF }, { 0x68, 0xFF, 0xFF, 0xFF, 0xFF }, 5, "color del puesto (1)" },
        { 0x5BCA3C, { 0x68, 0, 0, 0, 0xFF }, { 0x68, 0xFF, 0xFF, 0xFF, 0xFF }, 5, "color del puesto (2)" },
        { 0x5BCA81, { 0x68, 0, 0, 0, 0xFF }, { 0x68, 0xFF, 0xFF, 0xFF, 0xFF }, 5, "color del puesto (3)" },
        { 0x5BCAEF, { 0x68, 0, 0, 0, 0xFF }, { 0x68, 0xFF, 0xFF, 0xFF, 0xFF }, 5, "color del puesto (4)" },
        { 0x5BCB65, { 0x68, 0, 0, 0, 0xFF }, { 0x68, 0xFF, 0xFF, 0xFF, 0xFF }, 5, "color del puesto (5)" },
        { 0x5BCB9B, { 0x68, 0, 0, 0, 0xFF }, { 0x68, 0xFF, 0xFF, 0xFF, 0xFF }, 5, "color del puesto (6)" },
        /* ★ y su x (anonimo03, 09-oct: «los 3 un poquito más a la izquierda»): panel + 0xEC / + 0xFA en 8 sitios de
         * 0x5BC860 (el texto, el número y las flechitas); «Duracion» y «BPM» (PK_INFO_COL_X) van con él */
        { 0x5BC9F1, { 0x05, 0xEC, 0, 0, 0 }, { 0x05, (BYTE)(0xEC - PK_PUESTO_CORRE), 0, 0, 0 }, 5, "x del puesto (1)" },
        { 0x5BCA48, { 0x05, 0xEC, 0, 0, 0 }, { 0x05, (BYTE)(0xEC - PK_PUESTO_CORRE), 0, 0, 0 }, 5, "x del puesto (2)" },
        { 0x5BCA94, { 0x84, 0x3A, 0xEC, 0, 0, 0 }, { 0x84, 0x3A, (BYTE)(0xEC - PK_PUESTO_CORRE), 0, 0, 0 }, 6, "x del puesto (3)" },
        { 0x5BCABF, { 0x8C, 0x38, 0xEC, 0, 0, 0 }, { 0x8C, 0x38, (BYTE)(0xEC - PK_PUESTO_CORRE), 0, 0, 0 }, 6, "x del puesto (4)" },
        { 0x5BCB00, { 0x94, 0x39, 0xFA, 0, 0, 0 }, { 0x94, 0x39, (BYTE)(0xFA - PK_PUESTO_CORRE), 0, 0, 0 }, 6, "x del puesto (5)" },
        { 0x5BCB32, { 0x84, 0x3A, 0xEC, 0, 0, 0 }, { 0x84, 0x3A, (BYTE)(0xEC - PK_PUESTO_CORRE), 0, 0, 0 }, 6, "x del puesto (6)" },
        { 0x5BCB78, { 0x84, 0x3A, 0xFA, 0, 0, 0 }, { 0x84, 0x3A, (BYTE)(0xFA - PK_PUESTO_CORRE), 0, 0, 0 }, 6, "x del puesto (7)" },
        { 0x5BCBAE, { 0x8C, 0x38, 0xEC, 0, 0, 0 }, { 0x8C, 0x38, (BYTE)(0xEC - PK_PUESTO_CORRE), 0, 0, 0 }, 6, "x del puesto (8)" },
        /* el MENÚ de orden: 7 filas para el anfitrión */
        { 0x5BA208, { 0xC7, 0x44, 0x24, 0x18, 0x06, 0x00 }, { 0xC7, 0x44, 0x24, 0x18, 0x07, 0x00 }, 6, "filas del menú de orden" },
    };
    const int NP = (int)(sizeof(P) / sizeof(P[0]));

    /* las dos llamadas que se desvían: tienen que ser las de siempre */
    BYTE e_attr[5] = { 0xE8 }, e_niv[5] = { 0xE8 };
    *(int *)(e_attr + 1) = pk_rel(0x40DBE8, (DWORD)PKV(0x678160));
    *(int *)(e_niv + 1)  = pk_rel(0x5B9245, (DWORD)PKV(0x63A640));
    DWORD *vt = (DWORD *)PKV(0x882F3C);

    /* ⛔ TODO O NADA: si un solo sitio no es el esperado, el exe no es el que creemos */
    for (int i = 0; i < NP; i++)
        if (!pk_iguales(P[i].va, P[i].esp, P[i].n)) {
            apuntar("  [picker] ⛔ %s (0x%08X) no tiene los bytes esperados: no se toca nada", P[i].que, P[i].va);
            return;
        }
    static const BYTE e_vol[6] = { 0xD9, 0x86, 0x10, 0x03, 0x00, 0x00 };   /* fld dword [esi+0x310] */
    static const BYTE e_raton[7] = { 0x83, 0xC2, 0x05, 0x3B, 0xC8, 0x8B, 0xFA };  /* add edx,5 · cmp ecx,eax · mov edi,edx */
    static const BYTE e_ordenar[6] = { 0x55, 0x8B, 0xEC, 0x83, 0xE4, 0xF8 };     /* push ebp · mov ebp,esp · and esp,-8 */
    BYTE e_cab[5] = { 0xE8 }, e_fila[5] = { 0xE8 };
    *(int *)(e_cab + 1)  = pk_rel(0x5BA1B9, (DWORD)PKV(0x683FB0));
    *(int *)(e_fila + 1) = pk_rel(0x5BA29C, (DWORD)PKV(0x683FB0));
    if (!pk_iguales(0x40DBE8, e_attr, 5) || !pk_iguales(0x5B9245, e_niv, 5) ||
        *vt != (DWORD)PKV(0x5B8EB0) || !pk_iguales(0x5BFD07, e_vol, 6) || !pk_iguales(0x5BDFA4, e_raton, 7) ||
        !pk_iguales(0x5BD7C0, e_ordenar, 6) || !pk_iguales(0x5BA1B9, e_cab, 5) || !pk_iguales(0x5BA29C, e_fila, 5)) {
        apuntar("  [picker] ⛔ el lector del catálogo, la dificultad o el Render de la lista no son los esperados: no se toca nada");
        return;
    }
    g_pk_cueva = (BYTE *)VirtualAlloc(NULL, 128, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!g_pk_cueva) { apuntar("  [picker] ⛔ sin memoria para el salto"); return; }

    /* el salto de la dificultad: guarda la FILA y sigue en pk_nivel con la pila intacta.
     *   En la llamada: 0x20 de argumentos + la vuelta = 0x24; la fila está en [esp+0x1C] del
     *   cuadro de 0x5B8EB0 (0x5B920A: mov ecx,[esp+0x1C]) ⇒ [esp+0x40] adentro del salto. */
    BYTE *k = g_pk_cueva;
    k[0] = 0x8B; k[1] = 0x44; k[2] = 0x24; k[3] = 0x40;                    /* mov eax,[esp+0x40] */
    k[4] = 0xA3; *(DWORD *)(k + 5) = (DWORD)&g_pk_fila;                     /* mov [g_pk_fila],eax */
    k[9] = 0xE9; *(int *)(k + 10) = (int)((DWORD)pk_nivel - (DWORD)(k + 14)); /* jmp pk_nivel */
    /* el volumen del preview: fld [esi+0x310] · fmul [g_pk_vol] · y vuelve a 0x5BFD0D */
    BYTE *kv = g_pk_cueva + 32;
    CopyMemory(kv, e_vol, 6);
    kv[6] = 0xD8; kv[7] = 0x0D; *(DWORD *)(kv + 8) = (DWORD)&g_pk_vol;       /* fmul dword [g_pk_vol] */
    kv[12] = 0xE9; *(int *)(kv + 13) = (int)((DWORD)PKV(0x5BFD0D) - (DWORD)(kv + 17));
    /* el mouse del menú: lea edx,[edx*2+5] · cmp ecx,eax · mov edi,edx · jmp 0x5BDFAB (los flags del cmp siguen) */
    BYTE *km = g_pk_cueva + 64;
    km[0] = 0x8D; km[1] = 0x14; km[2] = 0x55; *(DWORD *)(km + 3) = 5;          /* lea edx,[edx*2+5] */
    km[7] = 0x3B; km[8] = 0xC8; km[9] = 0x8B; km[10] = 0xFA;                    /* cmp ecx,eax · mov edi,edx */
    km[11] = 0xE9; *(int *)(km + 12) = (int)((DWORD)PKV(0x5BDFAB) - (DWORD)(km + 16));
    /* el trampolín del ordenador: sus 6 bytes de entrada y vuelta a 0x5BD7C6 */
    BYTE *ko = g_pk_cueva + 96;
    CopyMemory(ko, e_ordenar, 6);
    ko[6] = 0xE9; *(int *)(ko + 7) = (int)((DWORD)PKV(0x5BD7C6) - (DWORD)(ko + 11));
    g_pk_ordenar_real = (F_PK_ORDENAR)ko;

    g_pk_atrib_real = (F_ATRIB)PKV(0x678160);
    g_pk_lista_real = (F_LISTA_DIBUJAR)PKV(0x5B8EB0);
    int ok = 1;
    for (int i = 0; i < NP; i++) ok &= pk_escribir(P[i].va, P[i].nue, P[i].n);
    BYTE n_attr[5] = { 0xE8 }, n_niv[5] = { 0xE8 };
    *(int *)(n_attr + 1) = pk_rel(0x40DBE8, (DWORD)pk_mi_atrib);
    *(int *)(n_niv + 1)  = pk_rel(0x5B9245, (DWORD)g_pk_cueva);
    ok &= pk_escribir(0x40DBE8, n_attr, 5);
    ok &= pk_escribir(0x5B9245, n_niv, 5);
    BYTE n_raton[7] = { 0xE9, 0, 0, 0, 0, 0x90, 0x90 };
    *(int *)(n_raton + 1) = (int)((DWORD)km - ((DWORD)PKV(0x5BDFA4) + 5));
    ok &= pk_escribir(0x5BDFA4, n_raton, 7);
    BYTE n_ord[6] = { 0xE9, 0, 0, 0, 0, 0x90 };
    *(int *)(n_ord + 1) = (int)((DWORD)pk_ordenar - ((DWORD)PKV(0x5BD7C0) + 5));
    ok &= pk_escribir(0x5BD7C0, n_ord, 6);
    BYTE n_cab[5] = { 0xE8 }, n_fila[5] = { 0xE8 };
    *(int *)(n_cab + 1)  = pk_rel(0x5BA1B9, (DWORD)pk_menu_cabecera);
    *(int *)(n_fila + 1) = pk_rel(0x5BA29C, (DWORD)pk_menu_fila);
    ok &= pk_escribir(0x5BA1B9, n_cab, 5);
    ok &= pk_escribir(0x5BA29C, n_fila, 5);
    BYTE n_vol[6] = { 0xE9, 0, 0, 0, 0, 0x90 };
    *(int *)(n_vol + 1) = (int)((DWORD)kv - ((DWORD)PKV(0x5BFD07) + 5));
    ok &= pk_escribir(0x5BFD07, n_vol, 6);
    DWORD mia = (DWORD)pk_lista;
    ok &= pk_escribir(0x882F3C, &mia, 4);
    if (ok) pk_sala_iniciar(ini);
    apuntar(ok ? "  [picker] ok: columna BPM, corazón corrido, BPM y TIME en el panel (info %d,%d), volumen del preview %d %%, «Orden por BPM»"
               : "  [picker] ⛔ VirtualProtect falló a mitad: el picker puede quedar raro", g_pk_info_x, g_pk_info_y,
            (int)(g_pk_vol * 100 + 0.5f));
}
