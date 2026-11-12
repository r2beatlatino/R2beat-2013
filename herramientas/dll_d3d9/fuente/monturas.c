/* monturas.c — (142) LAS MONTURAS (`callobject.txt` del 2019) en la sala del 2013, 1 a 1 con el 2019 (30-oct-2026)
 *
 *   anonimo03: «no replicar, no atajos: ENTENDER el 2019 para que el código que exportemos al 2013 —aunque no sea igual—
 *   funcione 1 a 1». Cada número de acá sale del código del 2019 leído y MEDIDO en vivo (Frida): el pseudo-C y las
 *   mediciones están en documentacion/MONTURAS_COMO_LO_HACE_EL_2019.md. Los datos (16 ítems, modelos, animaciones,
 *   la tabla `montura_datos.h`) los arma herramientas/monturas_crear.py. Se INCLUYE desde d3d9_proxy.c, DESPUÉS de
 *   flotar.c (usa sus ayudantes fl_*) y de selector.c (usa su canal con el server, sp_pedir).
 *
 *   LO QUE HACE EL 2019 (medido) Y CÓMO VA ACÁ
 *   · EL OBJETO. cCall_Object::Render (0x52C210) lo dibuja con la matriz del mundo = RotY(rumbo_obj) · T(P.x, P.y +
 *     ModelY, P.z): la Z «− ModelZ» de Create (0x52C5E0) se cancela con el T(0,0,+300) del fondo de la sala, que
 *     cRoom::Render (0xA5A474) deja puesto mientras dibuja los objetos (medido: mundo (0,0,300) al entrar, (0,150,0)
 *     al dibujar el caballito). O sea: el objeto va a la MISMA profundidad que el jugador, y por eso «tapa» o no según
 *     el z-buffer, pixel a pixel. ⛔ El intento 1 lo ponía 300 detrás: más chico por la perspectiva y siempre atrás.
 *     Acá es un Fx del personaje (0x4B06C0, el que ya sabe cargar el .md9 y su .ani) y al dibujarlo (0x4AFCB0:
 *     RotY(w + rumbo + π) · T(x, y + 21, z), medido) se le ponen x = P.x, y = P.y + ModelY − 21, z = P.z y el w que da
 *     el rumbo del 2019. La cámara del 2013 es la MISMA (medido: proyección 45° 4:3, vista con −1,8°, ojo en
 *     (x, 352, z − 1002): AplicarMontura 0xE5D4BB del 2019 y SetPosicion 0x5B0410 del 2013 usan los mismos números).
 *   · EL JUGADOR. GetSeat (0x52D6E0) = P + nodo del .md9 + asiento de la tabla (por cuerpo, lado y los casos por
 *     código); SetPosicion (0xE58300; acá 0x5B0360, que también mueve la cámara) y mira al frente (π).
 *   · LA ANIMACIÓN (sRoomUser::AniMontura 0xE5E870): «Ani_<cuerpo>» sola; de a dos con AniChange, «Ani_L/R_<cuerpo>»
 *     o «Ani_<cuerpo>_couple» (acá su alias «Ani_C_<cuerpo>»: el 2013 pega el cuerpo al final). El reloj del objeto
 *     = el del que monta (SyncAnim 0x52C0A0).
 *   · EL HOVER Y EL CLIC (cCall_ObjectMng::Process 0x530DF0, cCall_Object::Process 0x52B840): rayo del mouse contra
 *     la CAJA del modelo (el pick 0x52CB50 arma 12 triángulos con ella) en T(P.x, P.y+ModelY, P.z); sólo la montura
 *     propia o la de la pareja (si es de dos). Borde amarillo = DrawOutline(handle, 0xFF, 3, 1, 0x64FFFF00, 0x2020201):
 *     el 2013 tiene LA MISMA función (0x638210) y el mismo Outline.obj. Cursor 7 (action01, subir / unirse) y 12
 *     (action05, bajarse): el 2013 tiene las mismas 8 primeras de la lista; se le agregan las 5 del 2019.
 *     El clic pide al server (FFFB, el canal del selector) subir / bajar / unirse; el server contesta y repinta a
 *     toda la sala con el byte de arriba del Wing Id (servidor/monturas.py).
 *   [montura] activo=0 lo apaga · retrato=0 deja el minichar como el de fábrica · log=1 anota cada cambio (y cada 0,4 s
 *   el reloj, la animación y la posición de los que montan) · sincronizar=0 y volver=0: los controles al revés de la 3.ª
 *   vuelta (el reloj del que se une suelto; bajarse / el FF15 lo dejan donde lo pone Init) · bajar_donde_subio=1: se
 *   baja donde hizo clic para subir (el 2019 lo deja donde estaba sentado, en el piso: MONTURAS_COMO_LO_HACE_EL_2019.md §13).
 *
 *   ★ (144) LA QUE CAMINA: EL TIGRE BLANCO (백호, 11000958; documentacion/MONTURA_TIGRE.md). No es un callobject: el jinete
 *   va en el ORIGEN del tigre (sin asiento) y su .ani lo sube al lomo; el tigre y los jinetes cambian de animación según
 *   lo que hace el que maneja: quieto «콜11000958», caminando «…_walk» (el 2013 pide «걷기» / «대쉬» al caminar con las
 *   flechas) y rugiendo «…_skill_1». De a dos: «_BG» chico + chica, «_bb1» / «_bb2» dos chicos y «_gg1» / «_gg2» dos
 *   chicas (1 = el dueño, adelante; 2 = el que se une, atrás). El rugido: en el VFUN es un botón de la ventana de la
 *   montura (`rnr_ui2/mount/interaction.rui`); el 2013 no tiene esa ventana, así que lo dispara el gesto de «Mi Acción»
 *   con el tigre montado (en las otras monturas el gesto lo baja al piso). [montura] rugido=0 lo apaga.
 */
#include "montura_datos.h"

typedef void (__attribute__((thiscall)) *F_MO_PONER)(void *pj, int fx, float x, float y, float z, float w);   /* 0x4B06C0 */
typedef void (__attribute__((thiscall)) *F_MO_SACAR)(void *pj, int fx);                                     /* 0x4AF880 */
typedef DWORD (__attribute__((thiscall)) *F_MO_CHAR)(void *mgr, BYTE slot);                                 /* 0x436380 */
typedef const char *(__attribute__((thiscall)) *F_MO_CUERPO)(void *items, DWORD ch);                         /* 0x485F30 */
typedef BYTE (__attribute__((thiscall)) *F_MO_PAREJA)(void *mgr, BYTE slot);                                /* 0x500860 */
typedef void (__attribute__((thiscall)) *F_MO_SETPOS)(BYTE *usr, float x, float y, float z, int camara);    /* 0x5B0360 */
typedef void (__attribute__((thiscall)) *F_MO_CAMARA)(void *cam, int a, float x, float y, float z);         /* 0x643C20 / 0x643D40 */
typedef int (__attribute__((thiscall)) *F_MO_BORDE)(void *mm, DWORD h, int alfa, int pasada, int x, DWORD color, DWORD banderas); /* 0x638210 */
typedef void (__attribute__((thiscall)) *F_MO_D3D0)(void *d3d);                                             /* cD3D Push / Pop */
typedef void (__attribute__((thiscall)) *F_MO_D3D3)(void *d3d, float x, float y, float z);                  /* cD3D Translate */
typedef void (__attribute__((thiscall)) *F_MO_D3D1)(void *d3d, float a);                                    /* cD3D RotY */
typedef void (__attribute__((thiscall)) *F_MO_EMPUJAR)(void *vec, HCURSOR *c);                              /* 0x641080 */
typedef void (__cdecl *F_MO_CURSOR)(void);                                                                  /* 0x433140 */
typedef int (__attribute__((thiscall)) *F_MO_NODO)(void *modelo, const char *nombre);                       /* 0x6505E0 */
typedef void (__attribute__((thiscall)) *F_MO_CAJA)(void *modelo, int idx, float *a, float *b);              /* 0x650510 */
typedef void *(__attribute__((thiscall)) *F_MO_BUSCAR)(void *tabla, DWORD numero);                           /* 0x413000 */
typedef void (__attribute__((thiscall)) *F_MO_MATRIZ)(void *d3d, int estado, float *m);                      /* cD3D vt+0x64 */

#define MO_PI 3.14159265f
#define MO_MAX 32
#define MO_ITEM_SUBIBAJA 11000622
#define MO_ITEM_PERLA    11000640

static int g_mo_activo = 0, g_mo_log = 0, g_mo_retrato = 1, g_mo_avisos = 0;
static int g_mo_sincro = 1;     /* [montura] sincronizar=0 lo apaga (el control al revés de la 3.ª vuelta) */
static int g_mo_volver = 1;     /* [montura] volver=0: bajarse / el FF15 dejan al jugador donde los pone Init (el control) */
static int g_mo_bajar_clic = 0; /* [montura] bajar_donde_subio=1: donde hizo clic, no donde está sentado (el 2019) */
static int g_mo_rugido = 1;     /* (144) [montura] rugido=0: el gesto con el tigre montado lo baja al piso, como las demás */
static int g_mo_freno = 1;      /* (144) [montura] freno=0: el control al revés (frena con el largo de la animación de la montura) */
static int g_mo_al_dia = 1;     /* (144) [montura] al_dia=0: el control (el objeto se dibuja con la P del cuadro anterior) */
#define MO_MOV_QUIETO 0
#define MO_MOV_CAMINA 1
#define MO_MOV_RUGE   2

/* el estado de cada personaje de la sala (por pj = [usr+0x1B8], como flotar) */
typedef struct {
    void *pj;
    BYTE *usr;            /* el sRoomUser de la sala (no la copia de Init en la pila) */
    int byte;             /* el byte alto del Wing Id que llegó (-1 = nunca) */
    int k;                /* la montura PROPIA (-1 = no tiene) */
    int modo;             /* 0 parado · 1 en la propia · 2 en la de la pareja */
    float P[3];           /* dónde está parado = dónde se invocó su objeto (el 2019 guarda +0x2A4..: igual) */
    int hayP;
    int fx;               /* el Fx del objeto que tiene puesto (0 = ninguno) */
    int sentado;          /* 1 si se le aplicó el asiento */
    float asiento[3];     /* el último asiento aplicado */
    const char *llave;    /* la última animación de montura pedida (NULL = ninguna) */
    char llave_buf[48];
    BYTE slot, cuerpo;
    int hover;            /* este cuadro: el mouse está sobre SU objeto (y es mío o de mi pareja) */
    int dueno_slot;       /* modo 2: el casillero del dueño de la montura en la que va */
    float rel[3];         /* el asiento respecto de P SIN girar (nodo + columna): GetSeat del 2019 menos P */
    float rumbo_obj;      /* el giro del objeto (cCall_Object +0x130): el del que monta + π; 0 al invocarlo */
    /* ★ (142, 3.ª vuelta) DÓNDE ESTÁ PARADO: se sigue cada cuadro mientras no va montado y al subir se congela (el 2019
     *   lo guarda en SetModo 0xE5CEE0 → usr+0x2A4/+0x2A8/+0x2AC). Al bajar es adónde va (mo_bajar_calc), y un FF15 que lo
     *   rearma lo devuelve ahí. */
    float parado[3];
    int hay_parado;
    DWORD visto;          /* GetTickCount del último cuadro dibujado (para saber si el FF15 es de alguien que YA estaba) */
    int reinit;           /* lo rearmó un FF15 (Init lo pone en su casillero): devolverlo a `parado` en el próximo cuadro */
    int esperar_init;     /* el cambio llegó por la respuesta del server: el FF15 que viene atrás tampoco lo mueve */
    int subir, bajar;     /* pasó de parado a montado / de montado a parado (los dos los dice el byte) */
    float obj_rel[3];     /* `parado` respecto del objeto al subir (P y giro): si el objeto se movió, se baja en el mismo lugar relativo */
    float rumbo_subir;
    int hay_rel;
    /* ★ (142, prueba en masa) EL GESTO DE ENTRADA ANTES QUE LA MONTURA: al entrar / volver a la sala (Init) no se lo
     *   sienta hasta que termine su saludo (0x5B2260: la ceremonia o la pose de entrada). Si no, saluda flotando. */
    int espera_gesto;     /* recién armado por Init: todavía no se lo sienta */
    int gesto;            /* el juego le pidió una animación que no es de quieto / caminar: está saludando */
    int decidido;         /* ya se miró si viene con fade-in (sin fade-in no hay saludo) */
    int entrada_idx;      /* la fila de entrada que trajo su ficha (0 = ninguna) */
    DWORD espera_t, alfa_t;
    /* ★ (144) las que CAMINAN (el tigre): qué hace el OBJETO de este dueño — 0 quieto · 1 caminando · 2 rugiendo */
    int mov;
    DWORD ruge_t;
    /* ★ (144, anonimo03: «tardan en detenerse») el FRENO: el juego pidió «정지» (frenar, después de correr) o «탈진» (agotado)
     *   y le devolvimos la animación de la montura, mucho más larga. Mientras dura, el 2013 lo tiene «ocupado» (usr+0x14C
     *   = 1, 0x59B84E) y sigue deslizando hasta que la animación termina (0x5B2D66: reloj ≥ largo → 0x5B20C0). Acá se le
     *   corre el reloj para que le quede lo MISMO que a pie (boy_stop.ani 84, boy_tired.ani 180: montura_datos.h). */
    float freno;
    int dibujos;          /* (144, diagnóstico) veces que se dibujó su objeto en el cuadro */
    float P_dibujado[3];  /* (144, diagnóstico) dónde se dibujó su objeto en este cuadro */
    int hay_dibujado;
    float desfase_max;    /* (144, diagnóstico) lo más lejos que quedó el objeto del jinete al dibujarlos (cada 0,4 s) */
} MO_EST;
static MO_EST g_mo[MO_MAX];
static int g_mo_prox = 0;

/* el pedido al server (un hilo: el juego no se traba esperando) */
static volatile LONG g_mo_pidiendo = 0, g_mo_listo = 0;
static int g_mo_ped_accion = 0, g_mo_ped_slot = 0xFF, g_mo_res_ok = 0, g_mo_res_byte = 0;
static int g_mo_boton_antes = 0, g_mo_cursor_puesto = 0;
static HCURSOR g_mo_cursores[5];

