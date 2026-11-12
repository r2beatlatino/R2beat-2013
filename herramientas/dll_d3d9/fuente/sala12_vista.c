/* sala12_vista.c — la SALA DE 12 estilo coreano (el 6vs6, 10-oct-2026)
 *
 *   anonimo03 (con la maqueta v2): «las 12 iguales estilo coreano, con mi tarjeta grande · limpio · sin espectadores · la
 *   tuerquita en el slot · la cara animada como en su slot normal, y su ícono de licencia y nivel».
 *   Investigación: documentacion/MODO_6VS6.md §12 (y el informe del agente _trabajo/grupo/agente_sala/INFORME.md).
 *
 *   ⛔ La sala de carrera NO es un .rui: la dibuja por código cRoom (vtable 0x882A8C, objeto en [0x9314C0]). Por eso
 *   esto va desviando LLAMADAS, y sólo cuando el server dice que la sala es de 12 (4.º campo de la cola del FF13,
 *   `g_gr_sala`, lo lee panel_sala.c). En una sala normal todo sigue igual.
 *     0x5AEEEE  call 0x5980F0  (las 6 tarjetas de asiento)      → s12v_tarjetas: las NUESTRAS
 *     0x5A6FD9  call 0x5A2340  (los clics de esas tarjetas)     → s12v_clics: (etapa 2b) por ahora nada
 *     0x5AF10C  call 0x5B61B0  (el panel de espectadores)       → ★ 17-oct: debajo de la tarjeta grande, lugares 12..17
 *     0x5AF5B2  call 0x5B6140  (sus clics)                      → ★ 17-oct: los de fábrica, con esos números
 *
 *   Lo que se dibuja, con piezas del propio juego donde se puede (así se ve y se anima igual):
 *     · el fondo de cada tarjeta y las insignias 1..12: la hoja nuestra `sala12_tarjetas.tga` (rnr_ui_sala12.pak,
 *       el arte del coreano re-teñido: rojo 1..6 / azul 7..12 en equipos, violeta en todos contra todos)
 *     · «LISTO» / «Anfitrión»: gr_1.spr cortes 13 / 14 ([cRoom+0x1CC]) con 0x683FB0 · el botón i: 02.spr corte 8
 *     · el apodo: 0x63B350 (el pintor de texto del juego) · el ícono de licencia + nivel: 0x413B20 (animado)
 *     · ★ la CARA de la tarjeta grande: 0x596FC0(viewport, sRoomUser, asiento, 0) — el muñeco 3D en vivo, como en el
 *       asiento normal. El ancho del viewport lo clava la función (`mov [ebp+8],0x65` en 0x59745A): se cambia
 *       mientras dura la llamada.
 *   Los ocupantes: el std::map<asiento, sRoomUser> de cRoom+0x9C (cabeza [+0xB4], clave nodo+0xC, «nil» nodo+0x3A5):
 *   listo nodo+0x167 · apodo nodo+0x17C · clave del padrón nodo+0x155 · exp nodo+0x198.
 *   [sala12_vista] activo=0 lo apaga · z_fondo (milésimas, 500) · z_insignia (330).
 *
 *   ★ 14-oct · EL RELEVO DE 12 (RELEVO_12.md F3): en una sala de 12 de RELEVO ([cRoom+0x9568] = 2) hay 4 equipos de 3
 *   en lugares fijos (el server: asiento / 3 + 1) ⇒ las tarjetas van ROJO 1-3 · AZUL 4-6 · VERDE 7-9 · NARANJA 10-12
 *   (tarjetas e insignias verde/naranja nuevas en la hoja), y «Elija Equipo» abre un cartel de 4 BANDERAS: el de
 *   fábrica es gr_btn.tga 0x19/0x1A ([cRoom+0x1C4], lo dibuja 0x58CF90 desde 0x5AEFCC y lo atiende 0x58D180 desde
 *   0x5AA623: 2 rectángulos de 0x57×0x51 → FF18 1 ó 2 por 0x5C70F0). En el relevo de 12 se dibuja el NUESTRO
 *   (sala12_banderas.tga: el mismo arte con 4 casilleros, cada 112) y se atienden 4 → FF18 1..4 (el server lleva a
 *   los lugares fijos del equipo: salas.lado_del_equipo).
 */
#define S12VV(x) (g_s12v_base + ((DWORD)(x) - 0x400000))

static BYTE  *g_s12v_base = NULL;
static int    g_s12v_activo = 0;
static BYTE   g_s12v_hoja[0x100];                 /* el c2DImage de la hoja (la clase ocupa 0x40) */
static int    g_s12v_estado = 0;                  /* 0 sin cargar · 1 lista · -1 no se usa */
static float  g_s12v_z_fondo = 0.5f, g_s12v_z_insignia = 0.33f;
static int    g_s12v_n_insignia0 = 0;             /* el 1.er corte de las insignias en la hoja */
static BYTE   g_s12v_band[0x100];                 /* ★ 14-oct: la hoja del cartel de 4 banderas (y la flechita) */
static int    g_s12v_mx = -1, g_s12v_my = -1;     /* ★ 14-oct: el mouse en la sala (lo anota la cueva de 0x5AA628) */
#define S12V_FLECHA_DX 57                         /* la flechita en la tarjeta chica: a la izquierda de la «i» */
#define S12V_FLECHA_DY 25
static int    g_s12v_band_estado = 0;             /* 0 sin cargar · 1 lista · -1 no se usa */

#define S12V_X0 170                               /* la grilla: 2 filas de 6 */
#define S12V_Y0 42
#define S12V_DX 104
#define S12V_DY 52
#define S12V_GX 6                                 /* la tarjeta grande */
#define S12V_GY 162

typedef void *(TCK *F_S12V_CREAR)(void *self);
typedef int   (TCK *F_S12V_CARGAR)(void *self, const char *ruta, const char *prefijo);
typedef void  (TCK *F_S12V_RECORTE)(void *self, float x, float y, int u, int v, int w, int h, float z);
typedef void  (TCK *F_S12V_POS)(void *self, int n, int x, int y);
typedef void  (TCK *F_S12V_COLOR)(void *self, int n, DWORD argb);
typedef void  (TCK *F_S12V_DIBUJAR)(void *self, int n, int banderas);
typedef void  (TCK *F_S12V_SPR)(void *spr, int x, int y, int corte, int banderas);           /* 0x683FB0, ret 0x10 */
typedef void  (__cdecl *F_S12V_TEXTO)(void *pintor, int x, int y, DWORD color, const char *fmt, const char *s);
typedef BYTE  (TCK *F_S12V_LIC)(void *padron, int clave);                                   /* 0x44F260, ret 4 */
typedef int   (TCK *F_S12V_NIVEL)(void *nada, DWORD exp);                                   /* 0x4848D0, ret 4 */
typedef void  (TCK *F_S12V_ESTRELLA)(void *yo, int x, int y, int nivel, int lic, float f);  /* 0x413B20, ret 0x14 */
typedef void  (TCK *F_S12V_CARA)(void *sala, void *vp, void *u, int asiento, int bandera);  /* 0x596FC0, ret 0x10 */
typedef BYTE  (TCK *F_S12V_EQUIPOS)(void *sala);                                            /* 0x58BFF0 */
typedef void  (TCK *F_S12V_SALA)(void *sala);
typedef void  (TCK *F_S12V_SALA1)(void *sala, int a);
typedef void  (TCK *F_S12V_SALA7)(void *o, int a, int b, int c, int d, int e, int f, int g);

typedef struct { DWORD X, Y, Width, Height; float MinZ, MaxZ; } S12V_VP;
typedef void  (TCK *F_S12V_TAM)(void *img, int n, int w, int h);                             /* 0x64DB90 */

static int s12v_escribir(DWORD va, const void *b, int n)
{
    DWORD viejo = 0;
    if (!VirtualProtect(S12VV(va), n, PAGE_EXECUTE_READWRITE, &viejo)) return 0;
    CopyMemory(S12VV(va), b, n);
    VirtualProtect(S12VV(va), n, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), S12VV(va), n);
    return 1;
}

static int s12v_es_doce(void) { return g_s12v_activo && g_gr_sala == 12; }

/* ★ 14-oct: ¿la sala de 12 es de RELEVO? (CoopMode [cRoom+0x9568] = 2, el que lee 0x58BFF0)
 * ★ 15-oct: ...o de EQUIPO DE 4 (EQUIPOS_4.md): CoopMode 0 (equipo) y el server dice 4 equipos (el 5.º campo de la cola
 *   del FF13, `g_gr_equipos`). Las dos son la MISMA sala: 4 colores, lugares fijos, 4 banderas y la flechita. */
static int s12v_relevo12(BYTE *sala)
{
    if (!s12v_es_doce() || !sala) return 0;
    int coop = *(int *)(sala + 0x9568);
    return coop == 2 || (coop == 0 && g_gr_equipos == 4);
}

/* el color de la tarjeta/insignia del asiento a: 0 rojo · 1 azul · 2 violeta · 3 verde · 4 naranja */
static int s12v_color(BYTE *sala, int a, int equipos)
{
    static const int C4[4] = { 0, 1, 3, 4 };
    if (s12v_relevo12(sala)) return C4[(a / 3) & 3];
    return equipos ? (a < 6 ? 0 : 1) : 2;
}
static const int S12V_CORTE_COLOR[5] = { S12_CORTE_ROJO, S12_CORTE_AZUL, S12_CORTE_VIOLETA, S12_CORTE_VERDE,
                                         S12_CORTE_NARANJA };

/* el nodo del asiento `a` en el mapa de la sala (o NULL) */
static BYTE *s12v_nodo(BYTE *sala, int a)
{
    BYTE *cabeza = *(BYTE **)(sala + 0xB4);
    if (!cabeza) return NULL;
    BYTE *n = *(BYTE **)(cabeza + 4), *r = NULL;          /* la raíz */
    while (n && !n[0x3A5]) {
        if (n[0xC] < a) n = *(BYTE **)(n + 8);
        else { r = n; n = *(BYTE **)n; }
    }
    return (r && r != cabeza && r[0xC] == a) ? r : NULL;
}

static void s12v_cargar(void)
{
    g_s12v_estado = -1;
    ((F_S12V_CREAR)S12VV(0x64E560))(g_s12v_hoja);
    if (!((F_S12V_CARGAR)S12VV(0x64E1E0))(g_s12v_hoja, S12_TARJETAS_TGA, NULL)) {
        apuntar("  [sala12_vista] ⛔ no encontré %s (¿falta rnr_ui_sala12.pak?): la sala de 12 queda como siempre",
                S12_TARJETAS_TGA);
        return;
    }
    F_S12V_RECORTE rec = (F_S12V_RECORTE)S12VV(0x64EC40);
    int n = 0;
    for (int i = 0; i < (int)(sizeof(S12_CORTES) / sizeof(S12_CORTES[0])); i++, n++)
        rec(g_s12v_hoja, 0, 0, S12_CORTES[i][0], S12_CORTES[i][1], S12_CORTES[i][2], S12_CORTES[i][3],
            (i == S12_CORTE_LISTO || i == S12_CORTE_ANFITRION) ? g_s12v_z_insignia : g_s12v_z_fondo);
    g_s12v_n_insignia0 = n;
    for (int c = 0; c < S12_INSIGNIA_COLORES; c++)
        for (int k = 0; k < 12; k++, n++)
            rec(g_s12v_hoja, 0, 0, S12_INSIGNIA_FILA[c][0] + k * (S12_INSIGNIA_W + 2), S12_INSIGNIA_FILA[c][1],
                S12_INSIGNIA_W, S12_INSIGNIA_H, g_s12v_z_insignia);
    g_s12v_estado = 1;
    apuntar("  [sala12_vista] ★ hoja cargada: %d cortes", n);
}

