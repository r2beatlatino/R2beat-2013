/* selector.c — «Elige tu personaje» ADENTRO del juego (25-oct-2026)
 *
 *   anonimo03: el selector de la web r2portable (4 personajes por cuenta) en el cliente Windows, *"ocupando el lugar
 *   de creación"*, 1 a 1 con la web. Doc: documentacion/SELECTOR_PERSONAJE.md (§2 = el camino, MEDIDO con Frida).
 *
 *   El 2013 no tiene selector de casilleros: su cCharSelect es sólo la CREACIÓN, y el juego entra ahí cuando su lista
 *   de personajes queda vacía. Así que:
 *
 *     AL ARRANCAR   un hilo le dice al LoginServer «este juego tiene selector» (FFF6 HOLA, con la sesión de la línea de
 *                   comandos) -> el server le manda a la cuenta la ficha VACÍA y el juego abre la creación.
 *     LA ESCENA     se engancha la vtable de cCharSelect (0x87893C): el DIBUJO (+0x0C) y la LÓGICA (+0x18). Mientras el
 *                   selector está a la vista, lo nativo NO corre (no se ve ni se toca la creación) y se dibuja lo nuestro:
 *                   dos lienzos (el FONDO y el FRENTE) armados en memoria con las hojas del chino — la receta de top5.c.
 *     EL MOUSE      el WndProc de d3d9_proxy.c nos pasa los mensajes ANTES que al juego (selector_mensaje).
 *     ENTRAR        FFF8 ELEGIR -> g_pUser+0x7C/+0x1C8 = la sesión del elegido; se cierra la red del lobby
 *                   ([0x9314D0]->0x67C6A0) y se conecta al LoginServer ([0x9D43D8]->0x5C4220): el juego solo hace FF01,
 *                   la lista, el lobby y pide la ficha. Cuando aparece el personaje (0x485F90 ≠ 0): 0x5C5E00 -> la
 *                   bienvenida de siempre.
 *     CREAR         lo mismo con un casillero vacío (el server le reserva el usn): llega la ficha vacía y queda la
 *                   creación NATIVA, que manda su FF04 con ese usn.
 *   ⛔ NO volver a la escena Login: re-arma el catálogo encima del viejo y la tienda muere (§2, trampa 3).
 *   ⛔ [selector] activo=0 lo apaga entero (sin el HOLA, el server tampoco cambia nada).
 *     CAMBIAR       el botón «Cambiar personaje» de la ventana de salida (todayevent_msgbox.rui, en el medio): FFFA VOLVER
 *                   -> la sesión de la CUENTA, y el juego se RELANZA con ella (sale y vuelve a entrar: el selector de nuevo).
 *                   ⛔ No se vuelve a la escena del selector en el mismo proceso: la ficha del juego SUMA el inventario y
 *                   quedan la lista de personajes, los amigos y las misiones del anterior (SELECTOR_PERSONAJE.md §11).
 */
#include "selector_datos.h"
#include "selector_sonido.h"

#define SPV(x) (g_sp_base + ((DWORD)(x) - 0x400000))
#define SP_ARR 14                       /* el título sube 6 px sobre el cuadro: aire arriba del lienzo */
#define SP_ALTO_LZ (SP_H + SP_ARR + 40) /* + el renglón del aviso, debajo */

static BYTE *g_sp_base = NULL;
static int   g_sp_activo = 0;

/* ── la sesión de la línea de comandos (la del launcher) ── */
static DWORD g_sp_usn = 0;
static unsigned long long g_sp_vcode = 0;
static char  g_sp_ip[64] = "";
static int   g_sp_puerto = 48004;

/* ── la lista (la escribe el hilo de la red, la lee el juego: bajo g_sp_cs) ── */
typedef struct { int ranura; DWORD usn; int sexo; char apodo[33]; int nivel; DWORD char_id; int np; DWORD partes[32]; } SP_PJ;
static CRITICAL_SECTION g_sp_cs;
static SP_PJ g_sp_pj[4];
static int   g_sp_npj = 0, g_sp_lista_lista = 0;
static volatile LONG g_sp_hola = 0;     /* 1 = el server dijo que sí al HOLA */

/* ── lo que se ve ── */
static volatile int g_sp_visible = 0;   /* el selector está encima de la creación */
static int g_sp_elegida = 1, g_sp_pagina = 0;
static int g_sp_sobre = -1, g_sp_apretado = -1;   /* el control bajo el mouse / apretado (SPC_…) */
static char g_sp_aviso[160] = "";
static int g_sp_aviso_mal = 0;
static int g_sp_x0 = 0, g_sp_y0 = 0;    /* el cuadro en pantalla (esquina de arriba del lienzo) */

/* ── el pedido en curso al server (lo arma el juego, lo hace el hilo, lo aplica el juego) ── */
enum { SPP_NADA, SPP_LISTA, SPP_ELEGIR, SPP_BORRAR, SPP_VOLVER };
static volatile LONG g_sp_pedido = SPP_NADA, g_sp_listo = 0;
static int   g_sp_ped_ranura = 0, g_sp_ped_crear = 0;
static int   g_sp_res_ok = 0, g_sp_res_tiene = 0;
static DWORD g_sp_res_usn = 0;
static unsigned long long g_sp_res_vcode = 0;
static HANDLE g_sp_evento = NULL;
/* ── el cartel de BORRAR (del_user.rui del chino: chardelete02) ── */
static int   g_sp_borrar = 0;                 /* 0 = cerrado; si no, el casillero que se borra */
static char  g_sp_clave[33];
static int   g_sp_clave_n = 0;
static char  g_sp_borrar_error[120] = "";
static int   g_sp_bsobre = -1, g_sp_bapretado = -1;   /* SPB_BTN_OK / SPB_BTN_NO */
static char  g_sp_ped_hash[65];
static int   g_sp_res_borrar_ok = 0;
static char  g_sp_res_msg[120];
static char  g_sp_borrado_apodo[33];
static int   g_sp_esperando_pj = 0, g_sp_espera_cuadros = 0;

/* ═══ 1 · LA RED (un hilo propio: el juego no se traba esperando al server) ═════════════════════════════════════
 *   ws2_32 se carga a mano: la receta de compilar.py enlaza sólo kernel32/user32/gdi32 (y es determinista). */
typedef int (__stdcall *F_WSASTARTUP)(WORD, void *);
typedef UINT_PTR (__stdcall *F_SOCKET)(int, int, int);
typedef int (__stdcall *F_CONNECT)(UINT_PTR, const void *, int);
typedef int (__stdcall *F_SEND)(UINT_PTR, const char *, int, int);
typedef int (__stdcall *F_RECV)(UINT_PTR, char *, int, int);
typedef int (__stdcall *F_CLOSE)(UINT_PTR);
typedef int (__stdcall *F_SETSOCKOPT)(UINT_PTR, int, int, const char *, int);
typedef unsigned long (__stdcall *F_INET_ADDR)(const char *);
typedef unsigned short (__stdcall *F_HTONS)(unsigned short);
static F_SOCKET sp_socket; static F_CONNECT sp_connect; static F_SEND sp_send; static F_RECV sp_recv;
static F_CLOSE sp_close; static F_SETSOCKOPT sp_setsockopt; static F_INET_ADDR sp_inet_addr; static F_HTONS sp_htons;

static int sp_red_cargar(void)
{
    HMODULE w = LoadLibraryA("ws2_32.dll");
    if (!w) return 0;
    F_WSASTARTUP st = (F_WSASTARTUP)GetProcAddress(w, "WSAStartup");
    sp_socket = (F_SOCKET)GetProcAddress(w, "socket");
    sp_connect = (F_CONNECT)GetProcAddress(w, "connect");
    sp_send = (F_SEND)GetProcAddress(w, "send");
    sp_recv = (F_RECV)GetProcAddress(w, "recv");
    sp_close = (F_CLOSE)GetProcAddress(w, "closesocket");
    sp_setsockopt = (F_SETSOCKOPT)GetProcAddress(w, "setsockopt");
    sp_inet_addr = (F_INET_ADDR)GetProcAddress(w, "inet_addr");
    sp_htons = (F_HTONS)GetProcAddress(w, "htons");
    BYTE datos[512];
    return st && sp_socket && sp_connect && sp_send && sp_recv && sp_close && sp_setsockopt && sp_inet_addr
           && sp_htons && st(0x0202, datos) == 0;
}

/* `FF <cmd> <len> <cuerpo>` -> el cuerpo de la respuesta (leída entera). -> su largo, o -1 */
static int sp_pedir(BYTE cmd, const BYTE *cuerpo, int n, BYTE *resp, int max)
{
    struct { short fam; unsigned short puerto; unsigned long ip; char cero[8]; } dir;
    ZeroMemory(&dir, sizeof(dir));
    dir.fam = 2;                                            /* AF_INET */
    dir.puerto = sp_htons((unsigned short)g_sp_puerto);
    dir.ip = sp_inet_addr(g_sp_ip);
    UINT_PTR s = sp_socket(2, 1, 6);                        /* TCP */
    if (s == (UINT_PTR)~0) return -1;
    DWORD espera = 4000;
    sp_setsockopt(s, 0xFFFF, 0x1006, (const char *)&espera, 4);   /* SO_RCVTIMEO */
    int got = -1;
    if (sp_connect(s, &dir, sizeof(dir)) == 0) {
        BYTE pk[300];
        pk[0] = 0xFF; pk[1] = cmd; pk[2] = (BYTE)n; pk[3] = (BYTE)(n >> 8);
        CopyMemory(pk + 4, cuerpo, n);
        if (sp_send(s, (const char *)pk, n + 4, 0) == n + 4) {
            BYTE buf[2048];
            int t = 0;
            while (t < (int)sizeof(buf)) {
                int r = sp_recv(s, (char *)buf + t, (int)sizeof(buf) - t, 0);
                if (r <= 0) break;
                t += r;
                if (t >= 4 && t >= 4 + (buf[2] | buf[3] << 8)) break;
            }
            int largo = t >= 4 ? (buf[2] | buf[3] << 8) : -1;
            if (t >= 4 && buf[0] == 0xFF && buf[1] == cmd && t >= 4 + largo && largo <= max) {
                CopyMemory(resp, buf + 4, largo);
                got = largo;
            }
        }
    }
    sp_close(s);
    return got;
}

static int sp_sesion(BYTE *b)                              /* [usn:u32][vcode:u64] */
{
    *(DWORD *)b = g_sp_usn;
    *(unsigned long long *)(b + 4) = g_sp_vcode;
    return 12;
}

static void sp_red_lista(void)                             /* FFF7 LISTA -> g_sp_pj */
{
    BYTE c[12], r[2048];
    int n = sp_pedir(0xF7, c, sp_sesion(c), r, sizeof(r));
    if (n < 2 || r[0] != 0) { apuntar("  [selector] ⛔ LISTA: sin respuesta buena (%d)", n); return; }
    SP_PJ pj[4];
    int k = 0, o = 2;
    for (int i = 0; i < r[1] && k < 4; i++) {
        if (o + 7 > n) break;
        SP_PJ *p = &pj[k];
        p->ranura = r[o];
        p->usn = *(DWORD *)(r + o + 1);
        p->sexo = r[o + 5];
        int nl = r[o + 6];
        if (o + 7 + nl + 2 > n) break;
        int c2 = nl < 32 ? nl : 32;
        CopyMemory(p->apodo, r + o + 7, c2);
        p->apodo[c2] = 0;
        o += 7 + nl;
        p->nivel = r[o];
        p->np = r[o + 1] < 32 ? r[o + 1] : 32;
        for (int q = 0; q < p->np && o + 2 + 4 * q + 4 <= n; q++) p->partes[q] = *(DWORD *)(r + o + 2 + 4 * q);
        o += 2 + 4 * r[o + 1];
        p->char_id = o + 4 <= n ? *(DWORD *)(r + o) : 0;        /* ★ el CUERPO (sólo en el FFF7): el muñeco */
        o += 4;
        if (p->ranura >= 1 && p->ranura <= 4) k++;
    }
    EnterCriticalSection(&g_sp_cs);
    CopyMemory(g_sp_pj, pj, sizeof(pj));
    g_sp_npj = k;
    g_sp_lista_lista = 1;
    LeaveCriticalSection(&g_sp_cs);
    apuntar("  [selector] LISTA: %d personaje(s)", k);
}

/* la respuesta de FFF8 / FFFA (como el FF01): [st][usn:u32][4 ceros][len][vcode en HEX] -> 1 si es buena */
static int sp_leer_sesion(const BYTE *r, int m, DWORD *usn, unsigned long long *vcode)
{
    if (m < 10 || r[0] != 0) return 0;
    int largo = r[9];
    char hexa[24];
    int c2 = largo < 20 ? largo : 20;
    CopyMemory(hexa, r + 10, c2);
    hexa[c2] = 0;
    *usn = *(DWORD *)(r + 1);
    *vcode = 0;
    for (char *q = hexa; *q; q++) {                         /* ⚠ en HEX, como el del FF01 */
        int d = (*q >= '0' && *q <= '9') ? *q - '0' : (*q >= 'A' && *q <= 'F') ? *q - 'A' + 10
              : (*q >= 'a' && *q <= 'f') ? *q - 'a' + 10 : -1;
        if (d < 0) break;
        *vcode = *vcode * 16 + (unsigned)d;
    }
    return *usn != 0;
}

static void sp_red_elegir(void)                            /* FFF8 ELEGIR -> g_sp_res_… */
{
    BYTE c[16], r[64];
    int n = sp_sesion(c);
    c[n++] = (BYTE)g_sp_ped_ranura;
    c[n++] = (BYTE)(g_sp_ped_crear ? 1 : 0);
    int m = sp_pedir(0xF8, c, n, r, sizeof(r));
    g_sp_res_ok = sp_leer_sesion(r, m, &g_sp_res_usn, &g_sp_res_vcode);
    apuntar("  [selector] ELEGIR casillero %d%s -> %s (usn %u)", g_sp_ped_ranura, g_sp_ped_crear ? " (CREAR)" : "",
            g_sp_res_ok ? "OK" : "NO", g_sp_res_usn);
}

/* FFFA VOLVER, con la sesión del personaje que se está jugando (la del ELEGIR; si se entró derecho, la de la línea
 *   de comandos) -> la sesión de la CUENTA, ya en modo elegir */