/* ⛔⛔ (prueba en masa, 31-oct) LA SALA SE ARMA DE NUEVO al volver de la carrera (y al salir y entrar): los personajes
 *   (pj), sus sRoomUser y su lista de Fx son OTROS. La tabla guardaba los viejos y el primer byte que llegaba al volver
 *   hacía mo_objeto → 0x4AF880 (sacar el Fx) sobre un pj LIBERADO: se cayeron los 6 juegos a la vez (cajanegra:
 *   0x4AF88E desde Init, eax = 0x53A = el Fx del subibaja). Ahora: si la sala no se dibujó por más de 1 s, la tabla
 *   se vacía entera antes de usarla (sin tocar nada del juego: lo viejo ya no existe). */
static DWORD g_mo_render_t = 0;
/* ★ (paso 3) AL VOLVER DE LA CARRERA EL OBJETO VUELVE DONDE ESTABA: el 2019 lo recibe del server en el RoomInfo
 *   (cada objeto con su x, y, z y giro: lo que arma q19_objeto.py); el nuestro no lo guarda. Acá se recuerda, por
 *   casillero, dónde quedó cada objeto al irse la sala, y la montura nueva del mismo casillero y el mismo k lo retoma. */
static struct { int k; float P[3]; float rumbo; } g_mo_guardado[16];
static void mo_escena_nueva(void)
{
    /* ⚠ minimizado el juego no dibuja la sala pero los personajes siguen vivos: ahí no se olvida nada */
    if (g_mo_render_t && GetTickCount() - g_mo_render_t > 1000 && !(g_ventana && IsIconic(g_ventana))) {
        int n = 0;
        for (int i = 0; i < MO_MAX; i++) if (g_mo[i].pj) n++;
        for (int s = 0; s < 16; s++) g_mo_guardado[s].k = -1;
        for (int i = 0; i < MO_MAX; i++)
            if (g_mo[i].pj && g_mo[i].k >= 0 && g_mo[i].hayP && g_mo[i].slot < 16 && (g_mo[i].P[0] != 0.0f || g_mo[i].P[2] != 0.0f)) {
                g_mo_guardado[g_mo[i].slot].k = g_mo[i].k;
                for (int e = 0; e < 3; e++) g_mo_guardado[g_mo[i].slot].P[e] = g_mo[i].P[e];
                g_mo_guardado[g_mo[i].slot].rumbo = g_mo[i].rumbo_obj;
            }
        ZeroMemory(g_mo, sizeof g_mo);
        g_mo_render_t = 0;                       /* los Init que siguen (los demás de la sala) ya no borran */
        apuntar("  [montura] la sala se armó de nuevo (carrera / salir y entrar): olvido %d personajes viejos", n);
    }
}

static int mo_de_pj(void *pj)
{
    for (int i = 0; pj && i < MO_MAX; i++)
        if (g_mo[i].pj == pj) return i;
    return -1;
}

static int mo_de_slot(BYTE slot)
{
    for (int i = 0; i < MO_MAX; i++)
        if (g_mo[i].pj && g_mo[i].usr && g_mo[i].slot == slot && fl_leer(g_mo[i].usr, 0x1B8) == g_mo[i].pj) return i;
    return -1;
}

static int mo_nuevo(void *pj)
{
    int i = mo_de_pj(pj);
    if (i >= 0) return i;
    for (int j = 0; j < MO_MAX; j++)
        if (!g_mo[j].pj) { i = j; break; }
    if (i < 0) { i = g_mo_prox; g_mo_prox = (g_mo_prox + 1) % MO_MAX; }
    ZeroMemory(&g_mo[i], sizeof g_mo[i]);
    g_mo[i].pj = pj;
    g_mo[i].byte = -1;
    g_mo[i].k = -1;
    return i;
}

/* el cuerpo del de ese sRoomUser: 0 boy · 1 boy2 · 2 girl · 3 girl2 (el orden de las columnas de callobject.txt).
 *   El 2019 decide por el código del personaje: EsChica (0x692790) y Adultez (0x6858F0: ≤3 chico, ≤6 adulto). Acá, por
 *   el nombre del cuerpo del 2013 (0x485F30: «boy», «girl2»…), que es el mismo dato. */
static int mo_cuerpo(BYTE *usr)
{
    void *mgr = *(void **)FLV(0x931660), *items = *(void **)FLV(0x9314E0);
    if (!usr || !mgr || !items || !fl_leible(usr + 0x145, 1)) return 0;
    DWORD ch = ((F_MO_CHAR)FLV(0x436380))(mgr, usr[0x145]);
    if (!ch) return 0;
    const char *n = ((F_MO_CUERPO)FLV(0x485F30))(items, ch);
    if (!n || !fl_leible(n, 4)) return 0;
    int chica = n[0] == 'g', adulto = n[lstrlenA(n) - 1] == '2';
    return (chica ? 2 : 0) + (adulto ? 1 : 0);
}
#define MO_CHICA(c) ((c) >= 2)

static BYTE mo_mi_slot(void)
{
    BYTE *mgr = *(BYTE **)FLV(0x931660);
    return mgr && fl_leible(mgr + 0x40, 1) ? mgr[0x40] : 0xFF;
}

static BYTE mo_pareja_de(BYTE slot)
{
    void *mgr = *(void **)FLV(0x931660);
    return mgr && slot != 0xFF ? ((F_MO_PAREJA)FLV(0x500860))(mgr, slot) : 0xFF;
}

/* ¿sobre qué objeto está sentado este? (el dueño del objeto y el lado: 0 dueño, 1 la pareja) -> índice o -1 */
static int mo_objeto_de(int i, int *lado)
{
    if (g_mo[i].espera_gesto) return -1;             /* ★ saludando al entrar: todavía no va arriba de nada */
    if (g_mo[i].modo == 1 && g_mo[i].k >= 0) { *lado = 0; return i; }
    if (g_mo[i].modo == 2) {
        int j = mo_de_slot((BYTE)g_mo[i].dueno_slot);
        if (j >= 0 && g_mo[j].k >= 0 && g_mo[j].hayP && MO_TABLA[g_mo[j].k].pareja) { *lado = 1; return j; }
    }
    return -1;
}

/* el «kind» del objeto (cCall_Object+0x138, 0xE62480 en AplicarMontura): 10 lo monta un chico, 1 una chica, 11 los dos */
static int mo_kind(int dueno)
{
    int kind = 0;
    for (int i = 0; i < MO_MAX; i++) {
        int lado, o;
        if (!g_mo[i].pj || !g_mo[i].usr) continue;
        o = mo_objeto_de(i, &lado);
        if (o == dueno) kind |= MO_CHICA(g_mo[i].cuerpo) ? 1 : 10;
    }
    return kind;
}

/* ¿van los dos arriba de un objeto con AniChange? (el 2019: dueño modo 5 + pareja modo 6 -> AniMontura(1)) */
static int mo_de_a_dos(int dueno)
{
    if (dueno < 0 || g_mo[dueno].k < 0 || !MO_TABLA[g_mo[dueno].k].ani_change) return 0;
    int n = 0;
    for (int i = 0; i < MO_MAX; i++) {
        int lado;
        if (g_mo[i].pj && g_mo[i].usr && mo_objeto_de(i, &lado) == dueno) n++;
    }
    return n >= 2;
}

/* el OTRO que va en el objeto de `dueno` (el de a dos), o -1 */
static int mo_el_otro(int dueno, int i)
{
    for (int j = 0; j < MO_MAX; j++) {
        int lado;
        if (j != i && g_mo[j].pj && g_mo[j].usr && mo_objeto_de(j, &lado) == dueno) return j;
    }
    return -1;
}

/* RotY de Direct3D (vector fila): v · RotY(a) — el mismo giro que el 2019 le da al objeto (0x52C3A4) y al personaje */
static void mo_girar(const float *v, float a, float *out)
{
    float c = (float)__builtin_cosf(a), s = (float)__builtin_sinf(a);
    out[0] = v[0] * c + v[2] * s;                     /* D3DXMatrixRotationY: [c 0 -s / 0 1 0 / s 0 c], v · M */
    out[1] = v[1];
    out[2] = -v[0] * s + v[2] * c;
}

/* GetSeat (0x52D6E0): nodo[lado][cuerpo] (si el .md9 lo trae) + asiento[cuerpo], respecto de P y SIN girar; la Perla
 *   sin los dos arriba, con la x en 0 (la rama sin nodo, ítem 11000640 y kind != 11).
 *   ★ DE A DOS CON EL MISMO SEXO (lo que el 2019 no deja: sólo la pareja, y el subibaja y la perla con el 0x7B1): sin
 *   nodo, las columnas son por sexo y los dos caerían en el mismo lugar; el que se une toma la columna del otro sexo. */
static void mo_asiento_rel(int dueno, int lado, int cuerpo, int yo, float *rel)
{
    const MO_FILA *f = &MO_TABLA[g_mo[dueno].k];
    int c = cuerpo & 3;
    if (lado == 1 && !f->tiene_nodo[1][c]) {
        int otro = mo_el_otro(dueno, yo);
        if (otro >= 0 && MO_CHICA(g_mo[otro].cuerpo) == MO_CHICA(c)) c ^= 2;
    }
    for (int e = 0; e < 3; e++) rel[e] = f->asiento[c][e];
    if (f->tiene_nodo[lado][cuerpo & 3]) {
        for (int e = 0; e < 3; e++) rel[e] += f->nodo[lado][cuerpo & 3][e];
    } else if (f->item2019 == MO_ITEM_PERLA && mo_kind(dueno) != 11) {
        rel[0] = 0.0f;
    }
}

/* el asiento en el mundo: P + RotY(rumbo_obj) · rel (★ el 2019 no gira el asiento —su montado no se mueve—; con el
 *   giro en 2π, el de cuando se sube, es exactamente GetSeat) */
static void mo_asiento(int dueno, int lado, int cuerpo, int yo, float *out, float *rel)
{
    float g[3];
    mo_asiento_rel(dueno, lado, cuerpo, yo, rel);
    mo_girar(rel, g_mo[dueno].rumbo_obj, g);
    for (int e = 0; e < 3; e++) out[e] = g_mo[dueno].P[e] + g[e];
}

static void mo_anim(BYTE *usr, const char *llave)
{
    ((F_FL_ANIM)FLV(0x5B1670))(usr, llave, 0, 0);
    if (g_mo_log)
        apuntar("  [montura·diag] pid=%u t=%u slot=%d anim «%s»", GetCurrentProcessId(), GetTickCount(), usr[0x145], llave);
}

/* ★ DÓNDE SE BAJA (3.ª vuelta, MEDIDO en el 2019 con q19_baja.js): parado en (264, 0, 0), subibaja invocado en (-150, 0,
 *   0), se sube → sentado en (40, 80, 0); se baja → (40, 0, 0). O sea: queda DONDE ESTÁ SENTADO, en el piso. Leído:
 *   SetModo (0xE5CEE0) guarda la posición de parado en usr+0x2A4/+0x2AC, pero AplicarMontura la pisa con el asiento;
 *   Desmontar (0xE5D9B0) copia la posición actual (el asiento) a +0x2A4 y encola el estado 0xF, cuyo final (0xE5DEB0) pone
 *   +0x2A8 = el piso (0, o 100 si flota) y SetPosicion(+0x2A4). Acá: P del objeto + el asiento girado (lo mismo en todos
 *   los clientes, aunque Init lo haya movido) y la altura de cuando estaba parado. ⛔ Antes iba a P (donde se lo vio la
 *   1.ª vez): el que se unía volvía a «la posición base de la sala» (anonimo03, 31-oct).
 *   [montura] bajar_donde_subio=1: en cambio, donde estaba parado cuando hizo clic para subir (en el mismo lugar respecto
 *   del objeto, si el objeto se movió o giró con él arriba). Se calcula con el modo VIEJO. */
static void mo_bajar_calc(int i)
{
    MO_EST *m = &g_mo[i];
    int lado, o = mo_objeto_de(i, &lado);
    if (o >= 0 && m->hay_rel) {
        float g[3];
        if (g_mo_bajar_clic) {
            mo_girar(m->obj_rel, g_mo[o].rumbo_obj - m->rumbo_subir, g);
            for (int e = 0; e < 3; e++) m->parado[e] = g_mo[o].P[e] + g[e];
        } else {
            float r[3] = { m->rel[0], m->rel[1], m->rel[2] };
            /* (144) el tigre no tiene asiento (los dos van en su origen): cada uno se baja a un COSTADO, el dueño a la
             *   izquierda del tigre y el que se unió a la derecha (si no, quedaban parados uno encima del otro) */
            if (MO_TABLA[g_mo[o].k].camina) r[0] += lado == 0 ? -90.0f : 90.0f;
            mo_girar(r, g_mo[o].rumbo_obj, g);
            m->parado[0] = g_mo[o].P[0] + g[0];
            m->parado[2] = g_mo[o].P[2] + g[2];                       /* parado[1]: la del piso, de antes de subir */
        }
        m->hay_parado = 1;
    }
    if (!m->hay_parado) return;
    m->bajar = 1;
    m->esperar_init = 1;
    if (g_mo_log)
        apuntar("  [montura·diag] pid=%u t=%u slot=%d se baja en (%d, %d, %d)", GetCurrentProcessId(), GetTickCount(), m->slot,
                (int)m->parado[0], (int)m->parado[1], (int)m->parado[2]);
}

/* la cámara del que monta el subibaja (AplicarMontura 0xE5D56B del 2019): x ± 175 según el sexo */
static void mo_camara_subibaja(BYTE *usr, int chica)
{
    void *cam = *(void **)FLV(0x9314D4);
    if (!cam) return;
    float x = *(float *)(usr + 8) + (chica ? -175.0f : 175.0f), z = *(float *)(usr + 0x10);
    ((F_MO_CAMARA)FLV(0x643C20))(cam, 0, x, 352.0f, z - 1002.0f);
    ((F_MO_CAMARA)FLV(0x643D40))(cam, 0, x, 318.0f, z + 100.0f);
}