static void s12v_figura(int n, int x, int y)
{
    ((F_S12V_POS)S12VV(0x64D990))(g_s12v_hoja, n, x, y);
    ((F_S12V_COLOR)S12VV(0x64E710))(g_s12v_hoja, n, 0xFFFFFFFF);
    ((F_S12V_DIBUJAR)S12VV(0x64EE40))(g_s12v_hoja, n, 0);
}

static void s12v_spr(BYTE *sala, DWORD miembro, int x, int y, int corte)
{
    void *spr = *(void **)(sala + miembro);
    if (spr) ((F_S12V_SPR)S12VV(0x683FB0))(spr, x, y, corte, 0);
}

static void s12v_texto(int x, int y, const char *s)
{
    void *pintor = *(void **)S12VV(0x93149C);
    if (pintor && s && *s) ((F_S12V_TEXTO)S12VV(0x63B350))(pintor, x, y, 0xFFFFFFFF, (const char *)S12VV(0x873CA0), s);
}

static void s12v_licencia(BYTE *nodo, int x, int y)
{
    void *padron = *(void **)S12VV(0x931660), *yo = *(void **)S12VV(0x9314B4);
    if (!padron || !yo) return;
    BYTE lic = ((F_S12V_LIC)S12VV(0x44F260))(padron, nodo[0x155]);
    int nivel = ((F_S12V_NIVEL)S12VV(0x4848D0))(NULL, *(DWORD *)(nodo + 0x198));
    ((F_S12V_ESTRELLA)S12VV(0x413B20))(yo, x, y, nivel, lic, 0.5f);
}

/* ★ 2.ª vuelta (anonimo03, 10-oct): «el mini char pareciera que estuviera detrás de un filtro · mis ítems de adorno de
 *   slot dejaron de funcionar».
 *   · el FILTRO: lo 2D va a una cola que se dibuja al FINAL del cuadro, y la cara 3D se dibuja EN EL ACTO ⇒ el fondo
 *     translúcido de la tarjeta grande caía ENCIMA de la cara. Ahora: fondo y marco a la cola → se vacía la cola
 *     (`[0x93149C]->0x639780`, lo mismo que hace el juego antes de la cara de una pareja fusionada, 0x597054) → cara.
 *   · el MARCO DE ASIENTO («Slot …», nodo+0x1A4): el juego lo dibuja con su fila de slotpack (`0x50F8C0`, +8 sprite ·
 *     +9 primer cuadro · +0xA cuántos), el sprite del mapa cRoom+0x1F4 (`0x470330`) y el cuadro que avanza
 *     `[cRoom+0x11F+asiento]` (sólo 0..5: para 6..11 lo avanzamos nosotros). Acá va DETRÁS de la cara, estirado al
 *     recuadro de la tarjeta grande: el corte se agranda (`0x64DB90`, tamaño en la entrada +0x14/+0x18 del vector
 *     [spr+0x18], 0x50 B c/u), se encola (la cola COPIA la entrada) y se le devuelve el tamaño en el acto. */
typedef BYTE *(TCK *F_S12V_FILA)(void *tabla, int n);                                        /* 0x50F8C0, ret 4 */
typedef void  (TCK *F_S12V_BUSCAR)(void *mapa, void *out, void *clave);                      /* 0x470330, ret 8 */
typedef void  (TCK *F_S12V_VACIAR)(void *pintor);                                            /* 0x639780 */
typedef void  (TCK *F_S12V_ZCORTE)(void *spr, int corte, float z);                           /* 0x683F60, ret 8 */
static float g_s12v_z_marco = 0.45f;
static float g_s12v_cara_lejos = 1.25f;
static float g_s12v_z_tarjeta_nombre = 0.4f;

/* (tarjeta_bruma.c, que va incluido después) */
static int bru_par_marco(int marco, void *h, int *c1, int *c2, int *resto);
static int bru_par_tarjeta(void *h, int corte, int *c1, int *c2, int *resto);
static int bru_ajustar_grande(void *h, int *x, int *y, int *w, int *alto, int *corte);

/* un recorte estirado a w×h, con su z y su color (alfa < 255 = mezcla, 0x64E710); el tamaño vuelve a ser el de siempre */
typedef void (TCK *F_S12V_COLOR)(void *spr, int corte, DWORD argb);                               /* 0x64E710 */
static void s12v_cuadro_tam(BYTE *spr, int x, int y, int corte, int w, int h, float z, DWORD argb)
{
    BYTE *v0 = *(BYTE **)(spr + 0x18), *v1 = *(BYTE **)(spr + 0x1C);
    if (!v0 || corte < 0 || corte >= (int)((v1 - v0) / 0x50)) return;
    float *tam = (float *)(v0 + corte * 0x50 + 0x14);
    float w0 = tam[0], h0 = tam[1];
    ((F_S12V_ZCORTE)S12VV(0x683F60))(spr, corte, z);
    ((F_S12V_COLOR)S12VV(0x64E710))(spr, corte, argb);
    ((F_S12V_TAM)S12VV(0x64DB90))(spr, corte, w, h);
    ((F_S12V_SPR)S12VV(0x683FB0))(spr, x, y, corte, 0);
    tam[0] = w0;
    tam[1] = h0;
}

static void s12v_marco(BYTE *sala, BYTE *nodo, int a, int x, int y, int w, int h)
{
    static int dicho = 0;
    BYTE marco = nodo[0x1A4];
    void *tabla = *(void **)S12VV(0x931618);
    if (!marco || !tabla) { if (!(dicho & 1)) { dicho |= 1; apuntar("  [sala12_vista] marco: sin marco (%d) o sin tabla", marco); } return; }
    BYTE *fila = ((F_S12V_FILA)S12VV(0x50F8C0))(tabla, marco);
    if (!fila) { if (!(dicho & 2)) { dicho |= 2; apuntar("  [sala12_vista] marco %d: sin fila en slotpack", marco); } return; }
    struct { DWORD cont; BYTE *nodo; } it = { 0, NULL };
    ((F_S12V_BUSCAR)S12VV(0x470330))(sala + 0x1F4, &it, fila + 8);
    if (!it.nodo || it.nodo == *(BYTE **)(sala + 0x1F4 + 0x18)) {
        if (!(dicho & 4)) { dicho |= 4; apuntar("  [sala12_vista] marco %d: el sprite %d no está cargado en la sala", marco, fila[8]); }
        return;
    }
    BYTE *spr = *(BYTE **)(it.nodo + 0x10);
    if (!spr) return;
    int cuantos = fila[0xA] ? fila[0xA] : 1;
    int paso = (a < 6) ? sala[0x11F + a] : (int)((GetTickCount() / 100) % cuantos);
    int corte = fila[9] + (paso % cuantos);
    BYTE *v0 = *(BYTE **)(spr + 0x18), *v1 = *(BYTE **)(spr + 0x1C);
    if (!v0 || corte < 0 || corte >= (int)((v1 - v0) / 0x50)) return;
    float *tam = (float *)(v0 + corte * 0x50 + 0x14);
    float w0 = tam[0], h0 = tam[1];
    static int avisado = 0;
    if (!avisado) { avisado = 1; apuntar("  [sala12_vista] marco %d: sprite %d, cuadros %d+%d (%dx%d)", marco, fila[8], fila[9],
                                         cuantos, (int)w0, (int)h0); }
    /* ⛔ 3.ª vuelta: «no sale el marco». El juego le pone z 0.9 antes de dibujarlo (`0x683F60`, 0x5985EF): quedaba
     *   DETRÁS del fondo de la tarjeta grande (0.5). Va delante del fondo y detrás de lo demás. */
    /* ★ 23-oct: el Pack de Slot Mazino, animado como en el asiento (los SLM_N cuadros mezclados de tarjeta_bruma.c) */
    int c1, c2, resto;
    if (bru_par_marco(marco, spr, &c1, &c2, &resto)) {
        s12v_cuadro_tam(spr, x, y, c1, w, h, g_s12v_z_marco, 0xFFFFFFFF);
        if (resto > 2) s12v_cuadro_tam(spr, x, y, c2, w, h, g_s12v_z_marco, ((DWORD)resto << 24) | 0xFFFFFF);
        return;
    }
    ((F_S12V_ZCORTE)S12VV(0x683F60))(spr, corte, g_s12v_z_marco);
    ((F_S12V_TAM)S12VV(0x64DB90))(spr, corte, w, h);
    ((F_S12V_SPR)S12VV(0x683FB0))(spr, x, y, corte, 0);
    tam[0] = w0;                                                   /* el tamaño de siempre, para las salas normales */
    tam[1] = h0;
}

static void s12v_cara(BYTE *sala, BYTE *nodo, int a, int x, int y, int w, int h)
{
    void *pintor = *(void **)S12VV(0x93149C);
    if (pintor) ((F_S12V_VACIAR)S12VV(0x639780))(pintor);      /* lo encolado (fondo, marco) va ANTES que la cara */
    S12V_VP vp = { (DWORD)x, (DWORD)y, (DWORD)w, (DWORD)h, 0.0f, 1.0f };
    DWORD ancho = (DWORD)w, viejo = 0x65;
    /* ⛔ 5.ª vuelta (anonimo03): «parte del torso atraviesa el recuadro: tocará reducir el char para que quepa». La cara
     *   usa una proyección ORTOGRÁFICA de 125 × 117,4 (0x882460 / 0x88247C, `[0x931498]->+0x20` en 0x597489): más
     *   grande = el muñeco más chico y entero. Se agranda sólo durante esta llamada ([sala12_vista] cara_lejos, %). */
    float *pw = (float *)S12VV(0x882460), *ph = (float *)S12VV(0x88247C);
    float w0 = *pw, h0 = *ph, k = g_s12v_cara_lejos;
    s12v_escribir(0x59745A + 3, &ancho, 4);                 /* `mov [ebp+8], w` mientras dura */
    float nw = w0 * k, nh = h0 * k;
    s12v_escribir(0x882460, &nw, 4);
    s12v_escribir(0x88247C, &nh, 4);
    ((F_S12V_CARA)S12VV(0x596FC0))(sala, &vp, nodo + 0x10, a, 0);
    s12v_escribir(0x882460, &w0, 4);
    s12v_escribir(0x88247C, &h0, 4);
    s12v_escribir(0x59745A + 3, &viejo, 4);
}

