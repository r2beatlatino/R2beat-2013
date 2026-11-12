/* carrera12.c — el HUD de la CARRERA DE 12 (el 6vs6, 10-oct-2026)
 *
 *   anonimo03: «en carrera hay un 1th-2th, la posición en vivo, y sólo cuenta hasta 6th · si sólo podemos dibujar 6
 *   recuadros, los primeros 5 que sean los que van por delante, y el nuestro el sexto si vamos de últimos; si vamos
 *   5.º o 4.º, sube». Investigación: documentacion/MODO_6VS6.md §14.
 *
 *   La lista de la izquierda la arma cGame (0x4F2FC0, llamada sólo desde 0x55C6CE): recorre el multimapa de PUESTOS
 *   de cGame+0xAC0 (clave = puesto 0.., valor = asiento; nodo+0xC / +0xD, «nil» +0xF; lo rehace 0x4F3850 en cada
 *   cuadro, y sus bucles ya van hasta N por grande.c) y por cada uno llama a la TARJETA 0x55A9C0(hud, puesto,
 *   posición en la lista, asiento). La tarjeta propia dibuja además el «1ST..6TH» = [hud+8] (02.tga) corte puesto+2.
 *   ⇒ En la carrera de 12, `c12_lista` la reemplaza: sólo 6 tarjetas — los 5 primeros y YO sexto si voy 7.º o más
 *     atrás (si voy entre los 6 primeros, los 6 primeros).
 *
 *   Y la tarjeta sabe de 6 asientos (arreglos del HUD de 6 por asiento). Para los asientos 6..11 se tapan los cuatro
 *   sitios donde los usa, sin cambiar nada para 0..5 (por eso se instalan siempre):
 *     · la insignia «1P..6P» = [hud+0xC] (01.tga) corte asiento+4 / +0x43 / +0x49 (por asiento / rojo / azul)
 *         → c12_pos / c12_dib la cambian por la NUESTRA 7P..12P (sala12_carrera.tga, en rnr_ui_sala12.pak)
 *     · el «7TH..12TH» (puesto+2 caería en los números grandes de la cuenta regresiva) → el nuestro, del coreano
 *     · el color de la tarjeta (tabla de 6 en 0x55AC71: con asiento > 5 el color ERA el número de asiento, casi
 *       transparente) → la cueva usa el del asiento −6
 *     · la lista de ítems del asiento ([hud + 0xAA8 + asiento*0x1C], 6 listas: con 6..11 se lee FUERA) → se saltea
 *     · el botón de «mirar» ([hud + 0x4CC + asiento*0xD0], sólo para espectadores) → no se toca con 6..11
 *   [carrera12] activo=0 lo apaga · z (milésimas, 100: la del 1ST de fábrica) · cola=1 (PRUEBA: los 6 últimos).
 *
 *   ★★ 14-oct, TRES ARREGLOS (anonimo03: «el 5TH sólo sale en mi char · el gráfico de abajo, todos rojos, los azules
 *   sin iconito · los del equipo rojo tienen su 6P con su color, los azules no»). MEDIDO con una sonda de 0x64D990:
 *     1 · el PUESTO: la tarjeta (0x55A9C0) dibuja el «5TH» grande sólo en la propia ([hud+8] corte puesto+2) ⇒ en
 *         c12_lista, después de cada tarjeta ajena, el puesto CHICO nuestro (S12_PUESTO_CHICO + puesto) arriba a la
 *         derecha de la tarjeta ([carrera12] th_x / th_y).
 *     2 · la BARRA DE ABAJO (0x551BB0): un bucle de 6 (ebx += 7 hasta 0x2A) que pone el marcador «k+1» (corte 10+k
 *         de [hud+0xC], la columna ROJA de 01.tga) del corredor k en su avance ([cPlayer+0x20] → 0x550CE0) ⇒ los
 *         dos llamados del marcador (0x551CB5 / 0x551CC0) van al NUESTRO, rojo o azul según el equipo (0x4EC970), con
 *         el escalón vertical a la mitad (12 en el lugar de 6), y la llamada del final (0x551D55 → 0x550D70) dibuja
 *         antes los corredores 6..11 con la misma cuenta.
 *     3 · la INSIGNIA del recuadro de golpe (0x552680): asiento = [hud+0xA2B], equipo [hud+0xA2C] (0 por asiento,
 *         1 rojo +0x43, 2 azul +0x49) — con 6..11 el azul caía en otros cortes (83, 84) ⇒ sus dos llamados
 *         (0x55274B / 0x552756) pasan por c12_pos / c12_dib con ESE asiento: la 7P..12P nuestra del color.
 *
 *   ⚠ OJO, medido en la 1.ª prueba (10-oct): el «asiento» que recibe la tarjeta NO es el asiento de la sala: es el
 *   número de CORREDOR de la carrera (el padrón de cGame; yo soy siempre el 0 = «1P»). Por eso 7P..12P son los
 *   corredores 6..11, y con los NPC empatados (corren todos igual) nunca entran entre los 5 primeros.
 */
#define C12V(x) (g_c12_base + ((DWORD)(x) - 0x400000))

static BYTE  *g_c12_base = NULL;
static int    g_c12_activo = 0;
static BYTE   g_c12_hoja[0x100];                  /* el c2DImage de la hoja (la clase ocupa 0x40) */
static int    g_c12_estado = 0;                   /* 0 sin cargar · 1 lista · -1 no se usa */
static float  g_c12_z = 0.1f;
static float  g_c12_z_insignia = 0.5f;            /* si no se halla la de fábrica */
static int    g_c12_asiento = -1;                 /* la tarjeta que se está dibujando (sólo dentro de c12_lista) */
static int    g_c12_puesto = -1;
static int    g_c12_redirigido = -1;              /* el corte nuestro que puso c12_pos, para que lo dibuje c12_dib */
static BYTE  *g_c12_cuevas = NULL;
static int    g_c12_listas = 0;                   /* cuántas listas de 12 se dibujaron (para el log) */
static int    g_c12_cola = 0;                     /* [carrera12] cola=1: PRUEBA, la lista muestra los 6 ÚLTIMOS */
static int    g_c12_medir = 0;                    /* [carrera12] medir=1: anota los 12 corredores 1 vez por segundo */
static int    g_c12_th_x = 104, g_c12_th_y = -5;  /* ★ 14-oct: el puesto chico de las tarjetas ajenas: su CENTRO
                                                     (desde el x de la tarjeta) y alto, [carrera12] th_x / th_y */
static DWORD  g_c12_medido = 0;

typedef void (TCK *F_C12_LISTA)(void *g);                                          /* 0x4F2FC0 */
typedef void (TCK *F_C12_TARJETA)(void *hud, int puesto, int pos, int asiento);    /* 0x55A9C0, ret 0xC */
typedef void (TCK *F_C12_POS)(void *spr, int corte, int x, int y);                 /* 0x64D990, ret 0xC */
typedef void (TCK *F_C12_DIB)(void *spr, int corte, int banderas);                 /* 0x64EE40, ret 8 */
typedef void (TCK *F_C12_BOTON7)(void *b, int a, int c, int d, int e, int f, int g, int h);   /* 0x685D90, ret 0x1C */
typedef void (TCK *F_C12_BOTON2)(void *b, int x, int y);                           /* 0x685900, ret 8 */
typedef void (TCK *F_C12_BOTON3)(void *b, int a, int c, int d);                    /* 0x685920, ret 0xC */
typedef void *(TCK *F_C12_CREAR)(void *self);
typedef int   (TCK *F_C12_CARGAR)(void *self, const char *ruta, const char *prefijo);
typedef void  (TCK *F_C12_RECORTE)(void *self, float x, float y, int u, int v, int w, int h, float z);
typedef int   (TCK *F_C12_AVANCE_X)(void *hud, float avance, int ancho, int n);        /* 0x550CE0, ret 0xC */
typedef void  (TCK *F_C12_BARRA_FIN)(void *hud, int arg);                           /* 0x550D70, ret 4 */