/* pone / saca / cambia el Fx del objeto de i (quieto, monta un chico, monta una chica: AplicarMontura 0xE5D79F) */
static void mo_objeto(int i)
{
    MO_EST *m = &g_mo[i];
    int quiero = 0;
    if (m->k >= 0 && m->hayP) {
        const MO_FILA *f = &MO_TABLA[m->k];
        int kind = mo_kind(i);
        quiero = f->fx[0];
        if (f->camina) {
            if (!kind) m->mov = MO_MOV_QUIETO;                         /* nadie arriba: quieto */
            quiero = f->fx[m->mov >= 0 && m->mov <= 2 ? m->mov : 0];   /* (144) quieto · caminando · rugiendo */
        } else if (f->ani_ob && kind == 10) quiero = f->fx[1];
        else if (f->ani_ob && kind == 1) quiero = f->fx[2];
    }
    if (quiero == m->fx) return;
    if (m->fx) ((F_MO_SACAR)FLV(0x4AF880))(m->pj, m->fx);
    m->fx = 0;
    if (quiero) {
        /* la posición que se pasa vale un cuadro (el update 0x4AF177 la pisa): la de verdad la pone mo_fx_dibujo */
        ((F_MO_PONER)FLV(0x4B06C0))(m->pj, quiero, m->P[0], m->P[1], m->P[2], 0.0f);
        m->fx = quiero;
    }
    if (g_mo_log)
        apuntar("  [montura] objeto de %p: Fx %d (k=%d) en (%d, %d, %d)", m->pj, m->fx, m->k, (int)m->P[0], (int)m->P[1],
                (int)m->P[2]);
}

/* la animación del que va en el objeto de `o` por el `lado` (AniMontura 0xE5E870): «Ani» sola (el motor pega
 *   _<cuerpo>); de a dos con AniChange, «Ani_C» para el subibaja y la Perla (y Sexo16 == 0xFF), «Ani_L» / «Ani_R» para
 *   las demás (Sexo16: 0 chico, 1 chica). (144) El tigre: «Ani» + lo que hace («_walk», «_skill_1») + el de a dos
 *   («_BG» chico + chica; «_bb1» / «_bb2» dos chicos; «_gg1» / «_gg2» dos chicas: 1 el dueño, 2 el que se une). */
static void mo_llave_calc(int i, int o, int lado, char *nueva)
{
    MO_EST *m = &g_mo[i];
    const MO_FILA *f = &MO_TABLA[g_mo[o].k];
    if (f->camina) {
        const char *mov = g_mo[o].mov == MO_MOV_CAMINA ? "_walk" : g_mo[o].mov == MO_MOV_RUGE ? "_skill_1" : "";
        const char *par = "";
        if (mo_de_a_dos(o)) {
            int otro = mo_el_otro(o, i);
            if (otro >= 0 && MO_CHICA(g_mo[otro].cuerpo) != MO_CHICA(m->cuerpo)) par = "_BG";
            else if (MO_CHICA(m->cuerpo)) par = lado == 0 ? "_gg1" : "_gg2";
            else par = lado == 0 ? "_bb1" : "_bb2";
        }
        wsprintfA(nueva, "%s%s%s", f->ani, mov, par);
        return;
    }
    const char *sufijo = "";
    if (mo_de_a_dos(o)) {
        int otro = mo_el_otro(o, i);
        if (f->item2019 == MO_ITEM_SUBIBAJA || f->item2019 == MO_ITEM_PERLA || !f->ani_lr) sufijo = "_C";
        else if (otro >= 0 && MO_CHICA(g_mo[otro].cuerpo) == MO_CHICA(m->cuerpo))
            sufijo = lado == 0 ? "_L" : "_R";                          /* ★ mismo sexo: el dueño a la izquierda */
        else sufijo = MO_CHICA(m->cuerpo) ? "_R" : "_L";               /* Sexo16: 0 chico (L), 1 chica (R) */
    }
    wsprintfA(nueva, "%s%s", f->ani, sufijo);
}

/* sienta / baja / reanima a i según su modo y el de su pareja (AplicarMontura 0xE5D0B0 · Desmontar 0xE5D9B0 ·
 *   AniMontura 0xE5E870). Es idempotente: se llama cada vez que cambia algo de cualquiera. */
static void mo_aplicar(int i)
{
    MO_EST *m = &g_mo[i];
    BYTE *u = m->usr;
    if (!u || fl_leer(u, 0x1B8) != m->pj || !fl_leible(u + 0x218, 4)) return;
    int lado = 0, o = mo_objeto_de(i, &lado);
    int yo = m->slot == mo_mi_slot();
    if (o >= 0) {
        float s[3];
        if (m->subir) {
            /* SetModo (0xE5CEE0): guarda dónde estaba parado (usr+0x2A4..) ANTES de sentarlo. ★ Sólo al SUBIR (el byte
             *   pasó de 0 a montado): un FF15 que lo rearma montado no vuelve a guardar ni a girar el objeto */
            if (lado == 0) g_mo[o].rumbo_obj = MO_PI + MO_PI;          /* SetRumbo(π) al subir: objeto en π + π */
            if (m->hay_parado) {
                for (int e = 0; e < 3; e++) m->obj_rel[e] = m->parado[e] - g_mo[o].P[e];
                m->rumbo_subir = g_mo[o].rumbo_obj;
                m->hay_rel = 1;
            }
            m->subir = 0;
        }
        mo_asiento(o, lado, m->cuerpo, i, s, m->rel);
        if (!m->sentado || s[0] != m->asiento[0] || s[1] != m->asiento[1] || s[2] != m->asiento[2]) {
            /* SetPosicion (0x5B0360): escribe usr+8/+0xC/+0x10, ubica [usr+4] y, si es uno mismo, la cámara (x, 352,
             *   z − 1002) — exactamente lo que hace AplicarMontura del 2019 después de GetSeat */
            ((F_MO_SETPOS)FLV(0x5B0360))(u, s[0], s[1], s[2], 1);
            *(float *)(u + 0x24) = g_mo[o].rumbo_obj - MO_PI;              /* SetRumbo(π) + usr+0x2C = π (0xE5D28A) */
            *(float *)(u + 0x28) = g_mo[o].rumbo_obj - MO_PI;
            if (yo && MO_TABLA[g_mo[o].k].item2019 == MO_ITEM_SUBIBAJA) mo_camara_subibaja(u, MO_CHICA(m->cuerpo));
            m->asiento[0] = s[0]; m->asiento[1] = s[1]; m->asiento[2] = s[2];
            m->sentado = 1;
        }
        /* ⛔ (3.ª vuelta, MEDIDO) antes se escribía la llave nueva EN llave_buf y se la comparaba con m->llave, que
         *   apunta a llave_buf: siempre «igual», así que al cambiar de sola a de a dos (o al revés) NO se llamaba a 0x5B1670.
         *   El que ya iba arriba seguía con la vieja hasta que terminaba la vuelta y el juego la repetía (fl_anim →
         *   mo_llave_montado ya devolvía la nueva): el dueño entraba al «de a dos» hasta 300 tics tarde (desfasado del que
         *   se unió: 224 tics de 840 en los tres clientes) y, al bajarse el otro, seguía hamacándose hasta 840 (3,9 s). */
        char nueva[sizeof m->llave_buf];
        mo_llave_calc(i, o, lado, nueva);
        if (!m->llave || lstrcmpA(m->llave_buf, nueva)) {
            lstrcpyA(m->llave_buf, nueva);
            m->llave = m->llave_buf;
            mo_anim(u, m->llave);
        }
    } else if (m->sentado || m->bajar) {
        /* Desmontar (0xE5D9B0): al piso, donde estaba sentado (mo_bajar_calc, medido en el 2019) y la cámara; la
         *   animación de quieto. ⛔ Antes iba a P (el lugar donde se invocó el objeto o donde se lo vio la 1.ª vez): el que
         *   se unía volvía a la «posición base de la sala» (anonimo03, 31-oct). */
        if (m->bajar && m->hay_parado && g_mo_volver)
            ((F_MO_SETPOS)FLV(0x5B0360))(u, m->parado[0], m->parado[1], m->parado[2], 1);
        m->bajar = 0;
        m->sentado = 0;
        m->llave = NULL;
        mo_anim(u, FL_IDLE);
    }
}

static void mo_aplicar_todos(void);

/* (144) el objeto del dueño `o` (una que camina) pasa a hacer `mov`: su Fx y la animación de los que van arriba.
 *   `quien` (o -1): el que el juego está animando AHORA (fl_anim → mo_llave_montado): a ése sólo se le arma la llave
 *   nueva en llave_buf, porque la va a reproducir el juego con lo que devuelve el gancho. */
static void mo_tigre_mov(int o, int mov, int quien)
{
    if (o < 0 || g_mo[o].k < 0 || !MO_TABLA[g_mo[o].k].camina || g_mo[o].mov == mov) return;
    g_mo[o].mov = mov;
    if (mov == MO_MOV_RUGE) g_mo[o].ruge_t = GetTickCount();
    mo_objeto(o);
    if (g_mo[o].mov != mov) return;                                    /* nadie arriba: se quedó quieto */
    for (int j = 0; j < MO_MAX; j++) {
        int lado;
        if (!g_mo[j].pj || !g_mo[j].usr || !g_mo[j].sentado || mo_objeto_de(j, &lado) != o) continue;
        if (j == quien) {
            char nueva[sizeof g_mo[j].llave_buf];
            mo_llave_calc(j, o, lado, nueva);
            lstrcpyA(g_mo[j].llave_buf, nueva);
            g_mo[j].llave = g_mo[j].llave_buf;
        } else mo_aplicar(j);
    }
    if (g_mo_log)
        apuntar("  [montura·diag] pid=%u t=%u el tigre del slot %d: %s", GetCurrentProcessId(), GetTickCount(), g_mo[o].slot,
                mov == MO_MOV_CAMINA ? "camina" : mov == MO_MOV_RUGE ? "ruge" : "quieto");
}

static void mo_aplicar_todos(void)
{
    for (int i = 0; i < MO_MAX; i++)
        if (g_mo[i].pj) mo_objeto(i);
    for (int i = 0; i < MO_MAX; i++)
        if (g_mo[i].pj) mo_aplicar(i);
}

/* el objeto de este casillero estaba en otro lado antes de la carrera: vuelve ahí (g_mo_guardado) */
static void mo_retomar(int i)
{
    MO_EST *m = &g_mo[i];
    if (m->k < 0 || !m->usr || m->slot >= 16 || g_mo_guardado[m->slot].k != m->k) return;
    for (int e = 0; e < 3; e++) m->P[e] = g_mo_guardado[m->slot].P[e];
    m->rumbo_obj = g_mo_guardado[m->slot].rumbo;
    m->hayP = 1;
    g_mo_guardado[m->slot].k = -1;
    if (g_mo_log)
        apuntar("  [montura·diag] pid=%u slot=%d el objeto vuelve donde estaba: (%d, %d, %d)", GetCurrentProcessId(), m->slot,
                (int)m->P[0], (int)m->P[1], (int)m->P[2]);
}

/* el byte alto del Wing Id: 0x80 | 0x40 (tiene la suya) | modo << 4 | k   (servidor/monturas.py, `codificar`)
 *   ★ (144) con 0x40 el modo es 0 ó 1 (el 2 va sin 0x40), así que 0x20 lleva el 5.º bit de k: la 17.ª (k = 16) es 0xE0 */
static void mo_decodificar(int b, int *k, int *modo, int *dueno)
{
    *k = -1;
    *modo = 0;
    *dueno = -1;
    if (b < 0 || !(b & 0x80)) return;
    if (b & 0x40) {
        *modo = (b >> 4) & 1;
        *k = ((b & 0x20) >> 1) | (b & 0x0F);
    } else {
        *modo = (b >> 4) & 3;
        if (*modo == 2) { *dueno = b & 0x0F; return; }   /* en la de otro: los 4 bits de abajo son su casillero */
        *modo = 0;
    }
    if (*k >= MO_N) *k = -1;
    if (*modo == 1 && *k < 0) *modo = 0;
}

/* llegó un byte para este personaje (Init, las alas en vivo o la respuesta del server) */
static void mo_desde_byte(void *pj, BYTE *usr, int b)
{
    if (!g_mo_activo || !pj) return;
    mo_escena_nueva();
    int k, modo, dueno;
    mo_decodificar(b, &k, &modo, &dueno);
    int i = mo_de_pj(pj);
    if (i < 0) {
        if (k < 0 && !modo) return;
        i = mo_nuevo(pj);
    }
    MO_EST *m = &g_mo[i];
    if (usr && !fl_en_pila(usr) && fl_leer(usr, 0x1B8) == pj) {
        m->usr = usr;
        m->slot = usr[0x145];
        m->cuerpo = (BYTE)mo_cuerpo(usr);
    }
    /* ⛔ (prueba en masa) acá NO se toma P de usr: en el FF0C, Init todavía no lo ubicó (x = z = 0) y el objeto de
     *   jugador23 quedó en el centro de la sala (0, 0, 0) en los 3 clientes. Lo toma mo_render, con el de la sala ya ubicado. */
    if (m->byte == b && m->k == k && m->modo == modo) return;
    if (k >= 0 && m->k != k) {
        m->rumbo_obj = 0.0f;                                           /* invocada nueva: giro 0 (cCall_ObjectUI) */
        /* y donde está parado AHORA (no donde se lo vio la 1.ª vez, ni donde lo dejó Init) */
        if (m->hay_parado && !m->sentado && (m->parado[0] != 0.0f || m->parado[2] != 0.0f)) {
            for (int e = 0; e < 3; e++) m->P[e] = m->parado[e];
            m->hayP = 1;
        }
    }
    /* ★ los cambios de modo (con el modo VIEJO todavía puesto): bajarse calcula dónde; subir guarda dónde estaba */
    int bajo = m->modo != 0 && (modo != m->modo || (modo == 2 && dueno != m->dueno_slot));
    if (bajo) mo_bajar_calc(i);
    if (modo != 0 && (m->modo == 0 || bajo)) { m->subir = 1; m->bajar = 0; }
    m->dueno_slot = dueno;
    if (g_mo_log || g_mo_avisos < 24) {
        g_mo_avisos++;
        apuntar("  [montura] %p (slot %d): byte 0x%02X -> montura %d, modo %d", pj, m->slot, b & 0xFF, k, modo);
    }
    m->byte = b;
    m->k = k;
    m->modo = modo;
    if (m->usr) mo_retomar(i);                                         /* ★ volvió de la carrera: donde estaba */
    mo_aplicar_todos();
}

/* ═══ EL GESTO DE ENTRADA PRIMERO ═══════════════════════════════════════════════════════════════════════════════
 *   El 2013 saluda al entrar a la sala (sRoomUser 0x5B2260: lo llama Init y otra vez el fade-in cuando el alfa usr+0x144
 *   llega a 255, 0x5B2985): la fila de entrada (uno mismo 0x4B23A0(2, casillero); los demás 0x4B1840(2, usr+0x163,
 *   cuerpo)) con la pose, la cara, el Fx y el sonido (0x5B1D70). Cuando la pose termina, el juego pide «대기1» (0x5B2187).
 *   anonimo03: «el gesto de entrada debe funcionar antes de la montura; recién después iniciar la montura, si no el char
 *   queda flotando mientras hace su saludo». (El 2019 tampoco sienta en el acto: SetModo encola AplicarMontura con 15
 *   tics de demora en la cola usr+0x26C, 0xE5A6D0.) Acá: desde Init, el que tiene saludo espera parado hasta el «대기1»
 *   que sigue al saludo; el que no tiene, se sienta en el primer cuadro (el que entra ve bien a los que ya montan). */
