/* flotar.c — FLOTAR (`fly.txt` del 2019) en la sala del 2013, por la ruta NATIVA del 2019 (30-oct-2026)
 *
 *   anonimo03 (30-oct): «lo más cercano a un 1 a 1 con lo nativo del 2019 en el nuestro». Doc: FLOTAR.md. Los datos (la
 *   Carta Nube Flotante 1000729 y las 20 animaciones de flotar) los arma `herramientas/flotar_crear.py`.
 *
 *   Cómo lo hace el 2019 (medido, FLOTAR.md §1): la FICHA del jugador (CmdRoomUserInfo = nuestro FF15) trae si flota, y
 *   sRoomUser::Init (0xA286A0) lo arma YA flotando: 100 más arriba (396/496 en vez de 296/396) y con las animaciones de
 *   flotar. «Poner a flotar» (0xA2B870) es para los cambios en vivo: despegar → quieto en el aire; aterrizar.
 *
 *   El 2013 tiene la MISMA clase (sRoomUser.cpp), sin flotar. Medido:
 *     0x59FEF7  la ÚNICA llamada a sRoomUser::Init (0x5B2FF0, thiscall(usr, ficha, x), ret 8): sobre una COPIA en la
 *               PILA; la copia se arma entera y después pasa al sRoomUser de la sala (comparten el personaje [+0x1B8] y
 *               el modelo [+4]). La ficha trae el Wing Id en +0x34 — con nuestro byte de flotar arriba.
 *     0x5B1670  thiscall(sRoomUser, llave, 0, 0)     reproduce una animación (el motor agrega el sufijo del cuerpo):
 *               «대기1» quieto, «걷기» caminar, «대쉬» correr, «탈진» agotado, «정지» frenar. 23 llamadas.
 *     0x524470 / 0x524420  thiscall(modelo, &pos)     ubica el modelo; el sRoomUser los llama 6 veces con la altura del
 *               piso (380, o 480 si [usr+0x15C] o [usr+0x218]). x y z en [usr+8] y [usr+0x10].
 *   Lo nuestro, como el 2019:
 *     · el dato viaja con el ala y el aura: Wing Id | aura << 16 | flotar << 24 (catalogo.wing_id_con_aura);
 *     · ★ AL ENTRAR a Init se lee de la ficha: todo lo que hace Init (ubicar, la 1.ª animación) ya sale flotando, desde el
 *       primer cuadro. (La 1.ª versión se enteraba al final de Init, por las alas, y con retraso: anonimo03, «ya funciona,
 *       pero con delay».)
 *     · el estado es por PERSONAJE / MODELO, no por la dirección del sRoomUser (la copia y el de la sala son dos);
 *     · los cambios en vivo (ponerse / sacarse la Carta) llegan por las alas (aura_suelo.c → fl_desde_alas): se reubica
 *       (+100 / piso) y despega / aterriza;
 *     · mientras flota: quieto, caminar, correr, agotado y frenar → «공중부양-대기» (quieto en el aire), y cada ubicación
 *       del sRoomUser con el piso +100.
 *   ★ 30-oct: los CUATRO de flotar. El número que viaja (flotar_crear.ITEMS) elige las animaciones, como el FlyItem del
 *     2019: 1 la Carta Nube y 4 la Piedra Sónica, las comunes («공중부양-…»); 2 y 3 el Paso de Estrella Creciente (una
 *     mano, de chico y de chica), las suyas («AC0598B_공중부양-…», «AC0618G_공중부양-…»).
 *   [flotar] activo=0 lo apaga · [flotar] alto=N cambia los 100.
 */
#define FLV(x) (g_fl_base + ((DWORD)(x) - 0x400000))

/* ★ (142) LAS MONTURAS viven en monturas.c (se incluye DESPUÉS): el byte de arriba del Wing Id con 0x80 es de ellas
 *   (0x80 | 0x40 tiene la suya | modo << 4 | k); 1..4 siguen siendo flotar. */