static int g_sp_vol_ok = 0;
static DWORD g_sp_vol_usn = 0;
static unsigned long long g_sp_vol_vcode = 0;

static void sp_red_volver(void)
{
    BYTE c[12], r[64];
    *(DWORD *)c = g_sp_res_ok ? g_sp_res_usn : g_sp_usn;
    *(unsigned long long *)(c + 4) = g_sp_res_ok ? g_sp_res_vcode : g_sp_vcode;
    int m = sp_pedir(0xFA, c, 12, r, sizeof(r));
    g_sp_vol_ok = sp_leer_sesion(r, m, &g_sp_vol_usn, &g_sp_vol_vcode);
    apuntar("  [selector] VOLVER (usn %u) -> %s (cuenta %u)", *(DWORD *)c, g_sp_vol_ok ? "OK" : "NO", g_sp_vol_usn);
}

/* SHA-256 en hex MAYÚSCULA de la contraseña (como launcher2013.hash_pass): lo único que viaja */
static void sp_sha256_hex(const char *msg, char *hex)
{
    static const DWORD K[64] = {
        0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,
        0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,
        0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,
        0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
        0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,
        0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,
        0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2 };
    DWORD H[8] = { 0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19 };
    BYTE buf[64];
    int n = lstrlenA(msg), total = ((n + 9 + 63) / 64) * 64;
    for (int bloque = 0; bloque < total; bloque += 64) {
        for (int i = 0; i < 64; i++) {
            int k = bloque + i;
            buf[i] = k < n ? (BYTE)msg[k] : k == n ? 0x80 : 0;
        }
        if (bloque + 64 == total) {
            unsigned long long bits = (unsigned long long)n * 8;
            for (int i = 0; i < 8; i++) buf[63 - i] = (BYTE)(bits >> (8 * i));
        }
        DWORD w[64], a[8];
        for (int i = 0; i < 16; i++)
            w[i] = (DWORD)buf[4 * i] << 24 | (DWORD)buf[4 * i + 1] << 16 | (DWORD)buf[4 * i + 2] << 8 | buf[4 * i + 3];
#define SP_ROR(x, r) (((x) >> (r)) | ((x) << (32 - (r))))
        for (int i = 16; i < 64; i++) {
            DWORD s0 = SP_ROR(w[i - 15], 7) ^ SP_ROR(w[i - 15], 18) ^ (w[i - 15] >> 3);
            DWORD s1 = SP_ROR(w[i - 2], 17) ^ SP_ROR(w[i - 2], 19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16] + s0 + w[i - 7] + s1;
        }
        for (int i = 0; i < 8; i++) a[i] = H[i];
        for (int i = 0; i < 64; i++) {
            DWORD S1 = SP_ROR(a[4], 6) ^ SP_ROR(a[4], 11) ^ SP_ROR(a[4], 25), ch = (a[4] & a[5]) ^ (~a[4] & a[6]);
            DWORD t1 = a[7] + S1 + ch + K[i] + w[i];
            DWORD S0 = SP_ROR(a[0], 2) ^ SP_ROR(a[0], 13) ^ SP_ROR(a[0], 22), mj = (a[0] & a[1]) ^ (a[0] & a[2]) ^ (a[1] & a[2]);
            a[7] = a[6]; a[6] = a[5]; a[5] = a[4]; a[4] = a[3] + t1; a[3] = a[2]; a[2] = a[1]; a[1] = a[0]; a[0] = t1 + S0 + mj;
        }
#undef SP_ROR
        for (int i = 0; i < 8; i++) H[i] += a[i];
    }
    static const char *X = "0123456789ABCDEF";
    for (int i = 0; i < 32; i++) {
        BYTE b = (BYTE)(H[i / 4] >> (24 - 8 * (i % 4)));
        hex[2 * i] = X[b >> 4];
        hex[2 * i + 1] = X[b & 15];
    }
    hex[64] = 0;
}

static void sp_red_borrar(void)                            /* FFF9 BORRAR -> g_sp_res_borrar_ok / g_sp_res_msg */
{
    BYTE c[96], r[256];
    int n = sp_sesion(c);
    c[n++] = (BYTE)g_sp_borrar;
    c[n++] = 64;
    CopyMemory(c + n, g_sp_ped_hash, 64);
    n += 64;
    int m = sp_pedir(0xF9, c, n, r, sizeof(r));
    g_sp_res_borrar_ok = m >= 2 && r[0] == 0;
    g_sp_res_msg[0] = 0;
    if (m >= 2) {                                           /* el mensaje viene en UTF-8: a la página del juego */
        WCHAR w[120];
        int l = r[1] < m - 2 ? r[1] : m - 2;
        int nw = MultiByteToWideChar(CP_UTF8, 0, (const char *)r + 2, l, w, 119);
        w[nw] = 0;
        WideCharToMultiByte(1252, 0, w, -1, g_sp_res_msg, sizeof(g_sp_res_msg), NULL, NULL);
    }
    apuntar("  [selector] BORRAR casillero %d -> %s (%s)", g_sp_borrar, g_sp_res_borrar_ok ? "OK" : "NO", g_sp_res_msg);
    if (g_sp_res_borrar_ok) sp_red_lista();
}

static DWORD WINAPI sp_hilo(LPVOID x)
{
    (void)x;
    if (!sp_red_cargar()) { apuntar("  [selector] ⛔ no pude cargar ws2_32: sin selector"); return 0; }
    BYTE c[12], r[8];
    int n = sp_pedir(0xF6, c, sp_sesion(c), r, sizeof(r));     /* HOLA */
    if (n < 1 || r[0] != 0) {
        apuntar("  [selector] el server no conoce el selector o la sesión no es de una cuenta (%d): sigue como siempre", n);
        return 0;
    }
    InterlockedExchange(&g_sp_hola, 1);
    apuntar("  [selector] ★ HOLA: el server manda la ficha vacía -> el juego va a abrir la creación con el selector");
    sp_red_lista();
    for (;;) {
        WaitForSingleObject(g_sp_evento, INFINITE);
        LONG p = InterlockedExchange(&g_sp_pedido, SPP_NADA);
        if (p == SPP_LISTA) sp_red_lista();
        else if (p == SPP_ELEGIR) sp_red_elegir();
        else if (p == SPP_BORRAR) sp_red_borrar();
        else if (p == SPP_VOLVER) sp_red_volver();
        if (p != SPP_NADA) InterlockedExchange(&g_sp_listo, p);
    }
}

static void sp_pedir_al_hilo(LONG que)
{
    InterlockedExchange(&g_sp_listo, SPP_NADA);
    InterlockedExchange(&g_sp_pedido, que);
    SetEvent(g_sp_evento);
}

/* ═══ 2 · LAS IMÁGENES: las hojas a memoria (una vez) y los dos lienzos ═════════════════════════════════════════ */
typedef void *(TCK *SP_F_CREAR)(void *self);
typedef int   (TCK *SP_F_CARGAR)(void *self, const char *ruta, const char *prefijo);
typedef void  (TCK *SP_F_RECORTE)(void *self, float x, float y, int u, int v, int w, int h, float z);
typedef void  (TCK *SP_F_POS)(void *self, int n, int x, int y);
typedef void  (TCK *SP_F_COLOR)(void *self, int n, DWORD argb);
typedef void  (TCK *SP_F_DIBUJAR)(void *self, int n, int banderas);

/* la textura D3D de un c2DImage (la de top5.c, pero con la base de ESTE módulo: no depende de que top5 esté prendido) */
static void *sp_textura(BYTE *img)
{
    void *mgr = *(void **)SPV(0x931570);
    DWORD h = *(DWORD *)(img + 4);
    if (!mgr || !h) return NULL;
    BYTE *ent = ((F_T5_TEX_ENTRADA)SPV(0x4099E0))(mgr, h);
    if (!ent || *(DWORD *)(ent + 0x48)) return NULL;
    return ((F_T5_TEX_D3D)SPV(0x441420))(mgr, h, 0);
}

static int sp_escribir(DWORD va, const void *b, int n)
{
    BYTE *s = SPV(va);
    DWORD viejo = 0;
    if (!VirtualProtect(s, n, PAGE_EXECUTE_READWRITE, &viejo)) return 0;
    CopyMemory(s, b, n);
    VirtualProtect(s, n, viejo, &viejo);
    return 1;
}

static BYTE   g_sp_img[SP_NHOJAS][0x100], g_sp_lz_fondo[0x100], g_sp_lz_frente[0x100];
static DWORD *g_sp_hoja[SP_NHOJAS];
static int    g_sp_hoja_w[SP_NHOJAS];
static int    g_sp_img_estado = 0;      /* 0 sin cargar · 1 listo · -1 no se usa */
static DWORD  g_sp_px[SP_LIENZO * SP_ALTO_LZ];
static DWORD  g_sp_firma_fondo = 0, g_sp_firma_frente = 0;
static void  *g_sp_tex_fondo = NULL, *g_sp_tex_frente = NULL;
static float  g_sp_z_fondo = 0.12f, g_sp_z_frente = 0.1f;

static void sp_cargar(void)
{
    g_sp_img_estado = -1;
    for (int i = 0; i < SP_NHOJAS; i++) {
        ((SP_F_CREAR)SPV(0x64E560))(g_sp_img[i]);
        if (!((SP_F_CARGAR)SPV(0x64E1E0))(g_sp_img[i], SP_HOJA_TGA[i], NULL)) {
            apuntar("  [selector] ⛔ no encontré %s (¿falta rnr_ui_selector_pj.pak?): sin selector", SP_HOJA_TGA[i]);
            return;
        }
        ((SP_F_RECORTE)SPV(0x64EC40))(g_sp_img[i], 0, 0, 0, 0, 4, 4, g_sp_z_frente);
        void *tex = sp_textura(g_sp_img[i]);
        T5_DESC d;
        if (!tex || !t5_desc(tex, &d) || d.Format != 21) {
            apuntar("  [selector] ⛔ no pude leer %s (tex=%p fmt=%u)", SP_HOJA_TGA[i], tex, tex ? d.Format : 0);
            return;
        }
        void **vt = *(void ***)tex;
        T5_BLOQUEO b;
        if (((T5_T_BLOQUEAR)vt[19])(tex, 0, &b, NULL, 0x10) != 0) { apuntar("  [selector] ⛔ hoja %d no se deja leer", i); return; }
        g_sp_hoja[i] = (DWORD *)HeapAlloc(GetProcessHeap(), 0, d.Width * d.Height * 4);
        if (g_sp_hoja[i])
            for (UINT y = 0; y < d.Height; y++)
                CopyMemory(g_sp_hoja[i] + y * d.Width, (BYTE *)b.pBits + y * b.Pitch, d.Width * 4);
        ((T5_T_SOLTAR)vt[20])(tex, 0);
        if (!g_sp_hoja[i]) return;
        g_sp_hoja_w[i] = (int)d.Width;
    }
    BYTE *lz[2] = { g_sp_lz_fondo, g_sp_lz_frente };
    const char *ruta[2] = { SP_LIENZO_FONDO_TGA, SP_LIENZO_FRENTE_TGA };
    float z[2] = { g_sp_z_fondo, g_sp_z_frente };
    for (int i = 0; i < 2; i++) {
        ((SP_F_CREAR)SPV(0x64E560))(lz[i]);
        if (!((SP_F_CARGAR)SPV(0x64E1E0))(lz[i], ruta[i], NULL)) { apuntar("  [selector] ⛔ no encontré %s", ruta[i]); return; }
        ((SP_F_RECORTE)SPV(0x64EC40))(lz[i], 0, 0, 0, 0, SP_W, SP_ALTO_LZ, z[i]);
    }
    if (!g_t5_dc && !t5_gdi_preparar()) { apuntar("  [selector] ⛔ GDI: sin letra"); return; }
    g_sp_img_estado = 1;
    apuntar("  [selector] ★ imágenes listas: %d hojas y los dos lienzos", SP_NHOJAS);
}

/* una pieza de una hoja sobre el lienzo en memoria (mezcla con su alfa) */
static void sp_pieza(const SP_PIEZA *p, int x, int y)
{
    if (!p || p->hoja < 0) return;
    const DWORD *h = g_sp_hoja[p->hoja];
    int hw = g_sp_hoja_w[p->hoja];
    for (int j = 0; j < p->h; j++) {
        int ty = y + SP_ARR + j;
        if (ty < 0 || ty >= SP_ALTO_LZ) continue;
        for (int i = 0; i < p->w; i++) {
            int tx = x + i;
            if (tx < 0 || tx >= SP_LIENZO) continue;
            DWORD s = h[(p->v + j) * hw + p->u + i];
            int a = (int)(s >> 24);
            if (!a) continue;
            DWORD *dp = &g_sp_px[ty * SP_LIENZO + tx];
            if (a == 255) { *dp = s; continue; }
            DWORD dd = *dp;
            int da = (int)(dd >> 24), oa = a + da * (255 - a) / 255;
            if (!oa) continue;
            int r = (((s >> 16) & 255) * a + ((dd >> 16) & 255) * da * (255 - a) / 255) / oa;
            int g = (((s >> 8) & 255) * a + ((dd >> 8) & 255) * da * (255 - a) / 255) / oa;
            int b = ((s & 255) * a + (dd & 255) * da * (255 - a) / 255) / oa;
            *dp = ((DWORD)oa << 24) | ((DWORD)r << 16) | ((DWORD)g << 8) | (DWORD)b;
        }
    }
}