static void mo_soltar_gesto(int i, const char *por)
{
    MO_EST *m = &g_mo[i];
    if (!m->espera_gesto) return;
    m->espera_gesto = 0;
    m->gesto = 0;
    if (g_mo_log)
        apuntar("  [montura·diag] pid=%u t=%u slot=%d entrada: se sienta (%s, %u ms)", GetCurrentProcessId(), GetTickCount(),
                m->slot, por, GetTickCount() - m->espera_t);
    mo_aplicar_todos();
}

/* cada cuadro, desde el dibujo del sRoomUser de la sala, mientras espera el saludo */
static void mo_espera(int i, BYTE *usr)
{
    MO_EST *m = &g_mo[i];
    DWORD ahora = GetTickCount();
    if (!m->decidido) {
        m->decidido = 1;
        /* sin fade-in (alfa ya 255) el juego no vuelve a llamar a 0x5B2260: no hay saludo */
        /* MEDIDO (tanda 1): los demás sólo saludan si su ficha trae fila de entrada (idx, FF0C cola[17]); uno mismo
         *   la busca en su inventario (0x4B23A0). Un fade-in sin fila (el casillero 0 entra con ficha+0x21 = 0) no saluda. */
        int va = usr[0x144] != 0xFF && (m->entrada_idx != 0 || m->slot == mo_mi_slot());
        if (g_mo_log)
            apuntar("  [montura·diag] pid=%u t=%u slot=%d entrada: idx=%d alfa=%d -> %s", GetCurrentProcessId(), ahora,
                    m->slot, m->entrada_idx, usr[0x144], va ? "espera el fade-in y el saludo" : "sin saludo");
        if (!va && !m->gesto) { mo_soltar_gesto(i, "sin fade-in"); return; }
    }
    if (!m->gesto && usr[0x144] == 0xFF) {                              /* el fade-in terminó y no saludó */
        if (!m->alfa_t) m->alfa_t = ahora;
        else if (ahora - m->alfa_t > 300) { mo_soltar_gesto(i, "el saludo no vino"); return; }
    }
    if (ahora - m->espera_t > (m->gesto ? 30000u : 12000u)) mo_soltar_gesto(i, "tiempo");
}

/* después de sRoomUser::Init (flotar.c): el sRoomUser es NUEVO (FF0C / FF15): se lo vuelve a sentar si iba montado */
static void mo_tras_init(BYTE *usr, int b)
{
    if (!g_mo_activo || !usr) return;
    void *pj = fl_leer(usr, 0x1B8);
    if (!pj) return;
    mo_escena_nueva();
    int i = mo_de_pj(pj);
    if (i < 0) i = mo_nuevo(pj);
    /* ★ recién entrado (o de vuelta de la carrera): primero el saludo, después la montura (mo_espera) */
    g_mo[i].espera_gesto = 1;
    g_mo[i].gesto = 0;
    g_mo[i].decidido = 0;
    g_mo[i].espera_t = GetTickCount();
    g_mo[i].alfa_t = 0;
    g_mo[i].entrada_idx = g_mo_init_entrada;
    if (i >= 0 && !fl_en_pila(usr)) {
        /* recién armado: está parado en su lugar (Init lo ubica en el casillero) */
        g_mo[i].usr = usr;
    }
    if (i >= 0) {
        /* ★ Init lo puso en su casillero. Si YA estaba en la sala (se lo dibujó hace nada) y el FF15 es de las monturas
         *   (byte de montura, iba montado, o es el que sigue a la respuesta del server), vuelve a donde estaba: el 2019 no
         *   rearma a nadie por un CmdRoomUserInfo, así que nadie se mueve por eso. */
        DWORD hace = GetTickCount() - g_mo[i].visto;
        if (g_mo_volver && g_mo[i].hay_parado && hace < 1500 && ((b >= 0 && (b & 0x80)) || g_mo[i].modo || g_mo[i].esperar_init)) {
            g_mo[i].reinit = 1;
            g_mo[i].esperar_init = 0;
        }
        g_mo[i].sentado = 0;
        g_mo[i].llave = NULL;
        if (g_mo[i].k < 0) g_mo[i].hayP = 0;   /* ★ el objeto se queda donde estaba (se pudo mover montado) */
        g_mo[i].fx = 0;                    /* si el Fx sigue, 0x4B06C0 devuelve el mismo nodo (no duplica) */
        g_mo[i].byte = -2;                                             /* fuerza re-aplicar */
        if (fl_en_pila(usr)) g_mo[i].usr = NULL;                      /* el de la sala lo anota mo_render */
    }
    mo_desde_byte(pj, fl_en_pila(usr) ? NULL : usr, b);
}

/* ★ un gesto con él YA arriba: al piso donde está sentado mientras dura; el «대기1» del final lo vuelve a subir */
static void mo_gesto_montado(int i, BYTE *usr, const char *que)
{
    MO_EST *m = &g_mo[i];
    float y = m->hay_parado ? m->parado[1] : *(float *)(usr + 0xC) - m->rel[1];
    ((F_MO_SETPOS)FLV(0x5B0360))(usr, *(float *)(usr + 8), y, *(float *)(usr + 0x10), 1);
    m->sentado = 0;
    m->llave = NULL;
    m->espera_gesto = 1;
    m->gesto = 1;
    m->decidido = 1;
    m->espera_t = GetTickCount();
    if (g_mo_log)
        apuntar("  [montura·diag] pid=%u t=%u slot=%d gesto montado «%s»: se baja al piso mientras dura", GetCurrentProcessId(),
                GetTickCount(), m->slot, que);
    mo_aplicar_todos();
}

/* ★ los EMOTES de «Mi Acción» no pasan por 0x5B1670: los pone 0x4B43C0 directo en el modelo (MEDIDO con Frida en
 *   0x655C20: «…AC0531B_boy» desde 0x4B4438). Se los ve en el modelo: si el que va sentado tiene puesta una animación
 *   que no es la de su montura (el nombre en [[modelo+0x130]+0x20], el que usa 0x5B2CD4), está haciendo un gesto. */
static int mo_anim_ajena(int i, BYTE *usr)
{
    int lado, o = mo_objeto_de(i, &lado);
    if (o < 0 || !fl_leible(usr, 4)) return 0;
    void *tabla = *(void **)FLV(0x931620);
    if (!tabla) return 0;
    BYTE *r = (BYTE *)((F_MO_BUSCAR)FLV(0x413000))(tabla, *(DWORD *)usr);
    if (!r || !fl_leible(r + 0x1C, 4)) return 0;
    BYTE *modelo = *(BYTE **)(r + 0x1C);
    if (!modelo || !fl_leible(modelo + 0x130, 4)) return 0;
    BYTE *an = *(BYTE **)(modelo + 0x130);
    if (!an || !fl_leible(an + 0x20, 0x18)) return 0;
    const char *nombre = *(DWORD *)(an + 0x34) >= 0x10 ? *(const char **)(an + 0x20) : (const char *)(an + 0x20);
    if (!nombre || !fl_leible(nombre, 4)) return 0;
    /* ⚠ el modelo guarda el ARCHIVO («so1254a_girl.ani»), no la llave del animap («콜SO1254A_girl»): se compara con
     *   la llave sin el «콜» (2 bytes cp949) y sin mayúsculas (MEDIDO: [an+0x20] = "so1254a_girl.ani") */
    const char *base = MO_TABLA[g_mo[o].k].ani + 2;
    int n = lstrlenA(base);
    for (int k = 0; k < n; k++) {
        char x = nombre[k], y = base[k];
        if (x >= 'A' && x <= 'Z') x += 32;
        if (y >= 'A' && y <= 'Z') y += 32;
        if (x != y) return 1;
    }
    return 0;
}

/* (144) el largo de la animación que tiene puesta el modelo del personaje: [[modelo+0x130]+0x18], el que compara el
 *   update de sRoomUser con el reloj usr+0x2C para terminarla (0x5B2D5A) */
static float mo_largo_anim(BYTE *usr)
{
    void *tabla = *(void **)FLV(0x931620);
    if (!tabla || !fl_leible(usr, 4)) return 0.0f;
    BYTE *r = (BYTE *)((F_MO_BUSCAR)FLV(0x413000))(tabla, *(DWORD *)usr);
    if (!r || !fl_leible(r + 0x1C, 4)) return 0.0f;
    BYTE *modelo = *(BYTE **)(r + 0x1C);
    if (!modelo || !fl_leible(modelo + 0x130, 4)) return 0.0f;
    BYTE *an = *(BYTE **)(modelo + 0x130);
    return an && fl_leible(an + 0x18, 4) ? *(float *)(an + 0x18) : 0.0f;
}

/* las animaciones de quieto / caminar / correr / agotado / frenar: montado, la de la montura (el 2019 no tiene idle
 *   ni caminar montado: sRoomUser::Anim 0xE54590) */
static const char *mo_llave_montado(BYTE *usr, const char *llave)
{
    if (!g_mo_activo || !usr || !llave) return llave;
    int i = mo_de_pj(fl_leer(usr, 0x1B8));
    if (i < 0) return llave;
    int quieto = 0;
    for (int k = 0; k < (int)(sizeof FL_EN_EL_AIRE / sizeof *FL_EN_EL_AIRE); k++)
        if (!lstrcmpA(llave, FL_EN_EL_AIRE[k])) quieto = 1;
    if (g_mo[i].espera_gesto) {
        /* ★ el saludo de entrada: una animación que no es de quieto lo empieza; el «대기1» que pide el juego al terminar
         *   (0x5B2187) lo termina y recién ahí se sienta */
        if (!quieto) {
            if (!g_mo[i].gesto && g_mo_log)
                apuntar("  [montura·diag] pid=%u t=%u slot=%d entrada: saluda «%s»", GetCurrentProcessId(), GetTickCount(),
                        g_mo[i].slot, llave);
            g_mo[i].gesto = 1;
        } else if (g_mo[i].gesto && !fl_en_pila(usr)) {
            mo_soltar_gesto(i, "terminó el saludo");
            if (g_mo[i].sentado && g_mo[i].llave) return g_mo[i].llave;
        }
        return llave;
    }
    if (!g_mo[i].sentado || !g_mo[i].llave) return llave;
    if (g_mo_freno && quieto && (!lstrcmpA(llave, FL_EN_EL_AIRE[4]) || !lstrcmpA(llave, FL_EN_EL_AIRE[3])))
        g_mo[i].freno = (!lstrcmpA(llave, FL_EN_EL_AIRE[4]) ? MO_DUR_FRENO : MO_DUR_AGOTADO)[g_mo[i].cuerpo & 3];
    /* ★ (144) el tigre: lo que pide el juego para el que MANEJA (el dueño) es lo que hace el tigre — «걷기» y «대쉬»
     *   caminando, lo demás de quieto quieto. Mientras ruge, un pedido de quieto antes de 1,5 s es el del gesto que lo
     *   disparó y se ignora; después es el del final del rugido (la .ani dura 400 ≈ 3,3 s). */
    {
        int lado, o = mo_objeto_de(i, &lado);
        if (quieto && o >= 0 && MO_TABLA[g_mo[o].k].camina) {
            int camina = !lstrcmpA(llave, FL_EN_EL_AIRE[1]) || !lstrcmpA(llave, FL_EN_EL_AIRE[2]);
            if (lado == 0) {
                if (g_mo[o].mov == MO_MOV_RUGE && !camina && GetTickCount() - g_mo[o].ruge_t < 1500) return g_mo[i].llave;
                mo_tigre_mov(o, camina ? MO_MOV_CAMINA : MO_MOV_QUIETO, i);
            }
            return g_mo[i].llave;
        }
    }
    if (quieto) return g_mo[i].llave;
    /* ★ un gesto con él ARRIBA (su propio saludo de entrada, que el juego le pide sin fade-in; un emote; un baile): el
     *   2013 no tiene pose montada para eso y quedaba «flotando» a la altura del asiento. Se baja al piso donde está
     *   sentado, hace el gesto y, con el «대기1» que pide el juego al terminar, vuelve a subir. */
    if (!fl_en_pila(usr) && g_mo[i].usr == usr) mo_gesto_montado(i, usr, llave);
    return llave;
}

/* ═══ ¿HAY INTERFAZ ENCIMA DEL OBJETO? (bug 5 de la prueba en masa) ═══════════════════════════════════════════
 *   El 2019 no deja el clic si el mouse está sobre una ventana: cCall_ObjectMng::Process pregunta a 0x537A50 /
 *   0x5719A0 (f85e90(ventana, mouse, "rect"): el control «rect» de cada .rui contra el mouse) y a 0xA6C650. En el 2013
 *   no se encontró ese dato (MEDIDO: ninguna bandera en .data cambia con el mouse sobre la UI; el despachador de UI
 *   0x686530 no corre en la sala; el cursor lo pisa la dll). ⇒ Se pregunta a la IMAGEN: al hacer clic sobre un objeto
 *   se copia el pixel del mouse justo después de lo 3D (lo último de la sala son los Fx: mo_fx_dibujo) y otra vez en
 *   el Present (con la interfaz ya dibujada). Si cambió, algo 2D lo tapó: el clic no es para el objeto.
 *   Un pixel, sólo en el cuadro del clic. [montura] tapa=0 lo apaga. */
typedef HRESULT (__stdcall *F_MO_PRESENT)(void *dev, const void *a, const void *b, HWND w, const void *r);
static F_MO_PRESENT g_mo_present_real = NULL;
static void *g_mo_rt[2] = { 0 }, *g_mo_sys = NULL;
static int g_mo_tapa = 1, g_mo_tapa_fase = 0, g_mo_tapa_a = 0, g_mo_pend_accion = 0, g_mo_pend_slot = 0xFF;
static DWORD g_mo_tapa_fmt = 0;
typedef HRESULT (__stdcall *F_MO_GETRT)(void *, DWORD, void **);
typedef HRESULT (__stdcall *F_MO_DESC)(void *, DWORD *);
typedef HRESULT (__stdcall *F_MO_CREARRT)(void *, UINT, UINT, DWORD, DWORD, DWORD, BOOL, void **, void *);
typedef HRESULT (__stdcall *F_MO_CREAROFF)(void *, UINT, UINT, DWORD, DWORD, void **, void *);
typedef HRESULT (__stdcall *F_MO_STRETCH)(void *, void *, const RECT *, void *, const RECT *, DWORD);
typedef HRESULT (__stdcall *F_MO_RTDATA)(void *, void *, void *);
typedef HRESULT (__stdcall *F_MO_LOCK)(void *, void *, const RECT *, DWORD);
typedef HRESULT (__stdcall *F_MO_UNLOCK)(void *);
typedef ULONG (__stdcall *F_MO_REL)(void *);