static void mo_desde_byte(void *pj, BYTE *usr, int b);
static void mo_tras_init(BYTE *usr, int b);
static int g_mo_init_entrada;   /* (142) la fila de entrada de la ficha (FF0C cola[17], desc+0x43) del Init en curso */
static const char *mo_llave_montado(BYTE *usr, const char *llave);

typedef void (__attribute__((thiscall)) *F_FL_ANIM)(void *usr, const char *llave, int a, int b);   /* 0x5B1670 */
typedef void (__attribute__((thiscall)) *F_FL_POS)(void *modelo, float *v);                         /* 0x524470/0x524420 */
typedef void (__attribute__((thiscall)) *F_FL_INIT)(void *usr, void *ficha, int x);                 /* 0x5B2FF0 */

static const char FL_SUBIR[] = "\xB0\xF8\xC1\xDF\xBA\xCE\xBE\xE7\x2D\xBB\xF3\xBD\xC2";   /* 공중부양-상승 */
static const char FL_BAJAR[] = "\xB0\xF8\xC1\xDF\xBA\xCE\xBE\xE7\x2D\xC7\xCF\xB0\xAD";   /* 공중부양-하강 */
static const char FL_QUIETO[] = "\xB0\xF8\xC1\xDF\xBA\xCE\xBE\xE7\x2D\xB4\xEB\xB1\xE2";  /* 공중부양-대기 */
/* el prefijo de cada número de flotar (el «Up/Down/Default» de su FlyItem); NULL = las comunes */
#define FL_NUMS 5
static const char *const FL_PREFIJO[FL_NUMS] = { NULL, NULL, "AC0598B_", "AC0618G_", NULL };
static char g_fl_llave[FL_NUMS][3][40];                               /* [número][0 subir · 1 bajar · 2 quieto] */

static const char *fl_llave(int num, int cual)
{
    if (num <= 0 || num >= FL_NUMS) num = 1;
    return g_fl_llave[num][cual];
}
static const char FL_IDLE[] = "\xB4\xEB\xB1\xE2\x31";                                     /* 대기1 */
static const char FL_CAMINAR[] = "\xB0\xC8\xB1\xE2";                                      /* 걷기 */
static const char *const FL_EN_EL_AIRE[] = { FL_IDLE, FL_CAMINAR,
                                             "\xB4\xEB\xBD\xAC",                          /* 대쉬  correr  */
                                             "\xC5\xBB\xC1\xF8",                          /* 탈진  agotado */
                                             "\xC1\xA4\xC1\xF6" };                        /* 정지  frenar  */

static BYTE *g_fl_base = NULL;
static int   g_fl_activo = 0;
static float g_fl_alto = 100.0f;
static int   g_fl_avisos = 0;

/* ★ los personajes que flotan (o flotaron): por personaje [usr+0x1B8] y su modelo [usr+4]; `usr` = el último sRoomUser
 *   de la sala (fuera de la pila) que se vio con ese personaje, para reubicarlo en un cambio en vivo */
#define FL_MAX 64
static struct { void *pj, *modelo; BYTE *usr; BYTE vuela; } g_fl[FL_MAX];
static int g_fl_prox = 0;
/* mientras corre Init: la copia que se está armando y si su ficha dice que flota */
static BYTE *g_fl_init_usr = NULL;
static int   g_fl_init_vuela = 0;

static int fl_leible(const void *p, SIZE_T n)
{
    MEMORY_BASIC_INFORMATION mi;
    if (!p || !VirtualQuery(p, &mi, sizeof mi) || mi.State != MEM_COMMIT) return 0;
    if (mi.Protect & (PAGE_NOACCESS | PAGE_GUARD)) return 0;
    return (BYTE *)p + n <= (BYTE *)mi.BaseAddress + mi.RegionSize;
}

static int fl_en_pila(const void *p)
{
    NT_TIB *tib = (NT_TIB *)NtCurrentTeb();
    return tib && (BYTE *)p >= (BYTE *)tib->StackLimit && (BYTE *)p < (BYTE *)tib->StackBase;
}