/* un corte de un sprite del juego a OTRO tamaño (y se le devuelve el suyo: la cola copia la entrada) */
static void s12v_spr_tam(BYTE *sala, DWORD miembro, int x, int y, int corte, int w, int h)
{
    BYTE *spr = *(BYTE **)(sala + miembro);
    if (!spr) return;
    BYTE *v0 = *(BYTE **)(spr + 0x18), *v1 = *(BYTE **)(spr + 0x1C);
    if (!v0 || corte < 0 || corte >= (int)((v1 - v0) / 0x50)) return;
    float *tam = (float *)(v0 + corte * 0x50 + 0x14);
    float w0 = tam[0], h0 = tam[1];
    ((F_S12V_TAM)S12VV(0x64DB90))(spr, corte, w, h);
    ((F_S12V_SPR)S12VV(0x683FB0))(spr, x, y, corte, 0);
    tam[0] = w0;
    tam[1] = h0;
}

typedef BYTE (TCK *F_S12V_PUEDE_CAMBIAR)(void *sala, int a);                             /* 0x594390, ret 4 */
static void s12v_band_cargar(void);
static void s12v_band_figura(int n, int x, int y);

/* ★ 14-oct · LA FLECHITA DEL CAMBIO DE LUGAR (relevo de 12; anonimo03: «el cambio de lugar va con un botón con flechitas
 *   + pregunta al que recibe la propuesta»). La regla es la del juego: 0x594390(sala, asiento) — relevo, no el mío, no
 *   el del anfitrión, los huecos también (MODO_RELEVO §1.4). El clic manda el FF6B por 0x5D1270 como el botón de
 *   fábrica (0x5A2BDC); la pregunta al otro (FF6C, Sí/No) la hace el juego solo. */
static int s12v_flecha_visible(BYTE *sala, int a)
{
    return s12v_relevo12(sala) && ((F_S12V_PUEDE_CAMBIAR)S12VV(0x594390))(sala, a) != 0;
}

/* ★ 17-oct · LA TUERQUITA (anonimo03: «poner la tuerquita que permite pasar el master o expulsar usuarios al lado izquierdo de
 *   la "i"»). La de fábrica es un cUIButton por asiento (+0x7540 + a·0xD0) y el estado de su menú va en arreglos de 6
 *   ([sala+0x9369+a]) ⇒ en la de 12 se dibuja y se atiende la NUESTRA, con las mismas piezas de 02.spr ([sala+0x170]):
 *   ⚙ 80/81 · el menú como lo dibuja 0x5980F0 (fondo 0x5D+n, tapa 0x61, resaltado 0x58, rótulos 0x62+i / 0x65+i),
 *   con las mismas distancias a la tuerca. Las dos opciones abren el MISMO cartel Sí/No que el juego (0x5A2340:
 *   texto 0x1FF / 0x1FE con el apodo, el apodo copiado en [sala+0x9370], 0x4233A0 con 0x5912C0 = FF9B «cambia el
 *   dueño» / 0x5A2210 = FF20 «baneo»): resuelven el asiento por el APODO (0x4EBCB0), así que valen para los 12. */
#define S12V_TUERCA_DX 61                          /* a la izquierda de la «i» (x + 80) */
#define S12V_TUERCA_DY 26
#define S12V_TUERCA_W  21
static int g_s12v_menu = -1;                       /* el asiento con el menú abierto (−1 = ninguno) */
static int g_s12v_mio = -1, g_s12v_anf = -1;

static int s12v_tuerca_visible(BYTE *sala, int a)
{
    return g_s12v_mio >= 0 && g_s12v_mio == g_s12v_anf && a != g_s12v_mio && a < 12 && s12v_nodo(sala, a) != NULL;
}

static void s12v_tuerca_xy(int a, int *x, int *y)
{
    *x = S12V_X0 + (a % 6) * S12V_DX + S12V_TUERCA_DX;
    *y = S12V_Y0 + (a / 6) * S12V_DY + S12V_TUERCA_DY;
}

/* ⚠ 17-oct (anonimo03: «el botón ya existe, pero el ícono no se dibuja»): los cortes de 02.spr que en la de 12 sólo dibujamos
 *   nosotros (la tuerca 80/81, el menú) tienen el color en 0 (en la de 6 se lo pone su cUIButton) ⇒ invisibles. 02.spr
 *   es un c2DImage (s12v_spr_tam ya le usa 0x64DB90): se le pone blanco opaco (0x64E710) antes de dibujar. */
static void s12v_spr_opaco(BYTE *sala, int x, int y, int corte)
{
    void *spr = *(void **)(sala + 0x170);
    if (!spr) return;
    ((F_S12V_COLOR)S12VV(0x64E710))(spr, corte, 0xFFFFFFFF);
    ((F_S12V_SPR)S12VV(0x683FB0))(spr, x, y, corte, 0);
}

/* ⚠ 17-oct, 2.ª vuelta: con el color puesto seguía sin verse — el dibujo es DIFERIDO (se pinta al final del cuadro) y
 *   en el medio los cUIButton de fábrica de las tuercas de los 6 asientos (ocultos en la de 12) le vuelven a poner color 0
 *   al MISMO corte 80 de 02.spr. El menú se veía porque esos cortes no los toca nadie. ⇒ la tuerca sale de NUESTRA copia
 *   de 02.tga (cargada aparte, con sus 2 cortes: normal y resaltada). */
#define S12V_TUERCA_TGA "rnr_ui_lt/rnr_room_image/02.tga"
static BYTE g_s12v_tuerca_img[0x100];
static int  g_s12v_tuerca_estado = 0;               /* 0 sin cargar · 1 lista · -1 no se usa */

static void s12v_tuerca_cargar(void)
{
    g_s12v_tuerca_estado = -1;
    ((F_S12V_CREAR)S12VV(0x64E560))(g_s12v_tuerca_img);
    if (!((F_S12V_CARGAR)S12VV(0x64E1E0))(g_s12v_tuerca_img, S12V_TUERCA_TGA, NULL)) {
        apuntar("  [sala12_vista] ⚠ no pude cargar %s: sin tuerquita dibujada (el clic anda igual)", S12V_TUERCA_TGA);
        return;
    }
    F_S12V_RECORTE rec = (F_S12V_RECORTE)S12VV(0x64EC40);
    rec(g_s12v_tuerca_img, 0, 0, 5, 405, 21, 21, g_s12v_z_insignia);         /* 0: normal (02.spr corte 80) */
    rec(g_s12v_tuerca_img, 0, 0, 28, 405, 21, 21, g_s12v_z_insignia);        /* 1: resaltada (corte 81) */
    g_s12v_tuerca_estado = 1;
}

static void s12v_tuerca_dibujar(int x, int y, int resaltada)
{
    if (g_s12v_tuerca_estado == 0) s12v_tuerca_cargar();
    if (g_s12v_tuerca_estado != 1) return;
    int n = resaltada ? 1 : 0;
    ((F_S12V_POS)S12VV(0x64D990))(g_s12v_tuerca_img, n, x, y);
    ((F_S12V_COLOR)S12VV(0x64E710))(g_s12v_tuerca_img, n, 0xFFFFFFFF);
    ((F_S12V_DIBUJAR)S12VV(0x64EE40))(g_s12v_tuerca_img, n, 0);
}

static int s12v_dentro(int x, int y, int w, int h)
{
    return g_s12v_mx >= x && g_s12v_mx < x + w && g_s12v_my >= y && g_s12v_my < y + h;
}

typedef int (TCK *F_S12V_ALTO_CORTE)(void *spr, int corte);          /* 0x6840F0, ret 4: el alto del corte */

static void s12v_menu_dibujar(BYTE *sala)
{
    if (g_s12v_menu < 0 || !s12v_tuerca_visible(sala, g_s12v_menu)) { g_s12v_menu = -1; return; }
    void *spr = *(void **)(sala + 0x170);
    if (!spr) return;
    int gx, gy;
    s12v_tuerca_xy(g_s12v_menu, &gx, &gy);
    s12v_spr_opaco(sala, gx - 42, gy + 18, 0x5D + 2);
    int h = ((F_S12V_ALTO_CORTE)S12VV(0x6840F0))(spr, 0x5D + 2);       /* como 0x598B0F (los otros 2 push son de la siguiente) */
    s12v_spr_opaco(sala, gx - 42, gy + 18 + h, 0x61);
    for (int i = 0; i < 2; i++) {
        if (s12v_dentro(gx - 39, gy + 17 + i * 25, 62, 25)) {
            s12v_spr_opaco(sala, gx - 38, gy + 23 + i * 26, 0x58);
            s12v_spr_opaco(sala, gx - 36, gy + 22 + i * 25, 0x62 + i);
        } else
            s12v_spr_opaco(sala, gx - 36, gy + 22 + i * 25, 0x65 + i);
    }
}

typedef const char *(TCK *F_S12V_TEXTO_ID)(void *tabla, int id);                          /* 0x433380, ret 4 */
typedef int (TCK *F_S12V_CARTEL)(void *mgr, const char *txt, int tipo, void *si, void *no, void *param, int z);

static void s12v_menu_elegir(BYTE *sala, int a, int opcion)
{
    BYTE *nodo = s12v_nodo(sala, a);
    if (!nodo) return;
    const char *apodo = (const char *)(nodo + 0x17C);
    const char *fmt = ((F_S12V_TEXTO_ID)S12VV(0x433380))((void *)S12VV(0x9D50C0), opcion == 0 ? 0x1FF : 0x1FE);
    static char texto[512];
    wsprintfA(texto, fmt ? fmt : "%s", apodo);
    lstrcpynA((char *)(sala + 0x9370), apodo, 32);
    ((F_S12V_CARTEL)S12VV(0x4233A0))(*(void **)S12VV(0x9314B4), texto, 2,
                                       (void *)S12VV(opcion == 0 ? 0x5912C0 : 0x5A2210), (void *)S12VV(0x58C810),
                                       sala + 0x9370, 0);
    apuntar("  [sala12_vista] tuerquita del asiento %d: %s", a, opcion == 0 ? "cambia el dueño (FF9B)" : "baneo (FF20)");
}

/* ★ 17-oct · LA «i» (anonimo03: «aparece pero no es funcional»). La de fábrica es el cUIButton +0x7A20 + a·0xD0 (sólo 0..5)
 *   y la atiende 0x5A2340, que en la de 12 no se llama ⇒ la atendemos igual que él: si el asiento es un NPC (0x48A2B0
 *   del padrón, nodo +0xD2) nada; si es mi apodo ([0x9314E0]+0x1A8) → 0x599240 (mi ficha, FF77); si no →
 *   0x58E580(sRoomUser) (su perfil, FF78). Las dos ponen su sonido. El tamaño, el del corte 8 de 02.spr. */
typedef BYTE (TCK *F_S12V_NPC)(void *padron, int asiento);                                 /* 0x48A2B0, ret 4 */
typedef void (TCK *F_S12V_USUARIO)(void *sala, void *u);                                   /* 0x58E580, ret 4 */