static void *mo_dev(void)
{
    BYTE *d3d = *(BYTE **)FLV(0x931498);
    return d3d ? *(void **)(d3d + 0xC0) : NULL;
}

static void mo_soltar_com(void **p)
{
    if (*p) { ((F_MO_REL)(*(void ***)*p)[2])(*p); *p = NULL; }
}

/* copia el pixel del mouse del render target actual a g_mo_rt[cual] (1x1) */
static int mo_tapa_copiar(int cual)
{
    void *dev = mo_dev();
    if (!dev) return 0;
    void **vt = *(void ***)dev;
    void *rt = NULL;
    if (((F_MO_GETRT)vt[38])(dev, 0, &rt) < 0 || !rt) return 0;
    DWORD desc[8];
    int ok = 0;
    if (((F_MO_DESC)(*(void ***)rt)[12])(rt, desc) >= 0 && desc[6] && desc[7]) {
        if (g_mo_tapa_fmt != desc[0]) {                                /* (re)crear las de 1x1 con el formato del RT */
            mo_soltar_com(&g_mo_rt[0]); mo_soltar_com(&g_mo_rt[1]); mo_soltar_com(&g_mo_sys);
            g_mo_tapa_fmt = desc[0];
        }
        for (int k = 0; k < 2; k++)
            if (!g_mo_rt[k]) ((F_MO_CREARRT)vt[28])(dev, 1, 1, desc[0], 0, 0, FALSE, &g_mo_rt[k], NULL);
        if (!g_mo_sys) ((F_MO_CREAROFF)vt[36])(dev, 1, 1, desc[0], 2 /* D3DPOOL_SYSTEMMEM */, &g_mo_sys, NULL);
        RECT r, cl;
        int mx = *(int *)FLV(0x931198), my = *(int *)FLV(0x93119C);
        if (g_mo_rt[cual] && g_ventana && GetClientRect(g_ventana, &cl) && cl.right > 0 && cl.bottom > 0 && mx >= 0 && my >= 0) {
            r.left = (LONG)((long long)mx * desc[6] / cl.right);
            r.top = (LONG)((long long)my * desc[7] / cl.bottom);
            if (r.left >= (LONG)desc[6]) r.left = desc[6] - 1;
            if (r.top >= (LONG)desc[7]) r.top = desc[7] - 1;
            r.right = r.left + 1;
            r.bottom = r.top + 1;
            ok = ((F_MO_STRETCH)vt[34])(dev, rt, &r, g_mo_rt[cual], NULL, 0) >= 0;
        }
    }
    ((F_MO_REL)(*(void ***)rt)[2])(rt);
    return ok;
}

static int mo_tapa_leer(int cual, DWORD *px)
{
    void *dev = mo_dev();
    if (!dev || !g_mo_rt[cual] || !g_mo_sys) return 0;
    void **vt = *(void ***)dev;
    if (((F_MO_RTDATA)vt[32])(dev, g_mo_rt[cual], g_mo_sys) < 0) return 0;
    struct { INT pitch; void *bits; } lr;
    if (((F_MO_LOCK)(*(void ***)g_mo_sys)[13])(g_mo_sys, &lr, NULL, 0x10 /* D3DLOCK_READONLY */) < 0) return 0;
    *px = *(DWORD *)lr.bits;
    ((F_MO_UNLOCK)(*(void ***)g_mo_sys)[14])(g_mo_sys);
    return 1;
}

static void mo_pedir(int accion, int slot);

static HRESULT __stdcall mo_present(void *dev, const void *a, const void *b, HWND w, const void *r)
{
    if (g_mo_tapa_fase == 1) {
        g_mo_tapa_fase = 0;
        DWORD pa = 0, pb = 0;
        int va = g_mo_tapa_a && mo_tapa_leer(0, &pa);
        int vb = mo_tapa_copiar(1) && mo_tapa_leer(1, &pb);
        int dif = 0;
        for (int s = 0; s < 24; s += 8) {
            int d = (int)((pa >> s) & 0xFF) - (int)((pb >> s) & 0xFF);
            if (d < 0) d = -d;
            if (d > dif) dif = d;
        }
        int tapado = va && vb && dif > 6;
        apuntar("  [montura] clic sobre un objeto: pixel 3D %06X / con la interfaz %06X -> %s", pa & 0xFFFFFF, pb & 0xFFFFFF,
                tapado ? "TAPADO por la interfaz: no se monta" : (va && vb ? "libre" : "sin medida: va"));
        if (!tapado) mo_pedir(g_mo_pend_accion, g_mo_pend_slot);
    }
    return g_mo_present_real(dev, a, b, w, r);
}

static void mo_present_enganchar(void)
{
    void *dev = mo_dev();
    if (!dev || g_mo_present_real || !g_mo_tapa) return;
    void **vt = *(void ***)dev;
    DWORD viejo;
    if (!VirtualProtect(&vt[17], 4, PAGE_EXECUTE_READWRITE, &viejo)) return;
    g_mo_present_real = (F_MO_PRESENT)vt[17];
    vt[17] = (void *)mo_present;
    VirtualProtect(&vt[17], 4, viejo, &viejo);
    apuntar("  [montura] ok: Present enganchado para «¿hay interfaz encima del objeto?»");
}

/* el clic sobre un objeto: con la guarda, se pide en el Present (si nada 2D lo tapó) */
static void mo_clic_objeto(int accion, int slot)
{
    if (!g_mo_tapa || !g_mo_present_real) { mo_pedir(accion, slot); return; }
    g_mo_pend_accion = accion;
    g_mo_pend_slot = slot;
    g_mo_tapa_a = 0;
    g_mo_tapa_fase = 1;
}

/* ═══ EL MOUSE: rayo, caja, cursor y clic ═══════════════════════════════════════════════════════════════════════ */
static int mo_rayo(float *o, float *d)
{
    void *d3d = *(void **)FLV(0x931498);
    BYTE *dev = d3d ? *(BYTE **)((BYTE *)d3d + 0xC0) : NULL;
    if (!dev || !g_ventana) return 0;
    void **vt = *(void ***)dev;
    typedef HRESULT (__stdcall *F_GT)(void *, int, float *);
    typedef HRESULT (__stdcall *F_GV)(void *, DWORD *);
    float V[16], P[16];
    DWORD vp[6];
    if (((F_GT)vt[45])(dev, 2, V) < 0 || ((F_GT)vt[45])(dev, 3, P) < 0 || ((F_GV)vt[48])(dev, vp) < 0) return 0;
    /* el mouse que ve el JUEGO (no el de Windows): [0x931198] / [0x93119C] en píxeles de la ventana (MEDIDO: los dos
     *   valores de un WM_MOUSEMOVE aparecen ahí y en nada más del exe; 21 lectores). El 2019 igual: PickRay toma el
     *   mouse de su objeto de entrada (0x4583A0 → +0x8 / +0xC), no el cursor de Windows. */
    POINT c = { *(int *)FLV(0x931198), *(int *)FLV(0x93119C) };
    RECT r;
    if (!GetClientRect(g_ventana, &r) || r.right <= 0 || r.bottom <= 0) return 0;
    if (c.x < 0 || c.y < 0 || c.x >= r.right || c.y >= r.bottom || !P[0] || !P[5]) return 0;
    /* PickRay del 2019 (0x52E310): del píxel a la vista con la proyección, y al mundo con la inversa de la vista */
    float px = (float)c.x * (float)vp[2] / (float)r.right, py = (float)c.y * (float)vp[3] / (float)r.bottom;
    float vx = (2.0f * px / (float)vp[2] - 1.0f) / P[0], vy = (1.0f - 2.0f * py / (float)vp[3]) / P[5], vz = 1.0f;
    for (int j = 0; j < 3; j++) {
        d[j] = vx * V[j * 4 + 0] + vy * V[j * 4 + 1] + vz * V[j * 4 + 2];
        o[j] = -(V[12] * V[j * 4 + 0] + V[13] * V[j * 4 + 1] + V[14] * V[j * 4 + 2]);
    }
    return 1;
}

/* el pick del 2019 (0x52CB50): el rayo contra la caja del modelo trasladada a (P.x, P.y + ModelY, P.z), sin rotar */
static float mo_pica(int dueno, const float *o, const float *d)
{
    const MO_FILA *f = &MO_TABLA[g_mo[dueno].k];
    float t0 = -1e30f, t1 = 1e30f, base[3] = { g_mo[dueno].P[0], g_mo[dueno].P[1] + f->modelo_y, g_mo[dueno].P[2] };
    float ol[3], dl[3];
    if (f->camina) {
        /* (144) el tigre es largo (z −189 … 158): la caja va GIRADA con él (el rayo al marco del tigre); las 16 no
         *   (el pick del 2019 no gira: su montado no se mueve) */
        float v[3] = { o[0] - base[0], o[1] - base[1], o[2] - base[2] };
        mo_girar(v, -g_mo[dueno].rumbo_obj, ol);
        mo_girar(d, -g_mo[dueno].rumbo_obj, dl);
        for (int e = 0; e < 3; e++) ol[e] += base[e];
        o = ol;
        d = dl;
    }
    for (int e = 0; e < 3; e++) {
        float a = f->caja[e] + base[e], b = f->caja[e + 3] + base[e];
        if (d[e] > -1e-6f && d[e] < 1e-6f) {
            if (o[e] < a || o[e] > b) return -1.0f;
            continue;
        }
        float ta = (a - o[e]) / d[e], tb = (b - o[e]) / d[e];
        if (ta > tb) { float t = ta; ta = tb; tb = t; }
        if (ta > t0) t0 = ta;
        if (tb < t1) t1 = tb;
        if (t0 > t1) return -1.0f;
    }
    return t1 > 0 ? (t0 > 0 ? t0 : 0.0f) : -1.0f;
}

/* la lista de cursores del 2013 (vector en 0x931688: inicio [0x931694], fin [0x931698]) = las 8 primeras del 2019. Se le
 *   agregan las otras 5 en el mismo orden (con su push_back, 0x641080) para que el 7 y el 12 sean los del 2019. */
static int mo_cursores_listos(void)
{
    DWORD ini = *(DWORD *)FLV(0x931694), fin = *(DWORD *)FLV(0x931698);
    if (!ini || fin < ini) return 0;
    int n = (int)((fin - ini) / 4);
    if (n >= 13) return 1;
    if (n != 8) return 0;
    static const char *const ARCH[5] = { "sngcursor_sell.ani", "sngcursor_pet_touch.ani", "sngcursor_pet_touch_over.ani",
                                         "mouserbtn.ani", "action05.ani" };
    for (int k = 0; k < 5; k++) {
        g_mo_cursores[k] = LoadCursorFromFileA(ARCH[k]);
        if (!g_mo_cursores[k]) {
            apuntar("  [montura] ⛔ no está el cursor %s al lado del juego: el hover queda sin cursor", ARCH[k]);
            return 0;
        }
    }
    for (int k = 0; k < 5; k++) ((F_MO_EMPUJAR)FLV(0x641080))((void *)FLV(0x931688), &g_mo_cursores[k]);
    apuntar("  [montura] ok: los 5 cursores del 2019 agregados a la lista del juego (13, como el 2019)");
    return 1;
}

/* SetCursorIdx del 2019 (0xB4D870) = el del 2013: el índice en [0x931684] y 0x433140 lo aplica */
static void mo_cursor(int idx)
{
    DWORD ini = *(DWORD *)FLV(0x931694), fin = *(DWORD *)FLV(0x931698);
    int n = ini && fin > ini ? (int)((fin - ini) / 4) : 0;
    *(int *)FLV(0x931684) = idx < n ? idx : 0;
    ((F_MO_CURSOR)FLV(0x433140))();
}

/* la sesión del personaje que JUEGA (g_pUser [0x9314E0]: +0x7C usn, +0x1C8 vcode — la que deja el selector al elegir) */
static DWORD g_mo_usn = 0;
static unsigned long long g_mo_vcode = 0;

static DWORD WINAPI mo_hilo(LPVOID nada)
{
    (void)nada;
    BYTE c[16], r[8];
    *(DWORD *)c = g_mo_usn;
    *(unsigned long long *)(c + 4) = g_mo_vcode;
    int n = 12;
    c[n++] = (BYTE)g_mo_ped_accion;
    c[n++] = (BYTE)g_mo_ped_slot;                                     /* el casillero del dueño (unirse) */
    int got = sp_pedir(0xFB, c, n, r, sizeof r);
    g_mo_res_ok = got >= 2 && r[0] == 0;
    g_mo_res_byte = got >= 2 ? r[1] : -1;
    InterlockedExchange(&g_mo_listo, 1);
    InterlockedExchange(&g_mo_pidiendo, 0);
    return 0;
}

static void mo_pedir(int accion, int slot)
{
    if (g_mo_pidiendo) return;
    if (!sp_send && !sp_red_cargar()) {
        apuntar("  [montura] ⛔ sin red para pedirle al server");
        return;
    }
    if (!g_sp_ip[0]) sp_linea_de_comandos();                          /* el server: el de la línea de comandos */
    BYTE *u = *(BYTE **)FLV(0x9314E0);
    g_mo_usn = u && fl_leible(u + 0x1C8, 8) ? *(DWORD *)(u + 0x7C) : 0;
    g_mo_vcode = g_mo_usn ? *(unsigned long long *)(u + 0x1C8) : 0;
    if (!g_mo_usn || !g_sp_ip[0]) {
        apuntar("  [montura] ⛔ no tengo la sesión (g_pUser) o el server (la línea de comandos)");
        return;
    }
    g_mo_ped_accion = accion;
    g_mo_ped_slot = slot;
    InterlockedExchange(&g_mo_pidiendo, 1);
    HANDLE h = CreateThread(NULL, 0, mo_hilo, NULL, 0, NULL);
    if (h) CloseHandle(h);
    else InterlockedExchange(&g_mo_pidiendo, 0);
    if (g_mo_log) apuntar("  [montura] clic: pido %s", accion == 0 ? "bajar" : accion == 1 ? "subir" : "unirme");
}