/* las llamadas que se desvían: (sitio del `call`, a quién llama hoy) */
#define C12_LLAMA_LISTA 0x55C6CE
static const DWORD C12_POS_SITIOS[4] = { 0x55AB21, 0x55AD34, 0x55AD6C, 0x55ADAE };      /* → 0x64D990 */
static const DWORD C12_DIB_SITIOS[4] = { 0x55AB2C, 0x55AD3F, 0x55AD77, 0x55ADB9 };      /* → 0x64EE40 */
static const DWORD C12_BOTON7_SITIOS[2] = { 0x55AB9B, 0x55AC31 };                       /* → 0x685D90 */
#define C12_BOTON2_SITIO 0x55AC48                                                       /* → 0x685900 */
#define C12_BOTON3_SITIO 0x55AC58                                                       /* → 0x685920 */
/* ★ 14-oct: la barra de abajo (0x551BB0) y la insignia del recuadro de golpe (0x552680) */
#define C12_BARRA_POS 0x551CB5       /* → 0x64D990 (el marcador «k+1») */
#define C12_BARRA_DIB 0x551CC0       /* → 0x64EE40 */
#define C12_BARRA_FIN 0x551D55       /* → 0x550D70 (después del bucle de 6) */
#define C12_GOLPE_POS 0x55274B       /* → 0x64D990 (la insignia «nP») */
#define C12_GOLPE_DIB 0x552756       /* → 0x64EE40 */
#define C12_COLOR 0x55AC71           /* cmp ebx,5 · ja 0x55ACBC · jmp [ebx*4+0x55B178]   (12 bytes) */
#define C12_ITEMS 0x55AE2F           /* mov eax,[esp+0x4C] · lea ecx,[eax*8]               (11 bytes) */
#define C12_ITEMS_F1 0x550C00       /* movzx eax,byte [esp+4] · sub esp,8      (8 bytes, ret 8) */
#define C12_ITEMS_F2 0x554580       /* mov eax,[esp+8] · sub esp,8              (7 bytes, ret 8) */
static const BYTE C12_ITEMS_F1_BYTES[8] = { 0x0F, 0xB6, 0x44, 0x24, 0x04, 0x83, 0xEC, 0x08 };
static const BYTE C12_ITEMS_F2_BYTES[7] = { 0x8B, 0x44, 0x24, 0x08, 0x83, 0xEC, 0x08 };
static const BYTE C12_COLOR_BYTES[12] = { 0x83, 0xFB, 0x05, 0x77, 0x46, 0xFF, 0x24, 0x9D, 0x78, 0xB1, 0x55, 0x00 };
static const BYTE C12_ITEMS_BYTES[11] = { 0x8B, 0x44, 0x24, 0x4C, 0x8D, 0x0C, 0xC5, 0x00, 0x00, 0x00, 0x00 };

static int c12_escribir(DWORD va, const void *b, int n)
{
    DWORD viejo = 0;
    if (!VirtualProtect(C12V(va), n, PAGE_EXECUTE_READWRITE, &viejo)) return 0;
    CopyMemory(C12V(va), b, n);
    VirtualProtect(C12V(va), n, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), C12V(va), n);
    return 1;
}

static int c12_llama_a(DWORD sitio, DWORD destino)
{
    BYTE *c = C12V(sitio);
    return c[0] == 0xE8 && (DWORD)(c + 5 + *(int *)(c + 1)) == (DWORD)C12V(destino);
}

static void c12_desviar(DWORD sitio, void *a)
{
    int rel = (int)((DWORD)a - ((DWORD)C12V(sitio) + 5));
    c12_escribir(sitio + 1, &rel, 4);
}

static void c12_cargar(void)
{
    g_c12_estado = -1;
    ((F_C12_CREAR)C12V(0x64E560))(g_c12_hoja);
    if (!((F_C12_CARGAR)C12V(0x64E1E0))(g_c12_hoja, S12_CARRERA_TGA, NULL)) {
        apuntar("  [carrera12] ⛔ no encontré %s (¿falta rnr_ui_sala12.pak?): la lista de 12 sale sin 7P..12P ni"
                " 7TH..12TH", S12_CARRERA_TGA);
        return;
    }
    F_C12_RECORTE rec = (F_C12_RECORTE)C12V(0x64EC40);
    const float MARCA = 0.1234f;                               /* la z provisoria de las insignias, para hallarla */
    int nc = (int)(sizeof(S12_CARRERA_CORTES) / sizeof(S12_CARRERA_CORTES[0]));
    for (int i = 0; i < nc; i++)
        rec(g_c12_hoja, 0, 0, S12_CARRERA_CORTES[i][0], S12_CARRERA_CORTES[i][1], S12_CARRERA_CORTES[i][2],
            S12_CARRERA_CORTES[i][3], i < 6 ? g_c12_z : MARCA);
    /* ★ 2.ª prueba (anonimo03, 10-oct): la insignia 7P tapaba el «48» del nivel, y la 1P de fábrica queda DEBAJO. Las
     *   insignias tienen que ir a la MISMA z que las de fábrica: se busca en qué lugar del corte (0x50 B) quedó la
     *   marca y se copia de ahí la z del corte 4 («1P») de [hud+0xC]. */
    BYTE *nuestros = *(BYTE **)(g_c12_hoja + 0x18);
    BYTE *hud = *(BYTE **)C12V(0x931670);
    BYTE *fab = hud && *(BYTE **)(hud + 0xC) ? *(BYTE **)(*(BYTE **)(hud + 0xC) + 0x18) : NULL;
    int o = -1;
    for (int k = 0; nuestros && k < 0x50; k += 4)
        if (*(float *)(nuestros + 6 * 0x50 + k) == MARCA && *(float *)(nuestros + k) == g_c12_z) { o = k; break; }
    float z = g_c12_z_insignia;
    if (o >= 0 && fab) {
        float zf = *(float *)(fab + 4 * 0x50 + o);
        if (zf > 0.0f && zf <= 1.0f) z = zf;
    }
    for (int i = 6; o >= 0 && i < nc; i++) *(float *)(nuestros + i * 0x50 + o) = z;
    apuntar("  [carrera12] z de las insignias: %d/1000 (%s, en el corte +0x%X)", (int)(z * 1000),
            o < 0 ? "⚠ no hallé dónde va la z" : z == g_c12_z_insignia ? "la del ini" : "la de la 1P de fábrica", o);
    g_c12_estado = 1;
    apuntar("  [carrera12] ★ hoja de la carrera cargada: %d cortes",
            (int)(sizeof(S12_CARRERA_CORTES) / sizeof(S12_CARRERA_CORTES[0])));
}

/* ★ 14-oct · relevo de 12: el equipo del corredor k (1 rojo · 2 azul · 3 verde · 4 naranja; 0 si no hay equipos) */
typedef BYTE (TCK *F_C12_EQUIPO0)(void *padron, int asiento);                      /* 0x4EC970 */
static int c12_equipo(int k)
{
    void *padron = *(void **)C12V(0x931660);
    return padron ? ((F_C12_EQUIPO0)C12V(0x4EC970))(padron, k) : 0;
}

/* ★ 14-oct: la lista del relevo de 12 la arma relevo12.c (está después en la compilación): la pone acá al iniciar */
static void (*g_c12_lista_relevo)(BYTE *g) = NULL;