/* un texto con contorno (el de la web: 1 px a los cuatro lados), por GDI: blanco sobre negro = el alfa */
static void sp_texto(int x, int y, int alin, int tam, int negrita, const char *s, DWORD color, DWORD borde)
{
    if (!s || !*s || !g_t5_dc) return;
    HFONT f = CreateFontW(-tam, 0, 0, 0, negrita ? FW_BOLD : FW_SEMIBOLD, 0, 0, 0, DEFAULT_CHARSET, OUT_TT_PRECIS,
                          CLIP_DEFAULT_PRECIS, ANTIALIASED_QUALITY, DEFAULT_PITCH, L"Segoe UI");
    if (!f) return;
    HGDIOBJ viejo = SelectObject(g_t5_dc, f);
    WCHAR w[200];
    int nw = id_a_ancho(s, w, 200) - 1;
    if (nw <= 0) { SelectObject(g_t5_dc, viejo); DeleteObject(f); return; }
    SIZE sz;
    GetTextExtentPoint32W(g_t5_dc, w, nw, &sz);
    int ancho = sz.cx + 4 < T5_GDI_W ? sz.cx + 4 : T5_GDI_W, alto = sz.cy + 2 < T5_GDI_H ? sz.cy + 2 : T5_GDI_H;
    ZeroMemory(g_t5_gdi, T5_GDI_W * T5_GDI_H * 4);
    TextOutW(g_t5_dc, 2, 1, w, nw);
    GdiFlush();
    int x0 = alin == 1 ? x - ancho / 2 : alin == 2 ? x - ancho : x;
    for (int pasada = 0; pasada < 2; pasada++) {            /* 0: el contorno · 1: la letra */
        if (pasada == 0 && !borde) continue;
        static const int OX[4] = { -1, 1, 0, 0 }, OY[4] = { 0, 0, -1, 1 };
        for (int k = 0; k < (pasada ? 1 : 4); k++)
            for (int j = 0; j < alto; j++)
                for (int i = 0; i < ancho; i++) {
                    int a = (int)(g_t5_gdi[j * T5_GDI_W + i] & 255);
                    if (!a) continue;
                    int tx = x0 + i + (pasada ? 0 : OX[k]), ty = y + j + SP_ARR + (pasada ? 0 : OY[k]);
                    if (tx < 0 || tx >= SP_LIENZO || ty < 0 || ty >= SP_ALTO_LZ) continue;
                    DWORD col = pasada ? color : borde;
                    t5_mezclar(&g_sp_px[ty * SP_LIENZO + tx], col | 0xFF000000u, a);
                }
    }
    SelectObject(g_t5_dc, viejo);
    DeleteObject(f);
}

static int sp_subir(void *tex)
{
    void **vt = *(void ***)tex;
    T5_BLOQUEO b;
    if (((T5_T_BLOQUEAR)vt[19])(tex, 0, &b, NULL, 0) != 0) return 0;
    for (int y = 0; y < SP_ALTO_LZ; y++)
        CopyMemory((BYTE *)b.pBits + y * b.Pitch, g_sp_px + y * SP_LIENZO, SP_LIENZO * 4);
    ((T5_T_SOLTAR)vt[20])(tex, 0);
    return 1;
}

/* ═══ 3 · ARMAR (calcado de dibujarSelector / armarSelector de portable/web/inicio.html) ═════════════════════════ */
static int sp_de_la_pagina(int k) { return 2 * g_sp_pagina + k + 1; }

static const SP_PJ *sp_pj(int ranura)
{
    for (int i = 0; i < g_sp_npj; i++) if (g_sp_pj[i].ranura == ranura) return &g_sp_pj[i];
    return NULL;
}

static const SP_PIEZA *sp_estado(int c)                    /* el estado de un botón según el mouse */
{
    const SP_CONTROL *k = &SP_CTL[c];
    if (g_sp_apretado == c && g_sp_sobre == c && k->d.hoja >= 0) return &k->d;
    if (g_sp_sobre == c && k->u.hoja >= 0) return &k->u;
    return &k->n;
}

/* ═══ 3-bis · EL MUÑECO DE CADA TARJETA (como la web: el personaje vestido; anonimo03: «con la lógica de mi info») ══════
 *   Todo lo hace el código de la CREACIÓN, medido (repo Fuente CREACION.md §6):
 *     el cuerpo   ruta = [0x931618]->0x5105A0(char_id) · h = *[0x931620]->0x640550(&h, ruta, 0)   (0x5803A6/0x5803B3)
 *     la pose     cModelo([0x931620]->0x413000(h)+0x1C)->0x655C20("인터페이스_boy|girl", 0, 0.0)    (0x5803DD)
 *     el reloj    t += 2,0 por cuadro, vuelve a 0 al largo del clip (modelo+0x130 -> +0x18); 0x652A00(t, 0, 1, 0)
 *     la ropa     0x580080: el artículo ([0x931618]->0x511420, su .md9 en +0x1C), su modelo (0x640550) y
 *                 g_pUser->0x491E90(cuerpo, prenda, &sinFalda, 0); la falda: ranura 4 sin falda -> fuera «Skirt»
 *     el dibujo   0x57F7E3..0x57F906: cámara 8, ortogonal, viewport, ×1,5, giro, −40, [0x93149C]+0x13C(h, 0xFF, 3, 1)
 *   ⇒ las alas y la cara NO salen solas: ver «LAS ALAS Y LA CARA» abajo. ⏳ El anillo. Un muñeco por casillero, armado
 *     UNA vez (en la lógica: carga archivos) y rehecho sólo si cambia su ropa. */
typedef void (TCK *SP_W_NADA)(void *w);                          /* (los mismos de sp_isla, más abajo) */
typedef void (TCK *SP_C_CAMARA)(void *c, int n);
typedef void (TCK *SP_G_MODELO)(void *g, void *modelo, int a, int b, int c);
typedef const char *(TCK *SP_M_RUTA)(void *c, DWORD char_id);
typedef DWORD *(TCK *SP_M_CARGAR)(void *mgr, DWORD *h, const char *ruta, int z);
typedef BYTE *(TCK *SP_M_ENTRADA)(void *mgr, DWORD h);
typedef void (TCK *SP_M_POSE)(void *modelo, const char *nombre, int a, float b);
typedef void (TCK *SP_M_TIEMPO)(void *modelo, float t, int a, float b, float c);
typedef BYTE (TCK *SP_M_RANURA)(void *c, DWORD item);
typedef BYTE *(TCK *SP_M_ARTICULO)(void *c, DWORD item);
typedef void (TCK *SP_M_PONER)(void *u, DWORD cuerpo, DWORD prenda, int *sin_falda, int z);
typedef int (TCK *SP_M_MALLA)(void *modelo, const char *nombre);
typedef void (TCK *SP_M_QUITAR)(void *mgr, DWORD h, int malla);
typedef void (TCK *SP_M_NADA)(void *modelo);
typedef struct { DWORD firma, h; float t; int listo; DWORD mascota; float tm; int pet_modo, pet_espera;
                 char pet_quieta[32], pet_gesto[32];
                 DWORD cuerpo; int alas_ok, caras_ok; DWORD alas[8], caras[8]; BYTE cara; } SP_MUNECO;
                 /* listo: 0 sin armar · 1 listo · -1 falló · alas/caras: los contenedores del armario (ver abajo) */
static SP_MUNECO g_sp_mu[5];
static int g_sp_mu_dy = 42;
static int g_sp_pet_activo = 1, g_sp_pet_paso = 1, g_sp_pet_dibujo = 1;
static int g_sp_alas = 1, g_sp_caras = 1;                     /* [selector] alas / caras (para medir) */   /* [selector] mascota_paso / mascota_dibujo (para medir) */
static float g_sp_pet_vel = 1.0f;
static float g_sp_pet_x = -121.0f, g_sp_pet_y = 130.0f, g_sp_pet_z = 0.0f, g_sp_pet_escala = 0.75f;   /* arriba a la izq. */     /* ★ anonimo03: «baja un poco el char, que sus pies pisen y pasen un poco la plataforma» */

static void *sp_modelo(DWORD h)
{
    void *mgr = *(void **)SPV(0x931620);
    BYTE *e = mgr && h ? ((SP_M_ENTRADA)SPV(0x413000))(mgr, h) : NULL;
    return e ? *(void **)(e + 0x1C) : NULL;
}

static const char *sp_cadena(BYTE *s)                     /* un std::string de VC++ 2008 (+0x18 = capacidad) */
{
    return *(DWORD *)(s + 0x18) >= 16 ? *(const char **)(s + 4) : (const char *)(s + 4);
}

static DWORD sp_mu_firma(const SP_PJ *pj)
{
    DWORD f = pj->char_id * 2654435761u ^ (DWORD)pj->sexo;
    for (int i = 0; i < pj->np; i++) f = f * 31u + pj->partes[i];
    return f | 1u;
}

/* ★★ EL MUÑECO = UNA COPIA ARMADA POR EL JUEGO (25-oct, anonimo03: «con la lógica como en mi armario»).
 *   ⛔ Antes se cargaba el cuerpo (0x640550) y se vestía a mano (0x491E90). Medido en vivo: el gestor COMPARTE los
 *     modelos por ruta (las dos chicas dieron el mismo handle 131073 = el muñeco +0xF4 de la creación): la última
 *     vestida pisaba a la otra, ¡y se vestía el muñeco nativo de la creación! Y los accesorios (manos, mascota)
 *     quedaban mal puestos.
 *   ⇒ El armario, la bienvenida y los asientos de la sala arman su muñeco con g_pUser->0x4940B0(&h, 0, 0, &sPersonaje)
 *     (0x4945B0 / 0x4944A0): una COPIA propia con TODO lo puesto, por la lógica nativa. Se suelta con
 *     g_pUser->0x48E640(h). sPersonaje (0x30 B): +0 el cuerpo (char_id), +4 una prenda por ranura (0..10; la ranura es
 *     0x50E0B0(id): los 3 primeros dígitos de "%08d"). */
typedef void (TCK *SP_M_COPIA)(void *u, DWORD *h, int a, int b, const DWORD *personaje);
/* ★ LA MASCOTA de la tarjeta: la del ARMARIO (cMyRoom+0x48B4), una cPlayer74 (0x9C B). Medido en el exe:
 *     armado   0x525070 (constructor) · 0x525550(número) · 0x524420(&{0, 425, 0}) · 0x524B80(1, 0)     (0x4CFFBB..0x4CFFE5)
 *     número   [0x931618]->0x50E180(la prenda de la RANURA 6) = g_pUser->0x4860E0 -> 0x486000(6)  (los 600xxx)
 *     paso     0x525100 cada cuadro (0x4CEBD6) · dibujo 0x524370(70, 70, −600, 1.0), después del muñeco (0x4C9464)
 *     se va    0x525DE0 (0x4D140F, al salir del armario) */
typedef void (TCK *SP_P_NADA)(void *p);
typedef void (TCK *SP_P_NUMERO)(void *p, int n);
typedef void (TCK *SP_P_POS)(void *p, const float *v);
typedef void (TCK *SP_P_ANIM)(void *p, int a, int b);
typedef void (TCK *SP_P_DIBUJAR)(void *p, float x, float y, float z, float escala);
typedef WORD (TCK *SP_P_CUAL)(void *tabla, DWORD item);
typedef void (TCK *SP_M_SOLTAR)(void *u, DWORD h);

/* ★★ LAS ALAS Y LA CARA, como el ARMARIO (cMyRoom). Medido en el exe (SELECTOR_PERSONAJE.md §10):
 *   LAS ALAS no son prenda del modelo: son EFECTOS en una lista por muñeco (cMyRoom+0x49A8, una std::list de 0x1C B).
 *     armado   0x44F590 (constructor) · se va con 0x453950
 *     cuáles   [0x9316D4]->0x4B1740(lista, 0, 0, 0): recorre las alas del juego ([0x9316D4]+0xF4: +0x10 el ItemEffect,
 *              +0x12 el efecto) y pone las que g_pUser LLEVA (0x489160: el ItemEffect del artículo = +0x58 ^ 0x1FEF).
 *              ⇒ el mismo recorrido, preguntando por las prendas de la TARJETA, y 0x4B06C0(efecto, 0, 0, 0, 0) para cada una
 *     paso     0x4AF330(1) cada cuadro (0x4CEBD1; con 0 los efectos de una vez se borran al terminar)
 *     dibujo   0x4B0690(char_id, 1, 0, 1.0, 3) justo DESPUÉS del muñeco, antes de su pop (0x4C9426)
 *   LA CARA es una TEXTURA: [0x931618]->0x516B60(&h, cara, &sPersonaje, &cache, 1) le cambia la de la malla «Face»
 *     (0x4CFF28; 0x511B50 arma "rnr_char/FACE/%02d/…"). cara = la fila de Face.txt ([0x931618]+0x74: {ItemEffect:2,
 *     Index:1, CharType:1}) cuyo ItemEffect lleva y cuyo CharType le va al cuerpo (0x50DF60) — 0x489420, con la tarjeta.
 *     cache = las texturas puestas (cMyRoom+0x4988, una std::map de 0x20 B): 0x5BC450 (constructor) · al irse se suelta
 *     cada textura ([0x931570]->0x641C80(&nodo+0x10), 0x4CDF2D) y 0x542530 */
typedef void (TCK *SP_A_NADA)(void *c);
typedef void (TCK *SP_A_LLENAR)(void *mgr, void *c, float x, float y, float z);
typedef void (TCK *SP_A_PONER)(void *c, DWORD efecto, float x, float y, float z, float w);
typedef void (TCK *SP_A_PASO)(void *c, DWORD a);
typedef void (TCK *SP_A_DIBUJAR)(void *c, DWORD char_id, int a, int b, float escala, int d);
typedef void (TCK *SP_K_ARMAR)(void *c, BYTE *x, BYTE *y);
typedef void (TCK *SP_K_PONER)(void *tabla, DWORD *h, DWORD cara, const DWORD *personaje, void *cache, DWORD nuevo);
typedef void (TCK *SP_K_SOLTAR_TEX)(void *mgr, DWORD *h);
typedef BYTE (TCK *SP_K_LE_VA)(void *tabla, DWORD cuerpo, DWORD tipo);

static int sp_lleva_efecto(void *tabla, const SP_PJ *pj, DWORD efecto)
{
    for (int i = 0; i < pj->np; i++) {
        BYTE *art = ((SP_M_ARTICULO)SPV(0x511420))(tabla, pj->partes[i]);
        if ((DWORD)art < 0x10000) continue;
        if ((*(DWORD *)(art + 0x58) ^ 0x1FEFu) == efecto && !art[0x69]) return 1;
    }
    return 0;
}

static BYTE sp_mu_cara(void *tabla, const SP_PJ *pj, DWORD cuerpo)
{
    BYTE *e = *(BYTE **)((BYTE *)tabla + 0x74), *fin = *(BYTE **)((BYTE *)tabla + 0x78);
    for (; e && e < fin; e += 4)
        if (((SP_K_LE_VA)SPV(0x50DF60))(tabla, cuerpo, e[3]) && sp_lleva_efecto(tabla, pj, *(WORD *)e)) return e[2];
    return 0;
}

