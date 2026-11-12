/* sala_alfa.c — las piezas con TRANSPARENCIA de las escenas traídas de los clientes modernos se dibujan
 *               (02-nov-2026, la sala «Parque 2026» del coreano: herramientas/sala_parque2026.py)
 *
 * ★ POR QUÉ (medido en el juego, con sondas Frida sobre el dispositivo, `_trabajo/sala_parque2026/sonda_*.js`):
 *   en la sala nueva faltaban el castillo del fondo, la montaña rusa, los árboles, el jardín, las nubes y el carrusel:
 *   EXACTAMENTE las piezas cuya textura es DXT3 (las que tienen alfa). Lo medido, en orden:
 *     1. SÍ se mandan a dibujar (≈ 900 dibujos por segundo), con ALPHATEST=1 (NOTEQUAL 0) y ALPHABLEND=1.
 *     2. La textura está BIEN cargada: los bytes del nivel 0 son idénticos a los del .dds (LockRect).
 *     3. La etapa 0 hace COLOR = TEXTURA (SELECTARG1) y ALFA = TEXTURA × DIFUSO (MODULATE). El vértice NO trae color
 *        (FVF 0x112 = posición + normal + 1 textura), así que el difuso sale del MATERIAL… y el material que tiene puesto
 *        el 2013 en la sala es TODO CERO (difuso, ambiente y emisivo: 0,0,0,0), con LIGHTING=1.
 *   ⇒ alfa = textura × 0 = 0 ⇒ la prueba de alfa (≠ 0) descarta CADA píxel: la pieza se dibuja invisible.
 *   Lo opaco no lo nota porque su color sale de la textura sola. En los chinos el material viene con el difuso en 1.
 *
 * ★ EL ARREGLO (probado en vivo con Frida antes de escribirlo acá: con él aparecen castillo, montaña rusa y árboles;
 *   soltándolo vuelven a desaparecer — `juego/09_con_arreglo.png` · `10_sin_arreglo.png`): en el dibujo que cumple TODO
 *   esto, el alfa sale de la TEXTURA sola (ALPHAOP = SELECTARG1) y se deja como estaba al volver:
 *       · se dibuja con alfa (ALPHATEST o ALPHABLEND prendido);
 *       · la etapa 0 hace ALFA = TEXTURA × DIFUSO;
 *       · el vértice NO trae color (FVF sin D3DFVF_DIFFUSE, y no es una declaración);
 *       · el material tiene el difuso en alfa 0.
 *   O sea: sólo cuando el «difuso» es un cero que nadie puso a propósito. Lo que trae su color en el vértice, o un
 *   material con alfa, o se dibuja sin alfa, no se toca. Sirve para cualquier sala o escena que se traiga con DXT3/DXT5.
 *   [sala_alfa] activo=0 lo apaga.
 *   ⚠ El dispositivo NO es PURE (las sondas leyeron Get* sin problema): los Get* devuelven el estado guardado y no cuestan. */

/* índices de IDirect3DDevice9 (los tres primeros son IUnknown) */
#define SA_GETMATERIAL      50
#define SA_GETRENDERSTATE   58
#define SA_GETTSS           66
#define SA_SETTSS           67
#define SA_DRAWPRIMITIVE    81
#define SA_DRAWINDEXED      82
#define SA_GETFVF           90
/* estados */
#define SA_RS_ALPHATEST     15
#define SA_RS_ALPHABLEND    27
#define SA_TSS_ALPHAOP       4
#define SA_TSS_ALPHAARG1     5
#define SA_TSS_ALPHAARG2     6
#define SA_TOP_SELECTARG1    2
#define SA_TOP_MODULATE      4
#define SA_TA_DIFFUSE        0
#define SA_TA_TEXTURE        2
#define SA_FVF_DIFFUSE    0x40

typedef HRESULT (WINAPI *SA_GETMAT)(void *, float *);
typedef HRESULT (WINAPI *SA_GETRS)(void *, DWORD, DWORD *);
typedef HRESULT (WINAPI *SA_GETTS)(void *, DWORD, DWORD, DWORD *);
typedef HRESULT (WINAPI *SA_SETTS)(void *, DWORD, DWORD, DWORD);
typedef HRESULT (WINAPI *SA_GETF)(void *, DWORD *);
typedef HRESULT (WINAPI *SA_DIBUJAR)(void *, DWORD, DWORD, DWORD);                       /* DrawPrimitive */
typedef HRESULT (WINAPI *SA_DIBUJAR_IDX)(void *, DWORD, INT, UINT, UINT, UINT, UINT);    /* DrawIndexedPrimitive */