static int s12v_i_dentro(BYTE *sala, int x, int y)
{
    int w = 18, h = 18;
    BYTE *spr = *(BYTE **)(sala + 0x170);
    if (spr) {
        BYTE *v0 = *(BYTE **)(spr + 0x18), *v1 = *(BYTE **)(spr + 0x1C);
        if (v0 && (v1 - v0) / 0x50 > 8) {
            float *tam = (float *)(v0 + 8 * 0x50 + 0x14);
            if (tam[0] >= 8 && tam[0] <= 40 && tam[1] >= 8 && tam[1] <= 40) { w = (int)tam[0]; h = (int)tam[1]; }
        }
    }
    return s12v_dentro(x, y, w, h);
}

static void s12v_i_abrir(BYTE *sala, int a)
{
    BYTE *nodo = s12v_nodo(sala, a);
    void *padron = *(void **)S12VV(0x931660);
    BYTE *yo = *(BYTE **)S12VV(0x9314E0);
    if (!nodo || !padron || !yo) return;
    if (((F_S12V_NPC)S12VV(0x48A2B0))(padron, nodo[0xC])) return;                        /* un NPC: sin ficha */
    if (lstrcmpA((const char *)(nodo + 0x17C), (const char *)(yo + 0x1A8)) == 0) {
        ((F_S12V_SALA)S12VV(0x599240))(sala);                                              /* la mía (FF77) */
        apuntar("  [sala12_vista] la «i»: mi ficha");
    } else {
        ((F_S12V_USUARIO)S12VV(0x58E580))(sala, nodo + 0x10);                              /* la suya (FF78) */
        apuntar("  [sala12_vista] la «i» del asiento %d: su perfil", a);
    }
}

/* una tarjeta chica (asiento a) en (x, y)
 * ⛔ 3.ª vuelta (anonimo03): «el texto LISTO y Anfitrión chocan con el ícono de licencia»: LISTO mide 76×23 y Anfitrión
 *   65×21 (gr_1 13/14) y la tarjeta 102: van a 50×15 / 52×17, entre la insignia y la licencia. */
static void s12v_chica(BYTE *sala, int a, int x, int y, int equipos, int anfitrion)
{
    BYTE *nodo = s12v_nodo(sala, a);
    int color = s12v_color(sala, a, equipos);
    s12v_figura(nodo ? S12V_CORTE_COLOR[color] : S12_CORTE_VACIO, x, y);
    s12v_figura(g_s12v_n_insignia0 + color * 12 + a, x + 3, y + 3);
    if (!nodo) return;
    /* ⛔ 8.ª vuelta (anonimo03): «perdieron legibilidad al achicarlos»: 82 % del tamaño (era 66 %) y la licencia 2 px a la
     *   derecha · 9.ª: «los contornos con dientes» — los achicaba la placa de video sin suavizar: ahora vienen YA
     *   achicados con buen filtro en nuestra hoja (sala12_crear.py) y van 1:1 */
    if (a == anfitrion) s12v_figura(S12_CORTE_ANFITRION, x + 24, y + 4);           /* «Anfitrión» */
    else if (nodo[0x167]) s12v_figura(S12_CORTE_LISTO, x + 22, y + 3);             /* «LISTO» */
    s12v_licencia(nodo, x + 78, y + 2);           /* 9.ª: de vuelta a su lugar (anonimo03: «se sale de la caja») */
    s12v_texto(x + 6, y + 28, (const char *)(nodo + 0x17C));
    s12v_spr(sala, 0x170, x + 80, y + 26, s12v_i_dentro(sala, x + 80, y + 26) ? 9 : 8);   /* i (9 = resaltada) */
    int tuerca = s12v_tuerca_visible(sala, a);
    if (tuerca) {                                                                   /* ★ 17-oct: la tuerquita */
        int tx = x + S12V_TUERCA_DX, ty = y + S12V_TUERCA_DY;
        s12v_tuerca_dibujar(tx, ty, g_s12v_menu == a || s12v_dentro(tx, ty, S12V_TUERCA_W, S12V_TUERCA_W));
    }
    if (s12v_flecha_visible(sala, a)) {                                             /* ★ 14-oct: la flechita */
        if (g_s12v_band_estado == 0) s12v_band_cargar();
        int fx = x + S12V_FLECHA_DX - (tuerca ? 21 : 0), fy = y + S12V_FLECHA_DY;  /* con tuerca, más a la izquierda */
        int encima = g_s12v_mx >= fx && g_s12v_mx < fx + 21 && g_s12v_my >= fy && g_s12v_my < fy + 21;
        if (g_s12v_band_estado == 1) s12v_band_figura(encima ? 3 : 2, fx, fy);
    }
}

/* ⛔ 4.ª vuelta (anonimo03): «salió el popup, un NPC no pudo ponerse listo: el 8». El FF17 es `[asiento][listo]` y su
 *   handler (0x5CDB40) toma el asiento **7 como CÓDIGO DE ERROR** (`cmp byte [esp+4],7` en 0x5CDB62 → el cartel nº 7,
 *   «no se puede participar con 0 energía»): con 6 asientos nunca había un 7. En la sala de 12 ese 7 pasa a 0xFF
 *   (nadie lo manda); en las demás, vuelve el 7. */
#define S12V_FF17_ERROR 0x5CDB66
static void s12v_ff17(int doce)
{
    BYTE quiero = doce ? 0xFF : 7;
    if (*S12VV(S12V_FF17_ERROR) != quiero) s12v_escribir(S12V_FF17_ERROR, &quiero, 1);
}

/* la llama la lectura de la cola del FF13 (panel_sala.c), dentro de un pushad: el 7 del FF17 se cambia YA, antes de
 *   los FF17 de los NPC que llegan detrás (en el cuadro todavía no se dibujó la sala) */
/* ★ LOS 12 MUÑECOS EN LA SALA (10-oct; informe _trabajo/grupo/agente_avatares/INFORME.md). Los de los asientos 6..11
 *   ya existen (modelo, mascota, aro: el alta 0x59FDF0 no mira el asiento); sólo los frena «¿es asiento de mirón?»
 *   (`0x58DEC0`: `cmp al,6`) y la marca de mirón del FF0C (`0x528C52`). En la sala de 12 esos 6 pasan a 12 (y las copias
 *   en línea del mismo test, que son de PAREJA: el aura y el gesto de a dos). La posición la manda el server en el FF0C
 *   (2.ª fila: ajustes.FF0C_FONDO_*). Y la cámara de la sala se aleja (el double 1002 de 0x882C90 → 1500: su
 *   distancia al centrarse en mí, 0x5B34EE) para que entren las dos filas. Todo se pone al leer el FF13, antes de los
 *   FF0C. */
static const struct { DWORD va; BYTE seis; } S12V_MIRON[] = {
    { 0x58DED2, 6 }, { 0x528C54, 6 },                                   /* el test y la marca del FF0C */
    { 0x59853A, 6 }, { 0x59701C, 6 }, { 0x5929A3, 6 }, { 0x594E4A, 6 }, /* las copias (pareja) */
    { 0x594E5B, 6 }, { 0x594F49, 6 }, { 0x59E012, 6 }, { 0x59E061, 6 }, { 0x59E06E, 6 },
    /* ★ 15-oct: «¿cuántos jugadores sentados?» (0x4EBDB0 cuenta los de asiento < 6). Tras el FF6B (0x5EB4CA), si da 0
     *   el anfitrión pasa a 0xFF: el anfitrión SOLO que se pasaba al verde (7) o al naranja (10) perdía el «Anfitrión»
     *   (anonimo03). La usan también 0x4ED5EC, 0x56F444, 0x5E3032, 0x5E8F52 — todos «hay jugadores», y en la de 12 son 0..11 */
    { 0x4EBDF7, 6 } };
static double g_s12v_camara = 1200.0;

static void s12v_munecos(int doce)
{
    for (int i = 0; i < (int)(sizeof(S12V_MIRON) / sizeof(S12V_MIRON[0])); i++) {
        BYTE quiero = doce ? 12 : S12V_MIRON[i].seis;
        if (*S12VV(S12V_MIRON[i].va) != quiero) s12v_escribir(S12V_MIRON[i].va, &quiero, 1);
    }
    double d = doce ? g_s12v_camara : 1002.0;
    if (*(double *)S12VV(0x882C90) != d) s12v_escribir(0x882C90, &d, 8);
}

static void __cdecl s12v_tras_ff13(void)
{
    if (!g_s12v_activo) return;
    s12v_ff17(g_gr_sala == 12);
    s12v_munecos(g_gr_sala == 12);
}

/* la tarjeta de nombre (el adorno del nombre, nodo+0x1F5). El juego la dibuja con 0x4818D0 (ecx [0x93433C]: x, y, z,
 *   n.º, barra): la fila `0x481860(n)` dice [0] qué sprite de la lista [yo+0xC] y [1] qué corte; debajo pone un fondo
 *   de color ([yo+0x38], corte barra+5). Acá va SÓLO la placa, estirada al rectángulo pedido (el fondo es nuestra barra),
 *   y en z 0.4: el juego la pide en 0.9 y quedaba detrás de la barra (5.ª vuelta). */
typedef BYTE *(TCK *F_S12V_FILA_NOMBRE)(void *yo, int n);                                    /* 0x481860, ret 4 */
static void s12v_spr_obj_tam(BYTE *spr, int x, int y, int corte, int w, int h, float z)
{
    if (!spr) return;
    BYTE *v0 = *(BYTE **)(spr + 0x18), *v1 = *(BYTE **)(spr + 0x1C);
    if (!v0 || corte < 0 || corte >= (int)((v1 - v0) / 0x50)) return;
    float *tam = (float *)(v0 + corte * 0x50 + 0x14);
    float w0 = tam[0], h0 = tam[1];
    ((F_S12V_ZCORTE)S12VV(0x683F60))(spr, corte, z);
    ((F_S12V_TAM)S12VV(0x64DB90))(spr, corte, w, h);
    ((F_S12V_SPR)S12VV(0x683FB0))(spr, x, y, corte, 0);
    tam[0] = w0;
    tam[1] = h0;
}

static int s12v_tarjeta_nombre(BYTE *nodo, int x, int y, int w, int h)
{
    BYTE n = nodo[0x1F5];
    BYTE *yo = *(BYTE **)S12VV(0x93433C);
    if (!n || !yo) return 0;
    BYTE *fila = ((F_S12V_FILA_NOMBRE)S12VV(0x481860))(yo, n);
    if (!fila) return 0;
    BYTE **l0 = *(BYTE ***)(yo + 0xC), **l1 = *(BYTE ***)(yo + 0x10);
    if (!l0 || fila[0] >= (int)(l1 - l0)) return 0;
    int corte = fila[1], c1, c2, resto;
    bru_ajustar_grande(l0[fila[0]], &x, &y, &w, &h, &corte);   /* ★ 23-oct: la flama / el corazón, la línea a la barra */
    if (bru_par_tarjeta(l0[fila[0]], corte, &c1, &c2, &resto)) {          /* ★ 23-oct: la Bruma, animada */
        s12v_cuadro_tam(l0[fila[0]], x, y, c1, w, h, g_s12v_z_tarjeta_nombre, 0xFFFFFFFF);
        if (resto > 2)
            s12v_cuadro_tam(l0[fila[0]], x, y, c2, w, h, g_s12v_z_tarjeta_nombre, ((DWORD)resto << 24) | 0xFFFFFF);
        return 1;
    }
    s12v_spr_obj_tam(l0[fila[0]], x, y, corte, w, h, g_s12v_z_tarjeta_nombre);
    return 1;
}