static int sp_mu_alas(SP_MUNECO *m, void *tabla, const SP_PJ *pj)
{
    BYTE *mgr = *(BYTE **)SPV(0x9316D4);
    if (!mgr) return 0;
    if (!m->alas_ok) { ((SP_A_NADA)SPV(0x44F590))(m->alas); m->alas_ok = 1; }
    int n = 0;
    BYTE *cab = *(BYTE **)(mgr + 0xF4);
    for (BYTE *q = cab ? *(BYTE **)cab : NULL; q && q != cab; q = *(BYTE **)q)
        if (sp_lleva_efecto(tabla, pj, *(WORD *)(q + 0x10))) {
            ((SP_A_PONER)SPV(0x4B06C0))(m->alas, *(WORD *)(q + 0x12), 0.0f, 0.0f, 0.0f, 0.0f);
            n++;
        }
    return n;
}

static void sp_k_soltar_texturas(BYTE *nodo)                 /* en orden, como el iterador del juego (0x612F10) */
{
    if (!nodo || nodo[0x15]) return;
    sp_k_soltar_texturas(*(BYTE **)nodo);
    void *tex = *(void **)SPV(0x931570);
    if (tex) ((SP_K_SOLTAR_TEX)SPV(0x641C80))(tex, (DWORD *)(nodo + 0x10));
    sp_k_soltar_texturas(*(BYTE **)(nodo + 8));
}

static void sp_mu_soltar(SP_MUNECO *m)
{
    if (m->alas_ok) { ((SP_A_NADA)SPV(0x453950))(m->alas); m->alas_ok = 0; }
    void *u = *(void **)SPV(0x9314E0);
    if (m->mascota) {
        typedef void (TCK *SP_M_SOLTAR_MOD)(void *mgr, DWORD *h);
        void *mgr = *(void **)SPV(0x931620);
        if (mgr) ((SP_M_SOLTAR_MOD)SPV(0x63D980))(mgr, &m->mascota);       /* resta 1 a su cuenta de usos */
        m->mascota = 0;
    }
    if (m->listo == 1 && m->h && u) ((SP_M_SOLTAR)SPV(0x48E640))(u, m->h);
    if (m->caras_ok) {
        BYTE *cab = *(BYTE **)((BYTE *)m->caras + 0x18);
        if (cab) sp_k_soltar_texturas(*(BYTE **)(cab + 4));      /* la raíz */
        ((SP_A_NADA)SPV(0x542530))(m->caras);
        m->caras_ok = 0;
    }
    m->h = 0;
    m->cara = 0;
    m->listo = 0;
}

static void sp_mu_soltar_todos(void)
{
    for (int i = 1; i <= 4; i++) sp_mu_soltar(&g_sp_mu[i]);
}

static void sp_mu_armar(const SP_PJ *pj)
{
    SP_MUNECO *m = &g_sp_mu[pj->ranura];
    void *tabla = *(void **)SPV(0x931618), *u = *(void **)SPV(0x9314E0);
    sp_mu_soltar(m);
    m->firma = sp_mu_firma(pj);
    m->listo = -1;
    if (!tabla || !u) return;
    DWORD cuerpo = pj->char_id ? pj->char_id : (pj->sexo == 2 ? 130901 : 130900);
    DWORD personaje[12];
    ZeroMemory(personaje, sizeof(personaje));
    personaje[0] = cuerpo;
    int puestas = 0;
    for (int i = 0; i < pj->np; i++) {
        BYTE r = ((SP_M_RANURA)SPV(0x50E0B0))(tabla, pj->partes[i]);
        if (r <= 10) { personaje[1 + r] = pj->partes[i]; puestas++; }
    }
    DWORD h = 0;
    ((SP_M_COPIA)SPV(0x4940B0))(u, &h, 0, 0, personaje);
    void *mod = sp_modelo(h);
    if (!mod) { apuntar("  [selector] ⛔ muñeco %d: 0x4940B0 no armó la copia (cuerpo %u)", pj->ranura, cuerpo); return; }
    /* la pose: la del ARMARIO = la del selector chino, «대기1_<cuerpo>» (0x4CE97E..0x4CE9B4) */
    typedef const char *(TCK *SP_M_SUFIJO)(void *u, DWORD char_id);
    const char *suf = ((SP_M_SUFIJO)SPV(0x485F30))(u, cuerpo);
    char pose[64];
    wsprintfA(pose, (const char *)SPV(0x8765B4), suf ? suf : (pj->sexo == 2 ? "girl" : "boy"));
    ((SP_M_POSE)SPV(0x655C20))(mod, pose, 0, 0.0f);
    m->h = h;
    m->t = 0.0f;
    m->listo = 1;
    m->cuerpo = cuerpo;
    m->cara = g_sp_caras ? sp_mu_cara(tabla, pj, cuerpo) : 0;
    if (m->cara) {
        BYTE x = 0, y = 0;
        ((SP_K_ARMAR)SPV(0x5BC450))(m->caras, &x, &y);
        m->caras_ok = 1;
        ((SP_K_PONER)SPV(0x516B60))(tabla, &m->h, m->cara, personaje, m->caras, 1);
    }
    int alas = g_sp_alas ? sp_mu_alas(m, tabla, pj) : 0;
    apuntar("  [selector]   cara %u, alas %d", (unsigned)m->cara, alas);
    /* la mascota: la prenda de la ranura 6, si tiene */
    /* ★ LA MASCOTA = el MODELO de su ítem (la prenda de la ranura 6: los 600xxx), dibujado por nosotros al costado del
     *   muñeco. anonimo03: en la versión que vestía a mano «la mascota ya se renderizaba, en el lugar equivocado» (colgada
     *   del muñeco, a los pies). ⛔ La cPlayer74 del armario (0x525070/0x525550…) NO: MEDIDO, con ella el juego se caía en
     *   el heap de Windows aun sin paso ni dibujo (SELECTOR_PERSONAJE.md §9.1). La pose: la de la mascota en reposo,
     *   «pet_<número>» (0x524B80 usa pet_win_%d / pet_lose_%d / pet_rand1_%d; el número = [0x931618]->0x50E180). */
    WORD numero = 0;
    if (g_sp_pet_activo && personaje[1 + 6]) {
        /* como la arma el juego (cPet 0x525550, 0x52561F..0x525702):
         *   info = [0x931618]->0x5202F0(número): +4 la ruta del MODELO, +0x20 la de sus ANIMACIONES (std::string)
         *   base = [0x931620]->0x640550(ruta) · h = [0x931620]->0x6408A0(&h, base, nombre único): la COPIA propia
         *   la animación: [0x9342B0]->0x65F6B0(ruta_ani, "pet_<número>") — sin eso la pose no existe y queda quieta */
        typedef BYTE *(TCK *SP_PET_INFO)(void *tabla, int n);
        typedef DWORD *(TCK *SP_M_CLONAR)(void *mgr, DWORD *h, DWORD base, const char *nombre);
        typedef void (TCK *SP_M_SOLTAR_MOD)(void *mgr, DWORD *h);
        typedef void *(TCK *SP_ANI_CARGAR)(void *lib, const char *ruta, const char *nombre);
        void *mgr = *(void **)SPV(0x931620), *lib = *(void **)SPV(0x9342B0);
        numero = ((SP_P_CUAL)SPV(0x50E180))(tabla, personaje[1 + 6]);
        BYTE *info = numero ? ((SP_PET_INFO)SPV(0x5202F0))(tabla, numero) : NULL;
        const char *rm = (DWORD)info >= 0x10000 ? sp_cadena(info + 4) : NULL;
        const char *ra = (DWORD)info >= 0x10000 ? sp_cadena(info + 0x20) : NULL;
        if (mgr && rm && *rm) {
            DWORD base = 0, *pb = ((SP_M_CARGAR)SPV(0x640550))(mgr, &base, rm, 0);
            base = pb ? *pb : 0;
            char unico[32], nom[32];
            wsprintfA(unico, "selector_pet_%d", pj->ranura);
            DWORD hp = 0, *php = base ? ((SP_M_CLONAR)SPV(0x6408A0))(mgr, &hp, base, unico) : NULL;
            hp = php ? *php : 0;
            if (base) ((SP_M_SOLTAR_MOD)SPV(0x63D980))(mgr, &base);
            void *pm = sp_modelo(hp);
            if (pm) {
                /* ★ anonimo03: «en el juego suelen tener 2 animaciones: una estática y otra que se activa cada cierto
                 *   tiempo». La quieta = pet_<n> en su primer cuadro; el gesto = pet_rand1_<n> (si la mascota no lo
                 *   trae, su pet_<n> entera), una vez cada ~10 s */
                wsprintfA(nom, "pet_%d", numero);
                if (lib && ra && *ra) ((SP_ANI_CARGAR)SPV(0x65F6B0))(lib, ra, nom);
                lstrcpyA(m->pet_quieta, nom);
                lstrcpyA(m->pet_gesto, nom);
                ((SP_M_POSE)SPV(0x655C20))(pm, m->pet_quieta, 0, 0.0f);
                ((SP_M_TIEMPO)SPV(0x652A00))(pm, 0.0f, 0, 1.0f, 0.0f);
                m->mascota = hp;
                m->tm = 0.0f;
                m->pet_modo = 0;
                m->pet_espera = 300 + 120 * pj->ranura;             /* (que no gesticulen todas a la vez) */
            }
            apuntar("  [selector]   mascota %u: modelo %s, animaciones %s -> h=%u", (unsigned)numero, rm, ra ? ra : "?", hp);
        }
    }
    apuntar("  [selector] ★ muñeco del casillero %d: copia propia (h=%u), cuerpo %u, %d prendas, pose %s, mascota %u (%u)",
            pj->ranura, h, cuerpo, puestas, suf ? suf : "?", personaje[1 + 6], (unsigned)numero);
}

/* en la LÓGICA (el hilo del juego): arma los de la página y les corre el reloj */
static void sp_mu_logica(void)
{
    EnterCriticalSection(&g_sp_cs);
    for (int k = 0; k < 2; k++) {
        const SP_PJ *pj = sp_pj(sp_de_la_pagina(k));
        if (!pj) continue;
        SP_MUNECO *m = &g_sp_mu[pj->ranura];
        if (m->listo == 0 || (m->listo == 1 && m->firma != sp_mu_firma(pj))) sp_mu_armar(pj);
        void *mod = m->listo == 1 ? sp_modelo(m->h) : NULL;
        if (!mod) continue;
        BYTE *clip = *(BYTE **)((BYTE *)mod + 0x130);
        float largo = clip ? *(float *)(clip + 0x18) : 0.0f;
        m->t += 2.0f;
        if (m->t > largo) m->t = 0.0f;
        ((SP_M_TIEMPO)SPV(0x652A00))(mod, m->t, 0, 1.0f, 0.0f);
        if (m->alas_ok) ((SP_A_PASO)SPV(0x4AF330))(m->alas, 1);
        void *pm = m->mascota && g_sp_pet_paso ? sp_modelo(m->mascota) : NULL;
        if (pm) {
            /* ★ anonimo03: «aquí SOLO quiero su animación quieta, la estática que se mueve poco, no la que se activa cada
             *   cierto tiempo» ⇒ pet_<n> en bucle, más lenta que el muñeco: [selector] mascota_vel (décimas; 10 = 1,0) */
            BYTE *clip_m = *(BYTE **)((BYTE *)pm + 0x130);
            float largo_m = clip_m ? *(float *)(clip_m + 0x18) : 0.0f;
            m->tm += g_sp_pet_vel;
            if (m->tm > largo_m) m->tm = 0.0f;
            ((SP_M_TIEMPO)SPV(0x652A00))(pm, m->tm, 0, 1.0f, 0.0f);
        }
    }
    LeaveCriticalSection(&g_sp_cs);
}

typedef void (TCK *SP_W_ORTO)(void *w, float a, float b, float c, float d);
typedef void (TCK *SP_W_3F)(void *w, float x, float y, float z);
typedef void *(TCK *SP_W_DISP)(void *w);
typedef long (__stdcall *SP_D_VIEWPORT)(void *dev, const DWORD *vp);
typedef long (__stdcall *SP_D_LIMPIAR)(void *dev, DWORD n, const void *rects, DWORD que, DWORD color, float z, DWORD stencil);

/* ★ anonimo03 (25-oct): las alas salían «como dentro de una caja» — el rectángulo del muñeco (240×384) las cortaba, y
 *   «hay alas de distintos tamaños, así que el ajuste debe ser general». ⇒ el rectángulo crece alrededor del MISMO
 *   centro (hasta 2,5 veces, lo que entre en la pantalla) y la ortogonal crece igual: el muñeco queda del mismo tamaño
 *   y en el mismo lugar. Lo que sobra lo recorta la TARJETA (el recorte de D3D: SetScissorRect, sólo mientras se
 *   dibuja el muñeco). */
typedef long (__stdcall *SP_D_ESTADO)(void *dev, DWORD que, DWORD valor);
typedef long (__stdcall *SP_D_LEER_ESTADO)(void *dev, DWORD que, DWORD *valor);
typedef long (__stdcall *SP_D_RECORTE)(void *dev, RECT *r);