/* ¿este corte de este sprite de la tarjeta es uno de los que faltan? → el corte NUESTRO, o −1 */
static int c12_corte_nuestro(void *spr, int corte)
{
    if (g_c12_asiento < 0 || g_c12_estado != 1) return -1;
    BYTE *hud = *(BYTE **)C12V(0x931670);
    if (!hud) return -1;
    if (spr == *(void **)(hud + 8) && g_c12_puesto >= 6 && g_c12_puesto < 12 && corte == g_c12_puesto + 2)
        return g_c12_puesto - 6;                                         /* 7TH..12TH */
    if (spr == *(void **)(hud + 0xC) && g_c12_asiento >= 6 && g_c12_asiento < 12) {
        int d = corte - g_c12_asiento;
        int col = d == 4 ? 0 : d == 0x43 ? 1 : d == 0x49 ? 2 : -1;
        if (col >= 1) {                                                  /* ★ 14-oct: los equipos 3 y 4 del relevo de 12 */
            int e = c12_equipo(g_c12_asiento);
            if (e == 3) return S12_INSIG_VERDE + (g_c12_asiento - 6);
            if (e == 4) return S12_INSIG_NARANJA + (g_c12_asiento - 6);
        }
        if (col >= 0) return 6 + col * 6 + (g_c12_asiento - 6);          /* 7P..12P */
    }
    return -1;
}

static void __fastcall c12_pos(void *spr, void *nada, int corte, int x, int y)
{
    (void)nada;
    int mio = c12_corte_nuestro(spr, corte);
    g_c12_redirigido = mio;
    if (mio >= 0) ((F_C12_POS)C12V(0x64D990))(g_c12_hoja, mio, x, y);
    else ((F_C12_POS)C12V(0x64D990))(spr, corte, x, y);
}

static void __fastcall c12_dib(void *spr, void *nada, int corte, int banderas)
{
    (void)nada;
    if (g_c12_redirigido >= 0) {
        int mio = g_c12_redirigido;
        g_c12_redirigido = -1;
        ((F_C12_DIB)C12V(0x64EE40))(g_c12_hoja, mio, banderas);
        return;
    }
    ((F_C12_DIB)C12V(0x64EE40))(spr, corte, banderas);
}

/* el botón de «mirar» de cada asiento (6 en el HUD): con 6..11 sería memoria ajena.
 * ★ 14-oct · EL ESPECTADOR EN LA SALA DE 12 (ESPECTADOR_12.md): la tarjeta de un 7..12 usa PRESTADO el botón de un
 *   asiento 1..6 que en ese cuadro no tiene tarjeta (g_c12_boton_sust), y el clic de ese botón se traduce al 7..12
 *   (c12_mirar: g_c12_boton_de). Así el juego dibuja, resalta y atiende el clic como con los suyos. */
static int g_c12_boton_sust = -1;                 /* el botón prestado a la tarjeta que se está dibujando */
static int g_c12_boton_de[6] = { -1, -1, -1, -1, -1, -1 };   /* botón f → el asiento 7..12 al que mira (o -1) */
static void *c12_boton_de(void *b)
{
    if (g_c12_asiento < 6) return b;
    if (g_c12_boton_sust < 0) return NULL;
    BYTE *hud = *(BYTE **)C12V(0x931670);
    return hud ? hud + 0x4CC + g_c12_boton_sust * 0xD0 : NULL;
}

static void __fastcall c12_boton7(void *b, void *nada, int a, int c, int d, int e, int f, int g, int h)
{
    (void)nada;
    if (!(b = c12_boton_de(b))) return;
    ((F_C12_BOTON7)C12V(0x685D90))(b, a, c, d, e, f, g, h);
}

static void __fastcall c12_boton2(void *b, void *nada, int x, int y)
{
    (void)nada;
    if (!(b = c12_boton_de(b))) return;
    ((F_C12_BOTON2)C12V(0x685900))(b, x, y);
}

static void __fastcall c12_boton3(void *b, void *nada, int a, int c, int d)
{
    (void)nada;
    if (!(b = c12_boton_de(b))) return;
    ((F_C12_BOTON3)C12V(0x685920))(b, a, c, d);
}

/* 0x54D888 → 0x563930(asiento, 1) «pasar a mirar a»: el botón prestado f mira al asiento que tiene anotado */
typedef void (TCK *F_C12_MIRAR)(void *g, int asiento, int x);
static void __fastcall c12_mirar(void *g, void *nada, int asiento, int x)
{
    (void)nada;
    int a = asiento & 0xFF;
    if (a < 6 && g_c12_boton_de[a] >= 0) asiento = g_c12_boton_de[a];
    ((F_C12_MIRAR)C12V(0x563930))(g, asiento, x);
}

/* el nodo siguiente (en orden) del árbol del multimapa: izquierda +0, padre +4, derecha +8, «nil» +0xF */
static BYTE *c12_siguiente(BYTE *x)
{
    BYTE *r = *(BYTE **)(x + 8);
    if (!r[0xF]) {
        while (!(*(BYTE **)r)[0xF]) r = *(BYTE **)r;
        return r;
    }
    BYTE *p = *(BYTE **)(x + 4);
    while (!p[0xF] && x == *(BYTE **)(p + 8)) { x = p; p = *(BYTE **)(p + 4); }
    return p;
}

typedef BYTE (TCK *F_C12_EQUIPO)(void *padron, int asiento);                       /* 0x4EC970: nodo+0x4A */

/* ★ EN EQUIPOS (anonimo03, 10-oct): «la mitad de arriba para el equipo que va ganando, sus 3 que van en la punta; la de
 *   abajo el que va perdiendo, sus 3 mejores; si el que pierde toma la delantera, intercambian · y en mi equipo yo
 *   siempre ocupo uno de esos 3 lugares según mi desempeño». «Va ganando» = ★ 14-oct: el que va ganando la CARRERA
 *   A 3 (el primero que junta 3 en el orden de ahora), la misma regla con la que el server decide el ganador de la sala
 *   de 12 (`lobby_carrera.ganador_por_llegada`, DOCE_GANA_CON). Antes era el equipo del 1.º.
 *   Si no hay dos equipos de verdad (el padrón no los trae), devuelve 0 y queda la lista de siempre. */
static int c12_por_equipo(const BYTE *puesto, const BYTE *asiento, int n, int iyo, int *lista, int *pk)
{
    (void)puesto;
    void *padron = *(void **)C12V(0x931660);
    if (!padron || n < 1) return 0;
    BYTE eq[GR_TOPE];
    for (int i = 0; i < n; i++) eq[i] = ((F_C12_EQUIPO)C12V(0x4EC970))(padron, asiento[i]);
    BYTE primero = eq[0];
    int cuenta[3] = { 0, 0, 0 };
    for (int i = 0; i < n; i++)
        if ((eq[i] == 1 || eq[i] == 2) && ++cuenta[eq[i]] == 3) { primero = eq[i]; break; }
    if (primero != 1 && primero != 2) return 0;
    BYTE segundo = primero == 1 ? 2 : 1;
    int k = 0;
    for (int t = 0; t < 2; t++) {
        BYTE e = t == 0 ? primero : segundo;
        int sel[3], m = 0;
        for (int i = 0; i < n && m < 3; i++)
            if (eq[i] == e) sel[m++] = i;
        /* yo en mi equipo: si no estoy entre sus 3 primeros, ocupo el 3.º lugar */
        if (iyo >= 0 && eq[iyo] == e && m > 0) {
            int esta = 0;
            for (int j = 0; j < m; j++) esta |= sel[j] == iyo;
            if (!esta) sel[m - 1 < 2 ? m - 1 : 2] = iyo;
        }
        for (int j = 0; j < m; j++) lista[k++] = sel[j];
    }
    *pk = k;
    return k > 0;
}

/* ★ EL MEDIDOR DE LOS NPC QUE JUEGAN (11-oct). Una vez por segundo, de cada corredor (cGame+0xA14, el vector de
 *   cPlayer): el tiempo [+0x18], su paso [+0x1C], la posición en la pista [+0x20], la velocidad [+0x58], su contador
 *   [+0x68] (es el que resta el que recibe un 0x05: destino = A + contador − secuencia), [+0x54] y el estado [+0x2A0].
 *   Los float van ×100 (wvsprintf no sabe de float). Va al d3d9_proxy.log. */