static int  g_sa_activo = 1;
static long g_sa_arreglados = 0;

/* ⛔ MEDIDO 02-nov: la tabla de métodos del dispositivo que DIBUJA ([0x931498]+0xC0) NO es la del que se crea en
 *   CreateDevice (vive en memoria dinámica y su Reset no es el nuestro): engancharla al crear no sirve — se enganchó,
 *   lo dijo el registro, y el juego nunca pasó por ahí. Monturas ya lo había resuelto enganchando TARDE, sobre el
 *   que dibuja (`mo_dev`). Acá: un hilo mira cada medio segundo y engancha la tabla que esté usando; guarda los
 *   originales POR TABLA, por si el runtime cambia de tabla otra vez. */
#define SA_TABLAS 8
static struct { void **vt; SA_DIBUJAR real81; SA_DIBUJAR_IDX real82; } g_sa_tablas[SA_TABLAS];
static volatile LONG g_sa_ntablas = 0;

static int sa_tabla(void *dev)
{
    void **vt = *(void ***)dev;
    for (LONG i = 0; i < g_sa_ntablas; i++)
        if (g_sa_tablas[i].vt == vt) return (int)i;
    return -1;
}

/* ¿este dibujo es una pieza con alfa y difuso cero? Si lo es, pone ALPHAOP = SELECTARG1 y devuelve 1. */
static int sa_antes(void *dev)
{
    void **vt = *(void ***)dev;
    DWORD v = 0, fvf = 0;
    ((SA_GETRS)vt[SA_GETRENDERSTATE])(dev, SA_RS_ALPHATEST, &v);
    if (!v) {
        ((SA_GETRS)vt[SA_GETRENDERSTATE])(dev, SA_RS_ALPHABLEND, &v);
        if (!v) return 0;
    }
    ((SA_GETTS)vt[SA_GETTSS])(dev, 0, SA_TSS_ALPHAOP, &v);
    if (v != SA_TOP_MODULATE) return 0;
    ((SA_GETTS)vt[SA_GETTSS])(dev, 0, SA_TSS_ALPHAARG1, &v);
    if (v != SA_TA_TEXTURE) return 0;
    ((SA_GETTS)vt[SA_GETTSS])(dev, 0, SA_TSS_ALPHAARG2, &v);
    if (v != SA_TA_DIFFUSE) return 0;
    if (((SA_GETF)vt[SA_GETFVF])(dev, &fvf) != 0 || fvf == 0 || (fvf & SA_FVF_DIFFUSE)) return 0;
    float mat[17];
    if (((SA_GETMAT)vt[SA_GETMATERIAL])(dev, mat) != 0 || mat[3] != 0.0f) return 0;   /* difuso.a */
    ((SA_SETTS)vt[SA_SETTSS])(dev, 0, SA_TSS_ALPHAOP, SA_TOP_SELECTARG1);
    if (g_sa_arreglados++ == 0)
        apuntar("  [sala_alfa] ★ primera pieza con alfa y material en cero: el alfa sale de la textura (FVF 0x%X)", fvf);
    return 1;
}

static HRESULT WINAPI sa_dibujar(void *dev, DWORD tipo, DWORD inicio, DWORD cuantos)
{
    int t = sa_tabla(dev);
    if (t < 0) return E_FAIL;                         /* no pasa: sólo se pone en tablas anotadas */
    int cambie = sa_antes(dev);
    HRESULT hr = g_sa_tablas[t].real81(dev, tipo, inicio, cuantos);
    if (cambie) ((SA_SETTS)(*(void ***)dev)[SA_SETTSS])(dev, 0, SA_TSS_ALPHAOP, SA_TOP_MODULATE);
    return hr;
}

static HRESULT WINAPI sa_dibujar_idx(void *dev, DWORD tipo, INT base, UINT minimo, UINT nvert, UINT inicio, UINT cuantos)
{
    int t = sa_tabla(dev);
    if (t < 0) return E_FAIL;
    int cambie = sa_antes(dev);
    HRESULT hr = g_sa_tablas[t].real82(dev, tipo, base, minimo, nvert, inicio, cuantos);
    if (cambie) ((SA_SETTS)(*(void ***)dev)[SA_SETTSS])(dev, 0, SA_TSS_ALPHAOP, SA_TOP_MODULATE);
    return hr;
}

