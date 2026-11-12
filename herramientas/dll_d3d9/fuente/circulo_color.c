/* circulo_color.c — LOS CRAYONES DE CÍRCULO (23-oct-2026): el NOMBRE DEL CÍRCULO de color, por una MARCA en el texto
 *   · CRAYONES_MAZINO.md · los ítems (1000786..91) los arma `herramientas/crayon_crear.py`
 *
 * anonimo03: «¿podemos usar las bases del crayón de apodo para crear crayones de círculo? … que lo elija cada jugador».
 * El juego dibuja el nombre del círculo SIEMPRE en blanco (`push -1` en 0x481C46, la tarjeta del asiento; y en el
 * cartel de la cabeza `<%s> `), y el color del apodo vive en ~40 lugares (la tabla está copiada 10 veces: sala,
 * carrera, lobby, resultados…). ⇒ en vez de perseguirlos, el SERVER le pone al nombre del círculo una MARCA de dos
 * bytes al principio —'^' y 'A'+color— y la dll la saca y pinta ese texto del color.
 *
 * ⚠ La marca era 0x7F: el cliente lo LIMPIA del nombre del círculo de la tarjeta del asiento (el str2 del FF0C) y
 *   salía «BGM» en blanco. '^' no puede estar en un nombre de círculo (circulos.py: letras, números y _ - . * &).
 *
 * DÓNDE SE ENGANCHA. Hay ~14 funciones que dibujan texto (0x63A330..0x63BA40), cada una con sus argumentos en otro
 * orden (la 1.ª vuelta enganchó 3 por la entrada y la tarjeta del asiento usaba otra: salía «^DGM»). Las 14 hacen lo
 * mismo por dentro:  vsprintf al búfer → `texto->Asignar(búfer, largo)` (0x401F40, thiscall, ret 8) → el color en
 * `pedido+0x30` → `cola->Encolar(pedido)` (0x554CA0, thiscall, ret 4). ⇒ se desvían esas DOS llamadas en las 14:
 *   · al asignar: si el texto empieza con la marca (o es «<» + marca, el cartel de la cabeza) se saca y se ANOTA el color;
 *   · al encolar: si hay un color anotado va a `pedido+0x30`.
 * Y las dos que MIDEN (0x636100, 0x635350, por la entrada) miden sin la marca: que no corra el centrado.
 * [circulo_color] activo=0 en d3d9_proxy.ini lo apaga. */

#define CC_MARCA '^'
/* el color de la letra ('A' + n): 1..6 los «Crayón de Círculo» de Mazino (crayon_crear.COLORES, en ese orden:
 *   dorado, rosa, turquesa, blanco, violeta, rojo); el resto, blanco hasta que haya más */
#define CC_N 6
/*   7..17 los ESTILOS (las marcas de estilo 0..10 de estilos_texto.c: el dibujo del texto los pinta) */
#define CC_EST0 7
#define CC_TOTAL 18              /* catalogo.COLORES_CIRCULO: las letras 'A'..'A'+17 */
static const DWORD g_cc_colores[CC_TOTAL] = {
    0xFFFFFFFF, 0xFFFFD45C, 0xFFFB37A9, 0xFF00FFD5, 0xFFFFFFFF, 0xFF9B2CE0, 0xFFFF2626, EST_MARCA(0),
    EST_MARCA(1), EST_MARCA(2), EST_MARCA(3), EST_MARCA(4), EST_MARCA(5), EST_MARCA(6), EST_MARCA(7), EST_MARCA(8),
    EST_MARCA(9), EST_MARCA(10) };
#define CC_DESDE 0x63A330        /* las funciones que dibujan texto */
#define CC_HASTA 0x63BC00
#define CC_CUANTAS 14

static BYTE *g_cc_base = NULL;
#define CCV(x) (g_cc_base + ((DWORD)(x) - 0x400000))
static void *g_cc_medir[2];
static int g_cc_pendiente = -1;  /* el color del texto que se acaba de asignar (lo consume el encolar) */
static LONG g_cc_vistos = 0;
static char g_cc_buf[512];

/* dónde está la marca en `p`: 0 (al principio), 1 (después de «<»), o -1 */
static int cc_donde(const unsigned char *p, int n)
{
    if (!p || n < 2 || IsBadReadPtr(p, n < 3 ? n : 3)) return -1;
    if (p[0] == CC_MARCA && p[1] >= 'A' && p[1] < 'A' + CC_TOTAL) return 0;
    if (n >= 3 && p[0] == '<' && p[1] == CC_MARCA && p[2] >= 'A' && p[2] < 'A' + CC_TOTAL) return 1;
    return -1;
}

/* copia `p` sin la marca en g_cc_buf; devuelve el color, o -1 si no tenía */
static int cc_sacar(const char *p, int n, const char **sale, int *largo)
{
    int d = cc_donde((const unsigned char *)p, n);
    if (d < 0 || n >= (int)sizeof(g_cc_buf)) return -1;
    int c = (unsigned char)p[d + 1] - 'A';
    if (d) CopyMemory(g_cc_buf, p, d);
    CopyMemory(g_cc_buf + d, p + d + 2, n - d - 2);
    g_cc_buf[n - 2] = 0;
    *sale = g_cc_buf;
    *largo = n - 2;
    if (InterlockedIncrement(&g_cc_vistos) <= 8)
        apuntar("  [circulo_color] marca vista: color %d «%s»", c, g_cc_buf);
    return c;
}