static void c12_medir(BYTE *g)
{
    DWORD ahora = GetTickCount();
    if (ahora - g_c12_medido < 1000) return;
    g_c12_medido = ahora;
    BYTE **ini = *(BYTE ***)(g + 0xA14), **fin = *(BYTE ***)(g + 0xA18);
    if (!ini || fin <= ini) return;
    int total = (int)(fin - ini) < 12 ? (int)(fin - ini) : 12;
    for (int mitad = 0; mitad < total; mitad += 6) {                     /* de a 6 por línea: apuntar corta en 512 */
        char linea[480];
        int n = wsprintfA(linea, "  [medir] ");
        for (int i = mitad; i < total && i < mitad + 6; i++) {
            BYTE *p = ini[i];
            if (!p) continue;
            n += wsprintfA(linea + n, "%d:t%d p%d v%d c%d s%X%s ", i, (int)(*(float *)(p + 0x18) * 100),
                           (int)(*(float *)(p + 0x20) * 100), (int)(*(float *)(p + 0x58) * 1000),
                           *(WORD *)(p + 0x68), *(DWORD *)(p + 0x2A0), *(DWORD *)(p + 0x54) ? "*" : "");
        }
        apuntar("%s", linea);
    }
}

/* ── ★ 14-oct · 2 · la BARRA DE ABAJO ─────────────────────────────────────────────────────────────────────────────
 * ¿es la carrera de 12 (no relevo)? y el color del corredor k: azul si es del equipo 2 en una carrera por equipos */
static int g_c12_barra_vistos = 0;

static int c12_es_doce(void)
{
    BYTE *g = *(BYTE **)C12V(0x9314C8);
    return g_c12_activo && g_gr_puesto > 6 && g && g_c12_estado == 1;     /* ★ 14-oct: también el relevo de 12 */
}

static int c12_marca(int k)
{
    BYTE *g = *(BYTE **)C12V(0x9314C8);
    void *padron = *(void **)C12V(0x931660);
    int e = g && (*(WORD *)(g + 0xC) & 0x44) && padron ? ((F_C12_EQUIPO)C12V(0x4EC970))(padron, k) : 0;
    return (e == 2 ? S12_MARCA_AZUL : e == 3 ? S12_MARCA_VERDE : e == 4 ? S12_MARCA_NARANJA : S12_MARCA_ROJO) + k;
}

/* el marcador de los corredores 0..5 (lo pone el bucle de fábrica): el corte de fábrica es 10 + k (0x551CA1: lea edi,
 * [edi+edx+0xa], con edi = 0 salvo un modo raro que lo corre −2: ése se deja como está), y el escalón vertical va a la
 * mitad (7·k → 3,5·k: 12 en el lugar de 6). ⛔ 1.ª versión: k leído de la pila del llamador — dio basura (todos «12»). */
static void __fastcall c12_barra_pos(void *spr, void *nada, int corte, int x, int y)
{
    (void)nada;
    if (!c12_es_doce() || corte < 10 || corte > 15) {
        g_c12_redirigido = -1;
        ((F_C12_POS)C12V(0x64D990))(spr, corte, x, y);
        return;
    }
    int k = corte - 10;
    g_c12_redirigido = c12_marca(k);
    if (g_c12_barra_vistos < 12) {                                     /* las primeras: el corredor y el color */
        g_c12_barra_vistos++;
        apuntar("  [carrera12] barra: corredor %d (corte de fabrica %d) -> marcador %d (%d = rojo, %d = azul)", k, corte,
                g_c12_redirigido, S12_MARCA_ROJO, S12_MARCA_AZUL);
    }
    ((F_C12_POS)C12V(0x64D990))(g_c12_hoja, g_c12_redirigido, x, y - (7 * k) / 2);
}

/* los corredores 6..11, con la misma cuenta que el bucle (0x551C00..0x551CC5), antes de lo que sigue (0x550D70) */
static void __fastcall c12_barra_fin(BYTE *hud, void *nada, int arg)
{
    (void)nada;
    BYTE *g = *(BYTE **)C12V(0x9314C8);
    if (c12_es_doce() && hud) {
        BYTE **ini = *(BYTE ***)(g + 0xA14), **fin = *(BYTE ***)(g + 0xA18);
        int n = ini && fin > ini ? (int)(fin - ini) : 0;
        BYTE *aux = *(BYTE **)C12V(0x931498);
        for (int k = 6; k < n && k < 12 && aux; k++) {
            BYTE *p = ini[k];
            if (!p || *(DWORD *)(p + 0x54) || (p[0x140] & 0x10)) continue;       /* los mismos que saltea el bucle */
            int ax = ((F_C12_AVANCE_X)C12V(0x550CE0))(hud, *(float *)(p + 0x20), 0x310, 6);
            int x = *(int *)C12V(0x904084) + ax - 0x190;
            int y = *(int *)(aux + 8) + (7 * k) / 2 + arg - 0x3B;
            int c = c12_marca(k);
            ((F_C12_POS)C12V(0x64D990))(g_c12_hoja, c, x, y);
            ((F_C12_DIB)C12V(0x64EE40))(g_c12_hoja, c, 0);
        }
    }
    ((F_C12_BARRA_FIN)C12V(0x550D70))(hud, arg);
}

/* ── ★ 14-oct · 3 · la INSIGNIA del recuadro de golpe: el asiento es [hud+0xA2B] ─────────────────────────────── */
static void __fastcall c12_golpe_pos(void *spr, void *nada, int corte, int x, int y)
{
    (void)nada;
    BYTE *hud = *(BYTE **)C12V(0x931670);
    if (hud && g_c12_activo) {
        if (g_c12_estado == 0) c12_cargar();
        g_c12_asiento = hud[0xA2B];
        g_c12_puesto = -1;
    }
    c12_pos(spr, NULL, corte, x, y);
    g_c12_asiento = -1;
}

/* ── ★ 14-oct · 1 · el PUESTO CHICO en las tarjetas ajenas ──────────────────────────────────────────────────────── */
static void c12_puesto_chico(int puesto, int y0)
{
    BYTE *hud = *(BYTE **)C12V(0x931670);
    if (!hud || g_c12_estado != 1 || puesto < 0 || puesto > 11) return;
    int c = S12_PUESTO_CHICO + puesto;
    int x0 = 0x15 - *(int *)(hud + 0xA1C);                                     /* el x de la tarjeta (0x55AAC8) */
    int x = x0 + g_c12_th_x - S12_CARRERA_CORTES[c][2] / 2;                    /* centrado (anonimo03: «no están centrados») */
    ((F_C12_POS)C12V(0x64D990))(g_c12_hoja, c, x, y0 + g_c12_th_y);
    ((F_C12_DIB)C12V(0x64EE40))(g_c12_hoja, c, 0);
}

/* ── ★ 15-oct · LA LISTA DEL EQUIPO DE 4 (EQUIPOS_4.md) ──────────────────────────────────────────────────────────────
 *   Como la del relevo de 12 (la que aprobó anonimo03): UNA tarjeta por equipo — su mejor corredor — ordenadas por cómo
 *   va la carrera a 3 (gana el 1.º que mete a sus 3: va adelante el equipo cuyo ÚLTIMO corredor va más adelante), con
 *   el puesto del equipo (1ST..4TH) y debajo la fila chica de sus 3 en el orden de la carrera (yo, entero; los demás
 *   un poco apagados). Los ojitos de 7..12 con el botón prestado, como la lista de 12. */