/* una vez por cuadro, desde el dibujo de MI personaje: lo que hace cCall_ObjectMng::Process (0x530DF0) */
static void mo_diag(void)
{
    static DWORD ult = 0;
    DWORD t = GetTickCount();
    if (!g_mo_log || t - ult < 400) return;
    ult = t;
    for (int i = 0; i < MO_MAX; i++) {
        MO_EST *m = &g_mo[i];
        if (!m->pj || !m->usr || fl_leer(m->usr, 0x1B8) != m->pj || (m->k < 0 && !m->modo && !m->sentado)) continue;
        int nfx = 0;                                                   /* los Fx de montura que tiene en la lista */
        BYTE *cab = fl_leible((BYTE *)m->pj + 0x14, 4) ? *(BYTE **)((BYTE *)m->pj + 0x14) : NULL;
        BYTE *n = cab && fl_leible(cab, 8) ? *(BYTE **)cab : NULL;
        for (int v = 0; n && n != cab && v < 64 && fl_leible(n, 0x28); v++, n = *(BYTE **)n) {
            WORD id = *(WORD *)(n + 0x1C);
            for (int k = 0; k < MO_N; k++)
                if (id == MO_TABLA[k].fx[0] || id == MO_TABLA[k].fx[1] || id == MO_TABLA[k].fx[2]) nfx++;
        }
        apuntar("  [montura·diag] pid=%u t=%u slot=%d modo=%d sentado=%d reloj=%d llave=«%s» pos=(%d,%d,%d) P=(%d,%d,%d) fx=%d nfx=%d desfase=%d",
                GetCurrentProcessId(), t, m->slot, m->modo, m->sentado, (int)(*(float *)(m->usr + 0x2C) * 10.0f),
                m->llave ? m->llave : "-", (int)*(float *)(m->usr + 8), (int)*(float *)(m->usr + 0xC),
                (int)*(float *)(m->usr + 0x10), (int)m->P[0], (int)m->P[1], (int)m->P[2], m->fx, nfx,
                (int)__builtin_sqrtf(m->desfase_max));
        m->desfase_max = 0.0f;
    }
}

/* ★ [montura] qa=1 (SÓLO PRUEBAS, apagado de fábrica): la prueba en masa pide subir / bajar / unirse escribiendo
 *   «accion casillero» en R2Beat/montura_qa_<pid>.txt; va por el MISMO camino que el clic (mo_pedir → FFFB → server) */
static int g_mo_qa = 0;

/* ★ (144, SÓLO PRUEBAS) TECLAS DE MENTIRA para la prueba: «t <DIK> <ms>» aprieta una tecla, «d <DIK> <ms>» la toca dos
 *   veces (correr) y la deja apretada. NO se le manda nada a Windows (sin foco, sin teclas a otras ventanas): después de
 *   que el juego lee el teclado (la ÚNICA llamada, 0x66F359 → 0x66F220: copia ahora → antes y GetDeviceState en
 *   [[0x93156C]] + 8; herramienta.c §4b) se escribe la tecla en «ahora». Sólo con [montura] qa=1; si la R2beat tool ya
 *   tenía esa llamada, se la encadena. */
typedef int (__attribute__((thiscall)) *F_MO_TECLADO)(void *t);
static F_MO_TECLADO g_mo_teclado_prev = NULL;
static volatile int g_mo_qa_dik = 0;
static volatile DWORD g_mo_qa_t0 = 0, g_mo_qa_ms = 0;
static volatile int g_mo_qa_doble = 0;
static int __attribute__((thiscall)) mo_teclado(void *t)
{
    int r = g_mo_teclado_prev(t);
    int dik = g_mo_qa_dik;
    if (dik > 0 && dik < 256 && t && fl_leible((BYTE *)t + 8, 256)) {
        DWORD e = GetTickCount() - g_mo_qa_t0;
        int abajo;
        if (g_mo_qa_doble) abajo = e < 80 || (e >= 160 && e < 160 + g_mo_qa_ms);
        else abajo = e < g_mo_qa_ms;
        ((BYTE *)t)[8 + dik] = abajo ? 0x80 : 0;
        if (!abajo && e >= (g_mo_qa_doble ? 160 + g_mo_qa_ms : g_mo_qa_ms)) g_mo_qa_dik = 0;
    }
    return r;
}

static void mo_teclado_enganchar(void)
{
    BYTE *s = FLV(0x66F359);
    if (s[0] != 0xE8) { apuntar("  [montura·qa] ⛔ la llamada del teclado (0x66F359) no es un call: sin teclas de prueba"); return; }
    g_mo_teclado_prev = (F_MO_TECLADO)(s + 5 + *(int *)(s + 1));
    BYTE nue[5] = { 0xE8 };
    *(int *)(nue + 1) = (int)((BYTE *)mo_teclado - (s + 5));
    DWORD viejo;
    VirtualProtect(s, 5, PAGE_EXECUTE_READWRITE, &viejo);
    CopyMemory(s, nue, 5);
    VirtualProtect(s, 5, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), s, 5);
    apuntar("  [montura·qa] teclas de prueba enganchadas en 0x66F359 (antes iba a %p)", g_mo_teclado_prev);
}

static void mo_qa(void)
{
    static DWORD ult = 0;
    DWORD t = GetTickCount();
    if (!g_mo_qa || t - ult < 250 || g_mo_pidiendo) return;
    ult = t;
    char ruta[MAX_PATH], buf[32] = { 0 };
    wsprintfA(ruta, "%smontura_qa_%u.txt", g_carpeta, GetCurrentProcessId());
    HANDLE h = CreateFileA(ruta, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_DELETE, NULL, OPEN_EXISTING, 0, NULL);
    if (h == INVALID_HANDLE_VALUE) return;
    DWORD n = 0;
    ReadFile(h, buf, sizeof buf - 1, &n, NULL);
    CloseHandle(h);
    DeleteFileA(ruta);
    int accion = 0, slot = 0, k = 0;
    if (buf[0] == 'o') {                                               /* (144) «o freno|al_dia 0|1» */
        int v = buf[lstrlenA(buf) - 1] == '1';
        if (buf[2] == 'f') g_mo_freno = v;
        else if (buf[2] == 'a') g_mo_al_dia = v;
        apuntar("  [montura·qa] pid=%u t=%u freno=%d al_dia=%d", GetCurrentProcessId(), t, g_mo_freno, g_mo_al_dia);
        return;
    }
    if ((buf[0] == 't' || buf[0] == 'd') && g_mo_teclado_prev) {      /* (144) «t|d <DIK> <ms>» */
        int dik = 0, ms = 0;
        k = 1;
        while (buf[k] == ' ') k++;
        while (buf[k] >= '0' && buf[k] <= '9') dik = dik * 10 + (buf[k++] - '0');
        while (buf[k] == ' ') k++;
        while (buf[k] >= '0' && buf[k] <= '9') ms = ms * 10 + (buf[k++] - '0');
        g_mo_qa_doble = buf[0] == 'd';
        g_mo_qa_ms = (DWORD)ms;
        g_mo_qa_t0 = GetTickCount();
        g_mo_qa_dik = dik;
        apuntar("  [montura·qa] pid=%u t=%u tecla %s DIK %d por %d ms", GetCurrentProcessId(), t, g_mo_qa_doble ? "doble" : "simple",
                dik, ms);
        return;
    }
    while (buf[k] == ' ') k++;
    while (buf[k] >= '0' && buf[k] <= '9') accion = accion * 10 + (buf[k++] - '0');
    while (buf[k] == ' ') k++;
    if (buf[k] >= '0' && buf[k] <= '9') { while (buf[k] >= '0' && buf[k] <= '9') slot = slot * 10 + (buf[k++] - '0'); }
    else slot = 0xFF;
    apuntar("  [montura·qa] pid=%u t=%u pido %d casillero %d", GetCurrentProcessId(), t, accion, slot);
    mo_pedir(accion, slot);
}

static void mo_cuadro(int yo)
{
    mo_diag();
    mo_qa();
    if (g_mo_listo) {
        InterlockedExchange(&g_mo_listo, 0);
        if (g_mo_res_ok) mo_desde_byte(g_mo[yo].pj, NULL, g_mo_res_byte);
        else apuntar("  [montura] el server dijo que no (byte 0x%02X)", g_mo_res_byte & 0xFF);
    }
    for (int i = 0; i < MO_MAX; i++) g_mo[i].hover = 0;
    float o[3], d[3];
    int sobre = -1, cursor = -1;
    /* ⛔ «con una ventana abierta, nada» (el 2019: 0x537A50 / 0x5719A0 / 0xA6C650) NO está: el candidato del 2013
     *   ([0x9313B4], 2 → 0 al abrir «Cambiar Configuración» en el cliente de jugadora_prueba) falló su control: en el de cuenta_admin vale
     *   0 sin ninguna ventana. Ver MONTURAS_COMO_LO_HACE_EL_2019.md §9. */
    if (mo_rayo(o, d)) {
        /* la propia (pick(0)) y las de dos de los demás (pick(1), +0x70 Couple). ★ El 2019 sólo mira la de la PAREJA;
         *   acá la de cualquiera (anonimo03: «que las de 2 sean usables por 2 personas»). Gana la más cercana. */
        float mejor = 1e30f;
        for (int c = 0; c < MO_MAX; c++) {
            if (!g_mo[c].pj || g_mo[c].k < 0 || !g_mo[c].hayP || !g_mo[c].usr) continue;
            if (c != yo && !MO_TABLA[g_mo[c].k].pareja) continue;
            float t = mo_pica(c, o, d);
            if (t >= 0 && t < mejor) { mejor = t; sobre = c; }
        }
    }
    int montado = g_mo[yo].modo != 0;
    if (sobre >= 0) {
        g_mo[sobre].hover = 1;
        cursor = montado ? 12 : 7;            /* 7 = action01 (subir / unirse) · 12 = action05 (bajarse) */
    }
    if (cursor >= 0 && mo_cursores_listos()) {
        mo_cursor(cursor);
        g_mo_cursor_puesto = 1;
    } else if (cursor < 0 && g_mo_cursor_puesto) {
        mo_cursor(0);
        g_mo_cursor_puesto = 0;
    }
    /* el clic (cCall_Object::Process 0x52B840; el 2019 mira su bandera [0x13C3D18]): el botón izquierdo del JUEGO,
     *   [0x9311BC] (MEDIDO: 1 entre WM_LBUTTONDOWN y WM_LBUTTONUP, 0 fuera), en el flanco de bajada */
    int boton = *(int *)FLV(0x9311BC) != 0;
    if (boton && !g_mo_boton_antes && sobre >= 0) {
        if (montado) mo_clic_objeto(0, 0xFF);                          /* 0xE5E000: SendGuildRoomAction(ítem, 0, id) */
        else if (sobre == yo) mo_clic_objeto(1, 0xFF);                 /* 1 / 5 la propia */
        else mo_clic_objeto(2, g_mo[sobre].slot);                      /* 2 / 6 la de otro (el casillero del dueño) */
    }
    g_mo_boton_antes = boton;
}

/* ═══ MONTADO SE MUEVE Y GIRA ═════════════════════════════════════════════════════════════════════════════════
 *   El 2019 no deja caminar al montado (MEDIDO: ni clic en el piso ni flechas mandan el 0x23 ni lo mueven), pero el
 *   dibujo del objeto ya está hecho para seguirlo: con flyItem (la flor y el candelabro, obj+0x12C / usr+0x3C0) cada
 *   cuadro pone obj.X = usr.x, obj.Z = usr.z − ModelZ y obj.rumbo = usr.rumbo + π (0x52C311). ★ Acá (anonimo03: «moverse con
 *   el ítem, girar 360°») el montado camina con lo del 2013 (clic en el piso; el FF23 que el server ya les pasa a los
 *   demás) y TODAS las monturas lo siguen con esa regla, generalizada para los asientos que no están en el centro:
 *   el objeto queda donde el jinete menos su asiento girado, y el otro jinete, en su asiento girado del objeto. */
static void mo_seguir(int i, BYTE *usr)
{
    MO_EST *m = &g_mo[i];
    int lado, o = mo_objeto_de(i, &lado);
    if (o < 0) return;
    float g[3], *pos = (float *)(usr + 8);
    if (lado == 0) {
        float r = *(float *)(usr + 0x24);
        m->rumbo_obj = r + MO_PI;
        mo_girar(m->rel, m->rumbo_obj, g);
        m->P[0] = pos[0] - g[0];
        m->P[2] = pos[2] - g[2];
        pos[1] = m->P[1] + m->rel[1];                                  /* la altura del asiento no la cambia caminar */
    } else {
        MO_EST *d = &g_mo[o];
        mo_girar(m->rel, d->rumbo_obj, g);
        float nx = d->P[0] + g[0], ny = d->P[1] + g[1], nz = d->P[2] + g[2];
        if (nx != pos[0] || ny != pos[1] || nz != pos[2]) {
            if (m->slot == mo_mi_slot()) ((F_MO_SETPOS)FLV(0x5B0360))(usr, nx, ny, nz, 1);     /* + la cámara */
            else { pos[0] = nx; pos[1] = ny; pos[2] = nz; }
        }
        *(float *)(usr + 0x24) = d->rumbo_obj - MO_PI;
        *(float *)(usr + 0x28) = d->rumbo_obj - MO_PI;
        /* ★ EL RELOJ (3.ª vuelta). El 2019 pone en 0 los relojes del dueño y del que se une EN EL MISMO cuadro
         *   (AniMontura 0xE5E870 → usr+0x34 = 0, y AplicarMontura 0xE5D0B0 el de la pareja) y el objeto sigue al del dueño
         *   (SyncAnim 0x52C0A0): los tres quedan en fase porque nadie más los toca. En el 2013 el FF15 rearma al que se une
         *   (Init → otra animación → 0x5B1670 pone usr+0x2C = 0) un rato DESPUÉS de la respuesta del server: quedaba
         *   corrido (anonimo03: «M no está sincronizado»). Acá: mientras el dueño va arriba, el reloj del que se unió = el del
         *   dueño, cada cuadro — lo mismo que hace SyncAnim con el objeto. (El reloj lo avanza 0x5B2C94 y con él 0x652A00
         *   elige el cuadro de la animación; las del de a dos miden lo mismo: 840 / 840 en el subibaja.) */
        int l2;
        if (g_mo_sincro && d->sentado && d->usr && mo_objeto_de(o, &l2) == o && fl_leible(d->usr + 0x2C, 4))
            *(float *)(usr + 0x2C) = *(float *)(d->usr + 0x2C);
    }
}