static void *fl_leer(BYTE *usr, int off) { return usr && fl_leible(usr + off, 4) ? *(void **)(usr + off) : NULL; }

static float fl_piso(BYTE *usr)
{
    int otro = fl_leible(usr + 0x218, 4) && (*(int *)(usr + 0x15C) || *(int *)(usr + 0x218));
    return otro ? *(float *)FLV(0x8822F4) : *(float *)FLV(0x87D94C);            /* 480 / 380 */
}

static int fl_de_pj(void *pj)
{
    for (int i = 0; pj && i < FL_MAX; i++)
        if (g_fl[i].pj == pj) return i;
    return -1;
}

static int fl_de_modelo(void *modelo)
{
    for (int i = 0; modelo && i < FL_MAX; i++)
        if (g_fl[i].modelo == modelo) return i;
    return -1;
}

static int fl_nueva(void *pj)
{
    int i = fl_de_pj(pj);
    if (i >= 0) return i;
    i = g_fl_prox;
    g_fl_prox = (g_fl_prox + 1) % FL_MAX;
    g_fl[i].pj = pj;
    g_fl[i].modelo = NULL;
    g_fl[i].usr = NULL;
    g_fl[i].vuela = 0;
    return i;
}

/* ¿este sRoomUser flota? (la copia de Init, por su ficha; los demás, por su personaje) */
static int fl_vuela_usr(BYTE *usr)
{
    if (!usr) return 0;
    if (usr == g_fl_init_usr) return g_fl_init_vuela;
    int i = fl_de_pj(fl_leer(usr, 0x1B8));
    if (i < 0) return 0;
    if (!fl_en_pila(usr)) {                                            /* el de la sala: se anota para reubicarlo */
        g_fl[i].usr = usr;
        if (fl_leer(usr, 4)) g_fl[i].modelo = fl_leer(usr, 4);
    }
    return g_fl[i].vuela;
}

/* las animaciones: mientras flota, quieto / caminar / correr / agotado / frenar son «quieto en el aire» */
static void __fastcall fl_anim(BYTE *usr, void *nada, const char *llave, int a, int b)
{
    (void)nada;
    llave = mo_llave_montado(usr, llave);                             /* ★ (142) montado: la pose de la montura */
    int num = g_fl_activo && llave ? fl_vuela_usr(usr) : 0;
    if (num)
        for (int k = 0; k < (int)(sizeof FL_EN_EL_AIRE / sizeof *FL_EN_EL_AIRE); k++)
            if (!lstrcmpA(llave, FL_EN_EL_AIRE[k])) { llave = fl_llave(num, 2); break; }
    ((F_FL_ANIM)FLV(0x5B1670))(usr, llave, a, b);
}

/* las ubicaciones del sRoomUser: el modelo de uno que flota va `alto` más arriba */
static void fl_pos_comun(DWORD orig, void *modelo, float *v)
{
    float w[3];
    int vuela = 0;
    if (g_fl_activo && v) {
        if (g_fl_init_usr && modelo == fl_leer(g_fl_init_usr, 4)) vuela = g_fl_init_vuela;
        else {
            int i = fl_de_modelo(modelo);
            vuela = i >= 0 && g_fl[i].vuela;
        }
    }
    if (vuela) {
        w[0] = v[0]; w[1] = v[1] + g_fl_alto; w[2] = v[2];
        v = w;
    }
    ((F_FL_POS)FLV(orig))(modelo, v);
}
static void __fastcall fl_pos1(void *modelo, void *nada, float *v) { (void)nada; fl_pos_comun(0x524470, modelo, v); }
static void __fastcall fl_pos2(void *modelo, void *nada, float *v) { (void)nada; fl_pos_comun(0x524420, modelo, v); }