typedef void (TCK *F_C12_TINTE)(void *spr, int n, DWORD argb);                      /* 0x64E710 */
/* ★ 15-oct · EL FOCO DE CADA EQUIPO (anonimo03: «sólo podemos hacer clic en el ojito del que va primero de cada equipo;
 *   que los números chicos sirvan para cambiar manualmente la foto a otro jugador de ese equipo, y así hacer clic al
 *   mismo botón de la camarita — así no metés más elementos»). Tocar un número de la fila de un equipo pone a ESE en
 *   la tarjeta (foto, nombre, «nP» y el botón de mirar, que sale del asiento de la tarjeta); tocar el que ya está
 *   vuelve al automático (el mejor del equipo; en la tarjeta grande del espectador, el que mira). Igual en TODOS los
 *   equipos, también en la grande (anonimo03: «si soy espectador, al hacer clic al 3 o al 2, el char, el nombre y el slot
 *   deben cambiar al dueño de ese número» — ⛔ 1.er intento: en la grande el número cambiaba la cámara directo y la
 *   tarjeta quedaba clavada en el que mira). Se olvida si el elegido deja de estar en la fila (⚠ no al empezar otra
 *   carrera: el juego reusa el cGame). El clic: el mouse del juego (0x93156C), con flanco del botón izquierdo. */
static int   g_c12_foco4[5] = { -1, -1, -1, -1, -1 };    /* equipo 1..4 → el asiento elegido (o -1 = el mejor) */
static void *g_c12_foco4_de = NULL;                      /* el cGame de esa elección */
static int   g_c12_foco4_antes = 0;                      /* el botón izquierdo en el cuadro anterior */
#define C12_MARCA_PASO 23
#define C12_MARCA_LADO 20

/* ★ 15-oct · UNA SOLA TARJETA GRANDE («minichar»; anonimo03: «el corredor deja de ver el minichar si no está primero en
 *   su equipo · el corredor debe ver el minichar de quien esté primero de su equipo · el espectador, el de quien está
 *   mirando · sólo 1 por corredor / espectador»). La tarjeta 0x55A9C0 se agranda (alto 0x78, el marco 0x3F, el «nTH»
 *   grande) cuando su asiento es «yo» — y «yo» lo lee TRES veces: 0x55AA18, 0x55AAC5 y 0x55B01E (cGame+0x5D mirando,
 *   el padrón +0x40 corriendo). Las tres cuevas, tras leerlo, lo cambian por `g_c12_yo_tarjeta` si no es -1: así la
 *   lista de 4 equipos elige CUÁL va grande (fuera de esa lista vale -1 y todo queda de fábrica). */
static volatile int g_c12_yo_tarjeta = -1;

static int c12_cueva_yo(DWORD sitio, int n, BYTE reg_modrm, DWORD vuelta)
{
    BYTE *k = (BYTE *)VirtualAlloc(NULL, 48, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!k) return 0;
    int i = 0;
    CopyMemory(k, C12V(sitio), n); i += n;                                              /* lo de fábrica */
    k[i++] = 0x83; k[i++] = 0x3D; *(DWORD *)(k + i) = (DWORD)&g_c12_yo_tarjeta; i += 4; k[i++] = 0xFF;   /* cmp [g],-1 */
    k[i++] = 0x74; k[i++] = 0x06;                                                       /* je (salta el mov) */
    k[i++] = 0x8B; k[i++] = reg_modrm; *(DWORD *)(k + i) = (DWORD)&g_c12_yo_tarjeta; i += 4;   /* mov reg,[g] */
    k[i++] = 0xE9; *(int *)(k + i) = (int)((DWORD)C12V(vuelta) - (DWORD)(k + i + 4)); i += 4;
    BYTE s[8] = { 0xE9, 0, 0, 0, 0, 0x90, 0x90, 0x90 };
    *(int *)(s + 1) = (int)((DWORD)k - ((DWORD)C12V(sitio) + 5));
    return c12_escribir(sitio, s, n);
}

static int c12_cuevas_yo(void)
{
    static const BYTE a[8] = { 0x0F, 0xB6, 0xD2, 0x53, 0x8B, 0x5C, 0x24, 0x44 };      /* movzx edx,dl · push ebx · mov ebx,[esp+44] */
    static const BYTE b[6] = { 0x0F, 0xB6, 0xC8, 0x8D, 0x45, 0x15 };                  /* movzx ecx,al · lea eax,[ebp+15] */
    static const BYTE c[7] = { 0x8B, 0x5C, 0x24, 0x4C, 0x0F, 0xB6, 0xD1 };            /* mov ebx,[esp+4c] · movzx edx,cl */
    if (memcmp(C12V(0x55AA18), a, 8) || memcmp(C12V(0x55AAC5), b, 6) || memcmp(C12V(0x55B01E), c, 7)) return 0;
    return c12_cueva_yo(0x55AA18, 8, 0x15, 0x55AA20)                                   /* edx */
        && c12_cueva_yo(0x55AAC5, 6, 0x0D, 0x55AACB)                                   /* ecx */
        && c12_cueva_yo(0x55B01E, 7, 0x15, 0x55B025);                                  /* edx */
}

static void c12_lista4(BYTE *g, const BYTE *puesto, const BYTE *asiento, int n, int yo)
{
    (void)puesto;
    if (g != g_c12_foco4_de) {
        g_c12_foco4_de = g;
        for (int e = 0; e < 5; e++) g_c12_foco4[e] = -1;
    }
    /* el mouse COMO LO VE EL JUEGO (0x647650, el que reparte los mensajes a la interfaz): +4/+8 la posición del
     * WM_MOUSEMOVE y +0x10 el botón izquierdo (1 con el 0x201, 0 con el 0x202). Es la misma que usa el hit-test de sus
     * botones (0x685970) ⇒ en cualquier resolución los números se tocan donde se tocan el ojito y los demás */
    BYTE *raton = *(BYTE **)C12V(0x93156C);
    int mx = raton ? *(int *)(raton + 4) : -9999, my = raton ? *(int *)(raton + 8) : -9999;
    int boton = raton && *(int *)(raton + 0x10) != 0;
    int clic = boton && !g_c12_foco4_antes;
    g_c12_foco4_antes = boton;
    int mirando = g[0xC01] != 0;                                         /* espectador: «yo» = a quién miro */
    int yo_eq = yo >= 0 && yo < 12 ? c12_equipo(yo) : 0;
    int miembros[5][GR_TOPE], nm[5] = { 0 }, ultimo[5];
    for (int i = 0; i < n; i++) {
        int e = c12_equipo(asiento[i]);
        if (e < 1 || e > 4) e = 1;
        miembros[e][nm[e]++] = i;                                       /* ya vienen en orden de carrera */
    }
    int orden[4], ne = 0;
    for (int e = 1; e <= 4; e++)
        if (nm[e]) { ultimo[e] = miembros[e][nm[e] - 1]; orden[ne++] = e; }
    for (int i = 0; i < ne; i++)                                        /* por su último corredor */
        for (int j = i + 1; j < ne; j++)
            if (ultimo[orden[j]] < ultimo[orden[i]]) { int x = orden[i]; orden[i] = orden[j]; orden[j] = x; }
    BYTE *hud = *(BYTE **)C12V(0x931670);
    if (!hud) return;
    /* ★ el de la tarjeta de cada equipo: el elegido si sigue en su fila; si no, el mejor */
    int tarjeta[5];
    for (int e = 1; e <= 4; e++) {
        tarjeta[e] = nm[e] ? asiento[miembros[e][0]] : -1;
        int esta = 0;
        for (int i = 0; i < nm[e] && i < 6; i++) esta |= asiento[miembros[e][i]] == g_c12_foco4[e];
        if (g_c12_foco4[e] >= 0 && esta) tarjeta[e] = g_c12_foco4[e];
        else g_c12_foco4[e] = -1;
        if (mirando && e == yo_eq && g_c12_foco4[e] < 0) tarjeta[e] = yo; /* ★ espectador: si no eligió, el que mira */
    }
    /* los botones prestados (ver c12_lista) */
    int usado[6] = { 0 }, libres[6], nl = 0, pide[4];
    for (int p = 0; p < ne; p++) { int a = tarjeta[orden[p]]; if (a < 6) usado[a] = 1; }
    for (int f = 0; f < 6; f++) { g_c12_boton_de[f] = -1; if (!usado[f]) libres[nl++] = f; }
    for (int p = 0, u = 0; p < ne; p++) {
        int a = tarjeta[orden[p]];
        pide[p] = -1;
        if (a >= 6 && u < nl) { pide[p] = libres[u++]; g_c12_boton_de[pide[p]] = a; }
    }
    for (int p = 0; p < ne; p++) {
        int e = orden[p], a = tarjeta[e];
        g_c12_asiento = a;
        g_c12_puesto = p;
        g_c12_boton_sust = pide[p];
        int y0 = p == 0 ? 0xF : *(int *)C12V(0x904BF0);                    /* la tarjeta 0 lo pone en 0xF */
        int grande = e == yo_eq;                                         /* ★ UNA grande: la de mi equipo / del que miro */
        g_c12_yo_tarjeta = grande ? a : 0xFE;                           /* 0xFE: ningún asiento ⇒ chica */
        ((F_C12_TARJETA)C12V(0x55A9C0))(hud, p, p, a);
        g_c12_yo_tarjeta = -1;
        g_c12_asiento = g_c12_puesto = g_c12_redirigido = -1;
        g_c12_boton_sust = -1;
        if (!grande) c12_puesto_chico(p, y0);
        int *yy = (int *)C12V(0x904BF0);
        int y = *yy - 0xE + 1, x0 = 0x15 - *(int *)(hud + 0xA1C) + 4;
        for (int i = 0; i < nm[e] && i < 6; i++) {
            int k = asiento[miembros[e][i]], c = c12_marca(k), mx0 = x0 + i * C12_MARCA_PASO;
            if (clic && mx >= mx0 && mx < mx0 + C12_MARCA_LADO && my >= y && my < y + C12_MARCA_LADO) {
                g_c12_foco4[e] = k == a ? -1 : k;                           /* ★ el número elegido va a la tarjeta */
                clic = 0;
                apuntar("  [carrera12] pid %lu %s: número %d del equipo %d → la tarjeta %s%d (yo %d)", GetCurrentProcessId(),
                        mirando ? "espectador" : "corredor", k + 1, e,
                        g_c12_foco4[e] < 0 ? "vuelve a la automática · era " : "pasa al ", k + 1, yo + 1);
            }
            DWORD tinte = (k == a || k == yo) ? 0xFFFFFFFF : 0x90FFFFFF;     /* el de la tarjeta, entero */
            ((F_C12_TINTE)C12V(0x64E710))(g_c12_hoja, c, tinte);
            ((F_C12_POS)C12V(0x64D990))(g_c12_hoja, c, mx0, y);
            ((F_C12_DIB)C12V(0x64EE40))(g_c12_hoja, c, 0);
            ((F_C12_TINTE)C12V(0x64E710))(g_c12_hoja, c, 0xFFFFFFFF);
        }
        *yy += 24;
    }
    if (g_c12_listas++ == 0)
        apuntar("  [carrera12] ★ 1.ª lista del EQUIPO DE 4 (pid %lu, %s): %d equipos, %d corredores · yo asiento %d",
                GetCurrentProcessId(), mirando ? "espectador" : "corredor", ne, n, yo + 1);
}