/* engancha la tabla del dispositivo que dibuja, si todavía no está enganchada.
 * ⛔ MEDIDO 02-nov: la MISMA tabla aparecía sin el gancho al rato (3 veces en un arranque): Direct3D vuelve a escribir
 *   esos lugares (cambia de función de dibujo según el estado). ⇒ si la tabla ya estaba anotada, se ACTUALIZAN sus
 *   originales con lo que Direct3D puso ahora (no una entrada nueva: la vieja podría ser la versión equivocada). */
static long g_sa_reenganches = 0;

static void sa_enganchar_tabla(void **vt)
{
    if (!vt) return;
    void *p81 = vt[SA_DRAWPRIMITIVE], *p82 = vt[SA_DRAWINDEXED];
    if (p81 == (void *)sa_dibujar && p82 == (void *)sa_dibujar_idx) return;
    DWORD viejo = 0;
    if (!VirtualProtect(&vt[SA_DRAWPRIMITIVE], 2 * sizeof(void *), PAGE_EXECUTE_READWRITE, &viejo)) return;
    LONG i = 0;
    while (i < g_sa_ntablas && g_sa_tablas[i].vt != vt) i++;
    int nueva = (i == g_sa_ntablas);
    if (nueva && i >= SA_TABLAS) { VirtualProtect(&vt[SA_DRAWPRIMITIVE], 2 * sizeof(void *), viejo, &viejo); return; }
    g_sa_tablas[i].vt = vt;
    if (p81 != (void *)sa_dibujar) g_sa_tablas[i].real81 = (SA_DIBUJAR)p81;
    if (p82 != (void *)sa_dibujar_idx) g_sa_tablas[i].real82 = (SA_DIBUJAR_IDX)p82;
    if (nueva) InterlockedExchange(&g_sa_ntablas, i + 1);    /* anotada ANTES de poner el gancho */
    vt[SA_DRAWPRIMITIVE] = (void *)sa_dibujar;
    vt[SA_DRAWINDEXED] = (void *)sa_dibujar_idx;
    VirtualProtect(&vt[SA_DRAWPRIMITIVE], 2 * sizeof(void *), viejo, &viejo);
    if (nueva)
        apuntar("  [sala_alfa] ★ enganchada la tabla %p del dispositivo que dibuja (DrawPrimitive 81, DrawIndexedPrimitive 82)",
                (void *)vt);
    else if (g_sa_reenganches++ < 5)
        apuntar("  [sala_alfa] Direct3D volvió a escribir el dibujo de la tabla %p: originales actualizados y enganchada otra vez"
                " (81 %p · 82 %p)", (void *)vt, p81, p82);
}

static DWORD WINAPI sa_vigilar(LPVOID nada)
{
    (void)nada;
    BYTE *base = (BYTE *)GetModuleHandleA(NULL);
    for (;;) {
        Sleep(500);
        /* el compilador (zig, gnu) no tiene __try: se mira que cada puntero se pueda leer, como circulo_color.c */
        BYTE **pd3d = (BYTE **)(base + (0x931498 - 0x400000));
        BYTE *d3d = *pd3d;
        if (!d3d || IsBadReadPtr(d3d + 0xC0, sizeof(void *))) continue;
        void *dev = *(void **)(d3d + 0xC0);
        if (!dev || IsBadReadPtr(dev, sizeof(void *))) continue;
        void **vt = *(void ***)dev;
        if (!vt || IsBadReadPtr(vt, (SA_GETFVF + 1) * sizeof(void *))) continue;
        sa_enganchar_tabla(vt);
    }
    return 0;
}

static void sala_alfa_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    g_sa_activo = GetPrivateProfileIntA("sala_alfa", "activo", 1, ini);
    apuntar(g_sa_activo ? "  [sala_alfa] activo: las piezas con alfa y material en cero se van a ver"
                        : "  [sala_alfa] APAGADO ([sala_alfa] activo=0)");
}

/* lo llama `enganchar_dispositivo` al crear el dispositivo: arranca el vigía (UNA vez) */
static void sala_alfa_enganchar(void *dev)
{
    static int arrancado = 0;
    (void)dev;
    if (!g_sa_activo || arrancado) return;
    arrancado = 1;
    HANDLE h = CreateThread(NULL, 0, sa_vigilar, NULL, 0, NULL);
    if (h) CloseHandle(h);
    apuntar(h ? "  [sala_alfa] vigía puesto: engancha el dibujo del dispositivo que dibuja apenas aparece"
              : "  [sala_alfa] ⚠ no pude crear el vigía: las piezas con alfa siguen invisibles");
}