/* ★ la ruta nativa: sRoomUser::Init con la ficha en la mano — lo que arme ya sale flotando */
static void __fastcall fl_init(BYTE *usr, void *nada, BYTE *ficha, int x)
{
    (void)nada;
    BYTE *antes_usr = g_fl_init_usr;
    int antes_vuela = g_fl_init_vuela;
    int vuela = 0, byte = 0;
    if (g_fl_activo && ficha && fl_leible(ficha + 0x34, 4))
        byte = vuela = (int)((*(unsigned *)(ficha + 0x34) >> 24) & 0xFF);  /* el número de flotar (0 = no) */
    if (vuela & 0x80) vuela = 0;                                           /* ★ (142) es de una montura */
    g_fl_init_usr = usr;
    g_fl_init_vuela = vuela;
    ((F_FL_INIT)FLV(0x5B2FF0))(usr, ficha, x);
    g_fl_init_usr = antes_usr;
    g_fl_init_vuela = antes_vuela;
    void *pj = fl_leer(usr, 0x1B8);
    if (g_fl_activo && pj && (vuela || fl_de_pj(pj) >= 0)) {
        int i = fl_nueva(pj);
        g_fl[i].vuela = (BYTE)vuela;
        g_fl[i].modelo = fl_leer(usr, 4);
        if (vuela && g_fl_avisos < 12) {
            g_fl_avisos++;
            apuntar("  [flotar] armado flotando (ficha): personaje %p, modelo %p", pj, g_fl[i].modelo);
        }
    }
    g_mo_init_entrada = ficha && fl_leible(ficha + 0x43, 1) ? ficha[0x43] : 0;   /* ★ (142) el saludo de entrada */
    mo_tras_init(usr, byte);                                               /* ★ (142) las monturas */
}

/* los cambios EN VIVO: lo llama aura_suelo.c cuando el juego le pone las alas a un personaje de la sala */
static void fl_desde_alas(void *pj, int vuela)
{
    if (!g_fl_activo || !pj) return;
    mo_desde_byte(pj, NULL, vuela);                                        /* ★ (142) las monturas (0x80 | …) */
    if (vuela & 0x80) vuela = 0;
    if (vuela < 0 || vuela >= FL_NUMS) vuela = 1;
    if (g_fl_init_usr && fl_leer(g_fl_init_usr, 0x1B8) == pj) return;   /* dentro de Init: ya lo maneja fl_init */
    int i = fl_de_pj(pj);
    if (i < 0) {
        if (!vuela) return;
        i = fl_nueva(pj);
    }
    if (g_fl[i].vuela == vuela) return;
    int antes = g_fl[i].vuela;
    g_fl[i].vuela = (BYTE)vuela;
    BYTE *u = g_fl[i].usr;
    if (u && fl_leer(u, 0x1B8) == pj && fl_leer(u, 4) && fl_leible(u + 0x218, 4)) {
        float v[3] = { *(float *)(u + 8), fl_piso(u) + (vuela ? g_fl_alto : 0.0f), *(float *)(u + 0x10) };
        ((F_FL_POS)FLV(0x524470))(fl_leer(u, 4), v);
        /* despegar / aterrizar, como el 2019 (con las animaciones de SU ítem: al bajar, las del que tenía) */
        ((F_FL_ANIM)FLV(0x5B1670))(u, vuela ? fl_llave(vuela, 0) : fl_llave(antes, 1), 0, 0);
    }
    if (g_fl_avisos < 12) {
        g_fl_avisos++;
        apuntar("  [flotar] %s en vivo: personaje %p (sRoomUser %p)", vuela ? "despega" : "aterriza", pj, u);
    }
}

static const DWORD FL_ANIMS[] = { 0x593BF8, 0x594014, 0x5940CB, 0x59B26B, 0x59B5CA, 0x59B60E, 0x59B646, 0x59B6F2,
                                  0x59B781, 0x59B7D8, 0x59B86D, 0x5A10F1, 0x5A1134, 0x5A1199, 0x5B182F, 0x5B1DB5,
                                  0x5B1EC2, 0x5B2117, 0x5B2187, 0x5B22FA, 0x5B230B, 0x5B2B72, 0x5B33AB };
static const DWORD FL_POS1[] = { 0x5B0120, 0x5B0266, 0x5B1853 };
static const DWORD FL_POS2[] = { 0x5B03B6, 0x5B0798, 0x5B343C };
#define FL_INIT_SITIO 0x59FEF7