static void __fastcall c12_lista(BYTE *g, void *nada)
{
    (void)nada;
    if (g_c12_activo && g_gr_puesto > 6 && g && (*(WORD *)(g + 0xC) & 0x40) && g_c12_lista_relevo) {
        if (g_c12_estado == 0) c12_cargar();
        if (g_c12_estado == 1) { g_c12_lista_relevo(g); return; }        /* ★ 14-oct: el relevo de 12, por equipos */
    }
    if (!g_c12_activo || g_gr_puesto <= 6 || !g || (*(WORD *)(g + 0xC) & 0x40)) {   /* 0x40 = relevo: como siempre */
        ((F_C12_LISTA)C12V(0x4F2FC0))(g);
        return;
    }
    if (g_c12_estado == 0) c12_cargar();
    if (g_c12_medir) c12_medir(g);
    BYTE puesto[GR_TOPE], asiento[GR_TOPE];
    int n = 0;
    BYTE *cab = *(BYTE **)(g + 0xAD8);
    if (!cab) return;
    for (BYTE *x = *(BYTE **)cab; x && x != cab && !x[0xF] && n < GR_TOPE; x = c12_siguiente(x)) {
        puesto[n] = x[0xC];
        asiento[n] = x[0xD];
        n++;
    }
    /* yo: como lo mira la tarjeta (0x55AA01): en relevo o mirando, cGame+0x5D; si no, el padrón +0x40 */
    int yo = g[0xC01] ? g[0x5D] : (*(BYTE **)C12V(0x931660))[0x40];
    int iyo = -1;
    for (int i = 0; i < n; i++)
        if (asiento[i] == yo) { iyo = i; break; }
    int lista[6], k = 0;
    int equipos = (*(WORD *)(g + 0xC) & 4) != 0;                          /* 0x04 = batalla en equipo */
    if (equipos && g_gr_equipos == 4 && !g_c12_cola) {                    /* ★ 15-oct: el equipo de 4 */
        c12_lista4(g, puesto, asiento, n, yo);
        return;
    }
    if (g_c12_cola)                                                      /* prueba: los 6 de atrás */
        for (int i = n > 6 ? n - 6 : 0; i < n; i++) lista[k++] = i;
    else if (equipos && c12_por_equipo(puesto, asiento, n, iyo, lista, &k))
        ;                                                                /* ★ 6vs6: 3 + 3 por equipo */
    else if (iyo < 6)
        for (int i = 0; i < n && k < 6; i++) lista[k++] = i;
    else {
        for (int i = 0; i < 5; i++) lista[k++] = i;
        lista[k++] = iyo;                                                /* yo, sexto */
    }
    void *hud = *(void **)C12V(0x931670);
    /* ★ 14-oct · los botones prestados: los 1..6 que en este cuadro no tienen tarjeta, para las tarjetas de 7..12 */
    int usado[6] = { 0 }, libres[6], nl = 0, pide[6];
    for (int p = 0; p < k; p++) if (asiento[lista[p]] < 6) usado[asiento[lista[p]]] = 1;
    for (int f = 0; f < 6; f++) { g_c12_boton_de[f] = -1; if (!usado[f]) libres[nl++] = f; }
    for (int p = 0, u = 0; p < k; p++) {
        pide[p] = -1;
        if (asiento[lista[p]] >= 6 && u < nl) { pide[p] = libres[u++]; g_c12_boton_de[pide[p]] = asiento[lista[p]]; }
    }
    for (int p = 0; p < k; p++) {
        int i = lista[p];
        g_c12_asiento = asiento[i];
        g_c12_puesto = puesto[i];
        g_c12_boton_sust = pide[p];
        int y0 = p == 0 ? 0xF : *(int *)C12V(0x904BF0);                       /* la tarjeta 0 lo pone en 0xF */
        ((F_C12_TARJETA)C12V(0x55A9C0))(hud, puesto[i], p, asiento[i]);
        g_c12_asiento = g_c12_puesto = g_c12_redirigido = -1;
        g_c12_boton_sust = -1;
        if (asiento[i] != yo) c12_puesto_chico(puesto[i], y0);                 /* ★ 14-oct: el «nTH» de los demás */
    }
    g_c12_asiento = g_c12_puesto = g_c12_redirigido = -1;
    if (g_c12_listas++ == 0)
        apuntar("  [carrera12] ★ 1.ª lista de 12: %d corredores en el mapa de puestos · yo asiento %d puesto %d · %d"
                " tarjetas", n, yo, iyo + 1, k);
}