static void __fastcall s12v_tarjetas(BYTE *sala)
{
    s12v_ff17(s12v_es_doce());
    if (!s12v_es_doce()) { ((F_S12V_SALA)S12VV(0x5980F0))(sala); return; }
    if (g_s12v_estado == 0) s12v_cargar();
    if (g_s12v_estado != 1) { ((F_S12V_SALA)S12VV(0x5980F0))(sala); return; }
    BYTE *padron = *(BYTE **)S12VV(0x931660);
    int mio = padron ? padron[0x40] : -1, anfitrion = padron ? padron[0x41] : -1;
    g_s12v_mio = mio; g_s12v_anf = anfitrion;
    int equipos = ((F_S12V_EQUIPOS)S12VV(0x58BFF0))(sala) ? 1 : 0;
    for (int a = 0; a < 12; a++)
        s12v_chica(sala, a, S12V_X0 + (a % 6) * S12V_DX, S12V_Y0 + (a / 6) * S12V_DY, equipos, anfitrion);
    /* la tarjeta grande: la mía */
    BYTE *yo = (mio >= 0) ? s12v_nodo(sala, mio) : NULL;
    s12v_figura(S12_CORTE_GRANDE, S12V_GX, S12V_GY);
    if (yo) {
        s12v_marco(sala, yo, mio, S12V_GX + 6, S12V_GY + 6, 142, 126);
        s12v_cara(sala, yo, mio, S12V_GX + 10, S12V_GY + 9, 134, 120);
        int color = s12v_color(sala, mio, equipos);
        /* ★ 15-oct: el ESPECTADOR de la de 12 está en el lugar 12+k (ESPECTADOR_12.md): su insignia caía en la tira del
         *   color siguiente («1» de otro color, la «tarjeta grande 1 jugador31») ⇒ sin insignia */
        if (mio < 12) s12v_figura(g_s12v_n_insignia0 + color * 12 + mio, S12V_GX + 5, S12V_GY + 5);
        s12v_licencia(yo, S12V_GX + 118, S12V_GY + 4);
        if (mio == anfitrion) s12v_spr(sala, 0x1CC, S12V_GX + 6, S12V_GY + 131, 14);
        else if (yo[0x167]) s12v_spr(sala, 0x1CC, S12V_GX + 4, S12V_GY + 130, 13);
        /* ★ el adorno del nombre (anonimo03: «falta el que va en mi nombre»): en la barra de abajo, como en el asiento */
        int barra = equipos ? (mio < 6 ? 3 : 6) : 2 + (mio % 6);
        /* ⛔ 7.ª vuelta (anonimo03): «el nombre estaba bien donde estaba; el RECUADRO le falta centrarse y estirarse para
         *   cubrir por encima al de color rojo»: el adorno va estirado a toda la barra de abajo de la tarjeta grande */
        (void)barra;
        s12v_tarjeta_nombre(yo, S12V_GX + 2, S12V_GY + 151, S12_GRANDE_W - 4, S12_GRANDE_H - 151 - 2);
        s12v_texto(S12V_GX + 12, S12V_GY + 160, (const char *)(yo + 0x17C));
        s12v_spr(sala, 0x170, S12V_GX + 128, S12V_GY + 131, s12v_i_dentro(sala, S12V_GX + 128, S12V_GY + 131) ? 9 : 8);
    }
    s12v_menu_dibujar(sala);                              /* ★ 17-oct: el menú de la tuerquita, arriba de todo */
}

/* ── ★ 14-oct · EL CARTEL DE 4 BANDERAS (relevo de 12) ───────────────────────────────────────────────────────── */
static void s12v_band_cargar(void)
{
    g_s12v_band_estado = -1;
    ((F_S12V_CREAR)S12VV(0x64E560))(g_s12v_band);
    if (!((F_S12V_CARGAR)S12VV(0x64E1E0))(g_s12v_band, S12_BANDERAS_TGA, NULL)) {
        apuntar("  [sala12_vista] ⛔ no encontré %s: el cartel de equipo queda el de 2 banderas", S12_BANDERAS_TGA);
        return;
    }
    for (int i = 0; i < S12_BANDERAS_N; i++)
        ((F_S12V_RECORTE)S12VV(0x64EC40))(g_s12v_band, 0, 0, S12_BANDERAS_CORTES[i][0], S12_BANDERAS_CORTES[i][1],
                                          S12_BANDERAS_CORTES[i][2], S12_BANDERAS_CORTES[i][3], g_s12v_z_insignia);
    g_s12v_band_estado = 1;
}

static void s12v_band_figura(int n, int x, int y)
{
    ((F_S12V_POS)S12VV(0x64D990))(g_s12v_band, n, x, y);
    ((F_S12V_COLOR)S12VV(0x64E710))(g_s12v_band, n, 0xFFFFFFFF);
    ((F_S12V_DIBUJAR)S12VV(0x64EE40))(g_s12v_band, n, 0);
}

/* dónde va el cartel: lo mismo que 0x58CF90 (ancho/2 − 0x184, alto − 0xC8) */
static void s12v_band_origen(int *x, int *y)
{
    BYTE *pant = *(BYTE **)S12VV(0x931498);
    *x = pant ? *(int *)(pant + 4) / 2 - 0x184 : 124;
    *y = pant ? *(int *)(pant + 8) - 0xC8 : 568;
}

/* 0x5AEFCC → 0x58CF90 (thiscall, sin argumentos): el cartel de equipo */
static void __fastcall s12v_banderas(BYTE *sala)
{
    if (!s12v_relevo12(sala)) { ((F_S12V_SALA)S12VV(0x58CF90))(sala); return; }
    if (g_s12v_band_estado == 0) s12v_band_cargar();
    if (g_s12v_band_estado != 1) { ((F_S12V_SALA)S12VV(0x58CF90))(sala); return; }
    int x, y;
    s12v_band_origen(&x, &y);
    s12v_band_figura(0, x, y);
    int k = *(int *)(sala + 0x93F4);                            /* el elegido (0..3; el de fábrica guarda 0 ó 1) */
    /* ★ 15-oct: el marco va en MI equipo de ahora (el «elegido» de fábrica arranca en 0 = rojo aunque uno sea verde) */
    typedef BYTE (TCK *F_S12V_EQ)(void *padron, int asiento);                       /* 0x4EC970 */
    BYTE *padron = *(BYTE **)S12VV(0x931660);
    if (padron && padron[0x40] < 12) {
        int e = ((F_S12V_EQ)S12VV(0x4EC970))(padron, padron[0x40]);
        if (e >= 1 && e <= 4) k = e - 1;
    }
    if (k >= 0 && k < 4) s12v_band_figura(1, x + S12_BANDERAS_X0 - 7 + k * S12_BANDERAS_PASO, y + 12);
}

typedef void (TCK *F_S12V_CLIC2)(void *sala, int x, int y);                                 /* 0x58D180, ret 8 */
typedef void (TCK *F_S12V_EQUIPO_PIDE)(void *red, int equipo);                              /* 0x5C70F0, ret 4 */

/* 0x5AA623 → 0x58D180 (thiscall, x, y; ret 8): los clics del cartel — 4 casilleros → FF18 1..4 */
static void __fastcall s12v_banderas_clic(BYTE *sala, void *nada, int cx, int cy)
{
    (void)nada;
    if (!s12v_relevo12(sala) || g_s12v_band_estado != 1) { ((F_S12V_CLIC2)S12VV(0x58D180))(sala, cx, cy); return; }
    int x, y;
    s12v_band_origen(&x, &y);
    for (int k = 0; k < 4; k++) {
        int x0 = x + S12_BANDERAS_X0 + k * S12_BANDERAS_PASO, y0 = y + 12;
        if (cx >= x0 && cx <= x0 + 99 && cy >= y0 && cy <= y0 + 95) {
            ((F_S12_INT)S12VV(0x40B800))(*(void **)S12VV(0x9314E4), NULL, 3);           /* el sonido del clic */
            *(int *)(sala + 0x93F4) = k;
            sala[0x9361] = 0;                                                          /* se cierra */
            ((F_S12V_EQUIPO_PIDE)S12VV(0x5C70F0))(*(void **)S12VV(0x9314D0), k + 1);
            apuntar("  [sala12_vista] relevo de 12: pidió el equipo %d (FF18)", k + 1);
            return;
        }
    }
}

typedef void (TCK *F_S12V_PIDE_CAMBIO)(void *red, int asiento);                             /* 0x5D1270, ret 4 */

/* la cueva de 0x5AA628 (el manejador del mouse de la sala, con x = ebx, y = edi, [ebp+0x14] = clic): la flechita */
static void __cdecl s12v_raton(BYTE *sala, int x, int y, int clic)
{
    g_s12v_mx = x;
    g_s12v_my = y;
    if (clic && sala && s12v_es_doce() && !sala[0x9361]) {                         /* ★ 17-oct: la tuerquita y su menú */
        if (g_s12v_menu >= 0) {
            int gx, gy, a = g_s12v_menu;
            s12v_tuerca_xy(a, &gx, &gy);
            g_s12v_menu = -1;
            for (int i = 0; i < 2; i++)
                if (s12v_dentro(gx - 39, gy + 17 + i * 25, 62, 25)) {
                    ((F_S12_INT)S12VV(0x40B800))(*(void **)S12VV(0x9314E4), NULL, 1);
                    s12v_menu_elegir(sala, a, i);
                    return;
                }
            if (s12v_dentro(gx, gy, S12V_TUERCA_W, S12V_TUERCA_W)) return;      /* la misma tuerca: cierra */
        }
        for (int a = 0; a < 12; a++) {
            int gx, gy;
            s12v_tuerca_xy(a, &gx, &gy);
            if (s12v_tuerca_visible(sala, a) && s12v_dentro(gx, gy, S12V_TUERCA_W, S12V_TUERCA_W)) {
                ((F_S12_INT)S12VV(0x40B800))(*(void **)S12VV(0x9314E4), NULL, 1);
                g_s12v_menu = a;
                return;
            }
        }
        for (int a = 0; a < 12; a++)                                                 /* ★ 17-oct: la «i» */
            if (s12v_i_dentro(sala, S12V_X0 + (a % 6) * S12V_DX + 80, S12V_Y0 + (a / 6) * S12V_DY + 26)) {
                s12v_i_abrir(sala, a);
                return;
            }
        if (g_s12v_mio >= 0 && s12v_i_dentro(sala, S12V_GX + 128, S12V_GY + 131)) {  /* la de la tarjeta grande */
            s12v_i_abrir(sala, g_s12v_mio);
            return;
        }
    }
    if (!clic || !sala || !s12v_relevo12(sala) || sala[0x9361]) return;           /* con el cartel de banderas abierto, no */
    for (int a = 0; a < 12; a++) {
        int fx = S12V_X0 + (a % 6) * S12V_DX + S12V_FLECHA_DX - (s12v_tuerca_visible(sala, a) ? 21 : 0),
            fy = S12V_Y0 + (a / 6) * S12V_DY + S12V_FLECHA_DY;
        if (x >= fx && x < fx + 21 && y >= fy && y < fy + 21 && s12v_flecha_visible(sala, a)) {
            ((F_S12_INT)S12VV(0x40B800))(*(void **)S12VV(0x9314E4), NULL, 1);       /* el sonido del botón */
            ((F_S12V_PIDE_CAMBIO)S12VV(0x5D1270))(*(void **)S12VV(0x9314D0), a);    /* FF6B [a] */
            apuntar("  [sala12_vista] relevo de 12: la flechita del asiento %d (FF6B)", a);
            return;
        }
    }
}