static int fl_es_llamada(DWORD sitio, DWORD destino)
{
    BYTE *s = FLV(sitio);
    return s[0] == 0xE8 && (DWORD)(s + 5 + *(int *)(s + 1)) == (DWORD)FLV(destino);
}

static void fl_escribir(DWORD sitio, void *nuevo)
{
    BYTE *s = FLV(sitio);
    DWORD viejo = 0;
    VirtualProtect(s + 1, 4, PAGE_EXECUTE_READWRITE, &viejo);
    *(int *)(s + 1) = (int)((DWORD)nuevo - ((DWORD)s + 5));
    VirtualProtect(s + 1, 4, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), s, 5);
}

#define FL_N(a) ((int)(sizeof a / sizeof *a))

static void flotar_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("flotar", "activo", 1, ini)) {
        apuntar("  [flotar] apagado ([flotar] activo=0)");
        return;
    }
    g_fl_alto = (float)(int)GetPrivateProfileIntA("flotar", "alto", 100, ini);
    for (int n = 0; n < FL_NUMS; n++) {
        const char *pre = FL_PREFIJO[n] ? FL_PREFIJO[n] : "";
        wsprintfA(g_fl_llave[n][0], "%s%s", pre, FL_SUBIR);
        wsprintfA(g_fl_llave[n][1], "%s%s", pre, FL_BAJAR);
        wsprintfA(g_fl_llave[n][2], "%s%s", pre, FL_QUIETO);
    }
    g_fl_base = (BYTE *)GetModuleHandleA(NULL);
    /* ⚠ las 30 guardas ANTES de escribir la primera: o van todas o ninguna */
    for (int i = 0; i < FL_N(FL_ANIMS); i++)
        if (!fl_es_llamada(FL_ANIMS[i], 0x5B1670)) {
            apuntar("  [flotar] ⛔ la llamada de 0x%06X no va a «reproducir animación» (0x5B1670): no se toca nada", FL_ANIMS[i]);
            return;
        }
    for (int i = 0; i < FL_N(FL_POS1); i++)
        if (!fl_es_llamada(FL_POS1[i], 0x524470)) {
            apuntar("  [flotar] ⛔ la llamada de 0x%06X no va a «ubicar» (0x524470): no se toca nada", FL_POS1[i]);
            return;
        }
    for (int i = 0; i < FL_N(FL_POS2); i++)
        if (!fl_es_llamada(FL_POS2[i], 0x524420)) {
            apuntar("  [flotar] ⛔ la llamada de 0x%06X no va a «ubicar» (0x524420): no se toca nada", FL_POS2[i]);
            return;
        }
    if (!fl_es_llamada(FL_INIT_SITIO, 0x5B2FF0)) {
        apuntar("  [flotar] ⛔ la llamada de 0x%06X no va a sRoomUser::Init (0x5B2FF0): no se toca nada", FL_INIT_SITIO);
        return;
    }
    if (lstrcmpA((const char *)FLV(0x87D87C), FL_IDLE) || lstrcmpA((const char *)FLV(0x8823EC), FL_CAMINAR)) {
        apuntar("  [flotar] ⛔ «대기1» / «걷기» no están donde se midieron: no se toca nada");
        return;
    }
    for (int i = 0; i < FL_N(FL_ANIMS); i++) fl_escribir(FL_ANIMS[i], fl_anim);
    for (int i = 0; i < FL_N(FL_POS1); i++) fl_escribir(FL_POS1[i], fl_pos1);
    for (int i = 0; i < FL_N(FL_POS2); i++) fl_escribir(FL_POS2[i], fl_pos2);
    fl_escribir(FL_INIT_SITIO, fl_init);
    g_fl_activo = 1;
    apuntar("  [flotar] ok: sRoomUser::Init (la ficha), %d animaciones y %d ubicaciones enganchadas (alto %d)",
            FL_N(FL_ANIMS), FL_N(FL_POS1) + FL_N(FL_POS2), (int)g_fl_alto);
}