/* las dos cuevas: el color de la tarjeta (asiento −6) y saltear la lista de ítems de 6..11 */
static int c12_cuevas(void)
{
    g_c12_cuevas = (BYTE *)VirtualAlloc(NULL, 256, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!g_c12_cuevas) return 0;
    BYTE *k = g_c12_cuevas;
    DWORD tabla = (DWORD)C12V(0x55B178);
    int i = 0;
    /* el color */
    BYTE *color = k + i;
    k[i++] = 0x83; k[i++] = 0xFB; k[i++] = 0x05;                                            /* cmp ebx,5 */
    k[i++] = 0x76; k[i++] = 0x13;                                                            /* jbe L1 (+0x13) */
    k[i++] = 0x83; k[i++] = 0xFB; k[i++] = 0x0B;                                            /* cmp ebx,11 */
    k[i++] = 0x0F; k[i++] = 0x87; *(int *)(k + i) = (int)((DWORD)C12V(0x55ACBC) - (DWORD)(k + i + 4)); i += 4;
    k[i++] = 0x8D; k[i++] = 0x43; k[i++] = 0xFA;                                            /* lea eax,[ebx-6] */
    k[i++] = 0xFF; k[i++] = 0x24; k[i++] = 0x85; *(DWORD *)(k + i) = tabla; i += 4;          /* jmp [eax*4+tabla] */
    k[i++] = 0xFF; k[i++] = 0x24; k[i++] = 0x9D; *(DWORD *)(k + i) = tabla; i += 4;          /* L1: jmp [ebx*4+tabla] */
    /* los ítems */
    BYTE *items = k + i;
    k[i++] = 0x8B; k[i++] = 0x44; k[i++] = 0x24; k[i++] = 0x4C;                             /* mov eax,[esp+0x4C] */
    k[i++] = 0x83; k[i++] = 0xF8; k[i++] = 0x06;                                            /* cmp eax,6 */
    k[i++] = 0x0F; k[i++] = 0x83; *(int *)(k + i) = (int)((DWORD)C12V(0x55AFF1) - (DWORD)(k + i + 4)); i += 4;
    k[i++] = 0x8D; k[i++] = 0x0C; k[i++] = 0xC5; *(DWORD *)(k + i) = 0; i += 4;            /* lea ecx,[eax*8] */
    k[i] = 0xE9; *(int *)(k + i + 1) = (int)((DWORD)C12V(0x55AE3A) - (DWORD)(k + i + 5)); i += 5;
    /* el salto a cada una */
    BYTE s1[12] = { 0xE9, 0, 0, 0, 0, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90 };
    *(int *)(s1 + 1) = (int)((DWORD)color - ((DWORD)C12V(C12_COLOR) + 5));
    BYTE s2[11] = { 0xE9, 0, 0, 0, 0, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90 };
    *(int *)(s2 + 1) = (int)((DWORD)items - ((DWORD)C12V(C12_ITEMS) + 5));
    /* ★ 3.ª prueba (anonimo03, 10-oct): «en el equipo azul, al intercambiarse las mitades, el juego crasheó» — 0x54D234,
     *   leyendo 0: el std::find de una lista de ítems del HUD. Las DOS funciones que tocan la lista de ítems de UN
     *   asiento ([hud+0xAA8+a*0x1C], 6 listas) desde los avisos del juego — 0x550C00(asiento, …) y 0x554580(asiento, …),
     *   las dos `ret 8`, ninguna con referencias relativas en lo que se pisa — con 6..11 leían fuera. Con asiento ≥ 6 vuelven sin hacer nada (eax = 0). */
    BYTE *entradas[2];
    for (int e = 0; e < 2; e++) {
        DWORD f = e == 0 ? C12_ITEMS_F1 : C12_ITEMS_F2;
        int largo = e == 0 ? 8 : 7;
        entradas[e] = k + i;
        k[i++] = 0x80; k[i++] = 0x7C; k[i++] = 0x24; k[i++] = 0x04; k[i++] = 0x06;          /* cmp byte [esp+4],6 */
        k[i++] = 0x72; k[i++] = 0x05;                                                        /* jb +5 */
        k[i++] = 0x31; k[i++] = 0xC0;                                                        /* xor eax,eax */
        k[i++] = 0xC2; k[i++] = 0x08; k[i++] = 0x00;                                         /* ret 8 */
        CopyMemory(k + i, C12V(f), largo); i += largo;                                       /* lo que se pisa */
        k[i] = 0xE9; *(int *)(k + i + 1) = (int)((DWORD)C12V(f + largo) - (DWORD)(k + i + 5)); i += 5;
    }
    BYTE s3[8] = { 0xE9, 0, 0, 0, 0, 0x90, 0x90, 0x90 }, s4[7] = { 0xE9, 0, 0, 0, 0, 0x90, 0x90 };
    *(int *)(s3 + 1) = (int)((DWORD)entradas[0] - ((DWORD)C12V(C12_ITEMS_F1) + 5));
    *(int *)(s4 + 1) = (int)((DWORD)entradas[1] - ((DWORD)C12V(C12_ITEMS_F2) + 5));
    /* ★ 14-oct · relevo de 12: el color de la tarjeta por EQUIPO (0x55ACA7: con equipo ≠ 1 era azul) → 3 verde, 4 naranja.
     *   dec al · movzx eax,al · neg eax · sbb eax,eax · and eax,0xFF0100FF · add eax,0x80FF0000 · jmp 0x55ACC0 */
    static const BYTE e_col[0x15] = { 0xFE, 0xC8, 0x0F, 0xB6, 0xC0, 0xF7, 0xD8, 0x1B, 0xC0, 0x25, 0xFF, 0x00, 0x01, 0xFF,
                                      0x05, 0x00, 0x00, 0xFF, 0x80, 0xEB, 0x04 };
    int ok_col = memcmp(C12V(0x55ACA7), e_col, 0x15) == 0;
    if (ok_col) {
        BYTE *c = k + i;
        k[i++] = 0x3C; k[i++] = 0x03; k[i++] = 0x75; k[i++] = 0x0A;                         /* cmp al,3 · jne +10 */
        k[i++] = 0xB8; *(DWORD *)(k + i) = 0x8000C040; i += 4;                               /* mov eax, verde */
        k[i++] = 0xE9; *(int *)(k + i) = (int)((DWORD)C12V(0x55ACC0) - (DWORD)(k + i + 4)); i += 4;
        k[i++] = 0x3C; k[i++] = 0x04; k[i++] = 0x75; k[i++] = 0x0A;                         /* cmp al,4 · jne +10 */
        k[i++] = 0xB8; *(DWORD *)(k + i) = 0x80FF8C00; i += 4;                               /* mov eax, naranja */
        k[i++] = 0xE9; *(int *)(k + i) = (int)((DWORD)C12V(0x55ACC0) - (DWORD)(k + i + 4)); i += 4;
        CopyMemory(k + i, e_col, 0x13); i += 0x13;                                           /* lo de fábrica (sin el jmp) */
        k[i++] = 0xE9; *(int *)(k + i) = (int)((DWORD)C12V(0x55ACC0) - (DWORD)(k + i + 4)); i += 4;
        BYTE s5[0x15];
        s5[0] = 0xE9; *(int *)(s5 + 1) = (int)((DWORD)c - ((DWORD)C12V(0x55ACA7) + 5));
        for (int q = 5; q < 0x15; q++) s5[q] = 0x90;
        c12_escribir(0x55ACA7, s5, 0x15);
    }
    return c12_escribir(C12_COLOR, s1, 12) && c12_escribir(C12_ITEMS, s2, 11) &&
           c12_escribir(C12_ITEMS_F1, s3, 8) && c12_escribir(C12_ITEMS_F2, s4, 7);
}

/* ★ 15-oct · EL NOMBRE SOBRE EL CORREDOR en 4 equipos (EQUIPOS_4.md): 0x5009D0 lo pinta por equipo con
 *   `dec al · movzx · neg · sbb · and 0xFF0100FF · add 0xFFFF0000` = rojo el 1, AZUL cualquier otro — el verde y el
 *   naranja salían azules. Dos veces (0x500A1C y 0x500A73, 19 bytes hasta 0x500A2F / 0x500A86): una cueva mira el 3 y
 *   el 4 antes y si no, lo de fábrica. Con 2 equipos no cambia nada. */