typedef void *(__attribute__((thiscall)) *F_CC_ASIGNAR)(void *, const char *, int);   /* 0x401F40 */
typedef void (__attribute__((thiscall)) *F_CC_ENCOLAR)(void *, void *);               /* 0x554CA0 */
typedef int (__attribute__((thiscall)) *F_CC_M1)(void *, const char *);
typedef int (__attribute__((thiscall)) *F_CC_M2)(void *, const char *, int);

static void *__fastcall cc_asignar(void *texto, void *nada, const char *p, int n)
{
    (void)nada;
    const char *q = p;
    int m = n;
    g_cc_pendiente = cc_sacar(p, n, &q, &m);
    return ((F_CC_ASIGNAR)CCV(0x401F40))(texto, q, m);
}

static void __fastcall cc_encolar(void *cola, void *nada, BYTE *pedido)
{
    (void)nada;
    if (g_cc_pendiente >= 0 && pedido) *(DWORD *)(pedido + 0x30) = g_cc_colores[g_cc_pendiente < CC_TOTAL ? g_cc_pendiente : 0];
    g_cc_pendiente = -1;
    ((F_CC_ENCOLAR)CCV(0x554CA0))(cola, pedido);
}

static int __fastcall cc_m1(void *f, void *nada, const char *s)
{
    (void)nada;
    const char *q = s;
    int m;
    if (s && !IsBadReadPtr(s, 1)) cc_sacar(s, lstrlenA(s), &q, &m);
    return ((F_CC_M1)g_cc_medir[0])(f, q);
}

static int __fastcall cc_m2(void *f, void *nada, const char *s, int n)
{
    (void)nada;
    const char *q = s;
    int m;
    if (s && !IsBadReadPtr(s, 1)) cc_sacar(s, lstrlenA(s), &q, &m);
    return ((F_CC_M2)g_cc_medir[1])(f, q, n);
}

/* enganchar en la ENTRADA (las que miden): bytes de fábrica verificados, trampolín + jmp de vuelta */
static void *cc_enganchar(DWORD va, const BYTE *esperado, int n, void *nuestra, const char *que)
{
    if (memcmp(CCV(va), esperado, n) != 0) {
        apuntar("  [circulo_color] ⛔ %s (0x%06X): los bytes no son los de fábrica, no se toca", que, va);
        return NULL;
    }
    BYTE *t = (BYTE *)VirtualAlloc(NULL, 32, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!t) return NULL;
    CopyMemory(t, CCV(va), n);
    t[n] = 0xE9;
    *(int *)(t + n + 1) = (int)((DWORD)CCV(va + n) - (DWORD)(t + n + 5));
    BYTE salto[8];
    salto[0] = 0xE9;
    *(int *)(salto + 1) = (int)((DWORD)nuestra - ((DWORD)CCV(va) + 5));
    for (int i = 5; i < n; i++) salto[i] = 0x90;
    if (!escribir_bytes(va, esperado, salto, n, que)) return NULL;
    return t;
}

/* las llamadas a `destino` entre CC_DESDE y CC_HASTA (máx. 32) */
static int cc_sitios(DWORD destino, DWORD *va)
{
    int n = 0;
    for (DWORD a = CC_DESDE; a + 5 <= CC_HASTA && n < 32; a++) {
        BYTE *c = CCV(a);
        if (c[0] == 0xE8 && (DWORD)(c + 5 + *(int *)(c + 1)) == (DWORD)CCV(destino)) va[n++] = a;
    }
    return n;
}

static void circulo_color_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    g_cc_base = (BYTE *)GetModuleHandleA(NULL);
    if (!GetPrivateProfileIntA("circulo_color", "activo", 1, ini)) {
        apuntar("  [circulo_color] APAGADO ([circulo_color] activo=0)");
        return;
    }
    DWORD asig[32], enc[32];
    int na = cc_sitios(0x401F40, asig), ne = cc_sitios(0x554CA0, enc);
    if (na != CC_CUANTAS || ne != CC_CUANTAS) {
        apuntar("  [circulo_color] ⛔ esperaba %d+%d llamadas en las funciones de texto y hay %d+%d: no se toca nada",
                CC_CUANTAS, CC_CUANTAS, na, ne);
        return;
    }
    int ok = 0;
    for (int i = 0; i < na; i++) ok += bru_desviar(asig[i], 0x401F40, (void *)cc_asignar, "circulo_color: asignar");
    for (int i = 0; i < ne; i++) ok += bru_desviar(enc[i], 0x554CA0, (void *)cc_encolar, "circulo_color: encolar");
    static const BYTE e_m1[5] = { 0x53, 0x8B, 0x5C, 0x24, 0x08 };          /* push ebx · mov ebx,[esp+8] */
    static const BYTE e_m2[5] = { 0x83, 0xEC, 0x08, 0x53, 0x55 };          /* sub esp,8 · push ebx · push ebp */
    g_cc_medir[0] = cc_enganchar(0x636100, e_m1, 5, (void *)cc_m1, "circulo_color: medir");
    g_cc_medir[1] = cc_enganchar(0x635350, e_m2, 5, (void *)cc_m2, "circulo_color: medir (n)");
    apuntar("  [circulo_color] ★ el nombre del círculo con ^+letra sale de color (%d de %d llamadas desviadas;"
            " medir %d %d)", ok, na + ne, !!g_cc_medir[0], !!g_cc_medir[1]);
}