static void __fastcall s12v_clics(BYTE *sala, void *nada, int clic)
{
    (void)nada;
    if (s12v_es_doce()) return;                         /* etapa 2b: los clics de las tarjetas nuevas */
    ((F_S12V_SALA1)S12VV(0x5A2340))(sala, clic);
}

/* ★ 17-oct · (87) «VISUALIZAR / COMPETIR» E «INFO. DE ESPECTADORES» EN LA SALA DE 12 (anonimo03: «hoy sólo se puede
 *   espectar cuando la sala está llena · el botón Info de espectadores irá debajo del minichar grande · Visualizar/
 *   Competir es el mismo botón, alterna solo cuando se está en la fila de espectadores, y va en el mismo lugar»).
 *   El panel de fábrica es el objeto [cRoom+0x10ECC]; 0x5B61B0 lo dibuja en (5, 0x9B) — justo donde la de 12 pone la
 *   tarjeta grande — y 0x5B6140 atiende sus clics. Por dentro:
 *     · 0x5B5970(x, y): la cabecera «Info. de Espectadores» (botón +4) en (x, y) y el conmutador (botón +0xD4) ABAJO,
 *       junto a la botonera (x [0x904084]+0x58, y alto−0x3C), sólo si no soy el anfitrión ⇒ el conmutador ya queda en
 *       el mismo lugar que en la de 6: sólo se baja la cabecera.
 *     · 0x5B5DC0(mapa, x, y) la lista (fondo watch 4 en y+0x20, filas desde y+0x28 cada 0x1B) y 0x5B5BD0 sus clics:
 *       recorren los lugares 6..11 (`mov ebx,6` … `cmp eax,0xC`), que en la de 12 son CORREDORES ⇒ 12..17; y el clic
 *       en el apodo mira filas desde y = 0xC1 fijo ⇒ la nuestra.
 *     · el conmutador manda el FF99 vacío (0x5B56A0: al ir a mirar, antes el cartel 0x208 Sí/No). [obj+0xB64] = 1 dice
 *       «Visualizar» (8..10) y 0 «Competir» (5..7); lo da vuelta 0x5B5700, que llama SÓLO el FF99 de 5 bytes. En la de 12
 *       el server no usa ese FF99 (lugares 12+, ver lobby_salas.h_ff99_cambiar_de_puesto): el que cambia sale y vuelve a
 *       entrar por el FF11 ⇒ la etiqueta se pone acá según MI lugar (≥ 12 = mirando). */
#define S12V_ESP_X 5
#define S12V_ESP_Y (S12V_GY + S12_GRANDE_H + 3)
typedef BYTE (TCK *F_S12V_OBJ_SI)(void *obj);                                               /* 0x5B5810 */
typedef void (TCK *F_S12V_ESP_LISTA)(void *obj, int mapa, int x, int y);                    /* 0x5B5DC0, ret 0xC */
typedef void (TCK *F_S12V_ESP_CAB)(void *obj, int x, int y);                                /* 0x5B5970, ret 8 */
typedef void (TCK *F_S12V_BTN_SPR)(void *btn, void *spr, int a, int b, int c, int d, const char *s, int e);   /* 0x685D90 */
static const struct { DWORD va; BYTE n; DWORD seis, doce; } S12V_ESP_SITIOS[] = {
    { 0x5B5DFD, 4, 6, 12 }, { 0x5B6121, 1, 0x0C, 0x12 },             /* la lista: lugares 6..11 → 12..17 */
    { 0x5B5BF7, 4, 6, 12 }, { 0x5B5D08, 1, 0x0C, 0x12 },             /* sus clics */
    { 0x5B5C0D, 4, 0xC1, S12V_ESP_Y + 0x26 } };                      /* la 1.ª fila del clic en el apodo */
static int g_s12v_esp_ok = 0;                                         /* los sitios son los esperados */
static int g_s12v_b64_tocado = 0;

static void s12v_esp_parches(int doce)
{
    if (!g_s12v_esp_ok) return;
    for (int i = 0; i < (int)(sizeof(S12V_ESP_SITIOS) / sizeof(S12V_ESP_SITIOS[0])); i++) {
        DWORD quiero = doce ? S12V_ESP_SITIOS[i].doce : S12V_ESP_SITIOS[i].seis, hay = 0;
        CopyMemory(&hay, S12VV(S12V_ESP_SITIOS[i].va), S12V_ESP_SITIOS[i].n);
        if (hay != quiero) s12v_escribir(S12V_ESP_SITIOS[i].va, &quiero, S12V_ESP_SITIOS[i].n);
    }
}

/* la etiqueta del conmutador según MI lugar (en la de 12, mirando = 12..17) */
static void s12v_esp_boton(BYTE *obj, int tope)
{
    BYTE *padron = *(BYTE **)S12VV(0x931660);
    void *spr = *(void **)obj;
    if (!padron || !spr) return;
    BYTE quiero = padron[0x40] >= tope ? 0 : 1;                       /* 0 = mirando: «Competir» */
    if (obj[0xB64] == quiero) return;
    obj[0xB64] = quiero;
    ((F_S12V_BTN_SPR)S12VV(0x685D90))(obj + 0xD4, spr, quiero ? 8 : 5, quiero ? 9 : 6, quiero ? 10 : 7, 0,
                                       (const char *)S12VV(0x873C99), -1);
    apuntar("  [sala12_vista] el conmutador: %s (mi lugar %d)", quiero ? "Visualizar" : "Competir", padron[0x40]);
}

static void __fastcall s12v_mirones(BYTE *obj, void *nada, int mapa)
{
    (void)nada;
    int doce = s12v_es_doce();
    s12v_esp_parches(doce);
    if (!doce || !g_s12v_esp_ok) {
        /* al volver a una sala normal, la etiqueta que dejó la de 12 se acomoda una vez a mi lugar (6..11 = mirando) */
        if (g_s12v_b64_tocado) { g_s12v_b64_tocado = 0; s12v_esp_boton(obj, 6); }
        if (!doce) ((F_S12V_SALA1)S12VV(0x5B61B0))(obj, mapa);
        return;
    }
    g_s12v_b64_tocado = 1;
    s12v_esp_boton(obj, 12);
    if (!((F_S12V_OBJ_SI)S12VV(0x5B5810))(obj)) return;              /* lo de 0x5B61B0, más abajo */
    if (obj[0xB65]) ((F_S12V_ESP_LISTA)S12VV(0x5B5DC0))(obj, mapa, S12V_ESP_X, S12V_ESP_Y);
    ((F_S12V_ESP_CAB)S12VV(0x5B5970))(obj, S12V_ESP_X, S12V_ESP_Y);
}

/* ★ 17-oct · EL FF99 NATIVO EN LA DE 12 (anonimo03: «nativamente no se rehacía la sala, se cambiaba de slot»). El FF99 de 5
 *   bytes (handler 0x5E4A40, tipos 0 y 2 → 0x5A0900 → 0x5A0590) mueve al ocupante y su padrón y corrige «mi lugar» sin
 *   rehacer la sala — acepta 12..17 (sólo valida 0..5). Lo que NO hace es recalcular la marca «soy mirón» del padrón
 *   (+0xC3, la que lee 0x4440A0 al largar: C01): la pone el FF0C y, tras el FF6B, 0x528910(asiento) — que pregunta
 *   0x58DEC0 («¿es lugar de mirón?», en la de 12 ≥ 12). ⇒ después de cada movimiento del FF99, en la de 12, 0x528910 en
 *   los dos lugares (el que quedó vacío no hace nada: 0x527C70 no lo encuentra). */
typedef void (TCK *F_S12V_MOVER)(void *sala, int origen, int eq_o, int destino, int eq_d);       /* 0x5A0900, ret 0x10 */
static void __fastcall s12v_ff99_mover(BYTE *sala, void *nada, int origen, int eq_o, int destino, int eq_d)
{
    (void)nada;
    ((F_S12V_MOVER)S12VV(0x5A0900))(sala, origen, eq_o, destino, eq_d);
    if (!s12v_es_doce()) return;
    void *padron = *(void **)S12VV(0x931660);
    if (!padron) return;
    ((F_S12V_SALA1)S12VV(0x528910))(padron, origen & 0xFF);
    ((F_S12V_SALA1)S12VV(0x528910))(padron, destino & 0xFF);
    BYTE *p = (BYTE *)padron;
    apuntar("  [sala12_vista] FF99: %d → %d (mi lugar %d): marca de mirón recalculada", origen & 0xFF, destino & 0xFF, p[0x40]);
}

static void __fastcall s12v_mirones_clic(BYTE *obj, void *nada, int a, int b, int c, int d, int e, int f, int g)
{
    (void)nada;
    if (s12v_es_doce() && !g_s12v_esp_ok) return;
    ((F_S12V_SALA7)S12VV(0x5B6140))(obj, a, b, c, d, e, f, g);
}

/* ★ 15-oct · LOS AROS DEL PISO VERDE Y NARANJA (EQUIPOS_4.md §6; anonimo03: «al cambiar al verde, un efecto en el char;
 *   al naranja, la joya "pareja" sobre la cabeza»). El juego prende el aro del piso con el efecto de sala (roomfx.txt)
 *   «equipo + 1»: al cambiar de equipo (0x592EEE y 0x593088: movzx cx,bl · inc cx · movzx edx,cx → 0x5AFFD0) y al
 *   entrar (0x5B3463: 1 → 2, 2 → 3, el resto nada). Rojo 2 `circle_r` y azul 3 `circle_b` están bien; verde caía en el 4
 *   (`fx_candy_girl`, los corazones) y naranja en el 5 (`gold_ring`, la joya de pareja). Los aros nuevos los arma
 *   herramientas/aros4_crear.py (roomfx 990 / 991, rnr_room_aros4.pak) — ⚠ los Ids son los de AROS de ahí. */
#define AROS4_FX_VERDE   990
#define AROS4_FX_NARANJA 991
typedef void *(TCK *F_S12V_FX)(void *tabla, DWORD id);        /* 0x4B4080: la fila de roomfx.txt (y la carga), o NULL */
static int g_s12v_aros = -1;                                  /* ¿roomfx.txt trae los aros? (se pregunta una vez) */