static void c12_nombres_color(void)
{
    static const BYTE fab[19] = { 0xFE, 0xC8, 0x0F, 0xB6, 0xC0, 0xF7, 0xD8, 0x1B, 0xC0, 0x25, 0xFF, 0x00, 0x01, 0xFF,
                                  0x05, 0x00, 0x00, 0xFF, 0xFF };
    static const DWORD SITIO[2] = { 0x500A1C, 0x500A73 };
    BYTE *k = (BYTE *)VirtualAlloc(NULL, 128, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!k) return;
    for (int s = 0; s < 2; s++)
        if (memcmp(C12V(SITIO[s]), fab, 19) != 0) {
            apuntar("  [carrera12] ⚠ el color del nombre (0x%06X) no es el esperado: queda de fábrica", SITIO[s]);
            return;
        }
    int i = 0;
    for (int s = 0; s < 2; s++) {
        BYTE *c = k + i;
        DWORD fin = SITIO[s] + 19;
        k[i++] = 0x3C; k[i++] = 0x03; k[i++] = 0x75; k[i++] = 0x0A;                         /* cmp al,3 · jne +10 */
        k[i++] = 0xB8; *(DWORD *)(k + i) = 0xFF30D050; i += 4;                               /* mov eax, verde */
        k[i++] = 0xE9; *(int *)(k + i) = (int)((DWORD)C12V(fin) - (DWORD)(k + i + 4)); i += 4;
        k[i++] = 0x3C; k[i++] = 0x04; k[i++] = 0x75; k[i++] = 0x0A;                         /* cmp al,4 · jne +10 */
        k[i++] = 0xB8; *(DWORD *)(k + i) = 0xFFFF9020; i += 4;                               /* mov eax, naranja */
        k[i++] = 0xE9; *(int *)(k + i) = (int)((DWORD)C12V(fin) - (DWORD)(k + i + 4)); i += 4;
        CopyMemory(k + i, fab, 19); i += 19;                                                 /* lo de fábrica */
        k[i++] = 0xE9; *(int *)(k + i) = (int)((DWORD)C12V(fin) - (DWORD)(k + i + 4)); i += 4;
        BYTE salto[19];
        salto[0] = 0xE9; *(int *)(salto + 1) = (int)((DWORD)c - ((DWORD)C12V(SITIO[s]) + 5));
        for (int q = 5; q < 19; q++) salto[q] = 0x90;
        c12_escribir(SITIO[s], salto, 19);
    }
    apuntar("  [carrera12] el nombre sobre el corredor: verde / naranja para los equipos 3 y 4");
}

static void carrera12_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("carrera12", "activo", 1, ini)) {
        apuntar("  [carrera12] apagado ([carrera12] activo=0)");
        return;
    }
    g_c12_base = (BYTE *)GetModuleHandleA(NULL);
    g_c12_z = GetPrivateProfileIntA("carrera12", "z", 100, ini) / 1000.0f;
    g_c12_z_insignia = GetPrivateProfileIntA("carrera12", "z_insignia", 500, ini) / 1000.0f;
    g_c12_cola = GetPrivateProfileIntA("carrera12", "cola", 0, ini);
    g_c12_medir = GetPrivateProfileIntA("carrera12", "medir", 0, ini);
    g_c12_th_x = GetPrivateProfileIntA("carrera12", "th_x", 104, ini);
    g_c12_th_y = GetPrivateProfileIntA("carrera12", "th_y", -5, ini);
    /* la guarda: cada llamada llama a quien tiene que llamar, y las cuevas pisan lo de siempre */
    int ok = c12_llama_a(C12_LLAMA_LISTA, 0x4F2FC0) && c12_llama_a(C12_BOTON2_SITIO, 0x685900) &&
             c12_llama_a(C12_BOTON3_SITIO, 0x685920) &&
             memcmp(C12V(C12_COLOR), C12_COLOR_BYTES, 12) == 0 && memcmp(C12V(C12_ITEMS), C12_ITEMS_BYTES, 11) == 0 &&
             memcmp(C12V(C12_ITEMS_F1), C12_ITEMS_F1_BYTES, 8) == 0 && memcmp(C12V(C12_ITEMS_F2), C12_ITEMS_F2_BYTES, 7) == 0;
    for (int i = 0; i < 4 && ok; i++)
        ok = c12_llama_a(C12_POS_SITIOS[i], 0x64D990) && c12_llama_a(C12_DIB_SITIOS[i], 0x64EE40);
    for (int i = 0; i < 2 && ok; i++)
        ok = c12_llama_a(C12_BOTON7_SITIOS[i], 0x685D90);
    /* ★ 14-oct: la barra y el recuadro de golpe — guarda aparte: si no calzan, sólo esos dos quedan como estaban */
    int ok_barra = c12_llama_a(C12_BARRA_POS, 0x64D990) && c12_llama_a(C12_BARRA_DIB, 0x64EE40) &&
                   c12_llama_a(C12_BARRA_FIN, 0x550D70);
    int ok_golpe = c12_llama_a(C12_GOLPE_POS, 0x64D990) && c12_llama_a(C12_GOLPE_DIB, 0x64EE40);
    if (!ok) {
        apuntar("  [carrera12] ⛔ la lista o la tarjeta del HUD no son las esperadas: no se toca nada");
        return;
    }
    if (!c12_cuevas()) {
        apuntar("  [carrera12] ⛔ no pude armar las cuevas (color / ítems)");
        return;
    }
    c12_desviar(C12_LLAMA_LISTA, (void *)c12_lista);
    c12_nombres_color();                                                 /* ★ 15-oct: 4 equipos */
    if (!c12_cuevas_yo())                                                /* ★ 15-oct: una sola tarjeta grande */
        apuntar("  [carrera12] ⚠ el «yo» de la tarjeta (0x55AA18/0x55AAC5/0x55B01E) no es el esperado: en el equipo de 4"
                " la grande queda la de fábrica");
    for (int i = 0; i < 4; i++) {
        c12_desviar(C12_POS_SITIOS[i], (void *)c12_pos);
        c12_desviar(C12_DIB_SITIOS[i], (void *)c12_dib);
    }
    for (int i = 0; i < 2; i++) c12_desviar(C12_BOTON7_SITIOS[i], (void *)c12_boton7);
    if (c12_llama_a(0x54D888, 0x563930)) c12_desviar(0x54D888, (void *)c12_mirar);   /* ★ 14-oct: el clic del ojito prestado */
    c12_desviar(C12_BOTON2_SITIO, (void *)c12_boton2);
    c12_desviar(C12_BOTON3_SITIO, (void *)c12_boton3);
    if (ok_barra) {
        c12_desviar(C12_BARRA_POS, (void *)c12_barra_pos);
        c12_desviar(C12_BARRA_DIB, (void *)c12_dib);                          /* dibuja el corte que puso c12_barra_pos */
        c12_desviar(C12_BARRA_FIN, (void *)c12_barra_fin);
    }
    if (ok_golpe) {
        c12_desviar(C12_GOLPE_POS, (void *)c12_golpe_pos);
        c12_desviar(C12_GOLPE_DIB, (void *)c12_dib);
    }
    apuntar("  [carrera12] ★ 14-oct: la barra de abajo con 12 (rojo/azul) %s · la insignia del golpe 7P..12P %s · el"
            " puesto chico en las tarjetas (th_x=%d th_y=%d)", ok_barra ? "ok" : "⛔ no calza",
            ok_golpe ? "ok" : "⛔ no calza", g_c12_th_x, g_c12_th_y);
    g_c12_activo = 1;
    apuntar("  [carrera12] listo: la lista de la izquierda (0x55C6CE) + 4 insignias/puesto + 4 del botón + 2 cuevas"
            " · z=%d/1000%s", (int)(g_c12_z * 1000), g_c12_cola ? " · ⚠ PRUEBA cola=1: la lista muestra los 6 últimos" : "");
}