/* ═══ LOS GANCHOS DE DIBUJO ════════════════════════════════════════════════════════════════════════════════════ */
typedef void (__fastcall *F_MO_RENDER)(BYTE *usr, void *nada);
static void *g_mo_orig_render = NULL;
static int g_mo_orden = 1, g_mo_pasada_fx = 1, g_mo_solo = 0;
static void mo_dibujar_objetos(void);

/* sRoomUser::Render (0x5B1C90): dibuja con Translate(usr+8, +0xC, +0x10) — los campos que escribe SetPosicion. Acá
 *   sólo se anota quién es quién y, para el propio, el hover y el clic de este cuadro. */
static void __fastcall mo_render(BYTE *usr, void *nada)
{
    if (g_mo_activo && usr && fl_leible(usr + 0x1B8, 4)) {
        g_mo_render_t = GetTickCount();
        if (!g_mo_present_real) mo_present_enganchar();
        if (g_mo_orden && g_mo_pasada_fx) {                /* el primer usuario del cuadro: antes, todos los objetos */
            g_mo_pasada_fx = 0;
            mo_dibujar_objetos();
        }
        void *pj = *(void **)(usr + 0x1B8);
        int i = mo_de_pj(pj);
        if (!fl_en_pila(usr) && pj) {
            /* ★ a TODOS los de la sala se los sigue (no sólo a los que tienen montura): el que se une a la de otro no tiene
             *   byte hasta que se une, y para entonces el FF15 ya lo mandó a su casillero */
            if (i < 0) {
                i = mo_nuevo(pj);
                g_mo[i].usr = usr;
                g_mo[i].slot = usr[0x145];
                g_mo[i].cuerpo = (BYTE)mo_cuerpo(usr);
            }
            if (g_mo[i].usr != usr || g_mo[i].reinit) {
                /* el sRoomUser de la sala (Init arma una COPIA en la pila y después la pasa acá): recién ahora se puede
                 *   tomar dónde está parado y sentarlo */
                g_mo[i].usr = usr;
                g_mo[i].slot = usr[0x145];
                g_mo[i].cuerpo = (BYTE)mo_cuerpo(usr);
                if (g_mo[i].reinit && g_mo[i].hay_parado) {             /* el FF15 no lo mueve (mo_tras_init) */
                    ((F_MO_SETPOS)FLV(0x5B0360))(usr, g_mo[i].parado[0], g_mo[i].parado[1], g_mo[i].parado[2], 1);
                    if (g_mo_log)
                        apuntar("  [montura·diag] pid=%u t=%u slot=%d el FF15 lo deja en (%d, %d, %d)", GetCurrentProcessId(),
                                GetTickCount(), g_mo[i].slot, (int)g_mo[i].parado[0], (int)g_mo[i].parado[1], (int)g_mo[i].parado[2]);
                }
                g_mo[i].reinit = 0;
                if (!g_mo[i].hayP && !g_mo[i].sentado) {
                    g_mo[i].P[0] = *(float *)(usr + 8); g_mo[i].P[1] = *(float *)(usr + 0xC); g_mo[i].P[2] = *(float *)(usr + 0x10);
                    g_mo[i].hayP = 1;
                }
                mo_retomar(i);
                mo_aplicar_todos();
            }
            if (g_mo[i].k >= 0 && !g_mo[i].hayP && !g_mo[i].sentado) {   /* su objeto va donde está parado */
                g_mo[i].P[0] = *(float *)(usr + 8); g_mo[i].P[1] = *(float *)(usr + 0xC); g_mo[i].P[2] = *(float *)(usr + 0x10);
                g_mo[i].hayP = 1;
                mo_retomar(i);
                mo_aplicar_todos();
            }
            if (g_mo[i].espera_gesto) mo_espera(i, usr);
            if (g_mo[i].sentado && g_mo[i].llave && !g_mo[i].espera_gesto && mo_anim_ajena(i, usr)) {
                int lado, o = mo_objeto_de(i, &lado);
                if (g_mo_rugido && o >= 0 && MO_TABLA[g_mo[o].k].camina) {
                    /* (144) un gesto arriba del tigre: ruge el tigre y los dos jinetes, en el lugar */
                    if (g_mo[o].mov != MO_MOV_RUGE) mo_tigre_mov(o, MO_MOV_RUGE, -1);
                    else mo_aplicar(i);                                 /* ya rugía: éste vuelve a su pose */
                } else mo_gesto_montado(i, usr, "emote (0x4B43C0)");
            }
            int l0;
            if (g_mo[i].sentado && g_mo[i].k >= 0 && MO_TABLA[g_mo[i].k].camina && g_mo[i].mov == MO_MOV_RUGE
                && mo_objeto_de(i, &l0) == i) {
                /* (144) el final del rugido por el reloj del que maneja (por si el juego no pide nada al terminar) */
                float r = fl_leible(usr + 0x2C, 4) ? *(float *)(usr + 0x2C) : 0.0f;
                if (r >= MO_TABLA[g_mo[i].k].dur_fx[2] - 2.0f || GetTickCount() - g_mo[i].ruge_t > 8000)
                    mo_tigre_mov(i, MO_MOV_QUIETO, -1);
            }
            if (g_mo[i].freno > 0.0f) {
                float largo = mo_largo_anim(usr), *reloj = (float *)(usr + 0x2C);
                if (largo > g_mo[i].freno && *reloj < largo - g_mo[i].freno) {
                    if (g_mo_log)
                        apuntar("  [montura·diag] pid=%u t=%u slot=%d frena: la animación dura %d, le quedan %d (como a pie)",
                                GetCurrentProcessId(), GetTickCount(), g_mo[i].slot, (int)largo, (int)g_mo[i].freno);
                    *reloj = largo - g_mo[i].freno;
                }
                g_mo[i].freno = 0.0f;
            }
            {
                int l0;
                if (g_mo[i].sentado && g_mo[i].hay_dibujado && mo_objeto_de(i, &l0) == i) {
                    /* el jinete se dibuja en usr+8 (sRoomUser::Render); el objeto ya se dibujó en P_dibujado: con el asiento
                     *   en el origen (el tigre) los dos tienen que coincidir */
                    float g[3], *pos = (float *)(usr + 8);
                    mo_girar(g_mo[i].rel, g_mo[i].rumbo_obj, g);
                    float dx = pos[0] - g[0] - g_mo[i].P_dibujado[0], dz = pos[2] - g[2] - g_mo[i].P_dibujado[2];
                    float d = dx * dx + dz * dz;
                    if (d > g_mo[i].desfase_max) g_mo[i].desfase_max = d;
                    g_mo[i].hay_dibujado = 0;
                }
            }
            if (g_mo[i].sentado) mo_seguir(i, usr);
            else if (!g_mo[i].bajar) {                                  /* parado: dónde está (se congela al subir) */
                g_mo[i].parado[0] = *(float *)(usr + 8);
                g_mo[i].parado[1] = *(float *)(usr + 0xC);
                g_mo[i].parado[2] = *(float *)(usr + 0x10);
                g_mo[i].hay_parado = 1;
            }
            g_mo[i].visto = GetTickCount();
        }
        if (i >= 0 && usr[0x145] == mo_mi_slot()) mo_cuadro(i);
    }
    ((F_MO_RENDER)g_mo_orig_render)(usr, nada);
}

/* 0x4AFCB0 (thiscall pj, 6 argumentos, ret 0x18): dibuja la lista de Fx del pj (pj+0x14; nodo +0x0C reloj, +0x10/+0x14
 *   /+0x18 x/y/z, +0x1C id, +0x20 w). Al de la montura se le pone la posición, el giro y el reloj del 2019. */
typedef void (__fastcall *F_MO_FX_DIBUJO)(void *pj, void *nada, DWORD a, DWORD b, DWORD c, DWORD d, DWORD e, DWORD f);
static void *g_mo_orig_fx = NULL;
static BYTE *mo_nodo_del_objeto(int i, BYTE *pj)
{
    if (i < 0 || !g_mo[i].fx || g_mo[i].k < 0 || !fl_leible(pj + 0x14, 4)) return NULL;
    BYTE *cab = *(BYTE **)(pj + 0x14);
    BYTE *n = cab && fl_leible(cab, 8) ? *(BYTE **)cab : NULL;
    for (int v = 0; n && n != cab && v < 64 && fl_leible(n, 0x28); v++, n = *(BYTE **)n)
        if (*(WORD *)(n + 0x1C) == g_mo[i].fx) return n;
    return NULL;
}

static void __fastcall mo_fx_dibujo(BYTE *pj, void *nada, DWORD a, DWORD b, DWORD c, DWORD d, DWORD e, DWORD f)
{
    int i = g_mo_activo && pj ? mo_de_pj(pj) : -1;
    BYTE *q = mo_nodo_del_objeto(i, pj);
    float guarda[4] = { 0 };
    if (!g_mo_solo) g_mo_pasada_fx = 1;
    if (q && g_mo_orden && !g_mo_solo) {
        /* ★ en la pasada de los Fx (DESPUÉS de los jugadores) el objeto no va: ya se dibujó antes (mo_dibujar_objetos).
         *   Se lo saca de la lista (std::list: +0 siguiente, +4 anterior) durante el dibujo y se lo vuelve a poner. */
        BYTE *sig = *(BYTE **)q, *ant = *(BYTE **)(q + 4);
        *(BYTE **)ant = sig; *(BYTE **)(sig + 4) = ant;
        ((F_MO_FX_DIBUJO)g_mo_orig_fx)(pj, nada, a, b, c, d, e, f);
        *(BYTE **)ant = q; *(BYTE **)(sig + 4) = q;
        if (g_mo_tapa_fase == 1) g_mo_tapa_a = mo_tapa_copiar(0);   /* lo 3D hasta acá */
        return;
    }
    if (q) {
        const MO_FILA *fi = &MO_TABLA[g_mo[i].k];
        float *x = (float *)(q + 0x10), rumbo = *(float *)&a;
        g_mo[i].dibujos++;
        guarda[0] = x[0]; guarda[1] = x[1]; guarda[2] = x[2]; guarda[3] = *(float *)(q + 0x20);
        /* cCall_Object::Render: T(P.x, P.y + ModelY, P.z) — el 0x4AFCB0 le suma 21 a la y (medido) */
        x[0] = g_mo[i].P[0];
        x[1] = g_mo[i].P[1] + fi->modelo_y - 21.0f;
        x[2] = g_mo[i].P[2];
        g_mo[i].P_dibujado[0] = g_mo[i].P[0]; g_mo[i].P_dibujado[1] = g_mo[i].P[1]; g_mo[i].P_dibujado[2] = g_mo[i].P[2];
        g_mo[i].hay_dibujado = 1;
        /* el giro: montado, el del que monta + π (0x52C311); quieto, el que se le dio al invocarlo (0). El 0x4AFCB0
         *   gira RotY(w + rumbo + π): w = giro − rumbo − π */
        int lado, montado = 0, reloj_de = -1;
        for (int j = 0; j < MO_MAX; j++)
            if (g_mo[j].pj && g_mo[j].usr && g_mo[j].sentado && mo_objeto_de(j, &lado) == i) {
                montado = 1;
                if (reloj_de < 0 || lado == 0) reloj_de = j;           /* SyncAnim (0x52C0A0): el del dueño primero */
            }
        (void)montado;
        float giro = g_mo[i].rumbo_obj;                                /* cCall_Object +0x130 (mo_seguir lo mantiene) */
        *(float *)(q + 0x20) = giro - rumbo - MO_PI;
        /* el reloj del objeto = el del que monta (SyncAnim 0x52C0A0); usr+0x2C es el del personaje (mismas unidades) */
        if (reloj_de >= 0 && fl_leible(g_mo[reloj_de].usr + 0x2C, 4)) {
            float r = *(float *)(g_mo[reloj_de].usr + 0x2C);
            float dur = fi->camina && g_mo[i].mov >= 0 && g_mo[i].mov <= 2 ? fi->dur_fx[g_mo[i].mov] : 0.0f;
            if (dur > 0.0f && r >= dur) r -= dur * (float)(int)(r / dur);   /* (144) la vuelta del tigre: 2 por la del jinete */
            *(float *)(q + 0xC) = r;
        }
    }
    ((F_MO_FX_DIBUJO)g_mo_orig_fx)(pj, nada, a, b, c, d, e, f);
    if (g_mo_tapa_fase == 1 && !g_mo_solo) g_mo_tapa_a = mo_tapa_copiar(0);   /* lo 3D hasta acá (la pasada de los Fx) */
    if (q) {
        if (g_mo[i].hover) {
            /* el borde: DrawOutline(handle, 0xFF, 3, 1, 0x64FFFF00, 0x2020201) del 2019 (0xEE22A0) = 0x638210 del 2013,
             *   con la misma matriz del objeto (Push · RotY · Translate · dibujo · Pop) */
            void *d3d = *(void **)FLV(0x931498), *mm = *(void **)FLV(0x93149C);
            void **vt = d3d ? *(void ***)d3d : NULL;
            const MO_FILA *fi = &MO_TABLA[g_mo[i].k];
            if (vt && mm) {
                ((F_MO_D3D0)vt[0x6C / 4])(d3d);
                ((F_MO_D3D1)vt[0x88 / 4])(d3d, *(float *)(q + 0x20) + *(float *)&a + MO_PI);
                ((F_MO_D3D3)vt[0x7C / 4])(d3d, g_mo[i].P[0], g_mo[i].P[1] + fi->modelo_y, g_mo[i].P[2]);
                ((F_MO_BORDE)FLV(0x638210))(mm, *(DWORD *)(q + 8), 0xFF, 3, 1, 0x64FFFF00, 0x02020201);
                ((F_MO_D3D0)vt[0x70 / 4])(d3d);
            }
        }
        float *x = (float *)(q + 0x10);
        x[0] = guarda[0]; x[1] = guarda[1]; x[2] = guarda[2]; *(float *)(q + 0x20) = guarda[3];
    }
}

/* ★ EL ORDEN DEL 2019: cRoom::Render dibuja los objetos (cCall_ObjectMng::Render, 0xA5AA75) y DESPUÉS los usuarios.
 *   Con z-buffer da lo mismo en lo opaco, pero no en lo que tiene alfa (la luna, el corazón y la jaula: DXT5, ABLEND 1
 *   medido): lo que se dibuja antes escribe su profundidad. Acá: al primer usuario del cuadro, cada objeto se dibuja con
 *   la MISMA función del juego (0x4AFCB0) sobre una lista de un solo nodo — el suyo — y se vuelve todo a su lugar. */