static DWORD __cdecl s12v_aro_fx(DWORD equipo)
{
    equipo &= 0xFF;
    if (equipo != 3 && equipo != 4) return equipo + 1;         /* rojo y azul (y lo demás): lo de fábrica */
    if (g_s12v_aros < 0) {
        void *tabla = *(void **)S12VV(0x9316D4);
        F_S12V_FX fx = (F_S12V_FX)S12VV(0x4B4080);
        g_s12v_aros = tabla && fx(tabla, AROS4_FX_VERDE) && fx(tabla, AROS4_FX_NARANJA);
        apuntar(g_s12v_aros ? "  [sala12_vista] los aros verde y naranja (roomfx %d / %d) están"
                            : "  [sala12_vista] ⚠ roomfx.txt no trae los aros %d / %d (falta rnr_script.pak nuevo): "
                              "el verde y el naranja quedan sin aro", AROS4_FX_VERDE, AROS4_FX_NARANJA);
    }
    if (!g_s12v_aros) return 0;                                /* 0 = sin aro (el efecto 0 es la patada: no se prende) */
    return equipo == 3 ? AROS4_FX_VERDE : AROS4_FX_NARANJA;
}

/* las dos del cambio de equipo: [sitio] movzx cx,bl · inc cx · movzx edx,cx (9 bytes) → jmp cueva; sin aro → saca el
 * punto ya apilado (sub esp,0xC) y salta a después de la llamada a 0x5AFFD0 */
static int s12v_aro_cambio(DWORD sitio, DWORD despues)
{
    static const BYTE e[9] = { 0x66, 0x0F, 0xB6, 0xCB, 0x66, 0x41, 0x0F, 0xB7, 0xD1 };
    if (memcmp(S12VV(sitio), e, 9) != 0) return 0;
    BYTE *k = (BYTE *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!k) return 0;
    int i = 0, a_sin;
    k[i++] = 0x0F; k[i++] = 0xB6; k[i++] = 0xD3;                                        /* movzx edx,bl */
    k[i++] = 0x52;                                                                      /* push edx */
    k[i++] = 0xE8; *(int *)(k + i) = (int)((DWORD)s12v_aro_fx - (DWORD)(k + i + 4)); i += 4;
    k[i++] = 0x83; k[i++] = 0xC4; k[i++] = 0x04;                                        /* add esp,4 */
    k[i++] = 0x85; k[i++] = 0xC0;                                                       /* test eax,eax */
    k[i++] = 0x74; a_sin = i++;                                                         /* jz sin */
    k[i++] = 0x8B; k[i++] = 0xD0;                                                       /* mov edx,eax */
    k[i++] = 0xE9; *(int *)(k + i) = (int)((DWORD)S12VV(sitio + 9) - (DWORD)(k + i + 4)); i += 4;
    k[a_sin] = (BYTE)(i - (a_sin + 1));
    k[i++] = 0x83; k[i++] = 0xC4; k[i++] = 0x0C;                                        /* sin: add esp,0xC */
    k[i++] = 0xE9; *(int *)(k + i) = (int)((DWORD)S12VV(despues) - (DWORD)(k + i + 4)); i += 4;
    BYTE s[9] = { 0xE9, 0, 0, 0, 0, 0x90, 0x90, 0x90, 0x90 };
    *(int *)(s + 1) = (int)((DWORD)k - ((DWORD)S12VV(sitio) + 5));
    return s12v_escribir(sitio, s, 9);
}

/* ★ y al cambiar, el aro VIEJO: antes de prender el nuevo el juego borra a mano el 2 y el 3 (`push 2 · call 0x5B0020` y
 * `push 3 · mov ecx,ebx · call 0x5B0020`, la llamada en 0x592E14 y 0x592FC4) — el verde y el naranja se quedaban y se apilaban (anonimo03, 15-oct).
 * La llamada del 3 pasa a una cueva que borra el 3, el 990 y el 991 (borrar uno que no está no hace nada: el juego ya
 * borra siempre el que no tiene). 0x5B0020 es thiscall (ecx = el muñeco, el Id) y vuelve con ret 4. */
static int s12v_aro_borrar(DWORD llamada)
{
    BYTE *c = S12VV(llamada);
    if (c[-4] != 0x6A || c[-3] != 0x03 || c[-2] != 0x8B || c[-1] != 0xCB || c[0] != 0xE8   /* push 3 · mov ecx,ebx · call */ || (DWORD)(c + 5 + *(int *)(c + 1)) != (DWORD)S12VV(0x5B0020))
        return 0;
    BYTE *k = (BYTE *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!k) return 0;
    int i = 0;
#define S12V_BORRA() do { k[i++] = 0xE8; *(int *)(k + i) = (int)((DWORD)S12VV(0x5B0020) - (DWORD)(k + i + 4)); i += 4; } while (0)
    k[i++] = 0x51;                                                                      /* push ecx (el muñeco) */
    k[i++] = 0xFF; k[i++] = 0x74; k[i++] = 0x24; k[i++] = 0x08;                         /* push [esp+8] (el 3) */
    S12V_BORRA();
    k[i++] = 0x8B; k[i++] = 0x0C; k[i++] = 0x24;                                        /* mov ecx,[esp] */
    k[i++] = 0x68; *(DWORD *)(k + i) = AROS4_FX_VERDE; i += 4;                          /* push 990 */
    S12V_BORRA();
    k[i++] = 0x8B; k[i++] = 0x0C; k[i++] = 0x24;                                        /* mov ecx,[esp] */
    k[i++] = 0x68; *(DWORD *)(k + i) = AROS4_FX_NARANJA; i += 4;                        /* push 991 */
    S12V_BORRA();
    k[i++] = 0x59;                                                                      /* pop ecx */
    k[i++] = 0xC2; k[i++] = 0x04; k[i++] = 0x00;                                        /* ret 4 */
#undef S12V_BORRA
    int rel = (int)((DWORD)k - ((DWORD)c + 5));
    return s12v_escribir(llamada + 1, &rel, 4);
}

/* la de la entrada: 0x5B3463  mov al,[ebx+0x3a] · cmp al,1 · jne (7 bytes) → jmp cueva. 1 y 2 siguen por su camino de
 * fábrica; 3 y 4 arman el mismo punto (x,y,z de [ebp+8..0x10] y un 0) y empujan su aro antes de 0x5B34AC
 * (mov ecx,[ebp+0x1B8] · call 0x4B06C0); lo demás (o sin aros) salta a 0x5B34B7 como antes */
static int s12v_aro_entrada(void)
{
    static const BYTE e[7] = { 0x8A, 0x43, 0x3A, 0x3C, 0x01, 0x75, 0x20 };
    static const BYTE e2[4] = { 0x3C, 0x02, 0x75, 0x29 };
    static const BYTE e3[4] = { 0x6A, 0x03, 0x8B, 0x8D };
    if (memcmp(S12VV(0x5B3463), e, 7) || memcmp(S12VV(0x5B348A), e2, 4) || memcmp(S12VV(0x5B34AA), e3, 4)) return 0;
    BYTE *k = (BYTE *)VirtualAlloc(NULL, 128, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!k) return 0;
    int i = 0, a, a_no1, a_no2, a_no3;
#define S12V_JMP(va) do { k[i++] = 0xE9; *(int *)(k + i) = (int)((DWORD)S12VV(va) - (DWORD)(k + i + 4)); i += 4; } while (0)
    k[i++] = 0x8A; k[i++] = 0x43; k[i++] = 0x3A;                                        /* mov al,[ebx+0x3a] */
    k[i++] = 0x3C; k[i++] = 0x01; k[i++] = 0x75; a = i++; S12V_JMP(0x5B346A);           /* 1 → el rojo de fábrica */
    k[a] = (BYTE)(i - (a + 1));
    k[i++] = 0x3C; k[i++] = 0x02; k[i++] = 0x75; a = i++; S12V_JMP(0x5B348E);           /* 2 → el azul de fábrica */
    k[a] = (BYTE)(i - (a + 1));
    k[i++] = 0x3C; k[i++] = 0x03; k[i++] = 0x74; a = i++;                               /* 3 → sigue */
    k[i++] = 0x3C; k[i++] = 0x04; k[i++] = 0x75; a_no1 = i++;                           /* ni 3 ni 4 → no */
    k[a] = (BYTE)(i - (a + 1));
    k[i++] = 0x0F; k[i++] = 0xB6; k[i++] = 0xC0;                                        /* movzx eax,al */
    k[i++] = 0x50;                                                                      /* push eax */
    k[i++] = 0xE8; *(int *)(k + i) = (int)((DWORD)s12v_aro_fx - (DWORD)(k + i + 4)); i += 4;
    k[i++] = 0x83; k[i++] = 0xC4; k[i++] = 0x04;                                        /* add esp,4 */
    k[i++] = 0x85; k[i++] = 0xC0; k[i++] = 0x74; a_no2 = i++;                           /* sin aro → no */
    k[i++] = 0x83; k[i++] = 0xEC; k[i++] = 0x10;                                        /* sub esp,0x10 */
    k[i++] = 0xD9; k[i++] = 0xEE;                                                       /* fldz */
    k[i++] = 0xD9; k[i++] = 0x5C; k[i++] = 0x24; k[i++] = 0x0C;                         /* fstp [esp+0xc] */
    k[i++] = 0x8B; k[i++] = 0x4D; k[i++] = 0x08; k[i++] = 0x89; k[i++] = 0x0C; k[i++] = 0x24;               /* x */
    k[i++] = 0x8B; k[i++] = 0x4D; k[i++] = 0x0C; k[i++] = 0x89; k[i++] = 0x4C; k[i++] = 0x24; k[i++] = 0x04; /* y */
    k[i++] = 0x8B; k[i++] = 0x4D; k[i++] = 0x10; k[i++] = 0x89; k[i++] = 0x4C; k[i++] = 0x24; k[i++] = 0x08; /* z */
    k[i++] = 0x50;                                                                      /* push eax (el aro) */
    S12V_JMP(0x5B34AC);
    a_no3 = i;
    k[a_no1] = (BYTE)(a_no3 - (a_no1 + 1));
    k[a_no2] = (BYTE)(a_no3 - (a_no2 + 1));
    S12V_JMP(0x5B34B7);                                                                 /* no: como antes, sin aro */
#undef S12V_JMP
    BYTE s[7] = { 0xE9, 0, 0, 0, 0, 0x90, 0x90 };
    *(int *)(s + 1) = (int)((DWORD)k - ((DWORD)S12VV(0x5B3463) + 5));
    return s12v_escribir(0x5B3463, s, 7);
}