static void sp_mu_dibujar(SP_MUNECO *m, int x, int y, int w_, int h_, const RECT *tarjeta)
{
    void *w = *(void **)SPV(0x931498), *cam = *(void **)SPV(0x9314D4), *g = *(void **)SPV(0x93149C);
    DWORD h = m->h;
    if (!w || !cam || !g || !h) return;
    void **vt = *(void ***)w;
    int cx = x + w_ / 2, cy = y + h_ / 2;
    int mx = cx < (int)g_ancho - cx ? cx : (int)g_ancho - cx, my = cy < (int)g_alto - cy ? cy : (int)g_alto - cy;
    int W = w_ * 5 / 2, H = h_ * 5 / 2;                     /* el rectángulo grande: centrado y dentro de la pantalla */
    if (W > 2 * mx) W = 2 * mx;
    if (H > 2 * my) H = 2 * my;
    if (W * h_ > H * w_) W = H * w_ / h_; else H = W * h_ / w_;
    if (W < w_ || H < h_) { W = w_; H = h_; }
    ((SP_C_CAMARA)SPV(0x644050))(cam, 8);
    ((SP_W_ORTO)vt[0x20 / 4])(w, *(float *)SPV(0x881C48) * W / w_, *(float *)SPV(0x881C4C) * H / h_,
                              *(float *)SPV(0x8749CC), *(float *)SPV(0x8749D0));
    void *dev = ((SP_W_DISP)vt[0x58 / 4])(w);
    if (!dev) return;
    void **dv = *(void ***)dev;
    float cero = 0.0f, uno = 1.0f;
    DWORD vp[6] = { (DWORD)(cx - W / 2), (DWORD)(cy - H / 2), (DWORD)W, (DWORD)H, *(DWORD *)&cero, *(DWORD *)&uno };
    ((SP_D_VIEWPORT)dv[0xBC / 4])(dev, vp);
    /* 174 = D3DRS_SCISSORTESTENABLE · 58/57 = Get/SetRenderState · 76/75 = Get/SetScissorRect */
    DWORD recorte_antes = 0;
    RECT r_antes, r = *tarjeta;
    ((SP_D_LEER_ESTADO)dv[58])(dev, 174, &recorte_antes);
    ((SP_D_RECORTE)dv[76])(dev, &r_antes);
    ((SP_D_RECORTE)dv[75])(dev, &r);
    ((SP_D_ESTADO)dv[57])(dev, 174, 1);
    /* ★ la PROFUNDIDAD de la tarjeta, en limpio: el fondo del selector (2D, z 0,12) ya la escribió y el muñeco
     *   (ortogonal, z ≈ 0,5) quedaba «detrás» — no se veía (anonimo03, 25-oct: «está vacío»). Con el viewport puesto,
     *   Clear(0, NULL, …) limpia sólo ese rectángulo. 43 = IDirect3DDevice9::Clear · 2 = D3DCLEAR_ZBUFFER */
    ((SP_D_LIMPIAR)(*(void ***)dev)[43])(dev, 0, NULL, 2, 0, 1.0f, 0);
    ((SP_W_NADA)vt[0x6C / 4])(w);
    ((SP_W_3F)vt[0x94 / 4])(w, *(float *)SPV(0x873F6C), *(float *)SPV(0x873F6C), *(float *)SPV(0x873F6C));
    ((SP_W_3F)vt[0x80 / 4])(w, 0.0f, 0.0f, 0.0f);
    ((SP_W_3F)vt[0x7C / 4])(w, 0.0f, *(float *)SPV(0x87DC34), 0.0f);
    (*(SP_G_MODELO *)((BYTE *)g + 0x13C))(g, (void *)(UINT_PTR)h, 0xFF, 3, 1);
    if (m->alas_ok) ((SP_A_DIBUJAR)SPV(0x4B0690))(m->alas, m->cuerpo, 1, 0, 1.0f, 3);
    ((SP_W_NADA)vt[0x70 / 4])(w);
    ((SP_D_ESTADO)dv[57])(dev, 174, recorte_antes);
    ((SP_D_RECORTE)dv[75])(dev, &r_antes);
    DWORD todo[6] = { 0, 0, g_ancho, g_alto, *(DWORD *)&cero, *(DWORD *)&uno };
    ((SP_D_VIEWPORT)dv[0xBC / 4])(dev, todo);
}

/* ★ la MASCOTA, arriba a la izquierda de la tarjeta (anonimo03, con un dibujo: el recuadro rojo). Su viewport es la
 *   tarjeta ENTERA (360×576, el aspecto 0,625 del nativo) y se corre a ese rincón: [selector] mascota_x/y (unidades
 *   del modelo desde el centro de la tarjeta) y mascota_escala (en centésimas). */
static void sp_pet_dibujar(DWORD h, int x, int y)
{
    void *w = *(void **)SPV(0x931498), *cam = *(void **)SPV(0x9314D4), *g = *(void **)SPV(0x93149C);
    if (!w || !cam || !g || !h) return;
    void **vt = *(void ***)w;
    ((SP_C_CAMARA)SPV(0x644050))(cam, 8);
    ((SP_W_ORTO)vt[0x20 / 4])(w, *(float *)SPV(0x881C48), *(float *)SPV(0x881C4C), *(float *)SPV(0x8749CC),
                              *(float *)SPV(0x8749D0));
    void *dev = ((SP_W_DISP)vt[0x58 / 4])(w);
    if (!dev) return;
    float cero = 0.0f, uno = 1.0f;
    DWORD vp[6] = { (DWORD)x, (DWORD)y, 360, 576, *(DWORD *)&cero, *(DWORD *)&uno };
    ((SP_D_VIEWPORT)(*(void ***)dev)[0xBC / 4])(dev, vp);
    /* ★ la profundidad, también acá (anonimo03: «se ven entrecortadas»): fuera del rectángulo del muñeco seguía la del
     *   fondo 2D y cortaba la mascota justo en su borde */
    ((SP_D_LIMPIAR)(*(void ***)dev)[43])(dev, 0, NULL, 2, 0, 1.0f, 0);
    ((SP_W_NADA)vt[0x6C / 4])(w);
    ((SP_W_3F)vt[0x7C / 4])(w, g_sp_pet_x, g_sp_pet_y, g_sp_pet_z);
    ((SP_W_3F)vt[0x94 / 4])(w, g_sp_pet_escala, g_sp_pet_escala, g_sp_pet_escala);
    (*(SP_G_MODELO *)((BYTE *)g + 0x13C))(g, (void *)(UINT_PTR)h, 0xFF, 3, 1);
    ((SP_W_NADA)vt[0x70 / 4])(w);
    DWORD todo[6] = { 0, 0, g_ancho, g_alto, *(DWORD *)&cero, *(DWORD *)&uno };
    ((SP_D_VIEWPORT)(*(void ***)dev)[0xBC / 4])(dev, todo);
}

static void sp_mu_dibujar_tarjetas(void)
{
    for (int k = 0; k < 2; k++) {
        const SP_PJ *pj = sp_pj(sp_de_la_pagina(k));
        if (!pj || g_sp_mu[pj->ranura].listo != 1) continue;
        const SP_CONTROL *c = &SP_CTL[k ? SPC_CHAR_RIGHT : SPC_CHAR_LEFT];
        /* el lugar del muñeco de la web: 240×384 centrado, 52 px abajo del borde de la tarjeta (el aspecto 0,625 del
         *   viewport nativo, 200×320) */
        RECT tarjeta = { g_sp_x0 + c->x, g_sp_y0 + SP_ARR + c->y, g_sp_x0 + c->x + c->w, g_sp_y0 + SP_ARR + c->y + c->h };
        sp_mu_dibujar(&g_sp_mu[pj->ranura], g_sp_x0 + c->x + (c->w - 240) / 2, g_sp_y0 + SP_ARR + c->y + 52 + g_sp_mu_dy,
                      240, 384, &tarjeta);
        if (g_sp_mu[pj->ranura].mascota && g_sp_pet_dibujo)
            sp_pet_dibujar(g_sp_mu[pj->ranura].mascota, g_sp_x0 + c->x, g_sp_y0 + SP_ARR + c->y);
    }
}

static void sp_armar_fondo(void)
{
    ZeroMemory(g_sp_px, sizeof(g_sp_px));
    int lado = (g_sp_elegida - 1) % 2;
    for (int i = 0; i < 8; i++) {
        if (i >= SPF_IMGON1 && ((i == SPF_IMGON1 || i == SPF_IMGON2) != (lado == 0))) continue;   /* sólo la elegida */
        sp_pieza(&SP_FONDO[i].n, SP_FONDO[i].x, SP_FONDO[i].y);
    }
}

/* ★ El cartel de BORRAR: el del chino (del_user.rui: chardelete02), centrado, como abrirBorrar de la web. Encima de
 *   todo el FRENTE, con un velo que oscurece también el fondo (el frente va adelante). */
static int sp_cx(void) { return (SP_W - SP_BORRAR[SPB_BG].w) / 2 - SP_BORRAR[SPB_BG].x; }
static int sp_cy(void) { return (SP_H - SP_BORRAR[SPB_BG].h) / 2 - SP_BORRAR[SPB_BG].y; }

static const SP_PIEZA *sp_bestado(int c)
{
    const SP_CONTROL *k = &SP_BORRAR[c];
    if (g_sp_bapretado == c && g_sp_bsobre == c && k->d.hoja >= 0) return &k->d;
    if (g_sp_bsobre == c && k->u.hoja >= 0) return &k->u;
    return &k->n;
}

static void sp_armar_cartel(void)
{
    for (int i = 0; i < SP_LIENZO * SP_ALTO_LZ; i++) {           /* el velo: negro al 45 % sobre todo */
        DWORD d = g_sp_px[i];
        int a = (int)(d >> 24);
        if (!a) { g_sp_px[i] = 0x73000000u; continue; }
        int r = (int)((d >> 16) & 255) * 55 / 100, g = (int)((d >> 8) & 255) * 55 / 100, b = (int)(d & 255) * 55 / 100;
        g_sp_px[i] = ((DWORD)(a > 0x73 ? a : 0x73) << 24) | ((DWORD)r << 16) | ((DWORD)g << 8) | (DWORD)b;
    }
    int ox = sp_cx(), oy = sp_cy();
    const SP_CONTROL *bg = &SP_BORRAR[SPB_BG], *id = &SP_BORRAR[SPB_TEXT_ID], *pw = &SP_BORRAR[SPB_TEXT_PASSWORD];
    sp_pieza(&bg->n, bg->x + ox, bg->y + oy);
    sp_texto(bg->x + ox + 30, bg->y + oy + 24, 0, 26, 1, "Borrar personaje", 0xFFFFFF, 0x0D3557);
    const SP_PJ *pj = sp_pj(g_sp_borrar);
    char t[80];
    sp_texto(id->x + ox, id->y + oy - 28, 0, 13, 1, "Personaje", 0x0D3557, 0xFFFFFF);
    wsprintfA(t, "%s  \xB7  Nv. %d", pj ? pj->apodo : "?", pj ? pj->nivel : 0);
    sp_texto(id->x + ox + 10, id->y + oy + 2, 0, 15, 1, t, 0xFFFFFF, 0);
    sp_texto(id->x + ox, pw->y + oy - 28, 0, 13, 1, "Tu contrase\xF1" "a, para confirmar", 0x0D3557, 0xFFFFFF);
    char puntos[40];
    int k = 0;
    for (; k < g_sp_clave_n && k < 32; k++) puntos[k] = (char)0x95;      /* • */
    puntos[k++] = '|';                                                    /* el cursor */
    puntos[k] = 0;
    sp_texto(id->x + ox + 10, pw->y + oy + 1, 0, 15, 1, puntos, 0xFFFFFF, 0);
    sp_texto(id->x + ox, pw->y + oy + 44, 0, 12, 0, "Deja de aparecer en tu cuenta y su casillero queda libre.", 0x0D3557, 0xFFFFFF);
    if (g_sp_borrar_error[0]) sp_texto(id->x + ox, pw->y + oy + 64, 0, 12, 1, g_sp_borrar_error, 0xB3261E, 0);
    const SP_CONTROL *ok = &SP_BORRAR[SPB_BTN_OK], *no = &SP_BORRAR[SPB_BTN_NO];
    sp_pieza(sp_bestado(SPB_BTN_OK), ok->x + ox, ok->y + oy);
    sp_texto(ok->x + ox + ok->w / 2, ok->y + oy + 4, 1, 13, 1, g_sp_pedido == SPP_BORRAR ? "\x85" : "Borrar", 0xFFFFFF, 0x20303A);
    sp_pieza(sp_bestado(SPB_BTN_NO), no->x + ox, no->y + oy);
    sp_texto(no->x + ox + no->w / 2, no->y + oy + 4, 1, 13, 1, "Cancelar", 0xFFFFFF, 0x20303A);
}