static void mo_dibujar_objetos(void)
{
    void *mgr = *(void **)FLV(0x931660);
    if (g_mo_log) {                                                    /* (144) ¿algún objeto se dibujó 2 veces? */
        for (int i = 0; i < MO_MAX; i++)
            if (g_mo[i].dibujos > 1)
                apuntar("  [montura·diag] pid=%u t=%u slot=%d su objeto se dibujó %d veces en el cuadro", GetCurrentProcessId(),
                        GetTickCount(), g_mo[i].slot, g_mo[i].dibujos);
    }
    for (int i = 0; i < MO_MAX; i++) g_mo[i].dibujos = 0;
    /* ★ (144) el que maneja se movió en el update de ESTE cuadro y su mo_seguir corre recién cuando se lo dibuja (después
     *   de los objetos): el objeto quedaba un cuadro atrás. Corriendo (825 por segundo) son ~14 por cuadro. Se pone al día
     *   P antes de dibujar. */
    if (g_mo_al_dia)
        for (int i = 0; i < MO_MAX; i++) {
            int l0;
            if (g_mo[i].pj && g_mo[i].usr && g_mo[i].sentado && fl_leer(g_mo[i].usr, 0x1B8) == g_mo[i].pj
                && mo_objeto_de(i, &l0) == i)
                mo_seguir(i, g_mo[i].usr);
        }
    for (int i = 0; i < MO_MAX; i++) {
        MO_EST *m = &g_mo[i];
        if (!m->pj || !m->usr || fl_leer(m->usr, 0x1B8) != m->pj || !mgr) continue;
        BYTE *q = mo_nodo_del_objeto(i, (BYTE *)m->pj);
        if (!q) continue;
        BYTE *cab = *(BYTE **)((BYTE *)m->pj + 0x14);
        BYTE *cs = *(BYTE **)cab, *ca = *(BYTE **)(cab + 4), *qs = *(BYTE **)q, *qa = *(BYTE **)(q + 4);
        *(BYTE **)cab = q; *(BYTE **)(cab + 4) = q; *(BYTE **)q = cab; *(BYTE **)(q + 4) = cab;
        float uno = 1.0f;
        DWORD rumbo = *(DWORD *)(m->usr + 0x24), cuerpo = ((F_MO_CHAR)FLV(0x436380))(mgr, m->usr[0x145]);
        g_mo_solo = 1;
        mo_fx_dibujo((BYTE *)m->pj, NULL, rumbo, cuerpo, 0, 0, *(DWORD *)&uno, 3);   /* los argumentos de 0x593688 */
        g_mo_solo = 0;
        *(BYTE **)cab = cs; *(BYTE **)(cab + 4) = ca; *(BYTE **)q = qs; *(BYTE **)(q + 4) = qa;
    }
}

/* ═══ EL MINICHAR DEL CASILLERO (el retrato de arriba) ═════════════════════════════════════════════════════════
 *   El 2013 lo dibuja en 0x596FC0 con una cámara ortogonal FIJA (Translate(-65 | 0, -270 - off, -700)): la pose de
 *   montura saca la cara del cuadro. El 2019 (0xA8EE60), si está montado (IsMontado 0xE5CEC0), centra la caja del
 *   nodo «Face» de la pose ACTUAL: la cara en (x de fábrica, 0). Acá, lo mismo, en el Translate de las dos ramas. */
static void mo_retrato_centrar(BYTE *usr, float *xy, float x_cara)
{
    if (!g_mo_retrato || !g_mo_activo || !usr || !fl_leible(usr, 4) || !fl_leible(usr + 0x1B8, 4)) return;
    int i = mo_de_pj(*(void **)(usr + 0x1B8));
    if (i < 0 || !g_mo[i].sentado) return;
    void *tabla = *(void **)FLV(0x931620), *d3d = *(void **)FLV(0x931498);
    if (!tabla || !d3d) return;
    BYTE *r = (BYTE *)((F_MO_BUSCAR)FLV(0x413000))(tabla, *(DWORD *)usr);
    if (!r || !fl_leible(r + 0x1C, 4)) return;
    void *modelo = *(void **)(r + 0x1C);
    if (!modelo) return;
    int idx = ((F_MO_NODO)FLV(0x6505E0))(modelo, "Face");             /* ⛔ 0x650650 NO da el índice (intento 1) */
    if (idx < 0) return;
    float a[3], b[3], m[16];
    ((F_MO_CAJA)FLV(0x650510))(modelo, idx, a, b);                     /* = 0xEA2520 del 2019 */
    ((F_MO_MATRIZ)(*(void ***)d3d)[0x64 / 4])(d3d, 256 /* D3DTS_WORLD */, m);
    float c0 = (a[0] + b[0]) / 2, c1 = (a[1] + b[1]) / 2, c2 = (a[2] + b[2]) / 2;
    float cx = c0 * m[0] + c1 * m[4] + c2 * m[8] + m[12];
    float cy = c0 * m[1] + c1 * m[5] + c2 * m[9] + m[13];
    xy[0] = x_cara - cx;
    xy[1] = 0.0f - cy;
}
static void __stdcall mo_retrato(BYTE *usr, float *xy) { mo_retrato_centrar(usr, xy, -65.0f); }      /* pareja */
static void __stdcall mo_retrato_solo(BYTE *usr, float *xy) { mo_retrato_centrar(usr, xy, 0.0f); }   /* normal */

static void mo_parche_llamada(BYTE *sitio, int largo, BYTE *stub)
{
    BYTE parche[16];
    parche[0] = 0xE8;
    *(int *)(parche + 1) = (int)((DWORD)stub - ((DWORD)sitio + 5));
    for (int k = 5; k < largo; k++) parche[k] = 0x90;
    DWORD viejo;
    VirtualProtect(sitio, largo, PAGE_EXECUTE_READWRITE, &viejo);
    CopyMemory(sitio, parche, largo);
    VirtualProtect(sitio, largo, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), sitio, largo);
}

/* el retrato NORMAL: 0x5975B5  mov eax,[edx+0x7C] · fstp [esp+4] (y) · fldz · fstp [esp] (x = 0) · 0x5975C1 call eax */
static void mo_retrato_solo_instalar(void)
{
    static const BYTE e[12] = { 0x8B, 0x42, 0x7C, 0xD9, 0x5C, 0x24, 0x04, 0xD9, 0xEE, 0xD9, 0x1C, 0x24 };
    BYTE *sitio = FLV(0x5975B5);
    if (memcmp(sitio, e, 12) != 0) {
        apuntar("  [montura] ⛔ el retrato normal (0x5975B5) no es el de fábrica: queda como está");
        return;
    }
    BYTE *p = (BYTE *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!p) return;
    BYTE *q = p;
    *q++ = 0x8B; *q++ = 0x42; *q++ = 0x7C;                             /* mov eax, [edx+0x7C]                          */
    *q++ = 0xD9; *q++ = 0x5C; *q++ = 0x24; *q++ = 0x08;                /* fstp dword [esp+8]      y                    */
    *q++ = 0xD9; *q++ = 0xEE;                                          /* fldz                                         */
    *q++ = 0xD9; *q++ = 0x5C; *q++ = 0x24; *q++ = 0x04;                /* fstp dword [esp+4]      x = 0                */
    *q++ = 0x50; *q++ = 0x51; *q++ = 0x52;                             /* push eax / ecx / edx                         */
    *q++ = 0x8D; *q++ = 0x44; *q++ = 0x24; *q++ = 0x10;                /* lea eax, [esp+0x10]     = &x                 */
    *q++ = 0x50; *q++ = 0x53;                                          /* push eax (xy) · push ebx (usr)               */
    *q++ = 0xE8; *(int *)q = (int)((DWORD)mo_retrato_solo - (DWORD)(q + 4)); q += 4;
    *q++ = 0x5A; *q++ = 0x59; *q++ = 0x58;                             /* pop edx / ecx / eax                          */
    *q++ = 0xC3;                                                       /* ret → 0x5975BA, los NOP, 0x5975C1 call eax   */
    mo_parche_llamada(sitio, 12, p);
    apuntar("  [montura] ok: el retrato normal del casillero centra la cara de los montados (0x5975B5)");
}

/* el retrato de PAREJA: 0x5971C9  mov eax,[edx+0x7C] · fstp [esp+4] · fld [-65.0] · fstp [esp] · 0x5971D9 call eax */
static void mo_retrato_pareja_instalar(void)
{
    static const BYTE e[16] = { 0x8B, 0x42, 0x7C, 0xD9, 0x5C, 0x24, 0x04, 0xD9, 0x05, 0x68, 0x24, 0x88, 0x00, 0xD9, 0x1C, 0x24 };
    BYTE *sitio = FLV(0x5971C9);
    BYTE esperado[16];
    CopyMemory(esperado, e, 16);
    *(DWORD *)(esperado + 9) = (DWORD)FLV(0x882468);
    if (memcmp(sitio, esperado, 16) != 0) {
        apuntar("  [montura] ⛔ el retrato de pareja (0x5971C9) no es el de fábrica: queda como está");
        return;
    }
    BYTE *p = (BYTE *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!p) return;
    BYTE *q = p;
    *q++ = 0x8B; *q++ = 0x42; *q++ = 0x7C;                             /* mov eax, [edx+0x7C]     (lo de fábrica)      */
    *q++ = 0xD9; *q++ = 0x5C; *q++ = 0x24; *q++ = 0x08;                /* fstp dword [esp+8]      y                    */
    *q++ = 0xD9; *q++ = 0x05; *(DWORD *)q = (DWORD)FLV(0x882468); q += 4;   /* fld dword [-65.0]                  */
    *q++ = 0xD9; *q++ = 0x5C; *q++ = 0x24; *q++ = 0x04;                /* fstp dword [esp+4]      x                    */
    *q++ = 0x50; *q++ = 0x51; *q++ = 0x52;                             /* push eax / ecx / edx                         */
    *q++ = 0x8D; *q++ = 0x44; *q++ = 0x24; *q++ = 0x10;                /* lea eax, [esp+0x10]     = &x                 */
    *q++ = 0x50; *q++ = 0x53;                                          /* push eax (xy) · push ebx (usr)               */
    *q++ = 0xE8; *(int *)q = (int)((DWORD)mo_retrato - (DWORD)(q + 4)); q += 4;
    *q++ = 0x5A; *q++ = 0x59; *q++ = 0x58;                             /* pop edx / ecx / eax                          */
    *q++ = 0xC3;
    mo_parche_llamada(sitio, 16, p);
    apuntar("  [montura] ok: el retrato de pareja del casillero centra la cara de los montados (0x5971C9)");
}

/* trampolín de 11 bytes al principio de una función (lo de fábrica + jmp de vuelta) */
static void *mo_trampolin(DWORD va, const BYTE *e, void *nuevo)
{
    BYTE *s = FLV(va);
    if (memcmp(s, e, 11) != 0) return NULL;
    BYTE *tr = (BYTE *)VirtualAlloc(NULL, 32, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!tr) return NULL;
    CopyMemory(tr, e, 11);
    tr[11] = 0xE9;
    *(int *)(tr + 12) = (int)((DWORD)(s + 11) - (DWORD)(tr + 16));
    BYTE j[11] = { 0xE9, 0, 0, 0, 0, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90 };
    *(int *)(j + 1) = (int)((DWORD)nuevo - ((DWORD)s + 5));
    DWORD viejo;
    VirtualProtect(s, 11, PAGE_EXECUTE_READWRITE, &viejo);
    CopyMemory(s, j, 11);
    VirtualProtect(s, 11, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), s, 11);
    return tr;
}

static void monturas_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("montura", "activo", 1, ini)) {
        apuntar("  [montura] apagado ([montura] activo=0)");
        return;
    }
    if (!g_fl_activo) {
        apuntar("  [montura] ⛔ sin flotar.c (los ganchos de Init y de las animaciones): no hay monturas");
        return;
    }
    g_mo_log = GetPrivateProfileIntA("montura", "log", 0, ini);
    g_mo_retrato = GetPrivateProfileIntA("montura", "retrato", 1, ini);
    g_mo_orden = GetPrivateProfileIntA("montura", "orden_2019", 1, ini);
    g_mo_sincro = GetPrivateProfileIntA("montura", "sincronizar", 1, ini);
    g_mo_volver = GetPrivateProfileIntA("montura", "volver", 1, ini);
    g_mo_bajar_clic = GetPrivateProfileIntA("montura", "bajar_donde_subio", 0, ini);
    g_mo_qa = GetPrivateProfileIntA("montura", "qa", 0, ini);
    if (g_mo_qa) mo_teclado_enganchar();
    g_mo_tapa = GetPrivateProfileIntA("montura", "tapa", 1, ini);
    g_mo_rugido = GetPrivateProfileIntA("montura", "rugido", 1, ini);
    g_mo_freno = GetPrivateProfileIntA("montura", "freno", 1, ini);
    g_mo_al_dia = GetPrivateProfileIntA("montura", "al_dia", 1, ini);
    /* ⚠ las guardas ANTES de escribir: o van los dos ganchos de dibujo o ninguno */
    static const BYTE e_render[11] = { 0x51, 0x56, 0x8B, 0xF1, 0xF6, 0x86, 0x20, 0x02, 0x00, 0x00, 0x20 };
    static const BYTE e_fx[11] = { 0x83, 0xEC, 0x74, 0x83, 0xBC, 0x24, 0x80, 0x00, 0x00, 0x00, 0x01 };
    if (memcmp(FLV(0x5B1C90), e_render, 11) || memcmp(FLV(0x4AFCB0), e_fx, 11)) {
        apuntar("  [montura] ⛔ sRoomUser::Render (0x5B1C90) o el dibujo de los Fx (0x4AFCB0) no son los de fábrica: no hay monturas");
        return;
    }
    g_mo_orig_render = mo_trampolin(0x5B1C90, e_render, (void *)mo_render);
    g_mo_orig_fx = mo_trampolin(0x4AFCB0, e_fx, (void *)mo_fx_dibujo);
    if (!g_mo_orig_render || !g_mo_orig_fx) {
        apuntar("  [montura] ⛔ no pude armar los trampolines");
        return;
    }
    if (g_mo_retrato) { mo_retrato_solo_instalar(); mo_retrato_pareja_instalar(); }
    g_mo_activo = 1;
    apuntar("  [montura] ok: %d monturas; objeto en (P.x, P.y + ModelY, P.z) como el 2019, asiento por GetSeat, hover + clic",
            MO_N);
}