static void sala12_vista_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("sala12_vista", "activo", 1, ini)) {
        apuntar("  [sala12_vista] apagado ([sala12_vista] activo=0)");
        return;
    }
    g_s12v_base = (BYTE *)GetModuleHandleA(NULL);
    g_s12v_z_fondo = GetPrivateProfileIntA("sala12_vista", "z_fondo", 500, ini) / 1000.0f;
    g_s12v_z_insignia = GetPrivateProfileIntA("sala12_vista", "z_insignia", 330, ini) / 1000.0f;
    g_s12v_cara_lejos = GetPrivateProfileIntA("sala12_vista", "cara_lejos", 125, ini) / 100.0f;
    if (*(float *)S12VV(0x882460) != 125.0f || *(float *)S12VV(0x88247C) < 117.0f || *(float *)S12VV(0x88247C) > 118.0f) {
        apuntar("  [sala12_vista] ⛔ la proyección de la cara (0x882460) no es la esperada: no se toca nada");
        return;
    }
    static const struct { DWORD va, destino; void *mio; } LL[6] = {
        { 0x5AEEEE, 0x5980F0, (void *)s12v_tarjetas }, { 0x5A6FD9, 0x5A2340, (void *)s12v_clics },
        { 0x5AF10C, 0x5B61B0, (void *)s12v_mirones },  { 0x5AF5B2, 0x5B6140, (void *)s12v_mirones_clic },
        { 0x5AEFCC, 0x58CF90, (void *)s12v_banderas }, { 0x5AA623, 0x58D180, (void *)s12v_banderas_clic } };
    static const BYTE ANCHO[7] = { 0xC7, 0x45, 0x08, 0x65, 0x00, 0x00, 0x00 };
    static const BYTE FF17[5] = { 0x80, 0x7C, 0x24, 0x04, 0x07 };
    for (int i = 0; i < (int)(sizeof(S12V_MIRON) / sizeof(S12V_MIRON[0])); i++)
        if (*S12VV(S12V_MIRON[i].va) != 6) {
            apuntar("  [sala12_vista] ⛔ el «6» del mirón en 0x%06X no es el esperado: no se toca nada", S12V_MIRON[i].va);
            return;
        }
    if (*(double *)S12VV(0x882C90) != 1002.0) {
        apuntar("  [sala12_vista] ⛔ la distancia de la cámara de la sala (0x882C90) no es 1002: no se toca nada");
        return;
    }
    g_s12v_camara = GetPrivateProfileIntA("sala12_vista", "camara", 1200, ini);
    if (memcmp(S12VV(S12V_FF17_ERROR - 4), FF17, 5) != 0) {
        apuntar("  [sala12_vista] ⛔ el FF17 (0x5CDB62) no es el esperado: no se toca nada");
        return;
    }
    if (memcmp(S12VV(0x59745A), ANCHO, 7) != 0) {
        apuntar("  [sala12_vista] ⛔ el ancho de la cara (0x59745A) no es el esperado: no se toca nada");
        return;
    }
    for (int i = 0; i < 6; i++) {
        BYTE *c = S12VV(LL[i].va);
        if (c[0] != 0xE8 || (DWORD)(c + 5 + *(int *)(c + 1)) != (DWORD)S12VV(LL[i].destino)) {
            apuntar("  [sala12_vista] ⛔ la llamada de 0x%06X no es la esperada: no se toca nada", LL[i].va);
            return;
        }
    }
    /* ★ 17-oct: el FF99 nativo en la de 12 — las dos llamadas del handler (tipos 0 y 2) a 0x5A0900 */
    {
        static const DWORD FF99_MUEVE[2] = { 0x5E4AF5, 0x5E4B7D };
        int bien = 1;
        for (int i = 0; i < 2; i++) {
            BYTE *c = S12VV(FF99_MUEVE[i]);
            if (c[0] != 0xE8 || (DWORD)(c + 5 + *(int *)(c + 1)) != (DWORD)S12VV(0x5A0900)) bien = 0;
        }
        if (bien)
            for (int i = 0; i < 2; i++) {
                int rel = (int)((DWORD)s12v_ff99_mover - ((DWORD)S12VV(FF99_MUEVE[i]) + 5));
                s12v_escribir(FF99_MUEVE[i] + 1, &rel, 4);
            }
        else
            apuntar("  [sala12_vista] ⚠ el FF99 (0x5E4AF5/0x5E4B7D) no es el esperado: sin marca de mirón tras moverse");
    }
    /* ★ 17-oct (87): el panel de espectadores en la de 12 — sólo si los 5 números son los de fábrica */
    g_s12v_esp_ok = 1;
    for (int i = 0; i < (int)(sizeof(S12V_ESP_SITIOS) / sizeof(S12V_ESP_SITIOS[0])); i++) {
        DWORD hay = 0;
        CopyMemory(&hay, S12VV(S12V_ESP_SITIOS[i].va), S12V_ESP_SITIOS[i].n);
        if (hay != S12V_ESP_SITIOS[i].seis) g_s12v_esp_ok = 0;
    }
    if (!g_s12v_esp_ok)
        apuntar("  [sala12_vista] ⚠ el panel de espectadores (0x5B5DC0/0x5B5BD0) no es el esperado: en la de 12 sigue apagado");
    for (int i = 0; i < 6; i++) {
        int rel = (int)((DWORD)LL[i].mio - ((DWORD)S12VV(LL[i].va) + 5));
        s12v_escribir(LL[i].va + 1, &rel, 4);
    }
    /* ★ 14-oct: la cueva del mouse (la flechita del relevo de 12): 0x5AA628  cmp byte [esi+0x7395],0  →  jmp cueva */
    {
        static const BYTE e_raton[7] = { 0x80, 0xBE, 0x95, 0x73, 0x00, 0x00, 0x00 };
        BYTE *k = (BYTE *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
        if (k && memcmp(S12VV(0x5AA628), e_raton, 7) == 0) {
            int i = 0;
            k[i++] = 0x60;                                                              /* pushad */
            k[i++] = 0xFF; k[i++] = 0x75; k[i++] = 0x14;                                /* push [ebp+0x14] (clic) */
            k[i++] = 0x57; k[i++] = 0x53; k[i++] = 0x56;                                /* push edi (y) · ebx (x) · esi (sala) */
            k[i++] = 0xE8; *(int *)(k + i) = (int)((DWORD)s12v_raton - (DWORD)(k + i + 4)); i += 4;
            k[i++] = 0x83; k[i++] = 0xC4; k[i++] = 0x10;                                /* add esp,16 */
            k[i++] = 0x61;                                                              /* popad */
            CopyMemory(k + i, e_raton, 7); i += 7;                                      /* lo que se pisa */
            k[i++] = 0xE9; *(int *)(k + i) = (int)((DWORD)S12VV(0x5AA62F) - (DWORD)(k + i + 4)); i += 4;
            BYTE salto[7] = { 0xE9, 0, 0, 0, 0, 0x90, 0x90 };
            *(int *)(salto + 1) = (int)((DWORD)k - ((DWORD)S12VV(0x5AA628) + 5));
            s12v_escribir(0x5AA628, salto, 7);
        } else
            apuntar("  [sala12_vista] ⚠ el manejador del mouse (0x5AA628) no es el esperado: sin flechita en el relevo de 12");
    }
    g_s12v_activo = 1;
    /* ★ 15-oct · LA FLECHITA EN EL EQUIPO DE 4 (EQUIPOS_4.md: «la sala, igual al relevo»): la regla del juego
     *   «¿puedo cambiar de lugar con éste?» (0x594390) empieza con `cmp [sala+0x9568],2 · jne no` — sólo relevo. En la
     *   sala de 12 de 4 equipos (CoopMode 0 + `g_gr_equipos` 4) también pasa; el resto de la regla, la de fábrica. */
    {
        static const BYTE e_fl[13] = { 0x83, 0xBF, 0x68, 0x95, 0x00, 0x00, 0x02, 0x0F, 0x85, 0xA9, 0x00, 0x00, 0x00 };
        BYTE *k = (BYTE *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
        if (k && memcmp(S12VV(0x594398), e_fl, 13) == 0) {
            int i = 0, a_si, a_n1, a_n2, a_n3;
            k[i++] = 0x83; k[i++] = 0xBF; *(DWORD *)(k + i) = 0x9568; i += 4; k[i++] = 0x02;    /* cmp [edi+0x9568],2 */
            k[i++] = 0x74; a_si = i++;                                                           /* je si */
            k[i++] = 0x83; k[i++] = 0xBF; *(DWORD *)(k + i) = 0x9568; i += 4; k[i++] = 0x00;    /* cmp [edi+0x9568],0 */
            k[i++] = 0x75; a_n1 = i++;                                                           /* jne no */
            k[i++] = 0x80; k[i++] = 0x3D; *(DWORD *)(k + i) = (DWORD)&g_gr_equipos; i += 4; k[i++] = 0x04;
            k[i++] = 0x75; a_n2 = i++;                                                           /* jne no */
            k[i++] = 0x80; k[i++] = 0x3D; *(DWORD *)(k + i) = (DWORD)&g_gr_sala; i += 4; k[i++] = 0x0C;
            k[i++] = 0x75; a_n3 = i++;                                                           /* jne no */
            k[a_si] = (BYTE)(i - (a_si + 1));
            k[i++] = 0xE9; *(int *)(k + i) = (int)((DWORD)S12VV(0x5943A5) - (DWORD)(k + i + 4)); i += 4;   /* si */
            int no = i;
            k[i++] = 0xE9; *(int *)(k + i) = (int)((DWORD)S12VV(0x59444E) - (DWORD)(k + i + 4)); i += 4;   /* no */
            k[a_n1] = (BYTE)(no - (a_n1 + 1));
            k[a_n2] = (BYTE)(no - (a_n2 + 1));
            k[a_n3] = (BYTE)(no - (a_n3 + 1));
            BYTE s[13] = { 0xE9, 0, 0, 0, 0, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90 };
            *(int *)(s + 1) = (int)((DWORD)k - ((DWORD)S12VV(0x594398) + 5));
            s12v_escribir(0x594398, s, 13);
            apuntar("  [sala12_vista] la flechita (cambiar de lugar) también en el equipo de 4");
        } else
            apuntar("  [sala12_vista] ⚠ la regla de la flechita (0x594398) no es la esperada: sólo en el relevo");
    }
    /* ★ 15-oct: los aros del piso verde y naranja (al cambiar de equipo y al entrar) */
    {
        int c1 = s12v_aro_cambio(0x592EEE, 0x592F0B), c2 = s12v_aro_cambio(0x593088, 0x5930A5), en = s12v_aro_entrada();
        int b1 = s12v_aro_borrar(0x592E14), b2 = s12v_aro_borrar(0x592FC4);
        if (c1 && c2 && en && b1 && b2)
            apuntar("  [sala12_vista] los aros del piso: verde %d y naranja %d (ya no los corazones ni la joya)",
                    AROS4_FX_VERDE, AROS4_FX_NARANJA);
        else
            apuntar("  [sala12_vista] ⚠ los aros del piso: cambio %d/%d, entrada %d, borrar %d/%d (los 0 no son los "
                    "esperados)", c1, c2, en, b1, b2);
    }
    apuntar("  [sala12_vista] listo: la sala de 12 estilo coreano (tarjetas, clics y espectadores desviados)");
}