static void sp_armar_frente(void)
{
    ZeroMemory(g_sp_px, sizeof(g_sp_px));
    EnterCriticalSection(&g_sp_cs);
    /* las tarjetas: el apodo grande (⏳ la web dibuja acá el muñeco 3D: etapa 6) */
    for (int k = 0; k < 2; k++) {
        int r = sp_de_la_pagina(k);
        const SP_PJ *pj = sp_pj(r);
        const SP_CONTROL *c = &SP_CTL[k ? SPC_CHAR_RIGHT : SPC_CHAR_LEFT];
        int cx = c->x + c->w / 2;
        char t[64];
        if (pj && g_sp_mu[pj->ranura].listo != 1) {          /* sin muñeco (todavía): el apodo grande */
            sp_texto(cx, 200, 1, 34, 1, pj->apodo, 0xFFFFFF, 0x0B3D45);
            wsprintfA(t, "Nv.%d \xB7 %s", pj->nivel, pj->sexo == 2 ? "chica" : "chico");
            sp_texto(cx, 250, 1, 17, 1, t, 0xFFE95A, 0x0B3D45);
        } else if (!pj) {
            wsprintfA(t, "Casillero %d libre", r);
            sp_texto(cx, 215, 1, 21, 1, t, 0xD8F3F0, 0x0B3D45);
        }
    }
    sp_pieza(&SP_CTL[SPC_IMG_BAR_LEFT].n, SP_CTL[SPC_IMG_BAR_LEFT].x, SP_CTL[SPC_IMG_BAR_LEFT].y);
    sp_pieza(&SP_CTL[SPC_IMG_BAR_RIGHT].n, SP_CTL[SPC_IMG_BAR_RIGHT].x, SP_CTL[SPC_IMG_BAR_RIGHT].y);
    sp_pieza(&SP_CTL[SPC_IMG_INFO].n, SP_CTL[SPC_IMG_INFO].x, SP_CTL[SPC_IMG_INFO].y);
    sp_pieza(&SP_CTL[SPC_IMG_CASE_BG].n, SP_CTL[SPC_IMG_CASE_BG].x + 90 * g_sp_pagina, SP_CTL[SPC_IMG_CASE_BG].y);
    for (int k = 0; k < 4; k++) sp_pieza(&SP_CTL[SPC_TAB_NUM_0 + k].n, SP_CTL[SPC_TAB_NUM_0 + k].x, SP_CTL[SPC_TAB_NUM_0 + k].y);
    sp_pieza(&SP_CTL[SPC_IMG_CASE].n, SP_CTL[SPC_IMG_CASE].x + 90 * g_sp_pagina, SP_CTL[SPC_IMG_CASE].y);
    sp_pieza(&SP_CTL[SPC_IMG_TITLE].n, SP_CTL[SPC_IMG_TITLE].x, SP_CTL[SPC_IMG_TITLE].y);
    for (int k = 0; k < 2; k++) {
        int r = sp_de_la_pagina(k);
        const SP_PJ *pj = sp_pj(r);
        /* ON / OFF (el radio «SLOT»: N = OFF, D = ON) */
        const SP_CONTROL *o = &SP_CTL[k ? SPC_ON_RIGHT : SPC_ON_LEFT];
        sp_pieza(r == g_sp_elegida ? &o->d : &o->n, o->x, o->y);
        /* el nivel y el apodo en la barra: a la izquierda del ON / a la derecha del OFF */
        int ax = k ? SP_CTL[SPC_ON_RIGHT].x + 52 : SP_CTL[SPC_IMG_BAR_LEFT].x + 30;
        int ay = SP_CTL[SPC_TXT_LEFT].y - 4;
        if (pj) {
            char nv[16];
            wsprintfA(nv, "Nv.%d", pj->nivel);
            sp_texto(ax, ay + 2, 0, 12, 1, nv, 0xFFE95A, 0x0B3D45);
            sp_texto(ax + 38, ay, 0, 14, 1, pj->apodo, 0xFFFFFF, 0x0B3D45);
        } else sp_texto(ax, ay, 0, 14, 1, "libre", 0xFFFFFF, 0x0B3D45);
        /* «Borrar»: sólo con personaje y no en el 1 (es la cuenta misma) — ⏳ el cartel: etapa 5 */
        if (pj && r != 1) {
            int c = k ? SPC_BTN_DEL1 : SPC_BTN_DEL0;
            sp_pieza(sp_estado(c), SP_CTL[c].x, SP_CTL[c].y);
            sp_texto(SP_CTL[c].x + SP_CTL[c].w / 2, SP_CTL[c].y + 6, 1, 13, 1, "Borrar", 0xFFFFFF, 0x20303A);
        }
    }
    sp_pieza(sp_estado(SPC_BTN_LEFT), SP_CTL[SPC_BTN_LEFT].x, SP_CTL[SPC_BTN_LEFT].y);
    sp_pieza(sp_estado(SPC_BTN_RIGHT), SP_CTL[SPC_BTN_RIGHT].x, SP_CTL[SPC_BTN_RIGHT].y);
    int boton = sp_pj(g_sp_elegida) ? SPC_BTN_JOIN : SPC_BTN_CREATE;
    sp_pieza(sp_estado(boton), SP_CTL[boton].x, SP_CTL[boton].y);
    LeaveCriticalSection(&g_sp_cs);
    if (g_sp_aviso[0])
        sp_texto(SP_W / 2, SP_H + 6, 1, 14, 1, g_sp_aviso, g_sp_aviso_mal ? 0xFFB4AD : 0xFFFFFF, 0x000000);
    if (g_sp_borrar) sp_armar_cartel();
}

static void sp_figura(BYTE *img, int x, int y)
{
    ((SP_F_POS)SPV(0x64D990))(img, 0, x, y);
    ((SP_F_COLOR)SPV(0x64E710))(img, 0, 0xFFFFFFFF);
    ((SP_F_DIBUJAR)SPV(0x64EE40))(img, 0, 0);
}

static void sp_elegir(int r);

/* ═══ 4 · LA ESCENA: el DIBUJO y la LÓGICA de cCharSelect (la vtable 0x87893C) ═══════════════════════════════════ */
typedef void (TCK *SP_F_ESCENA)(void *self);
static SP_F_ESCENA g_sp_entrar_real = NULL, g_sp_dibujar_real = NULL, g_sp_logica_real = NULL;

/* ★ ENTRAR a la escena (+0x04, 0x5802A0). anonimo03: el cartel de nuevos jugadores («Sé un Patinador con ritmo!», texto
 *   0x1C1, las 5.000 Rcoin) NO va con el selector. Lo abre la propia escena UNA vez, si su +0xED está en 0 (0x580753:
 *   `if (+0xED == 0) { +0xED = 1; Show(0x1C1, 0x20…) }`; repo Fuente CREACION.md) ⇒ se pone en 1 antes de entrar.
 *   ⚠ +0xED también lo mira el lobby (0x4C0740) junto con g_pUser+0x2EC («creó personaje en esta sesión»): sólo si
 *     CREÓ uno sale el «Bienvenido a R2Beat…» nativo, que es de la creación de verdad y se deja. */
static int g_sp_mostrado = 0;
static void TCK sp_entrar(void *self)
{
    if (g_sp_hola) *((BYTE *)self + 0xED) = 1;
    g_sp_entrar_real(self);
    /* ★ el selector, a la vista DESDE LA ENTRADA (anonimo03, 25-oct: la creación «se renderiza antes que el selector»: se
     *   prendía en el 1.er cuadro de LÓGICA, y un cuadro de DIBUJO llegaba antes). La creación se ve sólo tras CREAR. */
    if (g_sp_hola && !g_sp_mostrado) {
        g_sp_mostrado = 1;
        sp_elegir(g_sp_elegida);
        g_sp_visible = 1;
        apuntar("  [selector] ★ a la vista sobre la creación (desde la entrada de la escena)");
    }
}

/* ¿hay un cartel del juego abierto? (cMsgBox [0x9314B4] -> 0x413970; la creación lo mira igual antes del OK) */
typedef int (TCK *SP_F_I)(void *self);
static int sp_cartel_abierto(void)
{
    void *m = *(void **)SPV(0x9314B4);
    return m && ((SP_F_I)SPV(0x413970))(m) != 0;
}

static DWORD sp_firma(int frente)
{
    DWORD f = (DWORD)g_sp_elegida * 31u + (DWORD)g_sp_pagina * 7u + 0x9E3779B9u;
    if (frente) {
        f ^= (DWORD)(g_sp_sobre + 2) * 2654435761u ^ (DWORD)(g_sp_apretado + 3) * 40503u ^ (DWORD)g_sp_npj * 977u;
        for (const char *q = g_sp_aviso; *q; q++) f = f * 33u + (BYTE)*q;
        for (int i = 0; i < g_sp_npj; i++) f = f * 131u + g_sp_pj[i].usn + (DWORD)g_sp_pj[i].ranura;
        f ^= (DWORD)g_sp_aviso_mal << 30;
        for (int i = 1; i <= 4; i++) f = f * 7u + (DWORD)(g_sp_mu[i].listo + 2);
        f = f * 31u + (DWORD)g_sp_borrar * 7919u + (DWORD)g_sp_clave_n * 104729u + (DWORD)(g_sp_bsobre + 2) * 13u
            + (DWORD)(g_sp_bapretado + 2) * 17u + (DWORD)g_sp_pedido * 23u;
        for (const char *q = g_sp_borrar_error; *q; q++) f = f * 33u + (BYTE)*q;
    }
    return f | 1u;
}

/* ★ LA ISLA ANIMADA DETRÁS DEL SELECTOR (anonimo03, 25-oct: «la isla no se anima»). La isla de esta escena es SU modelo
 *   (+0xF8, rnr_ui_bg/front/front.md9) y la dibuja SU dibujo (0x57F640), con la cámara 10 y en perspectiva; el reloj
 *   lo avanza su lógica (0x57FD90), que ya corre siempre. Saltear el dibujo entero dejaba la pantalla SIN LIMPIAR: lo
 *   que se veía era el último cuadro, congelado. ⇒ Se hace sólo la parte de la isla, calcada de 0x57F640..0x57F6BD, y
 *   el cierre de 0x57F7D8 / 0x57F927 (el volcado 2D y el fin de escena). Sin la interfaz de la creación ni el muñeco. */
typedef void (TCK *SP_W_LIMPIAR)(void *w, int que, DWORD color);
typedef void (TCK *SP_W_NADA)(void *w);
typedef void (TCK *SP_W_PERSP)(void *w, float fov, float aspecto, float cerca, float lejos);
typedef void (TCK *SP_C_CAMARA)(void *c, int n);
typedef void (TCK *SP_G_MODELO)(void *g, void *modelo, int a, int b, int c);

static void sp_isla(void *self)
{
    void *w = *(void **)SPV(0x931498), *cam = *(void **)SPV(0x9314D4), *g = *(void **)SPV(0x93149C);
    void *isla = *(void **)((BYTE *)self + 0xF8);
    if (!w || !cam || !g) return;
    void **vt = *(void ***)w;
    ((SP_W_LIMPIAR)vt[0x0C / 4])(w, 3, 0xFF000000);
    ((SP_W_NADA)vt[0x28 / 4])(w);
    ((SP_C_CAMARA)SPV(0x644050))(cam, 10);
    ((SP_W_PERSP)vt[0x24 / 4])(w, *(float *)SPV(0x904E98), *(float *)((BYTE *)w + 0xC), 1.0f, *(float *)SPV(0x878B5C));
    if (isla) (*(SP_G_MODELO *)((BYTE *)g + 0x13C))(g, isla, 0xFF, 3, 1);
}

static void sp_cerrar_escena(void)
{
    void *w = *(void **)SPV(0x931498), *g = *(void **)SPV(0x93149C);
    if (g) ((SP_W_NADA)SPV(0x639780))(g);                  /* el volcado de la cola 2D (0x57F7DE) */
    if (w) ((SP_W_NADA)(*(void ***)w)[0x2C / 4])(w);      /* el fin de escena (0x57F92F) */
}

static void TCK sp_dibujar(void *self)
{
    if (!g_sp_visible) { g_sp_dibujar_real(self); return; }
    if (g_sp_img_estado == 0) sp_cargar();
    if (g_sp_img_estado != 1) { g_sp_dibujar_real(self); return; }
    g_sp_x0 = ((int)g_ancho - SP_W) / 2;
    g_sp_y0 = ((int)g_alto - SP_H) / 2 - SP_ARR;
    sp_isla(self);
    void *tf = sp_textura(g_sp_lz_fondo), *tr = sp_textura(g_sp_lz_frente);
    if (!tf || !tr) { sp_cerrar_escena(); return; }
    DWORD f = sp_firma(0);
    if (f != g_sp_firma_fondo || tf != g_sp_tex_fondo) { sp_armar_fondo(); if (sp_subir(tf)) { g_sp_firma_fondo = f; g_sp_tex_fondo = tf; } }
    f = sp_firma(1);
    if (f != g_sp_firma_frente || tr != g_sp_tex_frente) { sp_armar_frente(); if (sp_subir(tr)) { g_sp_firma_frente = f; g_sp_tex_frente = tr; } }
    sp_figura(g_sp_lz_fondo, g_sp_x0, g_sp_y0);
    void *g = *(void **)SPV(0x93149C);
    if (g) ((SP_W_NADA)SPV(0x639780))(g);                  /* el fondo ya, ANTES de los muñecos (como 0x57F7DE) */
    sp_mu_dibujar_tarjetas();
    sp_figura(g_sp_lz_frente, g_sp_x0, g_sp_y0);
    sp_cerrar_escena();
}

/* el FX del juego (banco fxSound.txt, 0x40B800 sobre [0x9314E4]); el 1 = el clic, como en el chino */
typedef void (TCK *SP_F_FX)(void *self, int n);
static void sp_fx(int n)
{
    void *s = *(void **)SPV(0x9314E4);
    if (s) ((SP_F_FX)SPV(0x40B800))(s, n);
}

/* ★ El FX 195 del chino en ENTRAR/CREAR: «Lets_start.mp3» (MEDIDO en su charselect: 0x2720769 / 0x27207F9, cortando
 *   antes lo que suena). El banco del 2013 no lo trae (salta de 194 a 196) y meterlo en rnr_script.pak toca el banco
 *   de todos ⇒ lo toca la dll, por MCI (winmm, cargada a mano), con el mp3 adentro (selector_sonido.h) escrito una vez
 *   a %TEMP%. Respeta [SOUND] EFFECT del Config.ini del juego (0 = mudo). */
typedef DWORD (__stdcall *SP_F_MCI)(const char *orden, char *ret, UINT n, HWND h);
static void sp_lets_start(void)
{
    static SP_F_MCI mci = NULL;
    static int listo = 0;
    char cfg[MAX_PATH];
    lstrcpyA(cfg, g_carpeta);
    lstrcatA(cfg, "Config.ini");
    if (!GetPrivateProfileIntA("SOUND", "EFFECT", 1, cfg)) return;
    if (!listo) {
        listo = -1;
        HMODULE w = LoadLibraryA("winmm.dll");
        mci = w ? (SP_F_MCI)GetProcAddress(w, "mciSendStringA") : NULL;
        char ruta[MAX_PATH], orden[MAX_PATH + 64];
        DWORD n = GetTempPathA(MAX_PATH - 32, ruta);
        if (!mci || !n) return;
        lstrcatA(ruta, "r2beat_lets_start.mp3");
        HANDLE f = CreateFileA(ruta, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
        if (f == INVALID_HANDLE_VALUE) return;
        DWORD escrito = 0;
        WriteFile(f, SP_LETS_START, sizeof(SP_LETS_START), &escrito, NULL);
        CloseHandle(f);
        wsprintfA(orden, "open \"%s\" type mpegvideo alias r2sp_lets", ruta);
        if (escrito == sizeof(SP_LETS_START) && mci(orden, NULL, 0, NULL) == 0) listo = 1;
    }
    if (listo == 1) mci("play r2sp_lets from 0", NULL, 0, NULL);
}

typedef DWORD (TCK *SP_F_U)(void *self);
typedef BYTE  (TCK *SP_F_B)(void *self);
typedef void  (__cdecl *SP_F_V)(void);

static void sp_aplicar_eleccion(void)
{
    if (!g_sp_res_ok) {
        lstrcpynA(g_sp_aviso, "No se pudo entrar con ese personaje. Prob\xE1 de nuevo.", sizeof(g_sp_aviso));
        g_sp_aviso_mal = 1;
        return;
    }
    BYTE *u = *(BYTE **)SPV(0x9314E0);                      /* g_pUser */
    void *red = *(void **)SPV(0x9314D0), *login = *(void **)SPV(0x9D43D8);
    if (!u || !login) { lstrcpynA(g_sp_aviso, "El juego no est\xE1 listo todav\xED" "a.", sizeof(g_sp_aviso)); g_sp_aviso_mal = 1; return; }
    sp_mu_soltar_todos();                                   /* las copias de las tarjetas ya no se ven */
    /* ★ EL INVENTARIO DEL JUEGO, VACÍO antes de la ficha del elegido (25-oct, medido con «Cambiar personaje»: leído de
     *   la memoria, jugadora_prueba traía los 89 suyos + el 304 de cuenta_admin —un consumible que el FF69 FIJA aparte— + las 4 prendas
     *   que pone la creación). La ficha lo vuelve a llenar ENTERO (g_pUser+0x164..+0x168, entradas de 16 B sin punteros).
     *   Sólo al ENTRAR con uno que existe: la creación usa esas prendas. */
    if (g_sp_res_tiene) {
        apuntar("  [selector]   inventario del juego: %u entradas -> 0 (llega la ficha del elegido)",
                (*(DWORD *)(u + 0x168) - *(DWORD *)(u + 0x164)) / 16);
        *(DWORD *)(u + 0x168) = *(DWORD *)(u + 0x164);
    }
    *(DWORD *)(u + 0x7C) = g_sp_res_usn;
    *(unsigned long long *)(u + 0x1C8) = g_sp_res_vcode;
    if (red) ((SP_F_ESCENA)SPV(0x67C6A0))(red);             /* ⚠ sin esto el OnFF01 no pide la lista (0x67C860) */
    BYTE ok = ((SP_F_B)SPV(0x5C4220))(login);
    apuntar("  [selector] ★ reconecto con usn %u (%s): %s", g_sp_res_usn, g_sp_res_tiene ? "ENTRAR" : "CREAR",
            ok ? "conectando" : "⛔ no conectó");
    if (g_sp_res_tiene) { g_sp_esperando_pj = 1; g_sp_espera_cuadros = 0; }
    else g_sp_visible = 0;                                  /* CREAR: queda la creación nativa */
}

static void TCK sp_logica(void *self)
{
    /* la respuesta del hilo de la red, aplicada en ESTE hilo (el del juego) */
    LONG listo = InterlockedExchange(&g_sp_listo, SPP_NADA);
    if (listo == SPP_ELEGIR) sp_aplicar_eleccion();
    if (listo == SPP_BORRAR) {
        if (g_sp_res_borrar_ok) {
            int r = g_sp_borrar;
            g_sp_borrar = 0;
            sp_elegir(r);
            wsprintfA(g_sp_aviso, "%s ya no est\xE1 en tu cuenta.", g_sp_borrado_apodo);
            g_sp_aviso_mal = 0;
        } else lstrcpynA(g_sp_borrar_error, g_sp_res_msg[0] ? g_sp_res_msg : "No se pudo borrar.", sizeof(g_sp_borrar_error));
    }
    if (g_sp_esperando_pj) {
        BYTE *u = *(BYTE **)SPV(0x9314E0);
        if (u && ((SP_F_U)SPV(0x485F90))(u) != 0) {         /* llegó la ficha del elegido */
            g_sp_esperando_pj = 0;
            g_sp_visible = 0;
            apuntar("  [selector] ★ el personaje llegó (%d cuadros): a la bienvenida", g_sp_espera_cuadros);
            ((SP_F_V)SPV(0x5C5E00))();
            return;
        }
        if (++g_sp_espera_cuadros == 60 * 20) {
            lstrcpynA(g_sp_aviso, "El servidor no contesta. Prob\xE1 de nuevo.", sizeof(g_sp_aviso));
            g_sp_aviso_mal = 1;
            g_sp_esperando_pj = 0;
        }
        return;
    }
    /* ★ La lógica NATIVA corre SIEMPRE (anonimo03, 25-oct: «la isla no se anima» con el selector): ahí avanza el reloj
     *   de la escena y de los modelos (0x57FD90). Lo que hay que evitar es que se TOQUE la creación de abajo, y eso lo
     *   hace selector_mensaje: el mouse y el teclado son nuestros mientras el selector está a la vista. */
    g_sp_logica_real(self);
    if (g_sp_visible) sp_mu_logica();
}

/* ═══ 5 · EL MOUSE (lo llama el WndProc de d3d9_proxy.c ANTES que al juego) ════════════════════════════════════ */
static int sp_dentro(int x, int y, const SP_CONTROL *c, int dx)
{
    return x >= c->x + dx && x < c->x + dx + c->w && y >= c->y && y < c->y + c->h;
}

static int sp_control_en(int x, int y)                     /* (x, y) en coordenadas del cuadro */
{
    static const int BOTONES[] = { SPC_BTN_LEFT, SPC_BTN_RIGHT, SPC_BTN_DEL0, SPC_BTN_DEL1, SPC_ON_LEFT, SPC_ON_RIGHT,
                                   SPC_PAGE_0, SPC_PAGE_1 };
    int boton = sp_pj(g_sp_elegida) ? SPC_BTN_JOIN : SPC_BTN_CREATE;
    if (sp_dentro(x, y, &SP_CTL[boton], 0)) return boton;
    for (int i = 0; i < (int)(sizeof(BOTONES) / sizeof(BOTONES[0])); i++) {
        int c = BOTONES[i];
        if ((c == SPC_BTN_DEL0 || c == SPC_BTN_DEL1)) {
            int r = sp_de_la_pagina(c == SPC_BTN_DEL1);
            if (!sp_pj(r) || r == 1) continue;
        }
        if (sp_dentro(x, y, &SP_CTL[c], 0)) return c;
    }
    /* las tarjetas enteras (hasta la barra de abajo) */
    for (int k = 0; k < 2; k++) {
        const SP_CONTROL *c = &SP_CTL[k ? SPC_CHAR_RIGHT : SPC_CHAR_LEFT];
        if (x >= c->x && x < c->x + c->w && y >= c->y && y < SP_CTL[SPC_IMG_BAR_LEFT].y) return k ? SPC_CHAR_RIGHT : SPC_CHAR_LEFT;
    }
    return -1;
}

static void sp_elegir(int r)
{
    g_sp_elegida = r;
    g_sp_pagina = (r - 1) >> 1;
    if (sp_pj(r)) g_sp_aviso[0] = 0;
    else wsprintfA(g_sp_aviso, "El casillero %d est\xE1 libre: \xAB" "Crear\xBB para hacer un personaje.", r);
    g_sp_aviso_mal = 0;
}

static void sp_clic(int c)
{
    if (g_sp_esperando_pj || g_sp_pedido != SPP_NADA) return;      /* ya hay algo en curso */
    if (c == SPC_BTN_JOIN) sp_lets_start();                         /* el FX 195 del chino: SÓLO al entrar (anonimo03) */
    else sp_fx(1);
    switch (c) {
    case SPC_CHAR_LEFT: case SPC_ON_LEFT: sp_elegir(sp_de_la_pagina(0)); break;
    case SPC_CHAR_RIGHT: case SPC_ON_RIGHT: sp_elegir(sp_de_la_pagina(1)); break;
    case SPC_PAGE_0: g_sp_pagina = 0; sp_elegir(1 + (g_sp_elegida - 1) % 2); break;
    case SPC_PAGE_1: g_sp_pagina = 1; sp_elegir(3 + (g_sp_elegida - 1) % 2); break;
    case SPC_BTN_LEFT: case SPC_BTN_RIGHT: sp_elegir(2 * (1 - g_sp_pagina) + (g_sp_elegida - 1) % 2 + 1); break;
    case SPC_BTN_JOIN: case SPC_BTN_CREATE:
        g_sp_ped_ranura = g_sp_elegida;
        g_sp_ped_crear = c == SPC_BTN_CREATE;
        g_sp_res_tiene = c == SPC_BTN_JOIN;
        lstrcpynA(g_sp_aviso, c == SPC_BTN_JOIN ? "Entrando\x85" : "Preparando la creaci\xF3n\x85", sizeof(g_sp_aviso));
        g_sp_aviso_mal = 0;
        sp_pedir_al_hilo(SPP_ELEGIR);
        break;
    case SPC_BTN_DEL0: case SPC_BTN_DEL1: {
        int r = sp_de_la_pagina(c == SPC_BTN_DEL1);
        const SP_PJ *pj = sp_pj(r);
        if (!pj || r == 1) break;
        g_sp_borrar = r;
        lstrcpynA(g_sp_borrado_apodo, pj->apodo, sizeof(g_sp_borrado_apodo));
        g_sp_clave_n = 0;
        g_sp_clave[0] = 0;
        g_sp_borrar_error[0] = 0;
        g_sp_bsobre = g_sp_bapretado = -1;
        break;
    }
    }
}

static void sp_borrar_confirmar(void)
{
    if (g_sp_pedido != SPP_NADA) return;
    if (!g_sp_clave_n) { lstrcpynA(g_sp_borrar_error, "Escrib\xED tu contrase\xF1" "a.", sizeof(g_sp_borrar_error)); return; }
    g_sp_clave[g_sp_clave_n] = 0;
    sp_sha256_hex(g_sp_clave, g_sp_ped_hash);
    SecureZeroMemory(g_sp_clave, sizeof(g_sp_clave));            /* la contraseña en claro no se queda en memoria */
    g_sp_clave_n = 0;
    g_sp_borrar_error[0] = 0;
    sp_pedir_al_hilo(SPP_BORRAR);
}

static void sp_borrar_cerrar(void)
{
    SecureZeroMemory(g_sp_clave, sizeof(g_sp_clave));
    g_sp_clave_n = 0;
    g_sp_borrar = 0;
}

static int sp_cartel_mensaje(HWND h, UINT msg, WPARAM wp, LPARAM lp)
{
    if (msg == WM_CHAR) {
        if (wp == 27) { sp_fx(1); sp_borrar_cerrar(); }
        else if (wp == 13) { sp_fx(1); sp_borrar_confirmar(); }
        else if (wp == 8) { if (g_sp_clave_n > 0) g_sp_clave[--g_sp_clave_n] = 0; }
        else if (wp >= 32 && wp < 127 && g_sp_clave_n < 32) { g_sp_clave[g_sp_clave_n++] = (char)wp; g_sp_clave[g_sp_clave_n] = 0; g_sp_borrar_error[0] = 0; }
        return 1;
    }
    if (msg == WM_KEYDOWN || msg == WM_KEYUP) return 1;
    if (msg != WM_MOUSEMOVE && msg != WM_LBUTTONDOWN && msg != WM_LBUTTONUP && msg != WM_LBUTTONDBLCLK
        && msg != WM_RBUTTONDOWN && msg != WM_RBUTTONUP && msg != WM_MOUSEWHEEL) return 0;
    int x, y;
    if (!t5_a_juego(h, lp, msg == WM_MOUSEWHEEL, &x, &y)) return 1;
    x -= g_sp_x0 + sp_cx();
    y -= g_sp_y0 + SP_ARR + sp_cy();
    int c = sp_dentro(x, y, &SP_BORRAR[SPB_BTN_OK], 0) ? SPB_BTN_OK : sp_dentro(x, y, &SP_BORRAR[SPB_BTN_NO], 0) ? SPB_BTN_NO : -1;
    g_sp_bsobre = c;
    if (msg == WM_LBUTTONDOWN || msg == WM_LBUTTONDBLCLK) g_sp_bapretado = c;
    if (msg == WM_LBUTTONUP) {
        if (c >= 0 && c == g_sp_bapretado) {
            sp_fx(1);
            if (c == SPB_BTN_OK) sp_borrar_confirmar(); else sp_borrar_cerrar();
        }
        g_sp_bapretado = -1;
    }
    return 1;
}

static int selector_mensaje(HWND h, UINT msg, WPARAM wp, LPARAM lp)
{
    if (!g_sp_activo || !g_sp_visible) return 0;
    if (sp_cartel_abierto()) { g_sp_sobre = g_sp_apretado = -1; return 0; }   /* un cartel del juego: los clics son suyos */
    if (g_sp_borrar) return sp_cartel_mensaje(h, msg, wp, lp);               /* nuestro cartel de borrar */
    /* el teclado: que la creación de abajo no reciba ni el Enter (validaría un apodo vacío) ni letras para su caja.
     *   ⚠ WM_SYSKEY* NO: el alt+enter lo tiene que ver el juego (es él quien rehace la pantalla) */
    if (msg == WM_KEYDOWN || msg == WM_KEYUP || msg == WM_CHAR) return 1;
    if (msg != WM_MOUSEMOVE && msg != WM_LBUTTONDOWN && msg != WM_LBUTTONUP && msg != WM_LBUTTONDBLCLK
        && msg != WM_RBUTTONDOWN && msg != WM_RBUTTONUP && msg != WM_MOUSEWHEEL) return 0;
    int x, y;
    if (!t5_a_juego(h, lp, msg == WM_MOUSEWHEEL, &x, &y)) return 1;
    int c = sp_control_en(x - g_sp_x0, y - g_sp_y0 - SP_ARR);
    g_sp_sobre = c;
    if (msg == WM_LBUTTONDOWN || msg == WM_LBUTTONDBLCLK) g_sp_apretado = c;
    if (msg == WM_LBUTTONUP) {
        if (c >= 0 && c == g_sp_apretado) sp_clic(c);
        g_sp_apretado = -1;
    }
    return 1;                                               /* con el selector a la vista, la creación no se toca */
}

static int selector_quiere_ventana(void) { return g_sp_activo; }

/* ═══ 6 · ARRANQUE ═════════════════════════════════════════════════════════════════════════════════════════════ */
static int sp_linea_de_comandos(void)
{
    /* <exe> <USN> <vcode_decimal> <puerto> test:<ip>  (el contrato de launcher2013.py) */
    const char *s = GetCommandLineA();
    char t[5][128];
    int n = 0;
    while (*s && n < 5) {
        while (*s == ' ') s++;
        if (!*s) break;
        int q = *s == '"', k = 0;
        if (q) s++;
        while (*s && (q ? *s != '"' : *s != ' ')) { if (k < 127) t[n][k++] = *s; s++; }
        if (q && *s == '"') s++;
        t[n++][k] = 0;
    }
    if (n < 5 || lstrlenA(t[4]) < 6 || t[4][0] != 't' || t[4][4] != ':') return 0;
    g_sp_usn = 0;
    for (const char *p = t[1]; *p >= '0' && *p <= '9'; p++) g_sp_usn = g_sp_usn * 10 + (DWORD)(*p - '0');
    g_sp_vcode = 0;
    for (const char *p = t[2]; *p >= '0' && *p <= '9'; p++) g_sp_vcode = g_sp_vcode * 10 + (unsigned)(*p - '0');
    g_sp_puerto = 0;
    for (const char *p = t[3]; *p >= '0' && *p <= '9'; p++) g_sp_puerto = g_sp_puerto * 10 + (*p - '0');
    if (g_sp_puerto <= 0 || g_sp_puerto > 65535) g_sp_puerto = 48004;
    lstrcpynA(g_sp_ip, t[4] + 5, sizeof(g_sp_ip));
    return g_sp_usn && g_sp_vcode && g_sp_ip[0];
}

/* ═══ 7 · «CAMBIAR PERSONAJE» (anonimo03, 25-oct: «un tercer botón en el medio, mismo diseño, fuente y textura») ════════
 *   El botón es del .rui (`Button_cambiar_pj`, herramientas/boton_cambiar_personaje_pak.py). La ventana es la de
 *   «Misión de hoy» = la de SALIR (cEventTodayMission, [0x9314B0]); su lógica 0x480F90 la llama el lobby en 0x4C036F y
 *   reconoce sus botones POR NOMBRE (0x688650 sobre el control tocado [0x9313BC], con el clic en [0x9313B4] & 2): el
 *   nuestro no lo conoce nadie, y lo atendemos acá, después de la original. */
typedef void (TCK *SP_F_HOY)(void *hoy);
typedef BYTE (TCK *SP_F_ES)(void *ctl, const char *nombre);
static int g_sp_vol_estado = 0;                     /* 0 nada · 1 esperando al server · 2 relanzando */
static int g_sp_cambiar_relanzar = 0;
static int g_sp_limpiar_lic = 1;                    /* [selector] limpiar_licencias (para medir) */               /* [selector] cambiar_relanzar=1: el camino de respaldo (relanzar) */

/* ★ EN EL MISMO PROCESO (anonimo03, 25-oct: «que el botón vuelva a cargar la escena de seleccionar personaje y nuestra
 *   conexión no pierda la sesión de la cuenta; si volvemos a esa escena el juego limpiará, o al menos probemos»):
 *     la sesión de la CUENTA en g_pUser (+0x7C / +0x1C8) y en la nuestra (la LISTA y el ELEGIR la usan);
 *     la lista de personajes del juego VACÍA (g_pUser+0xC8..+0xCC: la lee el «llegó el elegido», 0x485F90);
 *     la red del lobby cerrada (0x67C6A0, como en ENTRAR) y la escena de crear: 0x49A4D0 (la del propio juego,
 *     [0x9314CC]+0xB1D4). Ahí la entrada de cCharSelect vuelve a mostrar el selector; ENTRAR sigue como siempre. */
static void sp_volver_al_selector(void)
{
    BYTE *u = *(BYTE **)SPV(0x9314E0);
    void *red = *(void **)SPV(0x9314D0), *escenas = *(void **)SPV(0x9314CC);
    if (!u || !escenas) { apuntar("  [selector] ⛔ VOLVER: el juego no está listo"); return; }
    apuntar("  [selector] ★ VOLVER al selector: lista de personajes del juego %u -> 0, sesión de la cuenta %u",
            (*(DWORD *)(u + 0xCC) - *(DWORD *)(u + 0xC8)) / 0x30, g_sp_vol_usn);
    *(DWORD *)(u + 0x7C) = g_sp_vol_usn;
    *(unsigned long long *)(u + 0x1C8) = g_sp_vol_vcode;
    g_sp_usn = g_sp_vol_usn;
    g_sp_vcode = g_sp_vol_vcode;
    g_sp_res_ok = 0;
    *(DWORD *)(u + 0xCC) = *(DWORD *)(u + 0xC8);            /* vacía (el sPersonaje es de 0x30 B, sin destructor) */
    /* ★ y el INVENTARIO del que se va (anonimo03: «el nuevo char heredó inventario» — con CREAR no se vaciaba): desde acá
     *   queda sólo lo que ponga la escena de crear, como una cuenta recién hecha. ENTRAR lo vacía otra vez. */
    apuntar("  [selector]   inventario del que se va: %u entradas -> 0", (*(DWORD *)(u + 0x168) - *(DWORD *)(u + 0x164)) / 16);
    *(DWORD *)(u + 0x168) = *(DWORD *)(u + 0x164);
    /* ★ y las LICENCIAS (anonimo03: «ya casi, sólo faltó la sección de licencia»): los registros de g_pUser+0x3C..+0x40
     *   (0x7C B cada uno, uno por licencia/misión) llevan en el byte +3 el bit 0 que prende 0x4884D0 (la licencia) y el
     *   bit 1 que prende 0x4885D0. Nada los apaga: el login del que entra (los nibbles del campo E, 0x48AC20) y sus
     *   misiones (FF125) prenden sólo los suyos. */
    int prendidas = 0;
    for (BYTE *r = *(BYTE **)(u + 0x3C), *fin = *(BYTE **)(u + 0x40); r && r < fin; r += 0x7C)
        if (r[3] & 3) { if (g_sp_limpiar_lic) r[3] &= (BYTE)~3; prendidas++; }
    apuntar("  [selector]   licencias del que se va: %d %s", prendidas, g_sp_limpiar_lic ? "apagadas" : "(quedan: limpiar_licencias=0)");
    if (red) ((SP_F_ESCENA)SPV(0x67C6A0))(red);
    sp_mu_soltar_todos();
    g_sp_mostrado = 0;
    g_sp_aviso[0] = 0;
    g_sp_pagina = 0;
    sp_pedir_al_hilo(SPP_LISTA);
    ((SP_F_ESCENA)SPV(0x49A4D0))(escenas);
}

static void sp_relanzar(void)
{
    WCHAR exe[MAX_PATH], dir[MAX_PATH], cmd[2048], ip[64];
    GetModuleFileNameW(NULL, exe, MAX_PATH);
    lstrcpyW(dir, exe);
    for (int i = lstrlenW(dir) - 1; i >= 0; i--) if (dir[i] == L'\\') { dir[i] = 0; break; }
    MultiByteToWideChar(CP_ACP, 0, g_sp_ip, -1, ip, 64);
    /* espera a que ESTE proceso termine (el juego no deja dos abiertos) y lo vuelve a abrir con la sesión de la cuenta;
     *   las comillas simples de la ruta se doblan para PowerShell */
    WCHAR exe_ps[MAX_PATH * 2], dir_ps[MAX_PATH * 2];
    int k = 0;
    for (const WCHAR *q = exe; *q && k < MAX_PATH * 2 - 2; q++) { if (*q == L'\'') exe_ps[k++] = L'\''; exe_ps[k++] = *q; }
    exe_ps[k] = 0;
    k = 0;
    for (const WCHAR *q = dir; *q && k < MAX_PATH * 2 - 2; q++) { if (*q == L'\'') dir_ps[k++] = L'\''; dir_ps[k++] = *q; }
    dir_ps[k] = 0;
    WCHAR vc[24];                                           /* el vcode en decimal (wsprintf no siempre sabe %I64u) */
    int nv = 0;
    unsigned long long v = g_sp_vol_vcode;
    do { vc[nv++] = (WCHAR)(L'0' + (int)(v % 10)); v /= 10; } while (v && nv < 23);
    for (int i = 0; i < nv / 2; i++) { WCHAR t = vc[i]; vc[i] = vc[nv - 1 - i]; vc[nv - 1 - i] = t; }
    vc[nv] = 0;
    wsprintfW(cmd, L"powershell.exe -NoProfile -WindowStyle Hidden -Command \"Wait-Process -Id %lu -ErrorAction "
                   L"SilentlyContinue; Start-Process -FilePath '%s' -WorkingDirectory '%s' -ArgumentList '%lu %s %d test:%s'\"",
              GetCurrentProcessId(), exe_ps, dir_ps, g_sp_vol_usn, vc, g_sp_puerto, ip);
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    if (!CreateProcessW(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, dir, &si, &pi)) {
        apuntar("  [selector] ⛔ no pude lanzar el relanzador (%lu)", GetLastError());
        g_sp_vol_estado = 0;
        return;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    apuntar("  [selector] ★ CAMBIAR PERSONAJE: el juego se cierra y vuelve a abrir con la cuenta (usn %u)", g_sp_vol_usn);
    void *escenas = *(void **)SPV(0x9314CC);
    if (escenas) ((SP_F_ESCENA)SPV(0x4946B0))(escenas);     /* la salida del juego, la de «Salir del juego» */
}

static void TCK sp_hoy_logica(void *hoy)
{
    ((SP_F_HOY)SPV(0x480F90))(hoy);
    if (g_sp_vol_estado == 1) {
        LONG listo = InterlockedCompareExchange(&g_sp_listo, SPP_NADA, SPP_VOLVER);
        if (listo == SPP_VOLVER) {
            if (!g_sp_vol_ok) g_sp_vol_estado = 0;
            else if (g_sp_cambiar_relanzar) { g_sp_vol_estado = 2; sp_relanzar(); }
            else { g_sp_vol_estado = 0; sp_volver_al_selector(); }
        }
        return;
    }
    if (g_sp_vol_estado || !g_sp_hola) return;
    BYTE *clic = SPV(0x9313B4);
    void *ctl = *(void **)SPV(0x9313BC);
    if (!(*clic & 2) || !ctl || !((SP_F_ES)SPV(0x688650))(ctl, "Button_cambiar_pj")) return;
    *clic &= (BYTE)~2;                                      /* el clic ya se atendió */
    sp_fx(1);
    ((SP_F_HOY)SPV(0x4808C0))(hoy);                         /* cierra la ventana (lo de «Regreso al juego») */
    g_sp_vol_estado = 1;
    apuntar("  [selector] ★ «Cambiar personaje»: pido la sesión de la cuenta (FFFA)");
    sp_pedir_al_hilo(SPP_VOLVER);
}

static void sp_enganchar_cambiar(void)
{
    BYTE *c = SPV(0x4C036F);
    if (c[0] != 0xE8 || (DWORD)(c + 5 + *(int *)(c + 1)) != (DWORD)SPV(0x480F90)) {
        apuntar("  [selector] ⛔ 0x4C036F no es la llamada a la ventana de salida: sin «Cambiar personaje»");
        return;
    }
    int rel = (int)((DWORD)sp_hoy_logica - (DWORD)(c + 5));
    if (sp_escribir(0x4C0370, &rel, 4)) apuntar("  [selector] ★ «Cambiar personaje» enganchado (0x4C036F)");
}

static void selector_iniciar(void)
{
    g_sp_base = (BYTE *)GetModuleHandleA(NULL);
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("selector", "activo", 1, ini)) { apuntar("  [selector] apagado ([selector] activo=0)"); return; }
    g_sp_mu_dy = (int)GetPrivateProfileIntA("selector", "muneco_dy", g_sp_mu_dy, ini);
    g_sp_pet_activo = (int)GetPrivateProfileIntA("selector", "mascota", 1, ini);
    g_sp_alas = (int)GetPrivateProfileIntA("selector", "alas", 1, ini);
    g_sp_caras = (int)GetPrivateProfileIntA("selector", "caras", 1, ini);
    g_sp_cambiar_relanzar = (int)GetPrivateProfileIntA("selector", "cambiar_relanzar", 0, ini);
    g_sp_limpiar_lic = (int)GetPrivateProfileIntA("selector", "limpiar_licencias", 1, ini);
    g_sp_pet_x = (float)(int)GetPrivateProfileIntA("selector", "mascota_x", (int)g_sp_pet_x, ini);
    g_sp_pet_y = (float)(int)GetPrivateProfileIntA("selector", "mascota_y", (int)g_sp_pet_y, ini);
    g_sp_pet_z = (float)(int)GetPrivateProfileIntA("selector", "mascota_z", (int)g_sp_pet_z, ini);
    g_sp_pet_escala = (float)(int)GetPrivateProfileIntA("selector", "mascota_escala", 75, ini) / 100.0f;
    g_sp_pet_vel = (float)(int)GetPrivateProfileIntA("selector", "mascota_vel", 10, ini) / 10.0f;
    g_sp_pet_paso = (int)GetPrivateProfileIntA("selector", "mascota_paso", 1, ini);
    g_sp_pet_dibujo = (int)GetPrivateProfileIntA("selector", "mascota_dibujo", 1, ini);
    if (!sp_linea_de_comandos()) { apuntar("  [selector] sin sesión en la línea de comandos: sin selector"); return; }
    /* la vtable de cCharSelect: tiene que ser la de siempre */
    DWORD *vt = (DWORD *)SPV(0x87893C);
    if (vt[1] != (DWORD)SPV(0x5802A0) || vt[3] != (DWORD)SPV(0x57F640) || vt[6] != (DWORD)SPV(0x580880)) {
        apuntar("  [selector] ⛔ la vtable de cCharSelect no es la esperada (%08X %08X): no se toca", vt[3], vt[6]);
        return;
    }
    g_sp_entrar_real = (SP_F_ESCENA)vt[1];
    g_sp_dibujar_real = (SP_F_ESCENA)vt[3];
    g_sp_logica_real = (SP_F_ESCENA)vt[6];
    DWORD e = (DWORD)sp_entrar, d = (DWORD)sp_dibujar, l = (DWORD)sp_logica;
    if (!sp_escribir(0x87893C + 0x04, &e, 4) || !sp_escribir(0x87893C + 0x0C, &d, 4) || !sp_escribir(0x87893C + 0x18, &l, 4)) {
        apuntar("  [selector] ⛔ VirtualProtect falló: sin selector");
        return;
    }
    InitializeCriticalSection(&g_sp_cs);
    g_sp_evento = CreateEventA(NULL, FALSE, FALSE, NULL);
    g_sp_activo = 1;
    CreateThread(NULL, 0, sp_hilo, NULL, 0, NULL);
    sp_enganchar_cambiar();
    apuntar("  [selector] ★ enganchado (cCharSelect entrada + dibujo + lógica): usn %u, server %s:%d", g_sp_usn, g_sp_ip, g_sp_puerto);
}
