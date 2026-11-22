/* isla_fx.c — la «capa 4» de la isla del lobby: NUESTROS sombreadores (mar vivo, aurora, luces que iluminan, nieve que
 *              destella, brillo suave) sobre la isla que el juego dibuja sin ellos.  (17-nov-2026, la isla «Fiesta polar»)
 *
 * ⛔ APAGADO DE FÁBRICA. Sin `[isla_fx] activo=1` (o `sonda=1`) en d3d9_proxy.ini este módulo no engancha NADA: ni la
 *   carga de texturas, ni el dibujo. Y a prueba de fallas: cualquier cosa que no sea exactamente lo medido (bytes del
 *   exe, capacidades de la tarjeta, forma del vértice, estados de la etapa 0, un sombreador que no se crea) ⇒ ese dibujo
 *   va como siempre y el log dice por qué. anonimo03: «sin romper el cliente».
 *
 * ★ LO MEDIDO en R2Beat/R2Beat.exe (sólo lectura, pefile + capstone, 17-nov; detalle en
 *   _trabajo/navidad/equipo/sombreadores/MEDICION.md):
 *   · TODAS las texturas de los modelos se cargan por el administrador de texturas 0x6427E0 (en [0x931570]): recibe el
 *     nombre ("rnr_ui_bg/front/Nocull_water.tga" = carpeta del .md9 + nombre del material, armado en 0x66B8AC), le
 *     cambia la extensión por "dds" (0x8779A4 "." + 0x878FF4 "dds"), lo busca en su mapa y, si es nuevo, crea el objeto
 *     textura (0x6426C0) y llama a 0x641620 = CARGAR(objeto, &nombre, memoria) — thiscall, `ret 8`, al = 1 si cargó.
 *   · 0x641620 decodifica el archivo (dds/tga/bmp/gif) y crea la textura con el envoltorio del dispositivo
 *     ([0x931498], método +0xCC = 0x6494A0 → IDirect3DDevice9::CreateTexture(an, al, NIVELES = 1, 0, formato,
 *     D3DPOOL_MANAGED)), copia los píxeles nivel por nivel (LockRect / memcpy / UnlockRect) y la guarda en un vector.
 *   · El objeto textura: el NOMBRE en +0x04 (std::string de VC9: texto adentro si la capacidad [+0x18] < 16, si no un
 *     puntero en +0x04; largo en +0x14) y las texturas en el vector de +0x30 (primero [+0x3C], último [+0x40]; más de
 *     una sólo en los .gif animados).
 *   ⇒ EL GANCHO DE IDENTIFICACIÓN: un trampolín en la ENTRADA de 0x641620 (6A FF 68 F6 C7 86 00 = push −1 · push
 *     0x86C7F6, 7 bytes que se copian enteros). Al volver con al = 1 se lee el nombre y la textura; si el nombre está en
 *     el perfil, la textura se anota: en una tabla propia (puntero → entrada) y ADENTRO de la textura misma
 *     (SetPrivateData con un GUID nuestro): si Direct3D la libera y otra textura cae en la misma dirección, la marca no
 *     la acompaña y no se le pone un sombreador ajeno.
 *   · El dibujo: el envoltorio llama a IDirect3DDevice9 por [[0x931498]+0xC0] (SetTexture +0x104, DrawPrimitive +0x144,
 *     DrawIndexedPrimitive +0x148, los «UP» +0x14C/+0x150). sala_alfa.c (02-nov) ya engancha 81/82 de ESE dispositivo
 *     (tarde, con un vigía, y re-enganchando cuando Direct3D pisa la tabla). En cada dibujo, GetTexture(0) dice qué
 *     textura está puesta ⇒ la tabla dice si es nuestra. (No se engancha SetTexture: un gancho menos.)
 *
 * ★ EL DIBUJO CON NUESTROS SOMBREADORES (sólo en las texturas marcadas, y sólo si TODO esto se cumple):
 *     1. el juego no tiene sombreadores puestos (GetVertexShader y GetPixelShader = NULL: es fixed-function);
 *     2. el vértice es uno de los tres que sabemos dibujar (FVF 0x112 · 0x152 · 0x102 — el de la isla es 0x112);
 *     3. la etapa 0 hace algo que sabemos copiar (fx_etapa0: textura sola, o × TEXTUREFACTOR, o × el color del
 *        vértice sin luces) — así el color de partida es EXACTAMENTE el del juego;
 *   se ponen nuestro sombreador de vértices (vs_3_0) y el de píxel del perfil (ps_3_0) con sus constantes, se dibuja con
 *   la función de Direct3D, y se vuelven a poner los dos en NULL (como estaban: lo dice el punto 1). Las constantes no
 *   molestan al fixed-function. Los estados de muestreo, la mezcla y la prueba de alfa son los del juego: no se tocan.
 *   Si el dibujo con sombreadores falla, se repite sin ellos (y a los 50 fallos la capa se apaga sola).
 *   ⚠ Direct3D (el de Microsoft) REESCRIBE las entradas 81/82 de su tabla según el estado (lo midió sala_alfa). Si al
 *     poner los sombreadores la entrada cambió, se llama a la NUEVA (la que Direct3D quiere para ese estado) y, al
 *     sacarlos, se vuelve a poner el gancho en el lugar con el original nuevo (fx_destino / fx_reponer). Lo cuenta la
 *     sonda: si pasa en cada dibujo, hay que saberlo.
 *
 * ★ CONVIVIR CON sala_alfa.c (incluido ANTES que éste): sala_alfa es dueño de las entradas 81/82. Si está prendido, este
 *   módulo NO las pisa: se mete en SU cadena (g_sa_tablas[i].real81/82 = nuestro gancho, y el original de Direct3D
 *   queda en nuestra tabla). Así el orden es sala_alfa (arregla el alfa) → isla_fx (sombreadores) → Direct3D, y ninguno
 *   envuelve al otro dos veces. Si sala_alfa está apagado, se enganchan las entradas directamente, con su misma lógica.
 *
 * ★ EL BRILLO (bloom): lo claro del cuadro se difumina y se suma. Va al TERMINAR LA ISLA: en el primer dibujo 2D
 *   (vértice ya transformado, XYZRHW, o proyección ortográfica) después de un dibujo de la isla, ANTES de dibujarlo —
 *   así los carteles y textos del lobby no brillan. Copia el cuadro (StretchRect, que además resuelve el MSAA), lo baja a
 *   1/4, lo desenfoca y lo suma. Guarda y repone TODO el estado con un bloque de estados (D3DSBT_ALL) + el destino y el
 *   z de antes. Sus texturas son D3DPOOL_DEFAULT ⇒ se sueltan antes de cada Reset (gancho en 16 de la misma tabla).
 *
 * ★ DÍA Y NOCHE: la hora la decidió isla_hora.c al arrancar (g_ih_esconder = 1 de noche); el perfil tiene perillas de
 *   día y de noche, y el cielo tiene dos sombreadores (aurora / sol con halo).
 *
 * ★ EL INI (d3d9_proxy.ini):
 *       [isla_fx]
 *       activo=0            ; ⛔ 1 = prende la capa 4
 *       sonda=0             ; 1 = sólo ANOTA en el log (qué texturas carga, cómo se dibuja cada una, cuántos dibujos):
 *                           ;     la medición para la sesión con el juego. Con activo=0 no cambia ni un píxel.
 *       fps=0               ; ★ turno 26: 1 = una línea por segundo con los CUADROS POR SEGUNDO reales (Present del
 *                           ;     dispositivo que dibuja: medio y peor tiempo de cuadro). Con sonda=1 va siempre. Con
 *                           ;     activo=0 mide la referencia SIN efectos (sólo se engancha para contar)
 *       perfil=isla_fx.ini  ; el perfil, al lado de la dll (herramientas/dll_d3d9/sombreadores/perfil.ini)
 *       hora=               ; vacío = la de isla_hora · dia · noche (para probar)
 *       mar=1  cielo=1  luces=1  nieve=1  emisivo=1  brillo=1     ; cada efecto por separado
 *       calidad=auto        ; ★ turno 2 / 27: auto (de fábrica: mide y baja sola, ver fx_auto_segundo) · alta · media ·
 *                           ;     baja (el mar liviano, 8 luces, la aurora quieta, sin brillo: PCs lentas)
 *       auto_umbral=50  auto_umbral_mar=45  auto_espera=5  auto_medir=5  auto_olvidar=0   ; ★ turno 27
 *       cercano=100         ; ★ turno 4: el near de la isla (z-fighting). 0 = el del juego (1)
 *       cercano_ojo=3000    ; ★ turno 4: sólo si la cámara está más lejos que esto del origen (no en primer plano)
 *
 * ★ TURNO 2 (17-nov, después de verlo en el juego: 60 cuadros sostenidos con todo prendido):
 *   · [brillo] excluir = texturas que NO brillan (la estrella/el sol/la luna del cartel se quemaban). Modo DIFERIR: su
 *     dibujo (81/82) se guarda con TODO su estado (bloque D3DSBT_ALL) y se hace después del brillo, encima, con el z de
 *     la escena; si en el cuadro no hubo brillo, se hace igual al presentar. Modo TOPE: su color se achica bajo el umbral.
 *   · perillas por textura: la sección «[<sombreador>@<textura>]» pisa las del sombreador para esa textura sola.
 *   · calidad: el sombreador de 16 / 8 luces y, cada vez que la cámara se mueve, las luces que más se VEN primero.
 *
 * ★ TURNO 4 (17-nov, lo que pidió anonimo03 al verla en el juego):
 *   · EL Z-FIGHTING («las texturas se pelean y se corren al mover la cámara»): la isla se dibuja con PROJ perspectiva
 *     45°, near 1, far 40.000 y la cámara a ~15.000 con un z de 24 bits ⇒ el z sólo distingue de a ~13 unidades y las
 *     capas casi pegadas (el piso de la tienda de los osos, la arena, las baldosas, la espuma) se pelean. En Steam se
 *     arregló con near = 100 (anonimo03 lo confirmó a ojo). Acá: un gancho en SetTransform (44) del dispositivo que dibuja
 *     reescribe ESA proyección con near = [isla_fx] cercano (100; 0 = apagado) — _33 y _43; fov, aspecto y far
 *     iguales ⇒ ningún píxel cambia de lugar en la pantalla, sólo el z. SÓLO si a la vez (fx_cercano_decide):
 *       1. la matriz es una perspectiva de Direct3D centrada con near 0,5..2 y far 30.000..50.000 (la de la isla);
 *       2. se dibujó una textura de la isla hace menos de 250 ms (la escena es la isla: las salas, la carrera, el
 *          armario y la UI 2D no pasan);
 *       3. la cámara (la VIEW, que el juego fija ANTES que la PROJ) está a más de [isla_fx] cercano_ojo (3.000) del
 *          origen: las cámaras de la isla están a 6.700..26.000 (todas las de rnr_script/camera); un personaje en
 *          primer plano (crear personaje, el selector) tiene la cámara al lado del origen y NO se toca.
 *     La sonda cuenta las reescritas por segundo y anota la primera (near, far) y las primeras que NO (y por qué).
 *   · [partir] en el perfil: una textura que usan dos cosas distintas (nocull_star: la estrella del cartel y las
 *     estrellitas de los rieles) se parte por la posición del nodo en la escena del .md9 (la traslación del Mundo
 *     de cada dibujo, devuelta a la escena con el ancla: fx_al_md9). La parte va con OTRO sombreador y sus perillas
 *     ([<sombreador>@<textura>~parte]) y no hereda la exclusión del brillo.
 *
 * ★ La lógica pura (perfil, nombres, etapa 0, matrices, tabla de marcas) se prueba SIN el juego en
 *   herramientas/dll_d3d9/banco/banco_isla_fx.c (lo arma y corre pruebas/probar_isla_fx.py). */

#include "isla_fx_sombreadores.h"
#include "isla_fx_campanillas.h"     /* ★ turno 5: las campanillas del trineo (mp3 con el fundido horneado) */

/* ── índices de IDirect3DDevice9 ─────────────────────────────────────────────────────────────────────────── */
#define FX_GETCAPS        7
#define FX_RESET         16
#define FX_PRESENT       17
#define FX_CREATETEX     23
#define FX_STRETCHRECT   34
#define FX_SETRT         37
#define FX_GETRT         38
#define FX_SETDS         39
#define FX_GETDS         40
#define FX_BEGINSCENE    41
#define FX_ENDSCENE      42
#define FX_GETTRANSFORM  45
#define FX_GETMATERIAL   50
#define FX_SETRS         57
#define FX_GETRS         58
#define FX_CREATESB      59
#define FX_GETTEX        64
#define FX_SETTEX        65
#define FX_GETTSS        66
#define FX_SETSAMP       69
#define FX_DP            81
#define FX_DIP           82
#define FX_DPUP          83
#define FX_DIPUP         84
#define FX_SETFVF        89
#define FX_GETFVF        90
#define FX_CREATEVS      91
#define FX_SETVS         92
#define FX_GETVS         93
#define FX_SETVSCF       94
#define FX_CREATEPS     106
#define FX_SETPS        107
#define FX_GETPS        108
#define FX_SETPSCF      109

/* estados (d3d9types.h) */
#define FX_RS_ZENABLE        7
#define FX_RS_FILLMODE       8
#define FX_RS_ZWRITE        14
#define FX_RS_ALPHATEST     15
#define FX_RS_SRCBLEND      19
#define FX_RS_DESTBLEND     20
#define FX_RS_CULL          22
#define FX_RS_ALPHABLEND    27
#define FX_RS_FOGENABLE     28
#define FX_RS_FOGCOLOR      34
#define FX_RS_FOGTABLEMODE  35
#define FX_RS_FOGSTART      36
#define FX_RS_FOGEND        37
#define FX_RS_FOGDENSITY    38
#define FX_RS_STENCIL       52
#define FX_RS_TFACTOR       60
#define FX_RS_LIGHTING     137
#define FX_RS_FOGVERTEXMODE 140
#define FX_RS_CLIPPLANES   152
#define FX_RS_COLORWRITE   168
#define FX_RS_BLENDOP      171
#define FX_RS_SCISSOR      174
#define FX_RS_SRGBWRITE    194
#define FX_RS_SEPALPHA     206

#define FX_TSS_COLOROP   1
#define FX_TSS_COLORARG1 2
#define FX_TSS_COLORARG2 3
#define FX_TSS_ALPHAOP   4
#define FX_TSS_ALPHAARG1 5
#define FX_TSS_ALPHAARG2 6

#define FX_TOP_SELECTARG1 2
#define FX_TOP_SELECTARG2 3
#define FX_TOP_MODULATE   4
#define FX_TOP_MODULATE2X 5
#define FX_TOP_MODULATE4X 6
#define FX_TA_DIFFUSE  0
#define FX_TA_TEXTURE  2
#define FX_TA_TFACTOR  3

#define FX_FVF_POSMASK  0x400E
#define FX_FVF_XYZ      0x002
#define FX_FVF_XYZRHW   0x004
#define FX_FVF_DIFFUSE  0x040

/* el objeto textura del juego y la función que lo carga (medidos: ver la cabecera) */
#define FX_VA_CARGAR     0x641620
#define FX_VA_CARGAR_RET 0x641AFC
#define FX_VA_LLAMADA    0x642A11
#define FX_VA_WRAP       0x931498

/* ── el perfil ──────────────────────────────────────────────────────────────────────────────────────────── */
enum { FX_MAR = 0, FX_CIELO, FX_LUCES, FX_NIEVE, FX_EMISIVO, FX_NSOMB, FX_NINGUNO = 99 };
static const char *const g_fx_nombre_sombra[FX_NSOMB] = { "mar", "cielo", "luces", "nieve", "emisivo" };

#define FX_MAX_TEX    160
#define FX_MAX_LUCES   64      /* ★ turno 6: las del PERFIL (eran 32): en cada cuadro van al sombreador las que más se ven */
#define FX_LUCES_SH    64      /* ★ turno 10: los lugares del sombreador de 64 (alta estable: c16..c79 / c80..c143);
                                 *   los de 32/16/8 usan los primeros (c16..c47 / c48..c79) */
#define FX_LARGO_NOM   48

typedef struct {
    int   ntex;
    char  tex[FX_MAX_TEX][FX_LARGO_NOM];
    int   sombra[FX_MAX_TEX];               /* FX_MAR.. o FX_NINGUNO */
    float c[FX_NSOMB][8][4];                /* c2..c9 de cada sombreador */
    /* ★ turno 16 · perillas EXTRA e0..e3 de cada sombreador (van a c144..c147: los c2..c9 ya estaban todos usados) */
    float e[FX_NSOMB][8][4];                 /* ★ turno 17: 8 (c144..c151) */
    float et[FX_MAX_TEX][8][4];
    int   estilo_b;                          /* 1 = [isla_fx] mar_estilo=b: [mar_b] pisa lo de [mar] */
    float mezcla;
    float astro_dir[4], astro_col[4], cielo_col[4];
    int   luces_activo, ancla, tiene_ancla_pos;
    float ancla_pos[3], luces_int;
    int   nluces, luces_de_mas;
    float luz[FX_MAX_LUCES][9];             /* x, y, z, radio, r, g, b, intensidad, parpadeo */
    int   brillo_activo, brillo_pases, brillo_en_present;
    float brillo_umbral, brillo_rodilla, brillo_int, brillo_sat, brillo_tinte[3];
    int   errores;                          /* líneas mal escritas (quedaron de fábrica) */
    /* ★ turno 2 */
    float ct[FX_MAX_TEX][8][4];             /* las perillas de CADA textura: las de su sombreador, o las de su sección
                                             * propia «[<sombreador>@<textura>]» si la tiene (el trineo dorado) */
    int   propia[FX_MAX_TEX];               /* 1 = tiene sección propia */
    int   sin_brillo[FX_MAX_TEX];           /* 1 = excluida del brillo ([brillo] excluir =) */
    int   excluir_modo;                     /* 0 = DIFERIR (se dibuja después del brillo) · 1 = TOPE (se achica su color) */
    float tope;                             /* el tope de brillo del modo 1 */
    /* ★ turno 3 */
    float astro_pos[3];                     /* dónde está el astro PINTADO en el cielo (escena del .md9; generar_astro.py) */
    int   tiene_astro_pos;
    int   reflejo_desde_pos;                /* 1 = el mar y lo iluminado TAMBIÉN miran a la posición (reflejo geométrico) */
    /* ★ turno 4 · [partir]: los dibujos de la textura i cuyo nodo tiene la coordenada `parte_eje` (0 x · 1 y · 2 z, en
     *   la escena del .md9) MENOR que `parte_lim` van como la entrada parte_de[i] − 1 (0 = la textura no se parte) */
    int   parte_de[FX_MAX_TEX], parte_eje[FX_MAX_TEX];
    float parte_lim[FX_MAX_TEX];
    int   npartes;
    /* ★ turno 5 · [halo]: color (rgb) y fuerza de la silueta que se dibuja ANTES del brillo (sólo las excluidas, DIFERIR) */
    float halo[FX_MAX_TEX][4];
    int   nhalos;
    /* ★ turno 8 · la silueta AGRANDADA: centro (escena del .md9), escala (1 = igual) y opacidad */
    float halo_centro[FX_MAX_TEX][3], halo_esc[FX_MAX_TEX], halo_op[FX_MAX_TEX];
    int   halo_tiene_centro[FX_MAX_TEX];
    float halo_radio[FX_MAX_TEX];            /* ★ turno 14: > 0 = RESPLANDOR radial de ese radio (unidades) en vez de silueta */
    float halo_bombillo[FX_MAX_TEX][4];      /* ★ turno 25: el NÚCLEO del resplandor (fuerza, ancho, blanco) y la caída de afuera */
    /* ★ turno 12 · [zsesgo]: «textura = depthbias, slopescaledepthbias» (D3DRS_DEPTHBIAS / SLOPESCALEDEPTHBIAS) */
    float zsesgo[FX_MAX_TEX][2];
    int   tiene_zsesgo[FX_MAX_TEX], nzsesgo;
} FX_PERFIL;

/* ★ los valores de FÁBRICA de c2..c9: los de la NOCHE del perfil.ini que se entrega (una perilla que falta o está mal
 *   escrita vuelve a éste, nunca a cero: un contraste 0 dejaría el mar negro). La prueba compara esta tabla con el
 *   perfil.ini leído de noche: si se separan, avisa. */
static const float fx_fabrica[FX_NSOMB][8][4] = {
    { /* mar */
        { 0.0015f, 0.006f, 0.6f, 0.25f }, { 0.70f, 1.0f, 0.6f, 0.5f }, { 0.0125f, 0.985f, 1.6f, 2.0f },
        { 0.06f, 0.12f, 0.22f, 0.85f }, { 0.66f, 4.0f, 1.2f, 0.45f }, { 0.9f, 40.0f, 1.6f, 0.25f },
        { 0.30f, 0.85f, 0.60f, 0.35f }, { 0.35f, 1.0f, 0.05f, 0.30f } },     /* ★ turno 4: c3 y c8 · turno 5: c5, c6, c9 de noche */
    { /* cielo */
        { 0.006f, 14.0f, 0.35f, 0.35f }, { 0.0f, 7.0f, 0.004f, 0.10f }, { 0.35f, 1.00f, 0.70f, 0.06f },
        { 0.85f, 0.40f, 1.00f, 0.6f }, { 22.0f, 1.1f, 0.0f, 0.0f }, { 60.0f, 0.992f, 1.0f, 1.5f },
        { 400.0f, 0.15f, 0.5f, 0.0f }, { 0.92f, 0.6965f, 0.5466f, 0.05f } },   /* ★ turno 18: c9.yzw = la luna */
    { /* luces (★ 17-nov: saturación de noche 1.05 → 1.15, como el perfil.ini) */
        { 0.82f, 1.15f, 1.0f, 0.55f }, { 0.72f, 1.4f, 0.15f, 0.15f }, { 0.10f, 0.30f, 0.22f, 0.35f },
        { 0.30f, 3.0f, 0.85f, 0.0f }, { 0, 0, 0, 0 }, { 0, 0, 0, 0 }, { 0, 0, 0, 0 }, { 0, 0, 0, 0 } },   /* ★ turno 14: el hombro */
    { /* nieve */
        { 0.82f, 1.05f, 1.0f, 0.55f }, { 0.72f, 1.4f, 0.15f, 0.15f }, { 0.10f, 0.30f, 0.22f, 0.35f },
        { 0.30f, 3.0f, 0.85f, 0.0f }, { 0.025f, 0.93f, 1.6f, 1.3f }, { 0.62f, 0.18f, 0.18f, 0.25f },
        { 0, 0, 0, 0 }, { 0, 0, 0, 0 } },
    { /* emisivo */
        { 0.9f, 0.15f, 0.4f, 0.002f }, { 1.0f, 0.85f, 0.6f, 0.45f }, { 0, 0, 0, 0 }, { 0, 0, 0, 0 },
        { 0, 0, 0, 0 }, { 0, 0, 0, 0 }, { 0, 0, 0, 0 }, { 0, 0, 0, 0 } },
};

/* ★ turno 16 · las extra e0..e3 de FÁBRICA (las del mar = las de [mar] del perfil.ini que se entrega; la prueba las
 *   compara). Mar: e0 = centro de la isla (x, y, z en la escena del .md9) y radio de la costa · e1 = las olas que van
 *   a la COSTA: largo, período (s), relieve, espuma de rompiente · e2 = especular, «plástico» de las crestas, contraste
 *   de las olas chicas, turbidez · e3 = el color del agua baja (r, g, b) y el ancho de la franja baja (×radio) */
/* ★ turno 17 · e4 = el cilindro del cielo (centro x, ·, z, radio; escena del .md9: el del nocull_sky medido) ·
 *   e5 = su mapeo (ángulo donde u = 1, v en y0, dv/dy, y0) · e6 = usar la costa horneada, usar el cielo real, fuerza
 *   del cielo real, cuánto lo tuercen las olas · e7 = el ruido de mundo (escala, fuerza, torsión, velocidad) */
static const float fx_fabrica_e[FX_NSOMB][8][4] = {
    { { 1281.0f, -100.0f, -1056.0f, 6970.0f }, { 1100.0f, 5.0f, 0.30f, 1.0f }, { 0.45f, 0.08f, 0.70f, 0.7f },
      { 0.20f, 0.70f, 0.66f, 1800.0f }, { 17.0f, 0.0f, -1225.0f, 17229.0f }, { 0.3927f, 0.988f, -6.035e-5f, -1620.0f },
      { 1.0f, 1.0f, 0.85f, 0.35f }, { 0.0035f, 0.45f, 0.6f, 0.04f } },
    /* ★ turno 23 · cielo: LA CAPA DE LA AURORA (aurora.hlsli, AuroraCapa; la textura en isla_fx_aurora.h) con su
     *   propio movimiento. e0 = intensidad, velocidad, flameo (UV de costado), período del vaivén (s) · e1 = ondas a lo
     *   alto (rad por v), viaje a lo largo (rad por u), pliegues: fuerza, cuántos (rad por u) · e2 = el brillo que
     *   recorre: fuerza, período (s), ancho (u) · e3 = tinte (r, g, b) y respiración · e6.w = el reflejo en el mar.
     *   (La aurora procedural del turno 21 quedó en aurora.hlsli bajo AURORA_PROCEDURAL, sin compilar.)
     *   Iguales a [cielo] e0..e7 del perfil.ini (la prueba las compara). */
    { { 1.0f, 1.0f, 0.012f, 5.0f }, { 14.0f, 14.0f, 0.35f, 25.0f }, { 0.5f, 14.0f, 0.10f, 0.0f },
      { 1.0f, 1.0f, 1.0f, 0.15f }, { 17.0f, 0.0f, -1225.0f, 0.3927f }, { 0 }, { 0.0f, 0.0f, 0.0f, 0.8f },
      { 0.70f, -0.55f, 0.15f, 1.3f } },     /* ★ turno 24: e4 = el cilindro (centro, eje de la u) · e7 = el lado izquierdo baja */
    { { 0 } }, { { 0 } }, { { 0 } },
};
static int g_fx_mar_estilo_b = 0;                       /* ★ turno 16: [isla_fx] mar_estilo=b */

/* ── la lógica pura (la prueba el banco) ─────────────────────────────────────────────────────────────────── */

/* lee hasta `n` números de "a, b, c" (punto decimal, coma o espacio entre números). Devuelve cuántos leyó, o −1 si
 * hay algo que no es un número (la perilla queda de fábrica). Sin la CRT: el separador decimal no depende del Windows. */
static int fx_numeros(const char *s, float *v, int n)
{
    int k = 0;
    if (!s) return 0;
    for (;;) {
        while (*s == ' ' || *s == '\t' || *s == ',' || *s == ';') {
            if (*s == ';') return k;                         /* comentario al final de la línea */
            s++;
        }
        if (!*s) return k;
        if (k >= n) return -1;                               /* sobran números */
        int neg = 0, dig = 0;
        double ent = 0.0, frac = 0.0, div = 1.0;
        if (*s == '-' || *s == '+') { neg = (*s == '-'); s++; }
        while (*s >= '0' && *s <= '9') { ent = ent * 10.0 + (*s - '0'); s++; dig++; }
        if (*s == '.') {
            s++;
            while (*s >= '0' && *s <= '9') { frac = frac * 10.0 + (*s - '0'); div *= 10.0; s++; dig++; }
        }
        if (!dig) return -1;
        double x = ent + frac / div;
        if (*s == 'e' || *s == 'E') {
            s++;
            int eneg = 0, e = 0, edig = 0;
            if (*s == '-' || *s == '+') { eneg = (*s == '-'); s++; }
            while (*s >= '0' && *s <= '9') { e = e * 10 + (*s - '0'); s++; edig++; if (e > 60) e = 60; }
            if (!edig) return -1;
            while (e-- > 0) x = eneg ? x / 10.0 : x * 10.0;
        }
        if (*s && *s != ' ' && *s != '\t' && *s != ',' && *s != ';') return -1;
        v[k++] = (float)(neg ? -x : x);
    }
}

/* "rnr_ui_bg/front/Nocull_Water.TGA" → "nocull_water" (sin carpeta, sin extensión, en minúsculas) */
static void fx_nombre_base(const char *ruta, char *out, int n)
{
    const char *b = ruta;
    for (const char *p = ruta; *p; p++)
        if (*p == '/' || *p == '\\') b = p + 1;
    const char *punto = NULL;
    for (const char *p = b; *p; p++)
        if (*p == '.') punto = p;
    int i = 0;
    for (const char *p = b; *p && p != punto && i < n - 1; p++) {
        char c = *p;
        if (c >= 'A' && c <= 'Z') c = (char)(c + 32);
        out[i++] = c;
    }
    out[i] = 0;
}

static int fx_perfil_buscar(const FX_PERFIL *pf, const char *base)
{
    for (int i = 0; i < pf->ntex; i++)
        if (lstrcmpA(pf->tex[i], base) == 0) return i;
    return -1;
}

static int fx_sombra_por_nombre(const char *s)
{
    char b[32];
    fx_nombre_base(s, b, sizeof(b));
    for (int i = 0; i < FX_NSOMB; i++)
        if (lstrcmpA(b, g_fx_nombre_sombra[i]) == 0) return i;
    if (lstrcmpA(b, "ninguno") == 0) return FX_NINGUNO;
    return -1;
}

/* una perilla con día y noche: "c2_noche" (o "_dia") gana sobre "c2". 1 = leída, 0 = no estaba, −1 = mal escrita */
static int fx_perilla(const char *ini, const char *sec, const char *clave, int noche, float *v, int n)
{
    char k[48], buf[256];
    wsprintfA(k, "%s_%s", clave, noche ? "noche" : "dia");
    buf[0] = 0;
    GetPrivateProfileStringA(sec, k, "", buf, sizeof(buf), ini);
    if (!buf[0]) GetPrivateProfileStringA(sec, clave, "", buf, sizeof(buf), ini);
    if (!buf[0]) return 0;
    float t[16];
    int r = fx_numeros(buf, t, n);
    if (r <= 0) return -1;
    for (int i = 0; i < r; i++) v[i] = t[i];
    return 1;
}

static void fx_perilla_anotar(FX_PERFIL *pf, const char *sec, const char *clave, int r)
{
    if (r < 0) {
        pf->errores++;
        apuntar("  [isla_fx] ⚠ perfil: [%s] %s está mal escrita: queda de fábrica", sec, clave);
    }
}

/* lee el perfil. Devuelve 1 si se puede usar (hay al menos una textura), 0 si no (la capa no se prende). */
static int fx_leer_perfil(const char *ini, int noche, FX_PERFIL *pf)
{
    static char sec[32768];
    ZeroMemory(pf, sizeof(*pf));
    for (int s = 0; s < FX_NSOMB; s++)
        for (int i = 0; i < 8; i++)
            for (int j = 0; j < 4; j++) pf->c[s][i][j] = fx_fabrica[s][i][j];
    pf->mezcla = 1.0f;
    pf->ancla = -1;
    if (GetFileAttributesA(ini) == INVALID_FILE_ATTRIBUTES) return 0;

    /* [texturas] */
    DWORD largo = GetPrivateProfileSectionA("texturas", sec, sizeof(sec), ini);
    for (char *p = sec; largo && *p; p += lstrlenA(p) + 1) {
        if (*p == ';') continue;
        char *igual = p;
        while (*igual && *igual != '=') igual++;
        if (!*igual) continue;
        *igual = 0;
        char clave[FX_LARGO_NOM];
        char *k = p, *fin = igual - 1;
        while (*k == ' ' || *k == '\t') k++;
        while (fin > k && (*fin == ' ' || *fin == '\t')) *fin-- = 0;
        fx_nombre_base(k, clave, sizeof(clave));
        char *v = igual + 1;
        while (*v == ' ' || *v == '\t') v++;
        char val[32];
        int i = 0;
        while (*v && *v != ' ' && *v != '\t' && *v != ';' && i < 31) val[i++] = *v++;
        val[i] = 0;
        int s = fx_sombra_por_nombre(val);
        if (s < 0 || !clave[0]) {
            pf->errores++;
            apuntar("  [isla_fx] ⚠ perfil: [texturas] %s = %s: no conozco ese sombreador (mar, cielo, luces, nieve, emisivo, ninguno)",
                    clave, val);
            continue;
        }
        if (fx_perfil_buscar(pf, clave) >= 0) continue;   /* la primera gana */
        if (pf->ntex >= FX_MAX_TEX) { pf->errores++; continue; }
        lstrcpynA(pf->tex[pf->ntex], clave, FX_LARGO_NOM);
        pf->sombra[pf->ntex++] = s;
    }

    /* las perillas de cada sombreador */
    for (int s = 0; s < FX_NSOMB; s++)
        for (int i = 0; i < 8; i++) {
            char clave[8];
            wsprintfA(clave, "c%d", i + 2);
            fx_perilla_anotar(pf, g_fx_nombre_sombra[s], clave,
                              fx_perilla(ini, g_fx_nombre_sombra[s], clave, noche, pf->c[s][i], 4));
        }
    /* ★ turno 16 · las extra e0..e3 (de fábrica las del mar, fx_fabrica_e) y el estilo B del mar */
    for (int s = 0; s < FX_NSOMB; s++)
        for (int i = 0; i < 8; i++) {
            for (int j = 0; j < 4; j++) pf->e[s][i][j] = fx_fabrica_e[s][i][j];
            char clave[8];
            wsprintfA(clave, "e%d", i);
            fx_perilla_anotar(pf, g_fx_nombre_sombra[s], clave,
                              fx_perilla(ini, g_fx_nombre_sombra[s], clave, noche, pf->e[s][i], 4));
        }
    pf->estilo_b = g_fx_mar_estilo_b;
    if (pf->estilo_b) {
        for (int i = 0; i < 8; i++) {
            char clave[8];
            wsprintfA(clave, "c%d", i + 2);
            fx_perilla_anotar(pf, "mar_b", clave, fx_perilla(ini, "mar_b", clave, noche, pf->c[FX_MAR][i], 4));
        }
        for (int i = 0; i < 8; i++) {
            char clave[8];
            wsprintfA(clave, "e%d", i);
            fx_perilla_anotar(pf, "mar_b", clave, fx_perilla(ini, "mar_b", clave, noche, pf->e[FX_MAR][i], 4));
        }
    }
    {
        float m = 1.0f;
        int r = fx_perilla(ini, "general", "mezcla", noche, &m, 1);
        fx_perilla_anotar(pf, "general", "mezcla", r);
        if (m < 0.0f) m = 0.0f;
        if (m > 1.0f) m = 1.0f;
        pf->mezcla = m;
    }

    /* [astro] */
    float d[4] = { 0.2214f, 0.2756f, 0.9350f, 0.9f }, c[4] = { 0.75f, 0.85f, 1.0f, 180.0f }, k3[4] = { 0.14f, 0.16f, 0.38f, 0 };
    if (!noche) {
        d[0] = 0.2214f; d[1] = 0.2756f; d[2] = 0.9350f; d[3] = 1.0f;
        c[0] = 1.0f; c[1] = 0.88f; c[2] = 0.70f; c[3] = 120.0f;
        k3[0] = 0.50f; k3[1] = 0.64f; k3[2] = 0.78f;
    }
    fx_perilla_anotar(pf, "astro", "dir", fx_perilla(ini, "astro", "dir", noche, d, 4));
    fx_perilla_anotar(pf, "astro", "color", fx_perilla(ini, "astro", "color", noche, c, 4));
    fx_perilla_anotar(pf, "astro", "cielo", fx_perilla(ini, "astro", "cielo", noche, k3, 3));
    float ln = d[0] * d[0] + d[1] * d[1] + d[2] * d[2];
    if (ln < 1e-6f) { d[0] = 0; d[1] = 1; d[2] = 0; ln = 1; }
    {
        /* normalizar sin sqrt de la CRT: una vuelta de Newton alcanza para una dirección */
        float r = 1.0f / ln, x = 1.0f;
        for (int it = 0; it < 20; it++) x = 0.5f * (x + r / x);
        d[0] *= x; d[1] *= x; d[2] *= x;
    }
    for (int i = 0; i < 4; i++) { pf->astro_dir[i] = d[i]; pf->astro_col[i] = c[i]; pf->cielo_col[i] = k3[i]; }
    /* ★ turno 3: la POSICIÓN del astro pintado (si está, gana sobre la dirección: cada píxel mira hacia ese punto) */
    {
        float ap[3];
        int r = fx_perilla(ini, "astro", "pos", noche, ap, 3);
        fx_perilla_anotar(pf, "astro", "pos", r);
        if (r == 1) {
            pf->astro_pos[0] = ap[0]; pf->astro_pos[1] = ap[1]; pf->astro_pos[2] = ap[2];
            pf->tiene_astro_pos = 1;
        }
        pf->reflejo_desde_pos = GetPrivateProfileIntA("astro", "reflejo_desde_pos", 0, ini);
    }

    /* [brillo] */
    pf->brillo_activo = GetPrivateProfileIntA("brillo", "activo", 1, ini);
    pf->brillo_pases = GetPrivateProfileIntA("brillo", "pases", 2, ini);
    if (pf->brillo_pases < 1) pf->brillo_pases = 1;
    if (pf->brillo_pases > 4) pf->brillo_pases = 4;
    pf->brillo_en_present = GetPrivateProfileIntA("brillo", "en_present", 0, ini);
    pf->brillo_umbral = 0.75f; pf->brillo_rodilla = 0.25f; pf->brillo_int = 0.55f; pf->brillo_sat = 1.0f;
    pf->brillo_tinte[0] = 1.0f; pf->brillo_tinte[1] = 0.97f; pf->brillo_tinte[2] = 0.92f;
    fx_perilla_anotar(pf, "brillo", "umbral", fx_perilla(ini, "brillo", "umbral", noche, &pf->brillo_umbral, 1));
    fx_perilla_anotar(pf, "brillo", "rodilla", fx_perilla(ini, "brillo", "rodilla", noche, &pf->brillo_rodilla, 1));
    fx_perilla_anotar(pf, "brillo", "intensidad", fx_perilla(ini, "brillo", "intensidad", noche, &pf->brillo_int, 1));
    fx_perilla_anotar(pf, "brillo", "saturacion", fx_perilla(ini, "brillo", "saturacion", noche, &pf->brillo_sat, 1));
    fx_perilla_anotar(pf, "brillo", "tinte", fx_perilla(ini, "brillo", "tinte", noche, pf->brillo_tinte, 3));
    if (pf->brillo_rodilla < 0.001f) pf->brillo_rodilla = 0.001f;
    /* ★ turno 2: las texturas que NO brillan (la estrella, el sol y la luna del cartel se quemaban: «amarillo plano,
     *   tapa WEIMAR»). DIFERIR = su dibujo se guarda y se hace DESPUÉS del brillo (exacto); TOPE = su color se achica
     *   para que no pase el umbral (por si diferir diera problemas). */
    {
        char lista[1024], modo[32];
        lista[0] = modo[0] = 0;
        GetPrivateProfileStringA("brillo", "excluir", "", lista, sizeof(lista), ini);
        GetPrivateProfileStringA("brillo", "excluir_modo", "diferir", modo, sizeof(modo), ini);
        pf->excluir_modo = lstrcmpiA(modo, "tope") == 0 ? 1 : 0;
        if (lstrcmpiA(modo, "tope") != 0 && lstrcmpiA(modo, "diferir") != 0) {
            pf->errores++;
            apuntar("  [isla_fx] ⚠ perfil: [brillo] excluir_modo = %s: no lo conozco (diferir / tope): uso diferir", modo);
        }
        pf->tope = pf->brillo_umbral - pf->brillo_rodilla;
        fx_perilla_anotar(pf, "brillo", "tope", fx_perilla(ini, "brillo", "tope", noche, &pf->tope, 1));
        if (pf->tope < 0.05f) pf->tope = 0.05f;
        char *p = lista;
        while (*p) {
            while (*p == ' ' || *p == '	' || *p == ',') p++;
            if (!*p || *p == ';') break;
            char nom[FX_LARGO_NOM * 2], base[FX_LARGO_NOM];
            int i = 0;
            while (*p && *p != ',' && *p != ' ' && *p != '	' && *p != ';' && i < (int)sizeof(nom) - 1) nom[i++] = *p++;
            nom[i] = 0;
            fx_nombre_base(nom, base, sizeof(base));
            int k = fx_perfil_buscar(pf, base);
            if (k < 0 && pf->ntex < FX_MAX_TEX) {              /* se anota aunque no lleve sombreador */
                lstrcpynA(pf->tex[pf->ntex], base, FX_LARGO_NOM);
                pf->sombra[pf->ntex] = FX_NINGUNO;
                k = pf->ntex++;
            }
            if (k >= 0) pf->sin_brillo[k] = 1;
        }
    }

    /* [luces_puntuales] */
    pf->luces_activo = GetPrivateProfileIntA("luces_puntuales", "activo", 1, ini);
    pf->luces_int = 1.0f;
    fx_perilla_anotar(pf, "luces_puntuales", "intensidad",
                      fx_perilla(ini, "luces_puntuales", "intensidad", noche, &pf->luces_int, 1));
    {
        char an[FX_LARGO_NOM * 2], base[FX_LARGO_NOM];
        an[0] = 0;
        GetPrivateProfileStringA("luces_puntuales", "ancla", "", an, sizeof(an), ini);
        if (an[0]) {
            fx_nombre_base(an, base, sizeof(base));
            int i = fx_perfil_buscar(pf, base);
            if (i < 0 && pf->ntex < FX_MAX_TEX) {            /* el ancla se anota aunque no lleve sombreador */
                lstrcpynA(pf->tex[pf->ntex], base, FX_LARGO_NOM);
                pf->sombra[pf->ntex] = FX_NINGUNO;
                i = pf->ntex++;
            }
            pf->ancla = i;
        }
        float ap[3];
        int r = fx_perilla(ini, "luces_puntuales", "ancla_pos", noche, ap, 3);
        fx_perilla_anotar(pf, "luces_puntuales", "ancla_pos", r);
        if (r == 1) { pf->ancla_pos[0] = ap[0]; pf->ancla_pos[1] = ap[1]; pf->ancla_pos[2] = ap[2]; pf->tiene_ancla_pos = 1; }
    }
    largo = GetPrivateProfileSectionA("luces_puntuales", sec, sizeof(sec), ini);
    for (char *p = sec; largo && *p; p += lstrlenA(p) + 1) {
        char *k = p;
        while (*k == ' ' || *k == '\t') k++;
        if ((k[0] | 32) != 'l' || (k[1] | 32) != 'u' || (k[2] | 32) != 'z') continue;
        /* ★ turno 6: «luz_noche.x = …» sólo de NOCHE (las bolas del árbol: de día no dan luz) */
        if (k[3] == '_' && (k[4] | 32) == 'n' && (k[5] | 32) == 'o' && (k[6] | 32) == 'c' && (k[7] | 32) == 'h'
            && (k[8] | 32) == 'e' && k[9] == '.') {
            if (!noche) continue;
        } else if (k[3] != '.') continue;
        char *igual = k;
        while (*igual && *igual != '=') igual++;
        if (!*igual) continue;
        float v[9];
        int r = fx_numeros(igual + 1, v, 9);
        if (r != 9 || v[3] <= 0.0f) {
            pf->errores++;
            apuntar("  [isla_fx] ⚠ perfil: luz mal escrita (hacen falta 9 números y radio > 0): %s", k);
            continue;
        }
        if (pf->nluces >= FX_MAX_LUCES) { pf->luces_de_mas++; continue; }
        for (int i = 0; i < 9; i++) pf->luz[pf->nluces][i] = v[i];
        pf->nluces++;
    }
    /* ★ turno 4 · [partir]: «textura = eje, límite, sombreador» ⇒ una entrada nueva «<textura>~parte» */
    largo = GetPrivateProfileSectionA("partir", sec, sizeof(sec), ini);
    for (char *p = sec; largo && *p; p += lstrlenA(p) + 1) {
        if (*p == ';') continue;
        char *igual = p;
        while (*igual && *igual != '=') igual++;
        if (!*igual) continue;
        *igual = 0;
        char clave[FX_LARGO_NOM], *k = p, *fin = igual - 1;
        while (*k == ' ' || *k == '\t') k++;
        while (fin > k && (*fin == ' ' || *fin == '\t')) *fin-- = 0;
        fx_nombre_base(k, clave, sizeof(clave));
        /* los tres campos, separados por coma */
        char campo[3][32];
        int nc = 0;
        char *v = igual + 1;
        while (nc < 3) {
            while (*v == ' ' || *v == '\t') v++;
            int i = 0;
            while (*v && *v != ',' && *v != ';' && i < 31) campo[nc][i++] = *v++;
            while (i > 0 && (campo[nc][i - 1] == ' ' || campo[nc][i - 1] == '\t')) i--;
            campo[nc][i] = 0;
            nc++;
            if (*v != ',') break;
            v++;
        }
        float lim = 0.0f;
        int eje = (nc == 3 && campo[0][0] && !campo[0][1])
                  ? ((campo[0][0] | 32) == 'x' ? 0 : (campo[0][0] | 32) == 'y' ? 1 : (campo[0][0] | 32) == 'z' ? 2 : -1) : -1;
        int s = nc == 3 ? fx_sombra_por_nombre(campo[2]) : -1;
        int b = fx_perfil_buscar(pf, clave);
        char nom[FX_LARGO_NOM + 8];
        wsprintfA(nom, "%s~parte", clave);
        if (eje < 0 || s < 0 || fx_numeros(campo[1], &lim, 1) != 1 || b < 0 || pf->parte_de[b]
            || lstrlenA(nom) >= FX_LARGO_NOM || pf->ntex >= FX_MAX_TEX) {
            pf->errores++;
            apuntar("  [isla_fx] ⚠ perfil: [partir] %s está mal escrita (hace falta: textura de [texturas] = x|y|z, límite,"
                    " sombreador): no se parte", clave);
            continue;
        }
        lstrcpynA(pf->tex[pf->ntex], nom, FX_LARGO_NOM);
        pf->sombra[pf->ntex] = s;
        pf->parte_de[b] = ++pf->ntex;                          /* índice + 1 */
        pf->parte_eje[b] = eje;
        pf->parte_lim[b] = lim;
        pf->npartes++;
    }

    /* ★ turno 5 · [halo]: «textura = r, g, b, fuerza» (con _dia / _noche). Sólo para texturas que ya están en el perfil */
    largo = GetPrivateProfileSectionA("halo", sec, sizeof(sec), ini);
    for (char *p = sec; largo && *p; p += lstrlenA(p) + 1) {
        if (*p == ';') continue;
        char *igual = p;
        while (*igual && *igual != '=') igual++;
        if (!*igual) continue;
        char clave[FX_LARGO_NOM * 2];
        int n = (int)(igual - p);
        if (n >= (int)sizeof(clave)) continue;
        lstrcpynA(clave, p, n + 1);
        while (n > 0 && (clave[n - 1] == ' ' || clave[n - 1] == '\t')) clave[--n] = 0;
        char base[FX_LARGO_NOM + 8];
        lstrcpynA(base, clave, sizeof(base));
        int lb = lstrlenA(base);
        /* ★ turno 8: «_centro», «_escala», «_opacidad» son datos del halo de esa textura, no texturas */
        if ((lb > 7 && lstrcmpiA(base + lb - 7, "_centro") == 0) || (lb > 7 && lstrcmpiA(base + lb - 7, "_escala") == 0)
            || (lb > 6 && lstrcmpiA(base + lb - 6, "_radio") == 0)
            || (lb > 9 && lstrcmpiA(base + lb - 9, "_bombillo") == 0)
            || (lb > 9 && lstrcmpiA(base + lb - 9, "_opacidad") == 0)) continue;
        if (lb > 4 && lstrcmpiA(base + lb - 4, "_dia") == 0) base[lb - 4] = 0;
        else if (lb > 6 && lstrcmpiA(base + lb - 6, "_noche") == 0) base[lb - 6] = 0;
        if (lstrcmpiA(base, clave) != 0) {
            /* una variante de hora: sólo cuenta si la base no está (se lee abajo con fx_perilla) */
            char sin[FX_LARGO_NOM + 8];
            GetPrivateProfileStringA("halo", base, "", sin, sizeof(sin), ini);
            if (sin[0]) continue;
        }
        char nb[FX_LARGO_NOM];
        fx_nombre_base(base, nb, sizeof(nb));
        int k = fx_perfil_buscar(pf, nb);
        if (k < 0 || pf->halo[k][3] != 0.0f) {
            if (k < 0) {
                pf->errores++;
                apuntar("  [isla_fx] ⚠ perfil: [halo] %s: esa textura no está en el perfil", nb);
            }
            continue;
        }
        float v[4] = { 0, 0, 0, 0 };
        int r = fx_perilla(ini, "halo", base, noche, v, 4);
        if (r != 1) { fx_perilla_anotar(pf, "halo", base, r < 0 ? -1 : 0); continue; }
        for (int j = 0; j < 4; j++) pf->halo[k][j] = v[j];
        if (v[3] > 0.0f) pf->nhalos++;
        {
            char kk[FX_LARGO_NOM + 16];
            float c3[3], e = 1.0f, o = 1.0f;
            wsprintfA(kk, "%s_centro", base);
            if (fx_perilla(ini, "halo", kk, noche, c3, 3) == 1) {
                pf->halo_centro[k][0] = c3[0]; pf->halo_centro[k][1] = c3[1]; pf->halo_centro[k][2] = c3[2];
                pf->halo_tiene_centro[k] = 1;
            }
            wsprintfA(kk, "%s_escala", base);
            fx_perilla_anotar(pf, "halo", kk, fx_perilla(ini, "halo", kk, noche, &e, 1));
            wsprintfA(kk, "%s_opacidad", base);
            fx_perilla_anotar(pf, "halo", kk, fx_perilla(ini, "halo", kk, noche, &o, 1));
            pf->halo_esc[k] = e < 1.0f ? 1.0f : e > 2.0f ? 2.0f : e;
            float ra = 0.0f;
            wsprintfA(kk, "%s_radio", base);
            fx_perilla_anotar(pf, "halo", kk, fx_perilla(ini, "halo", kk, noche, &ra, 1));
            pf->halo_radio[k] = ra < 0.0f ? 0.0f : ra;
            /* ★ turno 25 (anonimo03: «que se parezcan un poco a un BOMBILLO emanando luz, pero tan sólo un poco»):
             *   «_bombillo = fuerza del núcleo, su ancho (fracción del radio), cuánto tira a blanco (0..1), caída de
             *   afuera» (3 = la de antes; menos = más amplio). Sin la perilla: 0, 0.25, 0, 3 = como antes. */
            float bo[4] = { 0.0f, 0.25f, 0.0f, 3.0f };
            wsprintfA(kk, "%s_bombillo", base);
            fx_perilla_anotar(pf, "halo", kk, fx_perilla(ini, "halo", kk, noche, bo, 4));
            pf->halo_bombillo[k][0] = bo[0] < 0.0f ? 0.0f : bo[0];
            pf->halo_bombillo[k][1] = bo[1] < 0.02f ? 0.02f : bo[1] > 1.0f ? 1.0f : bo[1];
            pf->halo_bombillo[k][2] = bo[2] < 0.0f ? 0.0f : bo[2] > 1.0f ? 1.0f : bo[2];
            pf->halo_bombillo[k][3] = bo[3] < 0.5f ? 0.5f : bo[3] > 20.0f ? 20.0f : bo[3];
            pf->halo_op[k] = o < 0.0f ? 0.0f : o > 1.0f ? 1.0f : o;
        }
    }

    /* ★ turno 12 · [zsesgo]: el sesgo de z por textura (para separar dos que se pelean sin mover la malla) */
    largo = GetPrivateProfileSectionA("zsesgo", sec, sizeof(sec), ini);
    for (char *p = sec; largo && *p; p += lstrlenA(p) + 1) {
        if (*p == ';') continue;
        char *igual = p;
        while (*igual && *igual != '=') igual++;
        if (!*igual) continue;
        *igual = 0;
        char clave[FX_LARGO_NOM], *k = p, *fin = igual - 1;
        while (*k == ' ' || *k == '\t') k++;
        while (fin > k && (*fin == ' ' || *fin == '\t')) *fin-- = 0;
        fx_nombre_base(k, clave, sizeof(clave));
        float v[2] = { 0, 0 };
        int r = fx_numeros(igual + 1, v, 2);
        if (r < 1 || !clave[0]) { pf->errores++; apuntar("  [isla_fx] ⚠ perfil: [zsesgo] %s mal escrita", clave); continue; }
        int i = fx_perfil_buscar(pf, clave);
        if (i < 0 && pf->ntex < FX_MAX_TEX) {                   /* se anota aunque no lleve sombreador */
            lstrcpynA(pf->tex[pf->ntex], clave, FX_LARGO_NOM);
            pf->sombra[pf->ntex] = FX_NINGUNO;
            i = pf->ntex++;
        }
        if (i < 0) { pf->errores++; continue; }
        pf->zsesgo[i][0] = v[0]; pf->zsesgo[i][1] = r > 1 ? v[1] : 0.0f;
        pf->tiene_zsesgo[i] = 1;
        pf->nzsesgo++;
    }

    /* ★ turno 2: las perillas de cada textura = las de su sombreador, salvo que tenga sección propia
     *   «[<sombreador>@<textura>]» (p. ej. [emisivo@nocull_xm_trineo_cuerpo]: sólo los dorados) */
    for (int i = 0; i < pf->ntex; i++) {
        int s = pf->sombra[i];
        if (s == FX_NINGUNO) continue;
        for (int a = 0; a < 8; a++)
            for (int b = 0; b < 4; b++) pf->ct[i][a][b] = pf->c[s][a][b];
        for (int a = 0; a < 8; a++)
            for (int b = 0; b < 4; b++) pf->et[i][a][b] = pf->e[s][a][b];     /* ★ turno 16 / 17 */
        char secc[96], prueba[8];
        wsprintfA(secc, "%s@%s", g_fx_nombre_sombra[s], pf->tex[i]);
        if (!GetPrivateProfileSectionA(secc, prueba, sizeof(prueba), ini)) continue;
        pf->propia[i] = 1;
        for (int a = 0; a < 8; a++) {
            char clave[8];
            wsprintfA(clave, "c%d", a + 2);
            fx_perilla_anotar(pf, secc, clave, fx_perilla(ini, secc, clave, noche, pf->ct[i][a], 4));
        }
        for (int a = 0; a < 8; a++) {                                      /* ★ turno 16 / 17 */
            char clave[8];
            wsprintfA(clave, "e%d", a);
            fx_perilla_anotar(pf, secc, clave, fx_perilla(ini, secc, clave, noche, pf->et[i][a], 4));
        }
    }
    return pf->ntex > 0;
}

/* ★ turno 2 · LA CALIDAD: las `n` luces que más se ven en el cuadro van a los primeros lugares (el sombreador de
 *   calidad media/baja sólo recorre esos). Cuánto se ve una luz = intensidad × (radio / distancia)²: la distancia es la
 *   profundidad en la vista (las que quedan detrás de la cámara no cuentan). Las que no entran quedan apagadas.
 *   v = la matriz de vista (fila = vector). */
/* ★ turno 8 · SIN SALTOS al mover la cámara (anonimo03: «texturas parpadeando al mover la cámara» en la tienda y en
 *   multijugador). Con las bolas, de noche hay 43 luces y el sombreador lleva 32: en cada cuadro de un viaje de cámara
 *   cambiaban las que entran, y una luz que entra o sale de golpe hace titilar su charco. Ahora:
 *     · HISTÉRESIS: la que ya estaba elegida cuenta ×1,6 (para salir, otra la tiene que superar de verdad);
 *     · ENTRA SUAVE: una luz nueva sube de 0 a su color en FX_LUZ_ENTRA s (el peso multiplica su color).
 *   ant[i] = 1 si la luz i estaba elegida; peso[i] = 0..1. Devuelve 1 si alguna está todavía entrando. */
#define FX_LUZ_BONUS 1.6f
#define FX_LUZ_ENTRA 0.4f
static int fx_elegir_luces_suave(const float pos[][4], const float col[][4], const float *v, int n,
                                 float sel_pos[][4], float sel_col[][4], int *ant, float *peso, float dt);
static void fx_elegir_luces(const float pos[][4], const float col[][4], const float *v, int n,
                            float sel_pos[][4], float sel_col[][4])
{
    fx_elegir_luces_suave(pos, col, v, n, sel_pos, sel_col, NULL, NULL, 0.0f);
}

static int fx_elegir_luces_suave(const float pos[][4], const float col[][4], const float *v, int n,
                                 float sel_pos[][4], float sel_col[][4], int *ant, float *peso, float dt)
{
    float imp[FX_MAX_LUCES];
    int elegida[FX_MAX_LUCES], entrando = 0, prendidas = 0;
    int orden[FX_MAX_LUCES];
    if (n > FX_LUCES_SH) n = FX_LUCES_SH;
    for (int i = 0; i < FX_MAX_LUCES; i++)
        if (pos[i][3] < 1e19f && col[i][0] + col[i][1] + col[i][2] > 0.0f) prendidas++;
    /* ★ turno 10: si entran TODAS, no se elige nada (tampoco se dejan afuera las de detrás de la cámara: un charco
     *   que se ve puede venir de una luz que no se ve; si no, al girar la cámara entrarían y saldrían) */
    int todas = prendidas <= n;
    for (int i = 0; i < FX_MAX_LUCES; i++) {
        float z = pos[i][0] * v[2] + pos[i][1] * v[6] + pos[i][2] * v[10] + v[14];
        float inten = col[i][0] + col[i][1] + col[i][2];
        if (pos[i][3] >= 1e19f || inten <= 0.0f) imp[i] = 0.0f;
        else if (z <= 0.0f) imp[i] = todas ? 1e-30f : 0.0f;
        else {
            if (z < 1.0f) z = 1.0f;
            imp[i] = inten / (pos[i][3] * z * z);                 /* inten × r² / z² (pos.w = 1/r²) */
            if (ant && ant[i]) imp[i] *= FX_LUZ_BONUS;           /* ★ turno 8: histéresis */
        }
        orden[i] = i;
        elegida[i] = 0;
    }
    for (int i = 0; i < n; i++) {                                 /* selección: n chico, 32 luces */
        int m = i;
        for (int j = i + 1; j < FX_MAX_LUCES; j++)
            if (imp[orden[j]] > imp[orden[m]]) m = j;
        int t = orden[i]; orden[i] = orden[m]; orden[m] = t;
    }
    for (int i = 0; i < FX_LUCES_SH; i++) {
        int k = orden[i];
        if (i < n && imp[k] > 0.0f) {
            float w = 1.0f;
            elegida[k] = 1;
            if (peso) {                                           /* ★ turno 8: entra suave */
                if (!ant[k]) peso[k] = 0.0f;
                peso[k] += dt / FX_LUZ_ENTRA;
                if (peso[k] >= 1.0f) peso[k] = 1.0f; else entrando = 1;
                w = peso[k];
            }
            for (int j = 0; j < 4; j++) { sel_pos[i][j] = pos[k][j]; sel_col[i][j] = col[k][j]; }
            sel_col[i][0] *= w; sel_col[i][1] *= w; sel_col[i][2] *= w;
        } else {
            sel_pos[i][0] = sel_pos[i][1] = sel_pos[i][2] = 0.0f;
            sel_pos[i][3] = 1e20f;
            sel_col[i][0] = sel_col[i][1] = sel_col[i][2] = sel_col[i][3] = 0.0f;
        }
    }
    if (ant) for (int i = 0; i < FX_MAX_LUCES; i++) { ant[i] = elegida[i]; if (!elegida[i] && peso) peso[i] = 0.0f; }
    return entrando;
}

/* ★ la etapa 0 del juego → lo que hace nuestro sombreador para que el color de partida sea el MISMO.
 *   mul[4] = por qué se multiplica la textura (rgb, a); *vertice = 1 si además el color del vértice multiplica.
 *   Devuelve 0 si se puede, o un código de por qué no (el dibujo va como siempre):
 *     1 color no soportado · 2 alfa no soportado · 3 color/alfa con el vértice a medias · 4 modificadores de argumento */
static int fx_etapa0(DWORD cop, DWORD c1, DWORD c2, DWORD aop, DWORD a1, DWORD a2, DWORD tfactor, DWORD luces,
                     DWORD fvf, float mat_dif_a, float *mul, int *vertice)
{
    float tf[4] = { ((tfactor >> 16) & 0xFF) / 255.0f, ((tfactor >> 8) & 0xFF) / 255.0f, (tfactor & 0xFF) / 255.0f,
                    ((tfactor >> 24) & 0xFF) / 255.0f };
    int tiene_color = (fvf & FX_FVF_DIFFUSE) != 0;
    int vc = 0, va = 0;
    if ((c1 | c2 | a1 | a2) & 0xF0) return 4;                /* COMPLEMENT / ALPHAREPLICATE: no los copiamos */
    mul[0] = mul[1] = mul[2] = mul[3] = 1.0f;
    /* el color */
    if ((cop == FX_TOP_SELECTARG1 && c1 == FX_TA_TEXTURE) || (cop == FX_TOP_SELECTARG2 && c2 == FX_TA_TEXTURE)) {
        /* la textura sola */
    } else if ((cop == FX_TOP_MODULATE || cop == FX_TOP_MODULATE2X || cop == FX_TOP_MODULATE4X)
               && (c1 == FX_TA_TEXTURE || c2 == FX_TA_TEXTURE)) {
        DWORD otro = (c1 == FX_TA_TEXTURE) ? c2 : c1;
        float k = cop == FX_TOP_MODULATE ? 1.0f : cop == FX_TOP_MODULATE2X ? 2.0f : 4.0f;
        if (otro == FX_TA_TEXTURE) return 1;
        if (otro == FX_TA_TFACTOR) { mul[0] = tf[0] * k; mul[1] = tf[1] * k; mul[2] = tf[2] * k; }
        else if (otro == FX_TA_DIFFUSE && !luces) {
            mul[0] = mul[1] = mul[2] = k;
            vc = tiene_color;                                /* sin luces y sin color en el vértice: blanco */
        } else return 1;
    } else return 1;
    /* el alfa */
    if ((aop == FX_TOP_SELECTARG1 && a1 == FX_TA_TEXTURE) || (aop == FX_TOP_SELECTARG2 && a2 == FX_TA_TEXTURE)) {
        mul[3] = 1.0f;
    } else if (aop == FX_TOP_MODULATE && (a1 == FX_TA_TEXTURE || a2 == FX_TA_TEXTURE)) {
        DWORD otro = (a1 == FX_TA_TEXTURE) ? a2 : a1;
        if (otro == FX_TA_TFACTOR) mul[3] = tf[3];
        else if (otro == FX_TA_DIFFUSE) {
            if (!luces) { mul[3] = 1.0f; va = tiene_color; }
            else mul[3] = mat_dif_a;                         /* con luces: el alfa del difuso del material */
        } else return 2;
    } else return 2;
    if (vc != va) {
        /* uno de los dos usa el color del vértice y el otro no: sólo se puede si el vértice no trae color */
        if (tiene_color) return 3;
    }
    *vertice = vc && va;
    return 0;
}

/* matrices de Direct3D (fila = vector): r = a × b */
static void fx_mul44(const float *a, const float *b, float *r)
{
    for (int i = 0; i < 4; i++)
        for (int j = 0; j < 4; j++)
            r[i * 4 + j] = a[i * 4 + 0] * b[0 * 4 + j] + a[i * 4 + 1] * b[1 * 4 + j] + a[i * 4 + 2] * b[2 * 4 + j]
                         + a[i * 4 + 3] * b[3 * 4 + j];
}

/* ★ turno 18e · la inversa de una 4×4 (Gauss-Jordan con pivote). Devuelve 0 si no tiene. */
static int fx_inv44(const float *a, float *r)
{
    double m[4][8];
    for (int i = 0; i < 4; i++)
        for (int j = 0; j < 8; j++) m[i][j] = j < 4 ? a[i * 4 + j] : (j - 4 == i ? 1.0 : 0.0);
    for (int c = 0; c < 4; c++) {
        int pv = c;
        for (int i = c + 1; i < 4; i++) if ((m[i][c] < 0 ? -m[i][c] : m[i][c]) > (m[pv][c] < 0 ? -m[pv][c] : m[pv][c])) pv = i;
        if (m[pv][c] > -1e-12 && m[pv][c] < 1e-12) return 0;
        if (pv != c) for (int j = 0; j < 8; j++) { double x = m[c][j]; m[c][j] = m[pv][j]; m[pv][j] = x; }
        double d = m[c][c];
        for (int j = 0; j < 8; j++) m[c][j] /= d;
        for (int i = 0; i < 4; i++)
            if (i != c) { double f = m[i][c]; for (int j = 0; j < 8; j++) m[i][j] -= f * m[c][j]; }
    }
    for (int i = 0; i < 4; i++)
        for (int j = 0; j < 4; j++) r[i * 4 + j] = (float)m[i][j + 4];
    return 1;
}

/* la cámara en el mundo, de la matriz de vista (rotación ortonormal + traslación): cam = −t × Rᵀ */
static void fx_camara(const float *v, float *cam)
{
    for (int j = 0; j < 3; j++)
        cam[j] = -(v[12] * v[j * 4 + 0] + v[13] * v[j * 4 + 1] + v[14] * v[j * 4 + 2]);
}

/* las luces del perfil al mundo: (p − ancla_pos) × Mundo del ancla. Las que sobran quedan «apagadas» (1/r² = 1e20).
 *   pos[32][4] = x, y, z, 1/radio² ; col[32][4] = r·i, g·i, b·i, parpadeo */
static void fx_luces_al_mundo(const FX_PERFIL *pf, const float *mundo_ancla, float pos[][4], float col[][4])
{
    float esc = 1.0f;
    if (mundo_ancla) {
        float s2 = mundo_ancla[0] * mundo_ancla[0] + mundo_ancla[1] * mundo_ancla[1] + mundo_ancla[2] * mundo_ancla[2];
        float x = 1.0f;
        for (int it = 0; it < 30 && s2 > 0.0f; it++) x = 0.5f * (x + s2 / x);
        if (s2 > 0.0f) esc = x;
    }
    for (int i = 0; i < FX_MAX_LUCES; i++) {
        if (i >= pf->nluces || !pf->luces_activo) {
            pos[i][0] = pos[i][1] = pos[i][2] = 0.0f;
            pos[i][3] = 1e20f;
            col[i][0] = col[i][1] = col[i][2] = col[i][3] = 0.0f;
            continue;
        }
        const float *l = pf->luz[i];
        float p[3] = { l[0], l[1], l[2] };
        if (mundo_ancla) {
            if (pf->tiene_ancla_pos) { p[0] -= pf->ancla_pos[0]; p[1] -= pf->ancla_pos[1]; p[2] -= pf->ancla_pos[2]; }
            const float *m = mundo_ancla;
            float q[3];
            for (int j = 0; j < 3; j++) q[j] = p[0] * m[0 * 4 + j] + p[1] * m[1 * 4 + j] + p[2] * m[2 * 4 + j] + m[3 * 4 + j];
            p[0] = q[0]; p[1] = q[1]; p[2] = q[2];
        }
        float r = l[3] * esc;
        pos[i][0] = p[0]; pos[i][1] = p[1]; pos[i][2] = p[2];
        pos[i][3] = 1.0f / (r * r);
        float k = l[7] * pf->luces_int;
        col[i][0] = l[4] * k; col[i][1] = l[5] * k; col[i][2] = l[6] * k; col[i][3] = l[8];
    }
}

/* ★ turno 3 · un punto de la escena del .md9 al mundo, como las luces: (p − ancla_pos) × Mundo del ancla */
static void fx_punto_al_mundo(const FX_PERFIL *pf, const float *mundo_ancla, const float *p, float *out)
{
    float q[3] = { p[0], p[1], p[2] };
    if (!mundo_ancla) { out[0] = q[0]; out[1] = q[1]; out[2] = q[2]; return; }
    if (pf->tiene_ancla_pos) { q[0] -= pf->ancla_pos[0]; q[1] -= pf->ancla_pos[1]; q[2] -= pf->ancla_pos[2]; }
    const float *m = mundo_ancla;
    for (int j = 0; j < 3; j++) out[j] = q[0] * m[0 * 4 + j] + q[1] * m[1 * 4 + j] + q[2] * m[2 * 4 + j] + m[3 * 4 + j];
}

/* ★ turno 4 · lo contrario: un punto del MUNDO a la escena del .md9 (para saber de qué nodo es un dibujo).
 *   p = (q − traslación del ancla) × inversa(3×3 del ancla) + ancla_pos. Devuelve 0 si el ancla no se puede invertir. */
static int fx_al_md9(const FX_PERFIL *pf, const float *m, const float *q, float *out)
{
    float a = m[0], b = m[1], c = m[2], d = m[4], e = m[5], f = m[6], g = m[8], h = m[9], i = m[10];
    float A = e * i - f * h, B = -(d * i - f * g), C = d * h - e * g;
    float det = a * A + b * B + c * C;
    if (det > -1e-12f && det < 1e-12f) return 0;
    float r = 1.0f / det;
    /* la inversa (fila = vector, como Direct3D) */
    float inv[9] = { A * r, -(b * i - c * h) * r, (b * f - c * e) * r,
                     B * r, (a * i - c * g) * r, -(a * f - c * d) * r,
                     C * r, -(a * h - b * g) * r, (a * e - b * d) * r };
    float x[3] = { q[0] - m[12], q[1] - m[13], q[2] - m[14] };
    for (int j = 0; j < 3; j++) out[j] = x[0] * inv[0 * 3 + j] + x[1] * inv[1 * 3 + j] + x[2] * inv[2 * 3 + j];
    if (pf->tiene_ancla_pos) { out[0] += pf->ancla_pos[0]; out[1] += pf->ancla_pos[1]; out[2] += pf->ancla_pos[2]; }
    return 1;
}

/* ★ turno 4 · EL Z-FIGHTING: ¿es una proyección perspectiva de Direct3D centrada? (fila = vector:
 *   _11 = xs, _22 = ys, _33 = f/(f−n), _34 = 1, _43 = −n·f/(f−n), todo lo demás 0). Devuelve near y far. */
static float fx_abs(float x) { return x < 0.0f ? -x : x; }
static int fx_proj_perspectiva(const float *p, float *n, float *f)
{
    static const int ceros[11] = { 1, 2, 3, 4, 6, 7, 8, 9, 12, 13, 15 };
    for (int k = 0; k < 11; k++)
        if (fx_abs(p[ceros[k]]) > 1e-6f) return 0;
    if (p[0] <= 0.0f || p[5] <= 0.0f || fx_abs(p[11] - 1.0f) > 1e-6f || p[10] <= 1.0f || p[14] >= 0.0f) return 0;
    *n = -p[14] / p[10];
    *f = -p[14] / (p[10] - 1.0f);
    return 1;
}

/* la misma proyección con OTRO near (y el mismo far): sólo cambian _33 y _43 ⇒ x, y en la pantalla, iguales */
static void fx_proj_cercano(const float *p, float nuevo, float *out)
{
    float n, f;
    for (int k = 0; k < 16; k++) out[k] = p[k];
    if (!fx_proj_perspectiva(p, &n, &f) || nuevo >= f) return;
    float q = f / (f - nuevo);
    out[10] = q;
    out[14] = -nuevo * q;
}

/* ¿se reescribe ESTA proyección? 3 = sí (y `out` es la nueva) · 0 = no es la de la isla (forma, near o far) ·
 *   1 = la escena no es la isla (no se dibujó una textura suya hace < 250 ms) · 2 = la cámara está cerca del origen
 *   (un personaje en primer plano). `v` = la VIEW puesta (el juego la fija ANTES que la PROJ). */
#define FX_ISLA_MS 250
static int fx_cercano_decide(const float *p, const float *v, DWORD ahora, DWORD tick_isla, float ojo_min, float nuevo,
                             float *out, float *n_out, float *f_out, float *ojo_out)
{
    float n = 0, f = 0, cam[3];
    *ojo_out = 0;
    if (!fx_proj_perspectiva(p, &n, &f)) return 0;
    *n_out = n; *f_out = f;
    if (n < 0.5f || n > 2.0f || f < 30000.0f || f > 50000.0f || nuevo <= n || nuevo >= f * 0.5f) return 0;
    if (!tick_isla || (LONG)(ahora - tick_isla) > FX_ISLA_MS) return 1;     /* ★ turno 7: con signo */
    fx_camara(v, cam);
    float d2 = cam[0] * cam[0] + cam[1] * cam[1] + cam[2] * cam[2], x = d2 > 1.0f ? d2 : 1.0f;
    for (int it = 0; it < 40; it++) x = 0.5f * (x + d2 / x);
    *ojo_out = d2 > 0.0f ? x : 0.0f;
    if (d2 < ojo_min * ojo_min) return 2;
    fx_proj_cercano(p, nuevo, out);
    return 3;
}

/* ★ turno 7 · LAS CAMPANILLAS, UNA VEZ POR VISITA. Medido en el juego (turno 6): 56 disparos en 60 s. Dos fallas:
 *   1. el «tick» de la isla se guardaba como GetTickCount() | 1: en un milisegundo par quedaba 1 ms EN EL FUTURO, y
 *      `ahora − tick` (sin signo) daba 4.294.967.295 ⇒ «hace más de 1,5 s que no se dibuja» ⇒ visita nueva / «salió».
 *      Ahora el tick es el de verdad y toda resta de tiempos va CON signo (fx_ms).
 *   2. la visita se adivinaba por huecos de dibujo, y con la ventana en segundo plano hay huecos. Ahora:
 *      · la visita la dice el JUEGO: el reinicio del front.ani (las dos llamadas a 0x655C20 con «front.ani» desde el
 *        cuadro 0, 0x49AB2B al cargar y 0x4C3FE0 al entrar a la escena del frente) — un contador que sube una cueva
 *        de 11 bytes antes de saltar a 0x655C20 (fx_enganchar_ani). Sin el gancho (bytes distintos), por huecos de
 *        ≥ 2 s sin dibujar la isla;
 *      · por HUECOS (sin el gancho): nunca dos veces en menos de 20 s (esa visita queda muda);
 *      · por el .ani (★ turno 8, medido en el juego: el reinicio n.º 1 es la BIENVENIDA, el n.º 2 el LOBBY a < 20 s, y
 *        con la guarda el lobby quedaba mudo): cada reinicio CORTA lo que suena (fundido de 150 ms) y rearma, SIN la
 *        guarda de 20 s ⇒ suena en la intro, se corta al entrar al lobby y vuelve a sonar entera con su trineo;
 *      · se corta también si la isla lleva ≥ 2 s sin dibujarse (pasó a otra escena: sala, carrera). */
#define FX_CAMP_HUECO   2000
#define FX_CAMP_ENTRE  20000
typedef struct {
    DWORD ultima_isla;          /* el último dibujo de la isla (0 = nunca) */
    DWORD ultimo_toque;         /* cuándo sonó la última vez (0 = nunca) */
    LONG  ani_visto;            /* el contador de reinicios del front.ani que ya se usó */
    int   hay_gancho;           /* 1 = la visita la dice el reinicio del .ani */
    int   armada;               /* 1 = en esta visita todavía no sonó */
    DWORD visita_t0;
    long  toques, mudas;        /* (para la sonda y el banco) */
    int   hay_isla, hay_toque;  /* ★ turno 8: «nunca» es una bandera, no el tick 0 (el reloj también pasa por 0) */
} FX_CAMP;

static LONG fx_ms(DWORD ahora, DWORD antes) { return (LONG)(ahora - antes); }   /* CON signo: sin el «futuro» */

/* un dibujo de la isla en `ahora`; `ani` = el contador de reinicios del front.ani; `trineo` = 1 si este dibujo es el
 * trineo y se ve. Devuelve 1 si hay que tocar las campanillas AHORA. */
static int fx_camp_isla(FX_CAMP *c, DWORD ahora, LONG ani, int trineo)
{
    if (c->hay_gancho) {
        if (ani != c->ani_visto) { c->ani_visto = ani; c->armada = 1; c->visita_t0 = ahora; }
    } else if (!c->hay_isla || fx_ms(ahora, c->ultima_isla) >= FX_CAMP_HUECO) {
        c->armada = 1;
        c->visita_t0 = ahora;
    }
    if (!c->hay_isla || fx_ms(ahora, c->ultima_isla) > 0) { c->ultima_isla = ahora; c->hay_isla = 1; }
    if (!c->armada || !trineo) return 0;
    c->armada = 0;
    if (!c->hay_gancho && c->hay_toque && fx_ms(ahora, c->ultimo_toque) < FX_CAMP_ENTRE) { c->mudas++; return 0; }
    c->ultimo_toque = ahora;
    c->hay_toque = 1;
    c->toques++;
    return 1;
}

/* ¿se cortan? (sonando): la isla lleva ≥ 2 s sin dibujarse, o (con el gancho) el .ani se reinició desde que empezaron
 *   a sonar (`ani_al_tocar` = c->ani_visto en ese momento) */
static int fx_camp_cortar(const FX_CAMP *c, DWORD ahora)
{
    return c->hay_isla && fx_ms(ahora, c->ultima_isla) >= FX_CAMP_HUECO;
}
/* ★ turno 8 · ¿la cámara es la del LOBBY? (anonimo03: «debe salir al aparecer el trineo YA EN EL LOBBY, no en la
 *   bienvenida»). El reinicio n.º 1 del .ani es la INTRO, que también dibuja la isla y el trineo; la diferencia es la
 *   cámara: en el lobby (camera_front_front.xml) el ojo queda en (731, 8214, −18955) ± unas unidades; en la intro viaja
 *   de (−2249, 7081, −20589) — a 3.580 de ésa — hasta (544, 667, −6678). `ojo` = x, y, z, radio (0 = no mirar). */
static int fx_ojo_cerca(const float *vista, const float *ojo)
{
    float cam[3];
    if (ojo[3] <= 0.0f) return 1;
    fx_camara(vista, cam);
    float dx = cam[0] - ojo[0], dy = cam[1] - ojo[1], dz = cam[2] - ojo[2];
    return dx * dx + dy * dy + dz * dz <= ojo[3] * ojo[3];
}

static int fx_camp_corte(const FX_CAMP *c, DWORD ahora, LONG ani_al_tocar)
{
    return fx_camp_cortar(c, ahora) || (c->hay_gancho && c->ani_visto != ani_al_tocar);
}

/* ★ turno 9 · LOS MIPS de las texturas de la isla. MEDIDO (sonda, turno 5): el juego crea cada textura con UN nivel
 *   (CreateTexture(…, niveles = 1, …) en 0x6419A8) aunque los .dds traen 11: lo lejano se dibuja con el nivel 0 y
 *   «titila» al mover la cámara (ráfagas del director, turno 9: la isla de fábrica 145 píxeles por terna, la polar 155:
 *   es del juego). Al cargar una textura de rnr_ui_bg/front/ (DXT1/3/5, un nivel, lados múltiplos de 4) la dll arma
 *   la cadena entera EN EL MISMO FORMATO: decodifica el nivel 0, lo promedia de a 2×2 y vuelve a codificar cada nivel
 *   (hasta 4×4), crea la textura nueva (D3DPOOL_MANAGED, mismo formato), copia el nivel 0 TAL CUAL y la pone en lugar
 *   de la del juego en su vector. Costo medido: 6,5 → 8,7 MB las 114 texturas. Si algo falla, queda la del juego.
 *   En los dibujos de la isla: filtro de mips lineal + anisotrópico ([isla_fx] aniso=4), y se devuelve como estaba.
 *   [isla_fx] mips=1 (0 = como el juego) · aniso=4 (1 = trilineal sin anisotrópico) */

/* un color 565 → r, g, b (0..255) */
static void fx_565(WORD c, BYTE *o)
{
    o[0] = (BYTE)(((c >> 11) & 31) * 255 / 31);
    o[1] = (BYTE)(((c >> 5) & 63) * 255 / 63);
    o[2] = (BYTE)((c & 31) * 255 / 31);
}

/* un bloque 4×4 → 16 píxeles RGBA. fmt: 1 = DXT1, 3 = DXT3, 5 = DXT5 */
static void fx_dxt_leer(const BYTE *b, int fmt, BYTE px[16][4])
{
    const BYTE *cb = fmt == 1 ? b : b + 8;
    WORD c0 = (WORD)(cb[0] | (cb[1] << 8)), c1 = (WORD)(cb[2] | (cb[3] << 8));
    BYTE pal[4][4];
    fx_565(c0, pal[0]); fx_565(c1, pal[1]);
    pal[0][3] = pal[1][3] = 255;
    if (fmt != 1 || c0 > c1) {
        for (int k = 0; k < 3; k++) {
            pal[2][k] = (BYTE)((2 * pal[0][k] + pal[1][k]) / 3);
            pal[3][k] = (BYTE)((pal[0][k] + 2 * pal[1][k]) / 3);
        }
        pal[2][3] = pal[3][3] = 255;
    } else {
        for (int k = 0; k < 3; k++) { pal[2][k] = (BYTE)((pal[0][k] + pal[1][k]) / 2); pal[3][k] = 0; }
        pal[2][3] = 255; pal[3][3] = 0;                          /* el transparente de DXT1 */
    }
    DWORD idx = (DWORD)cb[4] | ((DWORD)cb[5] << 8) | ((DWORD)cb[6] << 16) | ((DWORD)cb[7] << 24);
    for (int i = 0; i < 16; i++) {
        int s = (idx >> (2 * i)) & 3;
        px[i][0] = pal[s][0]; px[i][1] = pal[s][1]; px[i][2] = pal[s][2]; px[i][3] = pal[s][3];
    }
    if (fmt == 3) {
        for (int i = 0; i < 16; i++) {
            int a = (b[i / 2] >> (4 * (i & 1))) & 15;
            px[i][3] = (BYTE)(a * 17);
        }
    } else if (fmt == 5) {
        int a0 = b[0], a1 = b[1], tab[8];
        tab[0] = a0; tab[1] = a1;
        if (a0 > a1) for (int k = 1; k <= 6; k++) tab[k + 1] = ((7 - k) * a0 + k * a1) / 7;
        else { for (int k = 1; k <= 4; k++) tab[k + 1] = ((5 - k) * a0 + k * a1) / 5; tab[6] = 0; tab[7] = 255; }
        unsigned long long bits = 0;
        for (int k = 0; k < 6; k++) bits |= (unsigned long long)b[2 + k] << (8 * k);
        for (int i = 0; i < 16; i++) px[i][3] = (BYTE)tab[(bits >> (3 * i)) & 7];
    }
}

static WORD fx_a565(const int *c)
{
    return (WORD)(((c[0] * 31 + 127) / 255) << 11 | ((c[1] * 63 + 127) / 255) << 5 | ((c[2] * 31 + 127) / 255));
}

/* 16 píxeles RGBA → un bloque. El color: los extremos de la caja de colores sobre su diagonal (rápido y suficiente
 * para un mip); DXT1 con algún píxel transparente (alfa < 128) usa el modo de 3 colores + transparente. */
static void fx_dxt_escribir(const BYTE px[16][4], int fmt, BYTE *b)
{
    BYTE *cb = fmt == 1 ? b : b + 8;
    int lo[3] = { 255, 255, 255 }, hi[3] = { 0, 0, 0 }, transp = 0, n = 0;
    for (int i = 0; i < 16; i++) {
        if (fmt == 1 && px[i][3] < 128) { transp = 1; continue; }
        n++;
        for (int k = 0; k < 3; k++) { if (px[i][k] < lo[k]) lo[k] = px[i][k]; if (px[i][k] > hi[k]) hi[k] = px[i][k]; }
    }
    if (!n) { lo[0] = lo[1] = lo[2] = hi[0] = hi[1] = hi[2] = 0; }
    /* los extremos sobre el EJE PRINCIPAL de los colores (la caja sola falla cuando un canal sube y otro baja: lo
     * midió el banco): media, covarianza, el eje por iteración de potencias, y las proyecciones mínima y máxima */
    float m[3] = { 0, 0, 0 }, cv[6] = { 0, 0, 0, 0, 0, 0 };
    for (int i = 0; i < 16; i++) {
        if (fmt == 1 && px[i][3] < 128) continue;
        for (int k = 0; k < 3; k++) m[k] += px[i][k];
    }
    for (int k = 0; k < 3; k++) m[k] /= (float)(n ? n : 1);
    for (int i = 0; i < 16; i++) {
        if (fmt == 1 && px[i][3] < 128) continue;
        float r = px[i][0] - m[0], g = px[i][1] - m[1], bb = px[i][2] - m[2];
        cv[0] += r * r; cv[1] += r * g; cv[2] += r * bb; cv[3] += g * g; cv[4] += g * bb; cv[5] += bb * bb;
    }
    float ax[3] = { (float)(hi[0] - lo[0]) + 1.0f, (float)(hi[1] - lo[1]) + 1.0f, (float)(hi[2] - lo[2]) + 1.0f };
    for (int it = 0; it < 8; it++) {
        float x = cv[0] * ax[0] + cv[1] * ax[1] + cv[2] * ax[2];
        float y = cv[1] * ax[0] + cv[3] * ax[1] + cv[4] * ax[2];
        float zz = cv[2] * ax[0] + cv[4] * ax[1] + cv[5] * ax[2];
        float mx = fx_abs(x) > fx_abs(y) ? fx_abs(x) : fx_abs(y);
        if (fx_abs(zz) > mx) mx = fx_abs(zz);
        if (mx < 1e-6f) break;
        ax[0] = x / mx; ax[1] = y / mx; ax[2] = zz / mx;
    }
    float l2 = ax[0] * ax[0] + ax[1] * ax[1] + ax[2] * ax[2], tmin = 0, tmax = 0;
    if (l2 < 1e-12f) { ax[0] = ax[1] = ax[2] = 0.57735f; l2 = 1.0f; }
    for (int i = 0; i < 16; i++) {
        if (fmt == 1 && px[i][3] < 128) continue;
        float s = ((px[i][0] - m[0]) * ax[0] + (px[i][1] - m[1]) * ax[1] + (px[i][2] - m[2]) * ax[2]) / l2;
        if (s < tmin) tmin = s;
        if (s > tmax) tmax = s;
    }
    int a[3], z[3];
    for (int k = 0; k < 3; k++) {
        float va = m[k] + ax[k] * tmax, vz = m[k] + ax[k] * tmin;
        a[k] = va < 0 ? 0 : va > 255 ? 255 : (int)(va + 0.5f);
        z[k] = vz < 0 ? 0 : vz > 255 ? 255 : (int)(vz + 0.5f);
    }
    WORD c0 = fx_a565(a), c1 = fx_a565(z);
    int cuatro = !(fmt == 1 && transp);
    if (cuatro) {
        if (c0 < c1) { WORD t = c0; c0 = c1; c1 = t; }
        if (c0 == c1) { if (c1 > 0) c1--; else c0++; }
    } else if (c0 > c1) { WORD t = c0; c0 = c1; c1 = t; }
    cb[0] = (BYTE)c0; cb[1] = (BYTE)(c0 >> 8); cb[2] = (BYTE)c1; cb[3] = (BYTE)(c1 >> 8);
    BYTE pal[4][4];
    fx_565(c0, pal[0]); fx_565(c1, pal[1]);
    int np = cuatro ? 4 : 3;
    for (int k = 0; k < 3; k++) {
        if (cuatro) { pal[2][k] = (BYTE)((2 * pal[0][k] + pal[1][k]) / 3); pal[3][k] = (BYTE)((pal[0][k] + 2 * pal[1][k]) / 3); }
        else pal[2][k] = (BYTE)((pal[0][k] + pal[1][k]) / 2);
    }
    DWORD idx = 0;
    for (int i = 0; i < 16; i++) {
        int s = 0;
        if (!cuatro && px[i][3] < 128) s = 3;
        else {
            int mejor = 1 << 30;
            for (int q = 0; q < np; q++) {
                int d0 = px[i][0] - pal[q][0], d1 = px[i][1] - pal[q][1], d2 = px[i][2] - pal[q][2];
                int d = d0 * d0 * 3 + d1 * d1 * 6 + d2 * d2;
                if (d < mejor) { mejor = d; s = q; }
            }
        }
        idx |= (DWORD)s << (2 * i);
    }
    cb[4] = (BYTE)idx; cb[5] = (BYTE)(idx >> 8); cb[6] = (BYTE)(idx >> 16); cb[7] = (BYTE)(idx >> 24);
    if (fmt == 3) {
        for (int i = 0; i < 8; i++) b[i] = (BYTE)(((px[2 * i][3] + 8) / 17) | (((px[2 * i + 1][3] + 8) / 17) << 4));
    } else if (fmt == 5) {
        int a0 = 0, a1 = 255;
        for (int i = 0; i < 16; i++) { if (px[i][3] > a0) a0 = px[i][3]; if (px[i][3] < a1) a1 = px[i][3]; }
        if (a0 == a1) { if (a1 > 0) a1--; else a0++; }
        int tab[8];
        tab[0] = a0; tab[1] = a1;
        for (int k = 1; k <= 6; k++) tab[k + 1] = ((7 - k) * a0 + k * a1) / 7;
        unsigned long long bits = 0;
        for (int i = 0; i < 16; i++) {
            int s = 0, mejor = 1 << 30;
            for (int q = 0; q < 8; q++) { int d = px[i][3] - tab[q]; d = d < 0 ? -d : d; if (d < mejor) { mejor = d; s = q; } }
            bits |= (unsigned long long)s << (3 * i);
        }
        b[0] = (BYTE)a0; b[1] = (BYTE)a1;
        for (int k = 0; k < 6; k++) b[2 + k] = (BYTE)(bits >> (8 * k));
    }
}

/* una imagen DXT (w×h, `paso` bytes por fila de bloques) ↔ RGBA (w×h×4) */
static void fx_dxt_a_rgba(const BYTE *d, int paso, int w, int h, int fmt, BYTE *rgba)
{
    int tb = fmt == 1 ? 8 : 16;
    BYTE px[16][4];
    for (int by = 0; by < (h + 3) / 4; by++)
        for (int bx = 0; bx < (w + 3) / 4; bx++) {
            fx_dxt_leer(d + by * paso + bx * tb, fmt, px);
            for (int i = 0; i < 16; i++) {
                int x = bx * 4 + (i & 3), y = by * 4 + (i >> 2);
                if (x < w && y < h) CopyMemory(rgba + (y * w + x) * 4, px[i], 4);
            }
        }
}

static void fx_rgba_a_dxt(const BYTE *rgba, int w, int h, int fmt, BYTE *d, int paso)
{
    int tb = fmt == 1 ? 8 : 16;
    BYTE px[16][4];
    for (int by = 0; by < (h + 3) / 4; by++)
        for (int bx = 0; bx < (w + 3) / 4; bx++) {
            for (int i = 0; i < 16; i++) {
                int x = bx * 4 + (i & 3), y = by * 4 + (i >> 2);
                if (x >= w) x = w - 1;
                if (y >= h) y = h - 1;
                CopyMemory(px[i], rgba + (y * w + x) * 4, 4);
            }
            fx_dxt_escribir(px, fmt, d + by * paso + bx * tb);
        }
}

/* el promedio de a 2×2 (el siguiente nivel). En DXT1 el alfa es «sí o no»: se promedia y se corta en la mitad. */
static void fx_mip_bajar(const BYTE *s, int w, int h, BYTE *d)
{
    int w2 = w > 1 ? w / 2 : 1, h2 = h > 1 ? h / 2 : 1;
    for (int y = 0; y < h2; y++)
        for (int x = 0; x < w2; x++)
            for (int k = 0; k < 4; k++) {
                int x0 = x * 2, y0 = y * 2, x1 = x0 + 1 < w ? x0 + 1 : x0, y1 = y0 + 1 < h ? y0 + 1 : y0;
                d[(y * w2 + x) * 4 + k] = (BYTE)((s[(y0 * w + x0) * 4 + k] + s[(y0 * w + x1) * 4 + k]
                                                  + s[(y1 * w + x0) * 4 + k] + s[(y1 * w + x1) * 4 + k] + 2) / 4);
            }
}

/* cuántos niveles: hasta que el lado chico llegue a 4 (los bloques DXT) */
static int fx_mip_niveles(int w, int h)
{
    int n = 1;
    while ((w >> n) >= 4 && (h >> n) >= 4) n++;
    return n;
}

/* ★ turno 13 · ¿«nombre» está en la lista «a, b, c»? (nombres de textura sin carpeta ni extensión, sin mayúsculas) */
static int fx_en_lista(const char *lista, const char *nombre)
{
    const char *p = lista;
    while (*p) {
        while (*p == ' ' || *p == '\t' || *p == ',') p++;
        if (!*p) break;
        char t[96], b[FX_LARGO_NOM];
        int i = 0;
        while (*p && *p != ',' && *p != ' ' && *p != '\t' && i < 95) t[i++] = *p++;
        t[i] = 0;
        fx_nombre_base(t, b, sizeof(b));
        if (lstrcmpiA(b, nombre) == 0) return 1;
    }
    return 0;
}

/* ★ turno 12 · COLORES FALSOS para cazar el glitch: cada textura su MATIZ (razón de oro: vecinas bien distintas) y
 *   el BRILLO según el orden de la llamada en el cuadro (n mod 4: 100 / 82 / 64 / 46 %). Devuelve 0xFFRRGGBB. */
static DWORD fx_color_falso(int id, long n)
{
    static const float brillo[4] = { 1.0f, 0.82f, 0.64f, 0.46f };
    float h = (float)id * 0.6180339887f;
    h -= (float)(int)h;
    float v = brillo[((n % 4) + 4) % 4], s = 0.85f, c = v * s, x6 = h * 6.0f;
    int sector = (int)x6;
    float f = x6 - (float)sector, rgb[3];
    float p = v - c, q = v - c * f, u = v - c * (1.0f - f);
    switch (sector % 6) {
    case 0: rgb[0] = v; rgb[1] = u; rgb[2] = p; break;
    case 1: rgb[0] = q; rgb[1] = v; rgb[2] = p; break;
    case 2: rgb[0] = p; rgb[1] = v; rgb[2] = u; break;
    case 3: rgb[0] = p; rgb[1] = q; rgb[2] = v; break;
    case 4: rgb[0] = u; rgb[1] = p; rgb[2] = v; break;
    default: rgb[0] = v; rgb[1] = p; rgb[2] = q; break;
    }
    DWORD r = (DWORD)(rgb[0] * 255.0f + 0.5f), g = (DWORD)(rgb[1] * 255.0f + 0.5f), b = (DWORD)(rgb[2] * 255.0f + 0.5f);
    return 0xFF000000u | (r << 16) | (g << 8) | b;
}

/* ── la tabla de marcas: puntero de textura → entrada del perfil ─────────────────────────────────────────── */
#define FX_HASH 2048
#define FX_BORRADA ((void *)1)
static void *volatile g_fx_hk[FX_HASH];
static short          g_fx_hv[FX_HASH];
static volatile LONG  g_fx_nmarcas = 0;

static DWORD fx_h(const void *p) { DWORD x = (DWORD)(ULONG_PTR)p; x ^= x >> 11; x *= 0x9E3779B1u; return (x >> 7) & (FX_HASH - 1); }

static int fx_marcar(void *tex, int idx)
{
    DWORD h = fx_h(tex);
    int libre = -1;
    for (int i = 0; i < FX_HASH; i++, h = (h + 1) & (FX_HASH - 1)) {
        void *k = g_fx_hk[h];
        if (k == tex) { g_fx_hv[h] = (short)idx; return 1; }
        if (k == FX_BORRADA && libre < 0) libre = (int)h;
        if (k == NULL) { if (libre < 0) libre = (int)h; break; }
    }
    if (libre < 0) return 0;
    g_fx_hv[libre] = (short)idx;                              /* el valor ANTES que la llave */
    g_fx_hk[libre] = tex;
    InterlockedIncrement(&g_fx_nmarcas);
    return 1;
}

static int fx_buscar(const void *tex)
{
    DWORD h = fx_h(tex);
    for (int i = 0; i < FX_HASH; i++, h = (h + 1) & (FX_HASH - 1)) {
        void *k = g_fx_hk[h];
        if (k == tex) return g_fx_hv[h];
        if (k == NULL) return -1;
    }
    return -1;
}

static void fx_desmarcar(const void *tex)
{
    DWORD h = fx_h(tex);
    for (int i = 0; i < FX_HASH; i++, h = (h + 1) & (FX_HASH - 1)) {
        void *k = g_fx_hk[h];
        if (k == tex) { g_fx_hk[h] = FX_BORRADA; InterlockedDecrement(&g_fx_nmarcas); return; }
        if (k == NULL) return;
    }
}

/* ══ de acá para abajo, lo que toca el juego y Direct3D ══════════════════════════════════════════════════════ */

#define FXV(o) (*(void ***)(o))
typedef ULONG   (WINAPI *FX_SOLTAR)(void *);
typedef HRESULT (WINAPI *FX_GETTEX_F)(void *, DWORD, void **);
typedef HRESULT (WINAPI *FX_GETTR_F)(void *, DWORD, float *);
typedef HRESULT (WINAPI *FX_GETRS_F)(void *, DWORD, DWORD *);
typedef HRESULT (WINAPI *FX_SETRS_F)(void *, DWORD, DWORD);
typedef HRESULT (WINAPI *FX_GETTSS_F)(void *, DWORD, DWORD, DWORD *);
typedef HRESULT (WINAPI *FX_GETF_F)(void *, DWORD *);
typedef HRESULT (WINAPI *FX_SETF_F)(void *, DWORD);
typedef HRESULT (WINAPI *FX_GETSH_F)(void *, void **);
typedef HRESULT (WINAPI *FX_SETSH_F)(void *, void *);
typedef HRESULT (WINAPI *FX_SETC_F)(void *, UINT, const float *, UINT);
typedef HRESULT (WINAPI *FX_CREASH_F)(void *, const DWORD *, void **);
typedef HRESULT (WINAPI *FX_GETMAT_F)(void *, float *);
typedef HRESULT (WINAPI *FX_CAPS_F)(void *, void *);
typedef HRESULT (WINAPI *FX_PRIV_GET)(void *, const GUID *, void *, DWORD *);
typedef HRESULT (WINAPI *FX_PRIV_SET)(void *, const GUID *, const void *, DWORD, DWORD);
typedef HRESULT (WINAPI *FX_D81)(void *, DWORD, UINT, UINT);
typedef HRESULT (WINAPI *FX_D82)(void *, DWORD, INT, UINT, UINT, UINT, UINT);
typedef HRESULT (WINAPI *FX_D83)(void *, DWORD, UINT, const void *, UINT);
typedef HRESULT (WINAPI *FX_D84)(void *, DWORD, UINT, UINT, UINT, const void *, DWORD, const void *, UINT);
typedef HRESULT (WINAPI *FX_PRESENT_F)(void *, const void *, const void *, HWND, const void *);
typedef HRESULT (WINAPI *FX_RESET_F)(void *, void *);
typedef HRESULT (WINAPI *FX_GETRT_F)(void *, DWORD, void **);
typedef HRESULT (WINAPI *FX_SETRT_F)(void *, DWORD, void *);
typedef HRESULT (WINAPI *FX_GETDS_F)(void *, void **);
typedef HRESULT (WINAPI *FX_SETDS_F)(void *, void *);
typedef HRESULT (WINAPI *FX_STRETCH_F)(void *, void *, const RECT *, void *, const RECT *, DWORD);
typedef HRESULT (WINAPI *FX_CREATETEX_F)(void *, UINT, UINT, UINT, DWORD, DWORD, DWORD, void **, HANDLE *);
typedef HRESULT (WINAPI *FX_NIVEL_F)(void *, UINT, void **);
typedef HRESULT (WINAPI *FX_DESC_F)(void *, DWORD *);
typedef HRESULT (WINAPI *FX_CREASB_F)(void *, DWORD, void **);
typedef HRESULT (WINAPI *FX_SB_F)(void *);
typedef HRESULT (WINAPI *FX_SETTEX_F)(void *, DWORD, void *);
typedef HRESULT (WINAPI *FX_SETSAMP_F)(void *, DWORD, DWORD, DWORD);
typedef HRESULT (WINAPI *FX_ESCENA_F)(void *);
typedef char    (__fastcall *FX_CARGAR_F)(void *obj, void *edx, void *nombre, void *mem);
typedef HRESULT (WINAPI *FX_DESC_NIVEL_F)(void *, UINT, DWORD *);   /* IDirect3DTexture9::GetLevelDesc (17) */
typedef DWORD   (WINAPI *FX_NIVELES_F)(void *);                     /* IDirect3DBaseTexture9::GetLevelCount (13) */

static void fx_soltar(void *o) { if (o) ((FX_SOLTAR)FXV(o)[2])(o); }

/* nuestro GUID para la marca dentro de la textura: {8E2B3F51-6C0A-4D7E-9A31-1F2E60C4B7A2} */
static const GUID g_fx_guid = { 0x8e2b3f51, 0x6c0a, 0x4d7e, { 0x9a, 0x31, 0x1f, 0x2e, 0x60, 0xc4, 0xb7, 0xa2 } };
/* ★ 21-nov · LO QUE NO SE DIBUJA CON «ELIGE TU PERSONAJE» (anonimo03: «que el gorila no se prenda en la pantalla de
 *   selección»). Con la cámara del selector el trineo pasa ENORME por delante y los renos y el trineo salen NEGROS
 *   (medido en el espejo: igual con DXVK y en d3d9 nativo). Cada textura de la lista se marca al cargarse (su propio
 *   GUID) y, mientras `g_sp_visible` (selector.c), sus dibujos se saltan. En el lobby vuela como siempre.
 *   [isla_fx] ocultar_en_selector = bases separadas por coma (vacío = no se oculta nada). */
static const GUID g_fx_guid_oculta = { 0x3d71a0c4, 0x52be, 0x4f19, { 0x8c, 0x07, 0x6a, 0xe4, 0x19, 0xd2, 0x5b, 0x83 } };
static char g_fx_ocultar[512] = "";                     /* ",base,base," en minúscula */
static volatile LONG g_fx_n_ocultas = 0, g_fx_n_saltados = 0;
static int g_fx_sonda_sel = 0;                          /* [isla_fx] sonda_selector=1: qué texturas dibujan 81/83 con el selector */
static int fx_en_lista_oc(const char *lista, const char *base)
{
    int n = lstrlenA(base);
    if (!n || !lista[0]) return 0;
    for (const char *p = lista; *p; p++)
        if (*p == ',' && p[1] && CompareStringA(LOCALE_INVARIANT, 0, p + 1, n, base, n) == CSTR_EQUAL && p[1 + n] == ',') return 1;
    return 0;
}
static DWORD WINAPI fx_mira_tabla(LPVOID p);
static void fx_ocultar_leer(const char *ini)
{
    char l[480];
    int j = 0;
    GetPrivateProfileStringA("isla_fx", "ocultar_en_selector", "nocull_xm_reno,nocull_xm_trineo_carga,nocull_xm_trineo_cuerpo,"
                             "nocull_xm_noel_acc,nocull_xm_noel_body,nocull_xm_noel_head,nocull_xm_noel_pants", l, sizeof(l), ini);
    g_fx_ocultar[j++] = ',';
    for (const char *p = l; *p && j < (int)sizeof(g_fx_ocultar) - 2; p++) {
        char c = *p;
        if (c == ' ' || c == '	') continue;
        if (c >= 'A' && c <= 'Z') c = (char)(c + 32);
        if (c == ',' && g_fx_ocultar[j - 1] == ',') continue;
        g_fx_ocultar[j++] = c;
    }
    if (g_fx_ocultar[j - 1] != ',') g_fx_ocultar[j++] = ',';
    g_fx_ocultar[j] = 0;
    if (j <= 1) g_fx_ocultar[0] = 0;
    g_fx_sonda_sel = GetPrivateProfileIntA("isla_fx", "sonda_selector", 0, ini);
    if (g_fx_sonda_sel >= 2) { HANDLE h = CreateThread(NULL, 0, fx_mira_tabla, NULL, 0, NULL); if (h) CloseHandle(h); }
}

/* ── el estado ── */
static int  g_fx_activo = 0, g_fx_sonda = 0, g_fx_noche = 1;
static int  g_fx_efecto[FX_NSOMB] = { 1, 1, 1, 1, 1 }, g_fx_brillo = 1;
static int  g_fx_perfil_ok = 0, g_fx_roto = 0, g_fx_brillo_roto = 0;
static FX_PERFIL g_fx_p;
static FX_CARGAR_F g_fx_cargar_real = NULL;
static long g_fx_cargadas = 0, g_fx_marcadas = 0, g_fx_fallos = 0;
static void *g_fx_dev = NULL;
static void *g_fx_vs[3] = { 0 }, *g_fx_ps[FX_SH_CUANTOS] = { 0 }, *g_fx_vs_pantalla = NULL, *g_fx_vs_halo = NULL;
static int  g_fx_creados = 0;                           /* 0 = no se intentó · 1 = listos · −1 = no se pudo */
static float g_fx_lpos[FX_MAX_LUCES][4], g_fx_lcol[FX_MAX_LUCES][4];
static float g_fx_ancla_m[16];
static int  g_fx_hay_ancla = 0;
static volatile LONG g_fx_d82_entradas = 0, g_fx_d82_isla = 0;   /* ★ 21-nov: el cuadro sin la capa 4 */
static void *volatile g_fx_esperado81 = NULL;
static volatile LONG g_fx_grabando = 0;                 /* ★ 21-nov: 1 entre BeginStateBlock y EndStateBlock */
static volatile DWORD g_fx_grab_t = 0;
static int fx_grabando(void) { return g_fx_grabando && GetTickCount() - g_fx_grab_t < 200; }   /* se vence sola */           /* ★ 21-nov: lo que tiene que haber en la entrada 81 */
static volatile LONG g_fx_dentro = 0;                   /* 1 mientras dibujamos lo nuestro (el brillo) */
static int  g_fx_isla_cuadro = 0, g_fx_brillo_hecho = 0;
static LARGE_INTEGER g_fx_qpf, g_fx_qp0;
static int  g_fx_vista_marca[FX_MAX_TEX];               /* la sonda: ya anotado el 1.er dibujo de esta textura */
static int  g_fx_motivo_visto[FX_MAX_TEX];
/* ★ turno 2 · la calidad, las luces elegidas para el cuadro y los dibujos DIFERIDOS (excluidos del brillo) */
static int  g_fx_nluz = 32;                              /* calidad: 32 alta · 16 media · 8 baja · ★ 64 alta estable */
static int  g_fx_luces_estables = 1;                     /* ★ turno 10: [isla_fx] luces_estables=1 */
/* ★ turno 27 (medido en la laptop vieja: Intel HD 5500 — ALTA 38 fps, sin el mar 60) · LA CALIDAD como nivel:
 *   2 alta · 1 media (mar con 3 octavas y 5 olas, la aurora reflejada quieta; 16 luces) · 0 baja (mar de 2 octavas,
 *   3 olas, 4 luces y sin la aurora reflejada; luces 8; el cielo con la aurora quieta; sin brillo). Se puede bajar
 *   andando (calidad=auto). */
static int  g_fx_calidad = 2, g_fx_brillo_pedido = 1, g_fx_auto = 0;
static long g_fx_auto_dib = 0;                           /* dibujos con efecto en este segundo (¿se ve la isla?) */
static long g_fx_n_luz_cambios = 0, g_fx_n_near1 = 0;    /* ★ turno 10: la sonda del parpadeo (por segundo) */
static long g_fx_n_resplandores = 0;                     /* ★ turno 14 */
static void *g_fx_tex_cielo = NULL;                      /* ★ turno 17: el cielo del juego (con AddRef), para el mar */
static int  g_fx_pisar_ps = 1;                           /* ★ turno 18: [isla_fx] pisar_ps (el selector) */
static void *g_fx_ps_ajeno = NULL;
static int  g_fx_pisar_vs = 3, g_fx_vs_ajeno_anotado = 0;   /* ★ turno 18b/c: [isla_fx] pisar_vs (0 nunca · 1 siempre · 2 sólo la normal) */
static void *g_fx_vs_ajeno = NULL;
/* ★ turno 18b · los motivos de salteo, por segundo: 0 capa apagada/rota · 1 textura sin efecto · 2 otro dispositivo ·
 *   3 sin sombreadores · 4 VS ajeno · 5 PS ajeno sin pisar · 6 FVF · 7 etapa 0 */
static long g_fx_salto[9];
static float g_fx_k_vs[10][4], g_fx_k_ps[160][4];          /* ★ turno 18f: las constantes del juego que pisamos */
static int  g_fx_k_vs_guardadas = 0, g_fx_k_ps_guardadas = 0;
static int  g_fx_niebla_ajena_anotada = 0;                /* ★ turno 18g */
static int  g_fx_mar_deriva = 1;                           /* ★ turno 18f: [isla_fx] mar_deriva (1 = hacia el horizonte) */                               /* 8 = ★ turno 18c: VS ajeno en una pasada NO normal */
static int  g_fx_pasadas_anotadas = 0;
static DWORD g_fx_pasadas_firma[8];
static long g_fx_n_ps_ajeno = 0;
static float g_fx_brillo_suave = 0.5f;                   /* ★ turno 10: [isla_fx] brillo_suave (0 = sin mezcla en el tiempo) */
static int  g_fx_trazar = 0, g_fx_traza_estado = 0;      /* ★ turno 11: la traza (ver «LA TRAZA DEL PARPADEO») */
static void fx_nombre_anotar(void *tex, const char *base);
static int  g_fx_nom_isla_ahora = 0;                     /* ★ turno 12: la textura que se anota es de la isla */
static void fx_traza_vista(const float *v);
static float g_fx_spos[FX_LUCES_SH][4], g_fx_scol[FX_LUCES_SH][4];
static float g_fx_v_ult[16];
static int  g_fx_luces_nuevas = 1;
static float g_fx_astro_m[3];                            /* ★ turno 3: el astro pintado, en el mundo */
#define FX_DIFERIDOS 8
static struct { int k; DWORD a[6]; void *sb; } g_fx_dif[FX_DIFERIDOS];
static int  g_fx_ndif = 0, g_fx_reproduciendo = 0;
static void *g_fx_sb_present = NULL;
static long g_fx_n_diferidos = 0, g_fx_dif_fallos = 0;
static void **g_fx_pr_vt = NULL;                         /* la tabla donde se engancharon Present y Reset */
/* ★ turno 4 · el near de la isla (z-fighting) */
static float g_fx_cercano = 100.0f, g_fx_cercano_ojo = 3000.0f;
static volatile DWORD g_fx_isla_tick = 0;                /* GetTickCount del último dibujo de una textura de la isla */
static long g_fx_n_cercano = 0, g_fx_n_cercano_no = 0, g_fx_cercano_total = 0;
static int  g_fx_cercano_no_anotados = 0;
/* ★ turno 5 · la sonda de las PROYECCIONES: cada PROJ distinta (forma + ojo) y, cada segundo, con qué PROJ se dibuja
 *   la isla de verdad (la bienvenida no pasaba por el near: ¿qué matriz usa?) */
static long g_fx_n_proj = 0;
static float g_fx_proj_vistas[24][4];
static int  g_fx_nproj_vistas = 0, g_fx_isla_proj_anotadas = 0, g_fx_z_anotado = 0;
static DWORD g_fx_isla_proj_t = 0;
static DWORD g_fx_cerc_t = 0;
static int  g_fx_idx_diferido = -1;                      /* ★ turno 5: la textura del dibujo que se va a diferir */
static long g_fx_n_halos = 0, g_fx_halo_fallos = 0;
static void fx_sonda_proj(const char *que, const float *m, const float *v);
/* ★ turno 5 · LAS CAMPANILLAS DEL TRINEO (anonimo03: «usar ese sonido mientras el trineo gorila aparece e ir reduciendo
 *   volumen hasta 0 mientras se esconde»). El sonido es el «징글벨» del juego (rnr_sound/bell.mp3, el 22 de
 *   fxsound.txt: el de las campanas), en bucle y con el fundido YA HORNEADO (13 s: pleno 7 s y baja a 0; lo arma
 *   t5/sonido/hornear_campanillas.py en isla_fx_campanillas.h). Ningún efecto del .aif de la isla dispara sonidos
 *   (fxsound / effectsound van por acciones del personaje), así que lo toca la dll, por MCI (winmm, como el
 *   «Lets_start» de selector.c):
 *     · el disparo: el PRIMER dibujo del trineo (la textura [isla_fx] campanillas_textura) con escala visible, en cada
 *       VISITA a la isla (una visita empieza cuando la isla vuelve a dibujarse después de > 1,5 s sin hacerlo);
 *     · el hilo de dibujo sólo levanta un evento: abrir y tocar lo hace un hilo aparte (MCI tarda);
 *     · se corta si la isla deja de dibujarse > 0,5 s (el jugador se fue del lobby);
 *     · respeta [SOUND] EFFECT del Config.ini del juego (0 = mudo).
 *   [isla_fx] campanillas=1 (0 = nada) · campanillas_espera_ms=0 (atraso desde que aparece) */
static int  g_fx_camp = 1, g_fx_camp_espera = 0, g_fx_camp_idx = -1;
static FX_CAMP g_fx_cs;                                  /* ★ turno 7: el estado de las campanillas */
static volatile LONG g_fx_ani_reinicios = 0;             /* ★ turno 7: lo sube la cueva antes de 0x655C20 */
static volatile LONG g_fx_ani_sitio[2] = { 0, 0 };       /* ★ turno 8: cuántos por 0x49AB2B y por 0x4C3FE0 */
static LONG g_fx_ani_anotado = 0;
static float g_fx_camp_ojo[4] = { 731.0f, 8214.0f, -18955.0f, 1500.0f };   /* ★ turno 8: la cámara del LOBBY */
static HANDLE g_fx_camp_ev = NULL;
static long g_fx_camp_veces = 0;                            /* ★ turno 5: el último repaso del near AL DIBUJAR */
static long g_fx_n_cercano_tarde = 0;
typedef HRESULT (WINAPI *FX_SETTR0_F)(void *, DWORD, const float *);
static FX_SETTR0_F g_fx_settr_real0 = NULL;              /* = g_fx_settr_real (se declara más abajo) */

/* la sonda: cuentas por segundo */
static long g_fx_n_dib[4], g_fx_n_marc[4], g_fx_n_aplic, g_fx_reescrituras, g_fx_n_brillo;
static DWORD g_fx_seg0 = 0;
static int  g_fx_seg_anotados = 0;

/* ── el tiempo ── */
static float fx_segundos(void)
{
    LARGE_INTEGER t;
    if (!g_fx_qpf.QuadPart) { QueryPerformanceFrequency(&g_fx_qpf); QueryPerformanceCounter(&g_fx_qp0); }
    QueryPerformanceCounter(&t);
    double s = (double)(t.QuadPart - g_fx_qp0.QuadPart) / (double)g_fx_qpf.QuadPart;
    s -= 3600.0 * (double)(long long)(s / 3600.0);      /* vuelve a 0 cada hora: el float no pierde precisión */
    return (float)s;
}

/* ★ turno 9 · los mips: armar la textura nueva (ver fx_dxt_*) y el filtro en los dibujos de la isla */
typedef HRESULT (WINAPI *FX_LOCK_F)(void *, UINT, DWORD *, const RECT *, DWORD);   /* IDirect3DTexture9::LockRect (19) */
typedef HRESULT (WINAPI *FX_UNLOCK_F)(void *, UINT);                               /* UnlockRect (20) */
typedef HRESULT (WINAPI *FX_GETDEV_F)(void *, void **);                            /* IDirect3DResource9::GetDevice (3) */
typedef HRESULT (WINAPI *FX_GETSAMP_F)(void *, DWORD, DWORD, DWORD *);
#define FX_GETSAMP 68
#define FX_FMT_DXT1 0x31545844
#define FX_FMT_DXT3 0x33545844
#define FX_FMT_DXT5 0x35545844
static int  g_fx_mips = 1, g_fx_aniso = 4;
static long g_fx_n_mips = 0, g_fx_mips_no = 0;
static DWORD g_fx_mips_bytes = 0;

/* la textura del juego (un nivel, DXT) → una nueva con la cadena entera, o NULL (y queda la del juego) */
static void *fx_mips_armar(void *tex)
{
    DWORD d[8];
    ZeroMemory(d, sizeof(d));
    if (((FX_DESC_NIVEL_F)FXV(tex)[17])(tex, 0, d) != 0) return NULL;
    int f = d[0] == FX_FMT_DXT1 ? 1 : d[0] == FX_FMT_DXT3 ? 3 : d[0] == FX_FMT_DXT5 ? 5 : 0;
    int w = (int)d[6], h = (int)d[7];
    if (!f || d[3] != 1 /* MANAGED */ || w < 8 || h < 8 || (w & 3) || (h & 3) || w > 4096 || h > 4096) return NULL;
    if (((FX_NIVELES_F)FXV(tex)[13])(tex) != 1) return NULL;
    int nl = fx_mip_niveles(w, h);
    if (nl < 2) return NULL;
    void *dev = NULL, *nueva = NULL;
    if (((FX_GETDEV_F)FXV(tex)[3])(tex, &dev) != 0 || !dev) return NULL;
    HRESULT hr = ((FX_CREATETEX_F)FXV(dev)[FX_CREATETEX])(dev, (UINT)w, (UINT)h, (UINT)nl, 0, d[0], 1, &nueva, NULL);
    fx_soltar(dev);
    if (hr != 0 || !nueva) return NULL;
    BYTE *a = (BYTE *)HeapAlloc(GetProcessHeap(), 0, (SIZE_T)w * h * 4);
    BYTE *b = (BYTE *)HeapAlloc(GetProcessHeap(), 0, (SIZE_T)(w / 2) * (h / 2) * 4);
    int ok = a && b;
    DWORD ls[2] = { 0, 0 }, ld[2] = { 0, 0 };                    /* D3DLOCKED_RECT: Pitch, pBits */
    int tb = f == 1 ? 8 : 16, fila = (w / 4) * tb;
    if (ok && ((FX_LOCK_F)FXV(tex)[19])(tex, 0, ls, NULL, 0x10 /* READONLY */) == 0) {
        if (((FX_LOCK_F)FXV(nueva)[19])(nueva, 0, ld, NULL, 0) == 0) {
            for (int y = 0; y < h / 4; y++)                          /* el nivel 0, TAL CUAL */
                CopyMemory((BYTE *)(ULONG_PTR)ld[1] + y * (int)ld[0], (BYTE *)(ULONG_PTR)ls[1] + y * (int)ls[0], fila);
            ((FX_UNLOCK_F)FXV(nueva)[20])(nueva, 0);
            fx_dxt_a_rgba((BYTE *)(ULONG_PTR)ls[1], (int)ls[0], w, h, f, a);
        } else ok = 0;
        ((FX_UNLOCK_F)FXV(tex)[20])(tex, 0);
    } else ok = 0;
    int cw = w, ch = h;
    for (int l = 1; ok && l < nl; l++) {
        fx_mip_bajar(a, cw, ch, b);
        cw /= 2; ch /= 2;
        if (((FX_LOCK_F)FXV(nueva)[19])(nueva, (UINT)l, ld, NULL, 0) != 0) { ok = 0; break; }
        fx_rgba_a_dxt(b, cw, ch, f, (BYTE *)(ULONG_PTR)ld[1], (int)ld[0]);
        ((FX_UNLOCK_F)FXV(nueva)[20])(nueva, (UINT)l);
        g_fx_mips_bytes += (DWORD)(((cw + 3) / 4) * ((ch + 3) / 4) * tb);
        BYTE *t = a; a = b; b = t;
    }
    if (a) HeapFree(GetProcessHeap(), 0, a);
    if (b) HeapFree(GetProcessHeap(), 0, b);
    if (!ok) { fx_soltar(nueva); return NULL; }
    return nueva;
}

/* en los dibujos de la isla: mips lineal + anisotrópico (se guarda lo de antes y se devuelve después del dibujo) */
static int g_fx_samp_puesto = 0;
static DWORD g_fx_samp_ant[3], g_fx_aniso_max = 0;
static void fx_samp_poner(void *dev, void **vt)
{
    if (!g_fx_mips || !g_fx_activo || g_fx_samp_puesto) return;
    if (!g_fx_aniso_max) {
        BYTE caps[512];
        ZeroMemory(caps, sizeof(caps));
        g_fx_aniso_max = 1;
        if (((FX_CAPS_F)vt[FX_GETCAPS])(dev, caps) == 0 && (*(DWORD *)(caps + 0x40) & 0x400 /* MINFANISOTROPIC */))
            g_fx_aniso_max = *(DWORD *)(caps + 0x6C) ? *(DWORD *)(caps + 0x6C) : 1;
    }
    FX_GETSAMP_F gs = (FX_GETSAMP_F)vt[FX_GETSAMP];
    FX_SETSAMP_F ss = (FX_SETSAMP_F)vt[FX_SETSAMP];
    gs(dev, 0, 6, &g_fx_samp_ant[0]); gs(dev, 0, 7, &g_fx_samp_ant[1]); gs(dev, 0, 10, &g_fx_samp_ant[2]);
    DWORD an = (DWORD)g_fx_aniso < g_fx_aniso_max ? (DWORD)g_fx_aniso : g_fx_aniso_max;
    ss(dev, 0, 6, an > 1 ? 3 : 2);                               /* MINFILTER: anisotrópico / lineal */
    ss(dev, 0, 7, 2);                                            /* MIPFILTER: lineal (trilineal) */
    if (an > 1) ss(dev, 0, 10, an);                              /* MAXANISOTROPY */
    g_fx_samp_puesto = 1;
}

/* ★ turno 12 · los colores falsos y el sesgo de z: lo que se cambia en un dibujo y se devuelve después */
static int  g_fx_falsos = 0, g_fx_zsesgo = 1, g_fx_falsos_puesto = 0, g_fx_zs_puesto = 0;
/* ★ turno 13 · para BISECAR: qué parte de los colores falsos se aplica, y a qué texturas */
static int  g_fx_cf_color = 1, g_fx_cf_etapa1 = 1, g_fx_cf_niebla = 1;
static char g_fx_cf_solo[1024], g_fx_cf_menos[1024];
static DWORD g_fx_falsos_ant[6], g_fx_zs_ant[2];
static void fx_falsos_sacar(void *dev)
{
    FX_SETRS_F rs = (FX_SETRS_F)FXV(dev)[FX_SETRS];
    if (g_fx_falsos_puesto) {
        typedef HRESULT (WINAPI *FX_SETTSS_F)(void *, DWORD, DWORD, DWORD);
        FX_SETTSS_F ts = (FX_SETTSS_F)FXV(dev)[67];
        ts(dev, 0, FX_TSS_COLOROP, g_fx_falsos_ant[0]); ts(dev, 0, FX_TSS_COLORARG1, g_fx_falsos_ant[1]);
        ts(dev, 1, FX_TSS_COLOROP, g_fx_falsos_ant[2]);
        rs(dev, FX_RS_TFACTOR, g_fx_falsos_ant[3]); rs(dev, FX_RS_FOGENABLE, g_fx_falsos_ant[4]);
        g_fx_falsos_puesto = 0;
    }
    if (g_fx_zs_puesto) {
        rs(dev, 195 /* DEPTHBIAS */, g_fx_zs_ant[0]); rs(dev, 175 /* SLOPESCALEDEPTHBIAS */, g_fx_zs_ant[1]);
        g_fx_zs_puesto = 0;
    }
}

static void fx_samp_sacar(void *dev)
{
    if (g_fx_falsos_puesto || g_fx_zs_puesto) fx_falsos_sacar(dev);       /* ★ turno 12 */
    if (!g_fx_samp_puesto) return;
    FX_SETSAMP_F ss = (FX_SETSAMP_F)FXV(dev)[FX_SETSAMP];
    ss(dev, 0, 6, g_fx_samp_ant[0]); ss(dev, 0, 7, g_fx_samp_ant[1]); ss(dev, 0, 10, g_fx_samp_ant[2]);
    g_fx_samp_puesto = 0;
}

/* ── la carga de texturas: el trampolín de 0x641620 ─────────────────────────────────────────────────────── */
static void fx_textura_cargada(BYTE *obj)
{
    if (!obj || IsBadReadPtr(obj, 0x48)) return;
    DWORD largo = *(DWORD *)(obj + 0x14), cap = *(DWORD *)(obj + 0x18);
    const char *nom = cap >= 16 ? *(const char **)(obj + 4) : (const char *)(obj + 4);
    if (!largo || largo > 300 || !nom || IsBadReadPtr(nom, largo)) return;
    char ruta[304], base[FX_LARGO_NOM];
    lstrcpynA(ruta, nom, (int)largo + 1);
    fx_nombre_base(ruta, base, sizeof(base));
    void **primero = *(void ***)(obj + 0x3C), **ultimo = *(void ***)(obj + 0x40);
    long n = g_fx_cargadas++;
    int idx = g_fx_perfil_ok ? fx_perfil_buscar(&g_fx_p, base) : -1;
    if (g_fx_sonda && n < 600) {
        /* formato, tamaño y niveles de la primera: lo medido dice CreateTexture(…, niveles = 1, …) — que lo confirme */
        DWORD d[8] = { 0 }, niveles = 0;
        void *t0 = (primero && ultimo > primero && !IsBadReadPtr(primero, sizeof(void *))) ? *primero : NULL;
        if (t0) {
            ((FX_DESC_NIVEL_F)FXV(t0)[17])(t0, 0, d);
            niveles = ((FX_NIVELES_F)FXV(t0)[13])(t0);
        }
        apuntar("  [isla_fx] sonda: textura %ld «%s» %ux%u formato %u niveles %u%s", n + 1, ruta, d[6], d[7], d[0], niveles,
                idx >= 0 ? "  ★ en el perfil" : "");
    }
    /* ★ turno 9 · los MIPS: cada textura de la isla (rnr_ui_bg/front/) con su cadena entera, en el mismo formato.
     *   La del juego NO se suelta (podría tener el puntero guardado en otro lado): son ~6,5 MB, una vez. */
    if (g_fx_mips && g_fx_activo && primero && ultimo > primero && !IsBadReadPtr(primero, sizeof(void *))
        && CompareStringA(LOCALE_INVARIANT, NORM_IGNORECASE, ruta, 16, "rnr_ui_bg/front/", 16) == CSTR_EQUAL) {
        for (void **pp = primero; pp < ultimo && pp - primero < 64; pp++) {
            void *tx = *pp;
            if (!tx || IsBadReadPtr(tx, sizeof(void *))) continue;
            void *nueva = fx_mips_armar(tx);
            if (nueva) { *pp = nueva; g_fx_n_mips++; }
            else g_fx_mips_no++;
        }
    }
    if ((g_fx_trazar || g_fx_falsos || g_fx_sonda_sel) && primero && ultimo > primero && !IsBadReadPtr(primero, sizeof(void *))) {
        g_fx_nom_isla_ahora = CompareStringA(LOCALE_INVARIANT, NORM_IGNORECASE, ruta, 16, "rnr_ui_bg/front/", 16) == CSTR_EQUAL;
        for (void **pp = primero; pp < ultimo && pp - primero < 64; pp++) if (*pp) fx_nombre_anotar(*pp, base);
    }
    if (lstrcmpiA(base, "nocull_sky") == 0 && primero && ultimo > primero && !IsBadReadPtr(primero, sizeof(void *))
        && *primero) {                                          /* ★ turno 17: el cielo real, para el reflejo del mar */
        void *nuevo = *primero;
        ((FX_SOLTAR)FXV(nuevo)[1])(nuevo);                      /* AddRef (índice 1): que no se libere mientras lo usamos */
        if (g_fx_tex_cielo) fx_soltar(g_fx_tex_cielo);
        g_fx_tex_cielo = nuevo;
    }
    if (g_fx_ocultar[0] && primero && ultimo > primero && !IsBadReadPtr(primero, sizeof(void *))
        && fx_en_lista_oc(g_fx_ocultar, base)) {                  /* ★ 21-nov: no se ve con «Elige tu personaje» */
        int k = 0;
        for (void **pp = primero; pp < ultimo && pp - primero < 64; pp++) {
            void *tx = *pp;
            if (!tx || IsBadReadPtr(tx, sizeof(void *))) continue;
            DWORD v = 1;
            if (((FX_PRIV_SET)FXV(tx)[4])(tx, &g_fx_guid_oculta, &v, sizeof(v), 0) == 0) k++;
        }
        if (k && InterlockedIncrement(&g_fx_n_ocultas) <= 12)
            apuntar("  [isla_fx] ★ «%s» no se dibuja mientras está «Elige tu personaje» (el trineo de cerca)", base);
    }
    if (idx < 0 || !primero || ultimo <= primero || IsBadReadPtr(primero, sizeof(void *))) return;
    int marcadas = 0;
    for (void **p = primero; p < ultimo && marcadas < 64; p++) {
        void *tex = *p;
        if (!tex || IsBadReadPtr(tex, sizeof(void *))) continue;
        DWORD v = (DWORD)idx;
        ((FX_PRIV_SET)FXV(tex)[4])(tex, &g_fx_guid, &v, sizeof(v), 0);
        if (fx_marcar(tex, idx)) marcadas++;
    }
    if (marcadas) g_fx_marcadas++;
}

static char __fastcall fx_cargar(void *obj, void *edx, void *nombre, void *mem)
{
    (void)edx;
    char r = g_fx_cargar_real(obj, NULL, nombre, mem);
    if (r) fx_textura_cargada((BYTE *)obj);
    return r;
}

/* el trampolín: se miran los bytes ANTES de escribir (la entrada, el `ret 8` y la llamada desde el administrador) */
static int g_fx_trampolin_intentos = 0;
static int fx_enganchar_carga(void)
{
    static const BYTE e_entrada[13] = { 0x6A, 0xFF, 0x68, 0xF6, 0xC7, 0x86, 0x00, 0x64, 0xA1, 0x00, 0x00, 0x00, 0x00 };
    static const BYTE e_ret[3] = { 0xC2, 0x08, 0x00 };
    g_fx_trampolin_intentos++;
    BYTE *base = (BYTE *)GetModuleHandleA(NULL);
    BYTE *f = base + (FX_VA_CARGAR - 0x400000), *ret = base + (FX_VA_CARGAR_RET - 0x400000);
    BYTE *call = base + (FX_VA_LLAMADA - 0x400000);
    if (IsBadReadPtr(f, 16) || IsBadReadPtr(ret, 4) || IsBadReadPtr(call, 5)
        || memcmp(f, e_entrada, sizeof(e_entrada)) || memcmp(ret, e_ret, sizeof(e_ret))
        || call[0] != 0xE8 || (DWORD)(ULONG_PTR)(call + 5 + *(int *)(call + 1)) != (DWORD)(ULONG_PTR)f) {
        apuntar("  [isla_fx] ⛔ 0x641620 (la carga de texturas) no es la medida: no se engancha nada");
        return 0;
    }
    BYTE *t = (BYTE *)VirtualAlloc(NULL, 32, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!t) return 0;
    CopyMemory(t, e_entrada, 7);                                   /* push −1 · push 0x86C7F6 */
    t[7] = 0xE9;
    *(int *)(t + 8) = (int)((DWORD)(ULONG_PTR)(f + 7) - (DWORD)(ULONG_PTR)(t + 12));
    g_fx_cargar_real = (FX_CARGAR_F)(void *)t;
    BYTE s[7] = { 0xE9, 0, 0, 0, 0, 0x90, 0x90 };
    *(int *)(s + 1) = (int)((DWORD)(ULONG_PTR)fx_cargar - ((DWORD)(ULONG_PTR)f + 5));
    DWORD viejo = 0;
    if (!VirtualProtect(f, 7, PAGE_EXECUTE_READWRITE, &viejo)) return 0;
    CopyMemory(f, s, 7);
    VirtualProtect(f, 7, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), f, 7);
    apuntar("  [isla_fx] ★ enganchada la carga de texturas (0x641620): cada textura se reconoce por su nombre");
    return 1;
}

/* ── los sombreadores: se crean la primera vez que hacen falta, en el hilo que dibuja ───────────────────── */
static int fx_crear(void *dev)
{
    if (g_fx_creados) return g_fx_creados > 0;
    void **vt = FXV(dev);
    BYTE caps[512];
    ZeroMemory(caps, sizeof(caps));
    g_fx_creados = -1;
    if (((FX_CAPS_F)vt[FX_GETCAPS])(dev, caps) != 0) {
        apuntar("  [isla_fx] ⛔ GetDeviceCaps falló: la capa 4 no se prende");
        return 0;
    }
    DWORD vsv = *(DWORD *)(caps + 0xC4), psv = *(DWORD *)(caps + 0xCC), ps30 = *(DWORD *)(caps + 0x12C);
    apuntar("  [isla_fx] la tarjeta: vértices %u.%u, píxeles %u.%u, %u instrucciones por sombreador de píxel 3.0",
            (vsv >> 8) & 0xFF, vsv & 0xFF, (psv >> 8) & 0xFF, psv & 0xFF, ps30);
    if ((vsv & 0xFFFF) < 0x300 || (psv & 0xFFFF) < 0x300) {
        apuntar("  [isla_fx] ⛔ la tarjeta no tiene sombreadores 3.0: la isla se dibuja como siempre");
        return 0;
    }
    int ok = 0, mal = 0;
    for (int i = 0; i < FX_SH_CUANTOS; i++) {
        void *sh = NULL;
        HRESULT hr = ((FX_CREASH_F)vt[fx_bc[i].es_vs ? FX_CREATEVS : FX_CREATEPS])(dev, fx_bc[i].bc, &sh);
        if (hr != 0 || !sh) {
            mal++;
            apuntar("  [isla_fx] ⚠ no se pudo crear %s (hr 0x%08X): ese efecto queda apagado", fx_bc[i].nombre, (unsigned)hr);
            continue;
        }
        ok++;
        if (i == FX_SH_VS_MUNDO) g_fx_vs[0] = sh;
        else if (i == FX_SH_VS_MUNDO_COLOR) g_fx_vs[1] = sh;
        else if (i == FX_SH_VS_MUNDO_SIN_NORMAL) g_fx_vs[2] = sh;
        else if (i == FX_SH_VS_PANTALLA) g_fx_vs_pantalla = sh;
        else if (i == FX_SH_VS_MUNDO_HALO) g_fx_vs_halo = sh;
        else g_fx_ps[i] = sh;
    }
    if (!g_fx_vs[0]) {
        apuntar("  [isla_fx] ⛔ sin el sombreador de vértices de la isla no hay capa 4");
        return 0;
    }
    g_fx_creados = 1;
    apuntar("  [isla_fx] ★ sombreadores creados: %d de %d%s", ok, FX_SH_CUANTOS, mal ? " (los que faltan, apagados)" : "");
    if (g_fx_nluz >= 64 && (!g_fx_ps[FX_SH_PS_MAR_64] || !g_fx_ps[FX_SH_PS_LUCES_64] || !g_fx_ps[FX_SH_PS_NIEVE_64])) {
        g_fx_nluz = 32;                                   /* ★ turno 10: la tarjeta no aguanta los de 64 */
        g_fx_luces_nuevas = 1;
        apuntar("  [isla_fx] ⚠ los sombreadores de 64 luces no se crearon (%u instrucciones por sombreador): vuelvo a 32"
                " elegidas por cuadro", ps30);
    }
    return 1;
}

static void *fx_ps_de(int sombra)
{
    switch (sombra) {
    case FX_MAR:                                        /* ★ turno 27: media y baja, el mar liviano */
        if (g_fx_calidad <= 0 && g_fx_ps[FX_SH_PS_MAR_BAJA]) return g_fx_ps[FX_SH_PS_MAR_BAJA];
        if (g_fx_calidad == 1 && g_fx_ps[FX_SH_PS_MAR_MEDIA]) return g_fx_ps[FX_SH_PS_MAR_MEDIA];
        return g_fx_ps[g_fx_nluz >= 64 ? FX_SH_PS_MAR_64 : g_fx_nluz >= 32 ? FX_SH_PS_MAR : g_fx_nluz >= 16 ? FX_SH_PS_MAR_16 : FX_SH_PS_MAR_8];
    case FX_CIELO:
        if (g_fx_noche && g_fx_calidad <= 0 && g_fx_ps[FX_SH_PS_CIELO_NOCHE_BAJA]) return g_fx_ps[FX_SH_PS_CIELO_NOCHE_BAJA];
        return g_fx_ps[g_fx_noche ? FX_SH_PS_CIELO_NOCHE : FX_SH_PS_CIELO_DIA];
    case FX_LUCES:   return g_fx_ps[g_fx_nluz >= 64 ? FX_SH_PS_LUCES_64 : g_fx_nluz >= 32 ? FX_SH_PS_LUCES : g_fx_nluz >= 16 ? FX_SH_PS_LUCES_16 : FX_SH_PS_LUCES_8];
    case FX_NIEVE:   return g_fx_ps[g_fx_nluz >= 64 ? FX_SH_PS_NIEVE_64 : g_fx_nluz >= 32 ? FX_SH_PS_NIEVE : g_fx_nluz >= 16 ? FX_SH_PS_NIEVE_16 : FX_SH_PS_NIEVE_8];
    case FX_EMISIVO: return g_fx_ps[FX_SH_PS_EMISIVO];
    }
    return NULL;
}

static DWORD fx_rs(void **vt, void *dev, DWORD e) { DWORD v = 0; ((FX_GETRS_F)vt[FX_GETRS])(dev, e, &v); return v; }
static DWORD fx_tss(void **vt, void *dev, DWORD e) { DWORD v = 0; ((FX_GETTSS_F)vt[FX_GETTSS])(dev, 0, e, &v); return v; }
static float fx_f(DWORD d) { float f; CopyMemory(&f, &d, 4); return f; }

/* la sonda: el primer dibujo de cada textura del perfil, con todo lo que hace falta saber */
static void fx_sonda_dibujo(void *dev, void **vt, int idx, int tipo)
{
    if (idx < 0 || idx >= FX_MAX_TEX || g_fx_vista_marca[idx]) return;
    g_fx_vista_marca[idx] = 1;
    DWORD fvf = 0;
    ((FX_GETF_F)vt[FX_GETFVF])(dev, &fvf);
    void *vs = NULL, *ps = NULL;
    ((FX_GETSH_F)vt[FX_GETVS])(dev, &vs);
    ((FX_GETSH_F)vt[FX_GETPS])(dev, &ps);
    fx_soltar(vs);
    fx_soltar(ps);
    float w[16], mat[17];
    ZeroMemory(w, sizeof(w));
    ZeroMemory(mat, sizeof(mat));
    ((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 256, w);
    ((FX_GETMAT_F)vt[FX_GETMATERIAL])(dev, mat);
    float mul[4];
    int vert = 0;
    int motivo = fx_etapa0(fx_tss(vt, dev, FX_TSS_COLOROP), fx_tss(vt, dev, FX_TSS_COLORARG1), fx_tss(vt, dev, FX_TSS_COLORARG2),
                           fx_tss(vt, dev, FX_TSS_ALPHAOP), fx_tss(vt, dev, FX_TSS_ALPHAARG1), fx_tss(vt, dev, FX_TSS_ALPHAARG2),
                           fx_rs(vt, dev, FX_RS_TFACTOR), fx_rs(vt, dev, FX_RS_LIGHTING), fvf, mat[3], mul, &vert);
    /* ⚠ apuntar() arma la línea en 512 B (wvsprintfA): se parte en tres */
    apuntar("  [isla_fx] sonda: 1.er dibujo de «%s» (%s) por %d · FVF 0x%X · VS %p PS %p · etapa0 %s",
            g_fx_p.tex[idx], g_fx_p.sombra[idx] == FX_NINGUNO ? "ninguno" : g_fx_nombre_sombra[g_fx_p.sombra[idx]],
            80 + tipo + 1, fvf, vs, ps,
            motivo == 0 ? "se puede copiar" : motivo == 1 ? "COLOR no soportado" : motivo == 2 ? "ALFA no soportado"
            : motivo == 3 ? "color de vértice a medias" : "modificadores");
    apuntar("  [isla_fx] sonda:   color op %u (%u,%u) · alfa op %u (%u,%u) · luces %u · alfatest %u · mezcla %u · z %u"
            " · tfactor %08X · difuso.a %d/1000",
            fx_tss(vt, dev, FX_TSS_COLOROP), fx_tss(vt, dev, FX_TSS_COLORARG1), fx_tss(vt, dev, FX_TSS_COLORARG2),
            fx_tss(vt, dev, FX_TSS_ALPHAOP), fx_tss(vt, dev, FX_TSS_ALPHAARG1), fx_tss(vt, dev, FX_TSS_ALPHAARG2),
            fx_rs(vt, dev, FX_RS_LIGHTING), fx_rs(vt, dev, FX_RS_ALPHATEST), fx_rs(vt, dev, FX_RS_ALPHABLEND),
            fx_rs(vt, dev, FX_RS_ZENABLE), (unsigned)fx_rs(vt, dev, FX_RS_TFACTOR), (int)(mat[3] * 1000.0f));
    apuntar("  [isla_fx] sonda:   niebla %u (modo tabla %u / vértice %u, %d..%d) · mundo (%d, %d, %d) escala %d/1000",
            fx_rs(vt, dev, FX_RS_FOGENABLE), fx_rs(vt, dev, FX_RS_FOGTABLEMODE), fx_rs(vt, dev, FX_RS_FOGVERTEXMODE),
            (int)fx_f(fx_rs(vt, dev, FX_RS_FOGSTART)), (int)fx_f(fx_rs(vt, dev, FX_RS_FOGEND)),
            (int)w[12], (int)w[13], (int)w[14], (int)(w[0] * 1000.0f));
}

static void fx_sonda_segundo(void)
{
    DWORD ahora = GetTickCount();
    if (!g_fx_seg0) { g_fx_seg0 = ahora; return; }
    if (ahora - g_fx_seg0 < 1000) return;
    g_fx_seg0 = ahora;
    long marc = g_fx_n_marc[0] + g_fx_n_marc[1] + g_fx_n_marc[2] + g_fx_n_marc[3];
    if (marc && g_fx_seg_anotados < 30) {
        g_fx_seg_anotados++;
        apuntar("  [isla_fx] sonda: en 1 s, dibujos 81/82/83/84 = %ld/%ld/%ld/%ld · de la isla %ld/%ld/%ld/%ld · con sombreador %ld"
                " · reescrituras de Direct3D %ld · brillos %ld · diferidos %ld · near %d: %ld (como la isla y no: %ld)",
                g_fx_n_dib[0], g_fx_n_dib[1], g_fx_n_dib[2], g_fx_n_dib[3],
                g_fx_n_marc[0], g_fx_n_marc[1], g_fx_n_marc[2], g_fx_n_marc[3], g_fx_n_aplic, g_fx_reescrituras, g_fx_n_brillo,
                g_fx_n_diferidos, (int)g_fx_cercano, g_fx_n_cercano, g_fx_n_cercano_no);
        apuntar("  [isla_fx] sonda:   PROJ puestas en ese segundo: %ld · near puesto AL DIBUJAR la isla: %ld · halos %ld"
                " · resplandores %ld · mips: %ld texturas con su cadena (+%lu KB), %ld sin (aniso %d de %lu)", g_fx_n_proj,
                g_fx_n_cercano_tarde, g_fx_n_halos, g_fx_n_resplandores, g_fx_n_mips, (unsigned long)(g_fx_mips_bytes / 1024), g_fx_mips_no, g_fx_aniso,
                (unsigned long)g_fx_aniso_max);
        apuntar("  [isla_fx] sonda:   SALTEOS por motivo: capa %ld · sin efecto %ld · otro disp. %ld · sin sombreadores %ld ·"
                " VS AJENO %ld · PS ajeno sin pisar %ld · FVF %ld · etapa0 %ld · pasada no normal (VS ajeno) %ld", g_fx_salto[0],
                g_fx_salto[1], g_fx_salto[2], g_fx_salto[3], g_fx_salto[4], g_fx_salto[5], g_fx_salto[6], g_fx_salto[7],
                g_fx_salto[8]);
        apuntar("  [isla_fx] sonda:   PARPADEO: luces que entraron o salieron %ld (lugares %d) · dibujos de la isla con near ~1: %ld"
                " · brillo suave %d/100 · dibujos con un sombreador de píxel AJENO (el selector) %ld%s", g_fx_n_luz_cambios,
                g_fx_nluz, g_fx_n_near1, (int)(g_fx_brillo_suave * 100.0f), g_fx_n_ps_ajeno,
                g_fx_pisar_ps ? " (se pisa)" : " (no se toca: pisar_ps=0)");
    }
    for (int i = 0; i < 4; i++) g_fx_n_dib[i] = g_fx_n_marc[i] = 0;
    g_fx_n_aplic = g_fx_n_brillo = g_fx_n_diferidos = 0;
    g_fx_n_cercano = g_fx_n_cercano_no = g_fx_n_proj = g_fx_n_cercano_tarde = g_fx_n_halos = 0;
    g_fx_n_luz_cambios = g_fx_n_near1 = 0;
    g_fx_n_ps_ajeno = 0;
    for (int i = 0; i < 9; i++) g_fx_salto[i] = 0;
    g_fx_n_resplandores = 0;
}

/* ── el brillo (bloom) ─────────────────────────────────────────────────────────────────────────────────── */
static void *g_fx_b_full = NULL, *g_fx_b_a = NULL, *g_fx_b_b = NULL, *g_fx_b_sb = NULL;
static void *g_fx_b_h1 = NULL, *g_fx_b_h2 = NULL;       /* ★ turno 10: el brillo del cuadro anterior (y el nuevo) */
static float g_fx_b_ultimo = -10.0f;
static float g_fx_isla_vp[16], g_fx_isla_p11 = 0, g_fx_isla_p22 = 0;   /* ★ turno 14 */
static int  g_fx_hay_vp = 0;
static UINT g_fx_b_w = 0, g_fx_b_h = 0;
static DWORD g_fx_b_fmt = 0;

static void fx_brillo_soltar(void)
{
    fx_soltar(g_fx_b_full); fx_soltar(g_fx_b_a); fx_soltar(g_fx_b_b); fx_soltar(g_fx_b_sb);
    fx_soltar(g_fx_b_h1); fx_soltar(g_fx_b_h2);
    g_fx_b_full = g_fx_b_a = g_fx_b_b = g_fx_b_sb = g_fx_b_h1 = g_fx_b_h2 = NULL;
    g_fx_b_ultimo = -10.0f;
    g_fx_b_w = g_fx_b_h = 0;
    for (int i = 0; i < FX_DIFERIDOS; i++) { fx_soltar(g_fx_dif[i].sb); g_fx_dif[i].sb = NULL; }
    fx_soltar(g_fx_sb_present);
    g_fx_sb_present = NULL;
    g_fx_ndif = 0;                                        /* un Reset en medio: lo diferido de este cuadro se pierde */
}

/* ★ turno 2 · los DIFERIDOS: guardar un dibujo (todo su estado en un bloque D3DSBT_ALL + sus números) */
static int fx_guardar(void *dev, int k, const DWORD *a)
{
    void **vt = FXV(dev);
    int i = g_fx_ndif;
    if (i >= FX_DIFERIDOS) return 0;
    if (!g_fx_dif[i].sb && ((FX_CREASB_F)vt[FX_CREATESB])(dev, 1 /* D3DSBT_ALL */, &g_fx_dif[i].sb) != 0) {
        g_fx_dif[i].sb = NULL;
        return 0;
    }
    if (((FX_SB_F)FXV(g_fx_dif[i].sb)[4])(g_fx_dif[i].sb) != 0) return 0;          /* Capture */
    g_fx_dif[i].k = k;
    for (int j = 0; j < 6; j++) g_fx_dif[i].a[j] = a[j];
    g_fx_ndif = i + 1;
    g_fx_n_diferidos++;
    return 1;
}

/* …y hacerlos: cada uno con SU estado, por la entrada de la tabla (así pasa por sala_alfa y por nuestro sombreador).
 *   Lo llama el brillo (ya con el destino y el z del juego puestos) o Present si el brillo no corrió. El estado que
 *   queda después lo repone quien llama. */
static void fx_reproducir(void *dev)
{
    int n = g_fx_ndif;
    g_fx_ndif = 0;
    if (n <= 0) return;
    void **vt = FXV(dev);
    g_fx_reproduciendo = 1;
    for (int i = 0; i < n; i++) {
        void *sb = g_fx_dif[i].sb;
        if (!sb) continue;
        ((FX_SB_F)FXV(sb)[5])(sb);                                                   /* Apply */
        const DWORD *a = g_fx_dif[i].a;
        HRESULT hr = g_fx_dif[i].k == 0
            ? ((FX_D81)vt[FX_DP])(dev, a[0], a[1], a[2])
            : ((FX_D82)vt[FX_DIP])(dev, a[0], (INT)a[1], a[2], a[3], a[4], a[5]);
        if (hr != 0 && g_fx_dif_fallos++ < 5)
            apuntar("  [isla_fx] ⚠ un dibujo diferido (excluido del brillo) falló: hr 0x%08X", (unsigned)hr);
    }
    g_fx_reproduciendo = 0;
}

/* los diferidos que quedaron sin brillo (no hubo 2D en el cuadro, o el brillo falló): se hacen igual, guardando y
 * reponiendo el estado del juego (el envoltorio del juego recuerda sus estados: no hay que dejarle nada cambiado) */
static void fx_reproducir_guardando(void *dev, int en_escena)
{
    if (g_fx_ndif <= 0) return;
    void **vt = FXV(dev);
    if (!g_fx_sb_present && ((FX_CREASB_F)vt[FX_CREATESB])(dev, 1, &g_fx_sb_present) != 0) g_fx_sb_present = NULL;
    if (!g_fx_sb_present) { g_fx_ndif = 0; return; }                                 /* sin bloque: no se arriesga */
    ((FX_SB_F)FXV(g_fx_sb_present)[4])(g_fx_sb_present);
    int escena = en_escena || ((FX_ESCENA_F)vt[FX_BEGINSCENE])(dev) == 0;
    if (escena) fx_reproducir(dev);
    else g_fx_ndif = 0;
    if (escena && !en_escena) ((FX_ESCENA_F)vt[FX_ENDSCENE])(dev);
    ((FX_SB_F)FXV(g_fx_sb_present)[5])(g_fx_sb_present);
}

/* las texturas del tamaño del destino actual (desc: Format, Type, Usage, Pool, MultiSampleType, Quality, Width, Height) */
static int fx_brillo_recursos(void *dev, void **vt, const DWORD *desc)
{
    if (g_fx_b_full && g_fx_b_w == desc[6] && g_fx_b_h == desc[7] && g_fx_b_fmt == desc[0]) return 1;
    fx_brillo_soltar();
    UINT w = desc[6], h = desc[7];
    if (w < 64 || h < 64) return 0;
    FX_CREATETEX_F crear = (FX_CREATETEX_F)vt[FX_CREATETEX];
    #define FX_USO_RT 1
    #define FX_POOL_DEFAULT 0
    #define FX_FMT_A8R8G8B8 21
    if (crear(dev, w, h, 1, FX_USO_RT, desc[0], FX_POOL_DEFAULT, &g_fx_b_full, NULL) != 0
        || crear(dev, w / 4, h / 4, 1, FX_USO_RT, FX_FMT_A8R8G8B8, FX_POOL_DEFAULT, &g_fx_b_a, NULL) != 0
        || crear(dev, w / 4, h / 4, 1, FX_USO_RT, FX_FMT_A8R8G8B8, FX_POOL_DEFAULT, &g_fx_b_b, NULL) != 0
        || (g_fx_brillo_suave > 0.0f
            && (crear(dev, w / 4, h / 4, 1, FX_USO_RT, FX_FMT_A8R8G8B8, FX_POOL_DEFAULT, &g_fx_b_h1, NULL) != 0
                || crear(dev, w / 4, h / 4, 1, FX_USO_RT, FX_FMT_A8R8G8B8, FX_POOL_DEFAULT, &g_fx_b_h2, NULL) != 0))
        || ((FX_CREASB_F)vt[FX_CREATESB])(dev, 1 /* D3DSBT_ALL */, &g_fx_b_sb) != 0) {
        fx_brillo_soltar();
        return 0;
    }
    g_fx_b_w = w; g_fx_b_h = h; g_fx_b_fmt = desc[0];
    return 1;
}

static void fx_cuadro(void *dev, void **vt, float w, float h)
{
    float c[4] = { -1.0f / w, 1.0f / h, 0, 0 };
    ((FX_SETC_F)vt[FX_SETVSCF])(dev, 0, c, 1);
    static const float q[4][5] = { { -1, 1, 0, 0, 0 }, { 1, 1, 0, 1, 0 }, { -1, -1, 0, 0, 1 }, { 1, -1, 0, 1, 1 } };
    ((FX_D83)vt[FX_DPUP])(dev, 5 /* TRIANGLESTRIP */, 2, q, 5 * sizeof(float));
}

static void *fx_superficie(void *tex)
{
    void *s = NULL;
    if (tex) ((FX_NIVEL_F)FXV(tex)[18])(tex, 0, &s);
    return s;
}

/* `en_escena` = 1 si estamos entre BeginScene y EndScene del juego (el disparo en un dibujo) */
static void fx_hacer_brillo(void *dev, int en_escena)
{
    void **vt = FXV(dev);
    if (g_fx_brillo_roto || !g_fx_vs_pantalla || !g_fx_ps[FX_SH_PS_BRILLO_EXTRAER] || !g_fx_ps[FX_SH_PS_BRILLO_DESENFOQUE]
        || !g_fx_ps[FX_SH_PS_BRILLO_SUMAR]) return;
    void *rt0 = NULL, *ds0 = NULL;
    if (((FX_GETRT_F)vt[FX_GETRT])(dev, 0, &rt0) != 0 || !rt0) return;
    DWORD desc[8];
    ZeroMemory(desc, sizeof(desc));
    ((FX_DESC_F)FXV(rt0)[12])(rt0, desc);
    if (!fx_brillo_recursos(dev, vt, desc)) {
        fx_soltar(rt0);
        g_fx_brillo_roto = 1;
        apuntar("  [isla_fx] ⚠ no pude crear las texturas del brillo (%ux%u, formato %u): brillo apagado", desc[6], desc[7], desc[0]);
        return;
    }
    InterlockedExchange(&g_fx_dentro, 1);
    ((FX_SB_F)FXV(g_fx_b_sb)[4])(g_fx_b_sb);                            /* Capture */
    ((FX_GETDS_F)vt[FX_GETDS])(dev, &ds0);
    if (en_escena && g_fx_hay_vp && g_fx_ps[FX_SH_PS_BRILLO_RESPLANDOR] && g_fx_vs_pantalla) {
        /* ★ turno 14 · los RESPLANDORES (luna, sol, estrella del cartel): un cuadrado de pantalla centrado en cada uno,
         *   con caída radial que llega a cero antes del borde, sumado al cuadro ANTES del brillo. Sin z (es luz en el
         *   aire); la cara nítida va después, encima (diferida). */
        FX_SETRS_F rs = (FX_SETRS_F)vt[FX_SETRS];
        FX_SETC_F pc = (FX_SETC_F)vt[FX_SETPSCF];
        rs(dev, FX_RS_ZENABLE, 0); rs(dev, FX_RS_ZWRITE, 0); rs(dev, FX_RS_ALPHATEST, 0); rs(dev, FX_RS_CULL, 1);
        rs(dev, FX_RS_FOGENABLE, 0); rs(dev, FX_RS_STENCIL, 0); rs(dev, FX_RS_COLORWRITE, 0xF); rs(dev, FX_RS_SRGBWRITE, 0);
        rs(dev, FX_RS_ALPHABLEND, 1); rs(dev, FX_RS_SRCBLEND, 2); rs(dev, FX_RS_DESTBLEND, 2); rs(dev, FX_RS_BLENDOP, 1);
        rs(dev, FX_RS_SEPALPHA, 0); rs(dev, FX_RS_FILLMODE, 3);
        ((FX_SETF_F)vt[FX_SETFVF])(dev, 0x102);
        ((FX_SETSH_F)vt[FX_SETVS])(dev, g_fx_vs_pantalla);
        ((FX_SETSH_F)vt[FX_SETPS])(dev, g_fx_ps[FX_SH_PS_BRILLO_RESPLANDOR]);
        for (int k = 0; k < g_fx_p.ntex; k++) {
            if (g_fx_p.halo[k][3] <= 0.0f || g_fx_p.halo_radio[k] <= 0.0f || !g_fx_p.halo_tiene_centro[k]) continue;
            float c[3], m[4];
            fx_punto_al_mundo(&g_fx_p, g_fx_hay_ancla == 1 ? g_fx_ancla_m : NULL, g_fx_p.halo_centro[k], c);
            for (int j = 0; j < 4; j++)
                m[j] = c[0] * g_fx_isla_vp[0 * 4 + j] + c[1] * g_fx_isla_vp[1 * 4 + j] + c[2] * g_fx_isla_vp[2 * 4 + j]
                       + g_fx_isla_vp[3 * 4 + j];
            if (m[3] <= 1.0f) continue;                              /* detrás de la cámara */
            float x = m[0] / m[3], y = m[1] / m[3];
            float rx = g_fx_p.halo_radio[k] * g_fx_isla_p11 / m[3], ry = g_fx_p.halo_radio[k] * g_fx_isla_p22 / m[3];
            if (x + rx < -1.0f || x - rx > 1.0f || y + ry < -1.0f || y - ry > 1.0f) continue;   /* fuera de la pantalla */
            float c0[4] = { g_fx_p.halo[k][0] * g_fx_p.halo[k][3], g_fx_p.halo[k][1] * g_fx_p.halo[k][3],
                            g_fx_p.halo[k][2] * g_fx_p.halo[k][3], 1.0f };
            /* ★ turno 25 · el BOMBILLO: c1.x = la caída de afuera, c1.y = la del núcleo (1/ancho²); c2 = el color del
             *   núcleo (el del astro, tirado a blanco) × su fuerza */
            const float *bo = g_fx_p.halo_bombillo[k];
            float c1[4] = { bo[3] > 0.0f ? bo[3] : 3.0f, 1.0f / (bo[1] * bo[1] > 1e-4f ? bo[1] * bo[1] : 1e-4f), 0, 0 };
            float c2[4];
            for (int j = 0; j < 3; j++) c2[j] = (g_fx_p.halo[k][j] + (1.0f - g_fx_p.halo[k][j]) * bo[2]) * bo[0];
            c2[3] = 0.0f;
            pc(dev, 0, c0, 1);
            pc(dev, 1, c1, 1);
            pc(dev, 2, c2, 1);
            DWORD desc[8];
            ZeroMemory(desc, sizeof(desc));
            ((FX_DESC_F)FXV(rt0)[12])(rt0, desc);
            float mp[4] = { desc[6] ? -1.0f / (float)desc[6] : 0.0f, desc[7] ? 1.0f / (float)desc[7] : 0.0f, 0, 0 };
            ((FX_SETC_F)vt[FX_SETVSCF])(dev, 0, mp, 1);
            float q[4][5] = { { x - rx, y + ry, 0, 0, 0 }, { x + rx, y + ry, 0, 1, 0 },
                              { x - rx, y - ry, 0, 0, 1 }, { x + rx, y - ry, 0, 1, 1 } };
            ((FX_D83)vt[FX_DPUP])(dev, 5 /* TRIANGLESTRIP */, 2, q, 5 * sizeof(float));
            g_fx_n_resplandores++;
        }
    }
    void *s_full = fx_superficie(g_fx_b_full), *s_a = fx_superficie(g_fx_b_a), *s_b = fx_superficie(g_fx_b_b);
    int ok = s_full && s_a && s_b
             && ((FX_STRETCH_F)vt[FX_STRETCHRECT])(dev, rt0, NULL, s_full, NULL, 0 /* NONE */) == 0;
    if (ok && !en_escena) ok = ((FX_ESCENA_F)vt[FX_BEGINSCENE])(dev) == 0;
    if (ok) {
        FX_SETRS_F rs = (FX_SETRS_F)vt[FX_SETRS];
        FX_SETSAMP_F sm = (FX_SETSAMP_F)vt[FX_SETSAMP];
        FX_SETTEX_F tx = (FX_SETTEX_F)vt[FX_SETTEX];
        FX_SETRT_F srt = (FX_SETRT_F)vt[FX_SETRT];
        FX_SETSH_F sps = (FX_SETSH_F)vt[FX_SETPS];
        FX_SETC_F pc = (FX_SETC_F)vt[FX_SETPSCF];
        rs(dev, FX_RS_ZENABLE, 0); rs(dev, FX_RS_ZWRITE, 0); rs(dev, FX_RS_ALPHATEST, 0); rs(dev, FX_RS_ALPHABLEND, 0);
        rs(dev, FX_RS_CULL, 1); rs(dev, FX_RS_FOGENABLE, 0); rs(dev, FX_RS_STENCIL, 0); rs(dev, FX_RS_SCISSOR, 0);
        rs(dev, FX_RS_COLORWRITE, 0xF); rs(dev, FX_RS_SRGBWRITE, 0); rs(dev, FX_RS_CLIPPLANES, 0); rs(dev, FX_RS_FILLMODE, 3);
        rs(dev, FX_RS_SEPALPHA, 0);
        sm(dev, 0, 5, 2); sm(dev, 0, 6, 2); sm(dev, 0, 7, 0);            /* MAG/MIN lineal, sin mip */
        sm(dev, 0, 1, 3); sm(dev, 0, 2, 3);                              /* CLAMP */
        sm(dev, 0, 11, 0);                                               /* SRGBTEXTURE */
        ((FX_SETF_F)vt[FX_SETFVF])(dev, 0x102);
        ((FX_SETSH_F)vt[FX_SETVS])(dev, g_fx_vs_pantalla);
        ((FX_SETDS_F)vt[FX_SETDS])(dev, NULL);
        float W = (float)g_fx_b_w, H = (float)g_fx_b_h, w4 = (float)(g_fx_b_w / 4), h4 = (float)(g_fx_b_h / 4);
        /* 1 · extraer: el cuadro entero → 1/4 */
        float c0[4] = { 1.0f / W, 1.0f / H, g_fx_p.brillo_umbral, g_fx_p.brillo_rodilla };
        srt(dev, 0, s_a); tx(dev, 0, g_fx_b_full); sps(dev, g_fx_ps[FX_SH_PS_BRILLO_EXTRAER]); pc(dev, 0, c0, 1);
        fx_cuadro(dev, vt, w4, h4);
        /* 2 · desenfocar: horizontal y vertical, `pases` veces */
        sps(dev, g_fx_ps[FX_SH_PS_BRILLO_DESENFOQUE]);
        for (int i = 0; i < g_fx_p.brillo_pases; i++) {
            float dx[4] = { 1.0f / w4, 0, 0, 0 }, dy[4] = { 0, 1.0f / h4, 0, 0 };
            srt(dev, 0, s_b); tx(dev, 0, g_fx_b_a); pc(dev, 0, dx, 1); fx_cuadro(dev, vt, w4, h4);
            srt(dev, 0, s_a); tx(dev, 0, g_fx_b_b); pc(dev, 0, dy, 1); fx_cuadro(dev, vt, w4, h4);
        }
        /* ★ turno 10 · 2b · ESTABLE en el tiempo: mezclado con el del cuadro anterior (si hubo uno hace < 0,5 s) */
        void *fuente = g_fx_b_a;
        if (g_fx_brillo_suave > 0.0f && g_fx_ps[FX_SH_PS_BRILLO_MEZCLAR] && g_fx_b_h1 && g_fx_b_h2) {
            void *s_h2 = fx_superficie(g_fx_b_h2);
            float ahora = fx_segundos(), dtb = ahora - g_fx_b_ultimo;
            float km[4] = { dtb >= 0.0f && dtb < 0.5f ? g_fx_brillo_suave : 0.0f, 0, 0, 0 };
            g_fx_b_ultimo = ahora;
            if (s_h2) {
                srt(dev, 0, s_h2); tx(dev, 0, g_fx_b_a); tx(dev, 1, g_fx_b_h1);
                sm(dev, 1, 5, 2); sm(dev, 1, 6, 2); sm(dev, 1, 7, 0); sm(dev, 1, 1, 3); sm(dev, 1, 2, 3); sm(dev, 1, 11, 0);
                sps(dev, g_fx_ps[FX_SH_PS_BRILLO_MEZCLAR]); pc(dev, 0, km, 1);
                fx_cuadro(dev, vt, w4, h4);
                tx(dev, 1, NULL);
                fx_soltar(s_h2);
                void *t = g_fx_b_h1; g_fx_b_h1 = g_fx_b_h2; g_fx_b_h2 = t;   /* el nuevo pasa a ser «el anterior» */
                fuente = g_fx_b_h1;
            }
        }
        /* 3 · sumar encima del cuadro */
        float k0[4] = { g_fx_p.brillo_int, g_fx_p.brillo_sat, 0, 0 };
        float k1[4] = { g_fx_p.brillo_tinte[0], g_fx_p.brillo_tinte[1], g_fx_p.brillo_tinte[2], 1 };
        srt(dev, 0, rt0); tx(dev, 0, fuente); sps(dev, g_fx_ps[FX_SH_PS_BRILLO_SUMAR]); pc(dev, 0, k0, 1); pc(dev, 1, k1, 1);
        rs(dev, FX_RS_ALPHABLEND, 1); rs(dev, FX_RS_SRCBLEND, 2); rs(dev, FX_RS_DESTBLEND, 2); rs(dev, FX_RS_BLENDOP, 1);
        fx_cuadro(dev, vt, W, H);
        g_fx_n_brillo++;
        /* ★ turno 2: lo excluido del brillo se dibuja AHORA, encima del brillo, con el z de la escena */
        if (g_fx_ndif > 0) {
            ((FX_SETRT_F)vt[FX_SETRT])(dev, 0, rt0);
            ((FX_SETDS_F)vt[FX_SETDS])(dev, ds0);
            InterlockedExchange(&g_fx_dentro, 0);
            fx_reproducir(dev);
            InterlockedExchange(&g_fx_dentro, 1);
        }
        if (!en_escena) ((FX_ESCENA_F)vt[FX_ENDSCENE])(dev);
    }
    ((FX_SETRT_F)vt[FX_SETRT])(dev, 0, rt0);
    ((FX_SETDS_F)vt[FX_SETDS])(dev, ds0);
    ((FX_SB_F)FXV(g_fx_b_sb)[5])(g_fx_b_sb);                            /* Apply: todo como estaba */
    fx_soltar(s_full); fx_soltar(s_a); fx_soltar(s_b);
    fx_soltar(ds0); fx_soltar(rt0);
    InterlockedExchange(&g_fx_dentro, 0);
    if (g_fx_ndif > 0) fx_reproducir_guardando(dev, en_escena);      /* si el brillo no llegó a hacerlos */
    if (!ok) {
        g_fx_brillo_roto = 1;
        apuntar("  [isla_fx] ⚠ el brillo falló (StretchRect/BeginScene): brillo apagado, la isla sigue");
    }
}

/* ¿este dibujo (que NO es de la isla) es el primero 2D después de la isla? */
static int fx_es_2d(void *dev, void **vt)
{
    DWORD fvf = 0;
    ((FX_GETF_F)vt[FX_GETFVF])(dev, &fvf);
    if ((fvf & FX_FVF_POSMASK) == FX_FVF_XYZRHW) return 1;
    float p[16];
    if (((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 3, p) != 0) return 0;
    return p[11] == 0.0f && p[15] == 1.0f;                     /* ortográfica: sin la división por w */
}

/* ★ turno 17 · las texturas del mar: s1 = la COSTA horneada (isla_fx_costa.h, creada una vez en D3DPOOL_MANAGED) y
 *   s2 = el CIELO real (la textura nocull_sky que cargó el juego; se guarda con AddRef al cargarse). Se ponen en el
 *   dibujo del mar y se devuelven (textura y muestreo de s1/s2) después. */
#include "isla_fx_costa.h"
static void *g_fx_tex_costa = NULL;
static int  g_fx_costa_rota = 0, g_fx_mar_tex_puesto = 0, g_fx_mar_cielo_puesto = 0;
static void *g_fx_mar_tex_ant[2];
static DWORD g_fx_mar_samp_ant[2][5];
static const DWORD g_fx_samp_tipos[5] = { 1, 2, 5, 6, 7 };       /* ADDRESSU, ADDRESSV, MAGFILTER, MINFILTER, MIPFILTER */
static int fx_mar_texturas(void *dev, void **vt, int con_cielo)
{
    if (g_fx_mar_tex_puesto) return 1;
    if (!g_fx_tex_costa && !g_fx_costa_rota) {
        void *tx = NULL;
        g_fx_costa_rota = 1;
        if (((FX_CREATETEX_F)vt[FX_CREATETEX])(dev, FX_COSTA_LADO, FX_COSTA_LADO, 1, 0, 21 /* A8R8G8B8 */, 1 /* MANAGED */,
                                               &tx, NULL) == 0 && tx) {
            DWORD lr[2] = { 0, 0 };
            if (((FX_LOCK_F)FXV(tx)[19])(tx, 0, lr, NULL, 0) == 0) {
                for (int y = 0; y < FX_COSTA_LADO; y++)
                    CopyMemory((BYTE *)(ULONG_PTR)lr[1] + y * (int)lr[0], FX_COSTA + y * FX_COSTA_LADO * 4, FX_COSTA_LADO * 4);
                ((FX_UNLOCK_F)FXV(tx)[20])(tx, 0);
                g_fx_tex_costa = tx;
                g_fx_costa_rota = 0;
                apuntar("  [isla_fx] ★ mar: la costa horneada (%dx%d) puesta", FX_COSTA_LADO, FX_COSTA_LADO);
            } else fx_soltar(tx);
        }
        if (g_fx_costa_rota) apuntar("  [isla_fx] ⚠ mar: no pude crear la textura de la costa: olas circulares de antes");
    }
    if (!g_fx_tex_costa) return 0;
    FX_GETSAMP_F gs = (FX_GETSAMP_F)vt[FX_GETSAMP];
    FX_SETSAMP_F ss = (FX_SETSAMP_F)vt[FX_SETSAMP];
    for (int s = 0; s < 2; s++) {
        g_fx_mar_tex_ant[s] = NULL;
        ((FX_GETTEX_F)vt[FX_GETTEX])(dev, 1 + s, &g_fx_mar_tex_ant[s]);
        for (int k = 0; k < 5; k++) gs(dev, 1 + s, g_fx_samp_tipos[k], &g_fx_mar_samp_ant[s][k]);
        ss(dev, 1 + s, 1, 3); ss(dev, 1 + s, 2, 3);              /* CLAMP */
        ss(dev, 1 + s, 5, 2); ss(dev, 1 + s, 6, 2); ss(dev, 1 + s, 7, s ? 2 : 0);
    }
    ((FX_SETTEX_F)vt[FX_SETTEX])(dev, 1, g_fx_tex_costa);
    g_fx_mar_cielo_puesto = con_cielo && g_fx_tex_cielo;
    ((FX_SETTEX_F)vt[FX_SETTEX])(dev, 2, g_fx_mar_cielo_puesto ? g_fx_tex_cielo : NULL);
    g_fx_mar_tex_puesto = 1;
    return 1;
}
/* ★ turno 23 · LA CAPA DE LA AURORA (isla_fx_aurora.h: la de texturas/aurora, DXT1 1024×512 con sus mips, en la UV
 *   de nocull_sky): se crea una vez (MANAGED) y se pone en s1 del CIELO y en s3 del MAR; después se devuelve. */
#include "isla_fx_aurora.h"
static void *g_fx_tex_aurora = NULL;
static int  g_fx_aurora_rota = 0, g_fx_aurora_etapa = -1;
static void *g_fx_aurora_ant = NULL;
static DWORD g_fx_aurora_samp_ant[5];
static int fx_aurora_poner(void *dev, void **vt, int etapa)
{
    if (g_fx_aurora_etapa >= 0) return 1;
    if (!g_fx_tex_aurora && !g_fx_aurora_rota) {
        void *tx = NULL;
        g_fx_aurora_rota = 1;
        if (((FX_CREATETEX_F)vt[FX_CREATETEX])(dev, FX_AURORA_ANCHO, FX_AURORA_ALTO, FX_AURORA_NIVELES, 0,
                                               0x31545844 /* DXT1 */, 1 /* MANAGED */, &tx, NULL) == 0 && tx) {
            const unsigned char *src = FX_AURORA;
            int ok = 1;
            for (int n = 0; n < FX_AURORA_NIVELES && ok; n++) {
                int w = FX_AURORA_ANCHO >> n, h = FX_AURORA_ALTO >> n;
                if (w < 1) w = 1;
                if (h < 1) h = 1;
                int bw = (w + 3) / 4, bh = (h + 3) / 4;
                DWORD lr[2] = { 0, 0 };
                if (((FX_LOCK_F)FXV(tx)[19])(tx, (UINT)n, lr, NULL, 0) != 0) { ok = 0; break; }
                for (int y = 0; y < bh; y++)                         /* una fila de bloques de 4×4 por vez */
                    CopyMemory((BYTE *)(ULONG_PTR)lr[1] + y * (int)lr[0], src + y * bw * 8, (SIZE_T)bw * 8);
                ((FX_UNLOCK_F)FXV(tx)[20])(tx, (UINT)n);
                src += bw * bh * 8;
            }
            if (ok && src == FX_AURORA + sizeof(FX_AURORA)) {
                g_fx_tex_aurora = tx;
                g_fx_aurora_rota = 0;
                apuntar("  [isla_fx] ★ aurora: la capa (%dx%d DXT1, %d niveles) puesta", FX_AURORA_ANCHO, FX_AURORA_ALTO,
                        FX_AURORA_NIVELES);
            } else fx_soltar(tx);
        }
        if (g_fx_aurora_rota) apuntar("  [isla_fx] ⚠ aurora: no pude crear la capa: el cielo sin aurora");
    }
    if (!g_fx_tex_aurora) return 0;
    FX_GETSAMP_F gs = (FX_GETSAMP_F)vt[FX_GETSAMP];
    FX_SETSAMP_F ss = (FX_SETSAMP_F)vt[FX_SETSAMP];
    g_fx_aurora_ant = NULL;
    ((FX_GETTEX_F)vt[FX_GETTEX])(dev, (DWORD)etapa, &g_fx_aurora_ant);
    for (int k = 0; k < 5; k++) gs(dev, (DWORD)etapa, g_fx_samp_tipos[k], &g_fx_aurora_samp_ant[k]);
    ss(dev, (DWORD)etapa, 1, 3); ss(dev, (DWORD)etapa, 2, 3);           /* CLAMP */
    ss(dev, (DWORD)etapa, 5, 2); ss(dev, (DWORD)etapa, 6, 2); ss(dev, (DWORD)etapa, 7, 2);   /* lineal, con mips */
    ((FX_SETTEX_F)vt[FX_SETTEX])(dev, (DWORD)etapa, g_fx_tex_aurora);
    g_fx_aurora_etapa = etapa;
    return 1;
}
static void fx_aurora_sacar(void *dev)
{
    if (g_fx_aurora_etapa < 0) return;
    void **vt = FXV(dev);
    FX_SETSAMP_F ss = (FX_SETSAMP_F)vt[FX_SETSAMP];
    ((FX_SETTEX_F)vt[FX_SETTEX])(dev, (DWORD)g_fx_aurora_etapa, g_fx_aurora_ant);
    fx_soltar(g_fx_aurora_ant);
    g_fx_aurora_ant = NULL;
    for (int k = 0; k < 5; k++) ss(dev, (DWORD)g_fx_aurora_etapa, g_fx_samp_tipos[k], g_fx_aurora_samp_ant[k]);
    g_fx_aurora_etapa = -1;
}

static void fx_mar_texturas_sacar(void *dev)
{
    if (!g_fx_mar_tex_puesto) return;
    void **vt = FXV(dev);
    FX_SETSAMP_F ss = (FX_SETSAMP_F)vt[FX_SETSAMP];
    for (int s = 0; s < 2; s++) {
        ((FX_SETTEX_F)vt[FX_SETTEX])(dev, 1 + s, g_fx_mar_tex_ant[s]);
        fx_soltar(g_fx_mar_tex_ant[s]);
        g_fx_mar_tex_ant[s] = NULL;
        for (int k = 0; k < 5; k++) ss(dev, 1 + s, g_fx_samp_tipos[k], g_fx_mar_samp_ant[s][k]);
    }
    g_fx_mar_tex_puesto = 0;
}

/* ★ turno 18c · ¿esta pasada es la «normal» (al backbuffer, viewport entero, sin planos de recorte, cull no invertido,
 *   sin mezcla, etapa 0 = textura sola)? La sonda anota cada forma distinta (las primeras 8). */
typedef HRESULT (WINAPI *FX_GETBB_F)(void *, UINT, UINT, DWORD, void **);   /* GetBackBuffer (18) */
static int fx_pasada_normal(void *dev, void **vt, int motivo, const float *mul, int vert)
{
    void *rt = NULL, *bb = NULL;
    DWORD vp[6], desc[8];
    ZeroMemory(vp, sizeof(vp));
    ZeroMemory(desc, sizeof(desc));
    ((FX_GETRT_F)vt[FX_GETRT])(dev, 0, &rt);
    ((FX_GETBB_F)vt[18])(dev, 0, 0, 0, &bb);
    if (rt) ((FX_DESC_F)FXV(rt)[12])(rt, desc);
    ((HRESULT (WINAPI *)(void *, DWORD *))vt[48])(dev, vp);            /* GetViewport */
    int al_bb = rt && rt == bb;
    fx_soltar(rt);
    fx_soltar(bb);
    int entero = vp[0] == 0 && vp[1] == 0 && vp[2] == desc[6] && vp[3] == desc[7];
    DWORD cull = fx_rs(vt, dev, FX_RS_CULL), recorte = fx_rs(vt, dev, FX_RS_CLIPPLANES), mezcla = fx_rs(vt, dev, FX_RS_ALPHABLEND);
    DWORD tf = fx_rs(vt, dev, FX_RS_TFACTOR), cop = fx_tss(vt, dev, FX_TSS_COLOROP), c1 = fx_tss(vt, dev, FX_TSS_COLORARG1);
    DWORD c2 = fx_tss(vt, dev, FX_TSS_COLORARG2);
    int textura_sola = !motivo && !vert && mul[0] == 1.0f && mul[1] == 1.0f && mul[2] == 1.0f;
    int normal = al_bb && entero && !recorte && cull != 2 /* CW = espejo */ && !mezcla && textura_sola;
    DWORD firma = (al_bb << 0) | (entero << 1) | ((recorte != 0) << 2) | (cull << 3) | (mezcla << 6) | (cop << 7) | (c1 << 12)
                  | (c2 << 17) | ((DWORD)(motivo & 7) << 22) | ((DWORD)textura_sola << 25);
    if (g_fx_sonda && g_fx_pasadas_anotadas < 8) {
        int vista = 0;
        for (int i = 0; i < g_fx_pasadas_anotadas; i++) vista |= g_fx_pasadas_firma[i] == firma;
        if (!vista) {
            g_fx_pasadas_firma[g_fx_pasadas_anotadas++] = firma;
            apuntar("  [isla_fx] sonda: PASADA con VS ajeno #%d: al backbuffer %d · viewport %u,%u %ux%u (destino %ux%u) · cull %u ·"
                    " recorte %u · mezcla %u · etapa0 op %u (%u,%u) motivo %d · tfactor %08X · ⇒ %s", g_fx_pasadas_anotadas, al_bb,
                    vp[0], vp[1], vp[2], vp[3], desc[6], desc[7], cull, recorte, mezcla, cop, c1, c2, motivo, (unsigned)tf,
                    normal ? "NORMAL (se pisa con pisar_vs=2)" : "no normal (no se toca con pisar_vs=2)");
        }
    }
    return normal;
}

/* ── el dibujo: antes y después ───────────────────────────────────────────────────────────────────────── */
static int fx_antes(void *dev, int tipo)
{
    void **vt = FXV(dev);
    if (g_fx_dentro) return 0;
    if (g_fx_sonda) { g_fx_n_dib[tipo]++; fx_sonda_segundo(); }
    if (!g_fx_nmarcas) return 0;
    void *tex = NULL;
    if (((FX_GETTEX_F)vt[FX_GETTEX])(dev, 0, &tex) != 0 || !tex) return 0;
    int idx = fx_buscar(tex);
    if (idx >= 0) {
        DWORD v = 0xFFFFFFFF, n = sizeof(v);
        if (((FX_PRIV_GET)FXV(tex)[5])(tex, &g_fx_guid, &v, &n) != 0 || v != (DWORD)idx) {
            fx_desmarcar(tex);                                   /* otra textura en la misma dirección */
            idx = -1;
        }
    }
    fx_soltar(tex);
    if (idx < 0 || idx >= g_fx_p.ntex) {
        if (g_fx_isla_cuadro && !g_fx_brillo_hecho && g_fx_activo && g_fx_brillo && g_fx_p.brillo_activo
            && g_fx_creados > 0 && fx_es_2d(dev, vt)) {
            g_fx_brillo_hecho = 1;
            fx_hacer_brillo(dev, 1);
        }
        return 0;
    }
    {
        /* ★ turno 7: el tick es el de VERDAD (antes «| 1» lo dejaba 1 ms en el futuro: ver FX_CAMP) */
        DWORD ahora = GetTickCount();
        g_fx_isla_tick = ahora ? ahora : 1;                      /* ★ turno 4: la escena es la isla (el near) */
        g_fx_d82_isla++;
        if (g_fx_camp_ev) {
            int trineo = 0;
            float w[16];
            float vw[16];
            if (idx == g_fx_camp_idx && g_fx_cs.armada && ((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 256, w) == 0
                && w[0] * w[0] + w[1] * w[1] + w[2] * w[2] > 1e-4f           /* escala del Mundo > 0,01: se ve */
                && ((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 2, vw) == 0
                && fx_ojo_cerca(vw, g_fx_camp_ojo))                          /* ★ turno 8: y la cámara es la del lobby */
                trineo = 1;
            if (g_fx_sonda && g_fx_ani_reinicios != g_fx_ani_anotado) {
                float cam[3];
                g_fx_ani_anotado = g_fx_ani_reinicios;
                if (((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 2, vw) == 0) {
                    fx_camara(vw, cam);
                    apuntar("  [isla_fx] sonda: campanillas: reinicio del .ani n.º %ld (por 0x49AB2B %ld · por 0x4C3FE0 %ld) ·"
                            " ojo (%d, %d, %d)", (long)g_fx_ani_reinicios, (long)g_fx_ani_sitio[0], (long)g_fx_ani_sitio[1],
                            (int)cam[0], (int)cam[1], (int)cam[2]);
                }
            }
            long mudas = g_fx_cs.mudas;
            if (fx_camp_isla(&g_fx_cs, ahora, g_fx_ani_reinicios, trineo)) {
                SetEvent(g_fx_camp_ev);
                if (g_fx_sonda)
                    apuntar("  [isla_fx] sonda: campanillas: el trineo se ve a %d ms de empezar la visita (%s, reinicio del"
                            " .ani n.º %ld)", (int)fx_ms(ahora, g_fx_cs.visita_t0), g_fx_cs.hay_gancho ? "por el .ani" : "por huecos",
                            (long)g_fx_ani_reinicios);
            } else if (g_fx_sonda && g_fx_cs.mudas != mudas)
                apuntar("  [isla_fx] sonda: campanillas: visita nueva a menos de 20 s de la anterior: queda muda");
        }
    }
    /* ★ turno 5 · el near TAMBIÉN al dibujar: si la PROJ se puso antes de que se viera la isla (la bienvenida la pone
     *   una vez, al empezar), SetTransform no la reconoce. Una vez por «tick» (~16 ms) se mira la PROJ puesta y, si es
     *   la de la isla con near ~1 (fx_cercano_decide, mismas tres condiciones), se pone la de near 100. Ya puesta, su
     *   near es 100 y no vuelve a entrar. */
    if (g_fx_activo && !g_fx_roto && g_fx_cercano > 0.0f && g_fx_settr_real0 && g_fx_isla_tick != g_fx_cerc_t) {
        float pj[16], vw[16], q[16], n = 0, f = 0, ojo = 0;
        g_fx_cerc_t = g_fx_isla_tick;
        if (((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 3, pj) == 0 && ((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 2, vw) == 0
            && fx_cercano_decide(pj, vw, g_fx_isla_tick, g_fx_isla_tick, g_fx_cercano_ojo, g_fx_cercano, q, &n, &f, &ojo) == 3) {
            g_fx_settr_real0(dev, 3, q);
            g_fx_n_cercano_tarde++;
        }
    }
    if (g_fx_sonda && g_fx_isla_proj_anotadas < 150 && g_fx_isla_tick - g_fx_isla_proj_t >= 1000) {
        /* ★ turno 5: la PROJ y el ojo con que SE DIBUJA la isla ahora (aunque el juego no llame a SetTransform) */
        float pj[16], vw[16];
        g_fx_isla_proj_t = g_fx_isla_tick;
        g_fx_isla_proj_anotadas++;
        if (((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 3, pj) == 0 && ((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 2, vw) == 0)
            fx_sonda_proj("la isla se dibuja con", pj, vw);
        if (!g_fx_z_anotado) {
            void *z = NULL;
            g_fx_z_anotado = 1;
            if (((FX_GETDS_F)vt[FX_GETDS])(dev, &z) == 0 && z) {
                DWORD d[8];
                ZeroMemory(d, sizeof(d));
                ((FX_DESC_F)FXV(z)[12])(z, d);
                apuntar("  [isla_fx] sonda: el z: formato %u (75 = D24S8 · 77 = D24X8 · 80 = D16 · 71 = D32) %ux%u, MSAA %u",
                        d[0], d[6], d[7], d[4]);
                fx_soltar(z);
            }
        }
    }
    /* ★ turno 4 · [partir]: el nodo de este dibujo, en la escena del .md9, decide si va como la parte */
    if (g_fx_p.parte_de[idx] && g_fx_hay_ancla == 1) {
        float w[16], q[3];
        if (((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 256, w) == 0 && fx_al_md9(&g_fx_p, g_fx_ancla_m, w + 12, q)
            && q[g_fx_p.parte_eje[idx]] < g_fx_p.parte_lim[idx])
            idx = g_fx_p.parte_de[idx] - 1;
    }
    fx_samp_poner(dev, vt);                                     /* ★ turno 9: trilineal + anisotrópico */
    if (g_fx_zsesgo && g_fx_p.tiene_zsesgo[idx] && !g_fx_zs_puesto) {      /* ★ turno 12: el sesgo de z de esta textura */
        g_fx_zs_ant[0] = fx_rs(vt, dev, 195);
        g_fx_zs_ant[1] = fx_rs(vt, dev, 175);
        DWORD a, b;
        CopyMemory(&a, &g_fx_p.zsesgo[idx][0], 4);
        CopyMemory(&b, &g_fx_p.zsesgo[idx][1], 4);
        ((FX_SETRS_F)vt[FX_SETRS])(dev, 195, a);
        ((FX_SETRS_F)vt[FX_SETRS])(dev, 175, b);
        g_fx_zs_puesto = 1;
    }
    if (g_fx_trazar && g_fx_traza_estado == 0) {                 /* ★ turno 11: ¿arrancó la cámara? */
        float vw[16];
        if (((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 2, vw) == 0) fx_traza_vista(vw);
    }
    if (g_fx_sonda) {                                           /* ★ turno 10: ¿algún dibujo de la isla con near ~1? */
        float pj[16];
        if (((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 3, pj) == 0 && pj[10] > 1.0f && -pj[14] / pj[10] < 50.0f) g_fx_n_near1++;
    }
    if (g_fx_sonda) { g_fx_n_marc[tipo]++; fx_sonda_dibujo(dev, vt, idx, tipo); }
    g_fx_isla_cuadro = 1;

    /* el ancla: dónde está la isla en el mundo ⇒ las luces */
    if (idx == g_fx_p.ancla) {
        float w[16];
        if (((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 256, w) == 0 && (!g_fx_hay_ancla || memcmp(w, g_fx_ancla_m, sizeof(w)))) {
            CopyMemory(g_fx_ancla_m, w, sizeof(w));
            g_fx_hay_ancla = 1;
            fx_luces_al_mundo(&g_fx_p, g_fx_ancla_m, g_fx_lpos, g_fx_lcol);
            fx_punto_al_mundo(&g_fx_p, g_fx_ancla_m, g_fx_p.astro_pos, g_fx_astro_m);
            g_fx_luces_nuevas = 1;
        }
    }
    if (g_fx_falsos) return 0;                                  /* ★ turno 12: colores falsos ⇒ el pipeline del juego */
    /* ★ turno 2 · excluida del brillo, modo DIFERIR: este dibujo se guarda y se hace DESPUÉS del brillo (fx_reproducir).
     *   Sólo 81/82 (los «UP» traen los vértices en memoria del juego, que no dura) y sólo si el brillo va a correr. */
    if (g_fx_p.sin_brillo[idx] && g_fx_p.excluir_modo == 0 && tipo < 2 && !g_fx_reproduciendo && g_fx_activo
        && g_fx_brillo && g_fx_p.brillo_activo && !g_fx_brillo_hecho && !g_fx_brillo_roto && g_fx_creados > 0
        && g_fx_pr_vt && g_fx_ndif < FX_DIFERIDOS) {
        g_fx_idx_diferido = idx;
        return 2;
    }
    int sombra = g_fx_p.sombra[idx];
    /* ★ turno 18b · cada salteo cuenta su MOTIVO (la sonda lo dice por segundo: en el selector todo daba «con
     *   sombreador 0» sin ningún aviso) */
    if (!g_fx_activo || g_fx_roto) { g_fx_salto[0]++; return 0; }
    if (sombra == FX_NINGUNO || !g_fx_efecto[sombra]) { g_fx_salto[1]++; return 0; }
    if (dev != g_fx_dev) {
        if (g_fx_dev) {
            g_fx_roto = 1;
            apuntar("  [isla_fx] ⚠ cambió el dispositivo que dibuja (%p → %p): la capa 4 se apaga", g_fx_dev, dev);
            g_fx_salto[2]++;
            return 0;
        }
        g_fx_dev = dev;
    }
    if (!fx_crear(dev)) { g_fx_salto[3]++; return 0; }
    void *ps = fx_ps_de(sombra);
    if (!ps) { g_fx_salto[3]++; return 0; }

    /* 1 · el juego sin sombreadores */
    void *vs0 = NULL, *ps0 = NULL;
    ((FX_GETSH_F)vt[FX_GETVS])(dev, &vs0);
    ((FX_GETSH_F)vt[FX_GETPS])(dev, &ps0);
    /* ★ turno 18 · EL SELECTOR: ahí la isla se dibuja con un sombreador de PÍXEL ajeno puesto (lo deja el dibujo de
     *   los muñecos; los vértices siguen en fixed-function) y por eso no iba lo nuestro (la sonda: «con sombreador 0»
     *   en toda la escena). Con [isla_fx] pisar_ps=1 (de fábrica) se pone el nuestro igual y DESPUÉS se devuelve el
     *   ajeno (fx_despues); con un sombreador de VÉRTICES ajeno, nunca. */
    /* ★ turno 18b · y un sombreador de VÉRTICES ajeno (la sonda lo cuenta): con [isla_fx] pisar_vs=1 se pone el nuestro
     *   SÓLO si la proyección puesta es la de la isla (perspectiva, far 30.000..50.000: las matrices de Direct3D son las
     *   de la isla y las nuestras dan lo mismo) y después se devuelve el ajeno. */
    int vs_ok = !vs0;
    int vs_ajeno = vs0 != NULL;
    if (vs0) {
        g_fx_salto[4]++;
        float pj[16], n0 = 0, f0 = 0;
        if (g_fx_pisar_vs && (g_fx_pisar_vs != 3 || sombra == FX_MAR || sombra == FX_CIELO)
            && ((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 3, pj) == 0 && fx_proj_perspectiva(pj, &n0, &f0)
            && f0 > 30000.0f && f0 < 50000.0f) vs_ok = 1;
        if (!g_fx_vs_ajeno_anotado) {
            DWORD fv = 0;
            ((FX_GETF_F)vt[FX_GETFVF])(dev, &fv);
            g_fx_vs_ajeno_anotado = 1;
            apuntar("  [isla_fx] la isla se dibuja con un sombreador de VÉRTICES ajeno (%p, FVF 0x%X, PROJ far %d): pisar_vs=%d",
                    vs0, fv, (int)f0, g_fx_pisar_vs);
            /* ★ turno 18d · ¿el VS ajeno lleva las matrices en sus CONSTANTES? Se anotan c0..c11 y la Mundo×Vista×Proy de
             *   GetTransform, para comparar (y algún día reconstruir la nuestra desde ahí) */
            float cs[12][4], mw[16], mv[16], mp[16], a1[16], a2[16];
            ZeroMemory(cs, sizeof(cs));
            ((HRESULT (WINAPI *)(void *, UINT, float *, UINT))vt[95])(dev, 0, &cs[0][0], 12);   /* GetVertexShaderConstantF */
            if (((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 256, mw) == 0 && ((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 2, mv) == 0
                && ((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 3, mp) == 0) {
                fx_mul44(mw, mv, a1);
                fx_mul44(a1, mp, a2);
                for (int r = 0; r < 4; r++)
                    apuntar("  [isla_fx]   MxVxP fila %d (×1000): %d %d %d %d · columna %d: %d %d %d %d", r,
                            (int)(a2[r * 4] * 1000), (int)(a2[r * 4 + 1] * 1000), (int)(a2[r * 4 + 2] * 1000), (int)(a2[r * 4 + 3] * 1000), r,
                            (int)(a2[r] * 1000), (int)(a2[4 + r] * 1000), (int)(a2[8 + r] * 1000), (int)(a2[12 + r] * 1000));
            }
            for (int r = 0; r < 12; r++)
                apuntar("  [isla_fx]   VS ajeno c%d (×1000): %d %d %d %d", r, (int)(cs[r][0] * 1000), (int)(cs[r][1] * 1000),
                        (int)(cs[r][2] * 1000), (int)(cs[r][3] * 1000));
        }
    }
    int libres = vs_ok && (!ps0 || g_fx_pisar_ps);
    if (ps0) { g_fx_n_ps_ajeno++; if (!g_fx_pisar_ps) g_fx_salto[5]++; }
    fx_soltar(vs0);
    fx_soltar(ps0);
    if (!libres) return 0;
    /* 2 · la forma del vértice */
    DWORD fvf = 0;
    ((FX_GETF_F)vt[FX_GETFVF])(dev, &fvf);
    void *vs = fvf == 0x112 ? g_fx_vs[0] : fvf == 0x152 ? g_fx_vs[1] : fvf == 0x102 ? g_fx_vs[2] : NULL;
    if (!vs) {
        g_fx_salto[6]++;
        if (!g_fx_motivo_visto[idx]) { g_fx_motivo_visto[idx] = 1; apuntar("  [isla_fx] «%s»: FVF 0x%X no soportado, va como siempre", g_fx_p.tex[idx], fvf); }
        return 0;
    }
    /* 3 · la etapa 0 */
    float mat[17], mul[4];
    ZeroMemory(mat, sizeof(mat));
    ((FX_GETMAT_F)vt[FX_GETMATERIAL])(dev, mat);
    int vert = 0;
    int motivo = fx_etapa0(fx_tss(vt, dev, FX_TSS_COLOROP), fx_tss(vt, dev, FX_TSS_COLORARG1), fx_tss(vt, dev, FX_TSS_COLORARG2),
                           fx_tss(vt, dev, FX_TSS_ALPHAOP), fx_tss(vt, dev, FX_TSS_ALPHAARG1), fx_tss(vt, dev, FX_TSS_ALPHAARG2),
                           fx_rs(vt, dev, FX_RS_TFACTOR), fx_rs(vt, dev, FX_RS_LIGHTING), fvf, mat[3], mul, &vert);
    /* ★ turno 18c · con un VS ajeno, la PASADA: en el selector la isla va DOS veces por cuadro con un VS ajeno; pisar
     *   las dos dejó una cuña negra y la ballena negra. La sonda anota cada forma de pasada distinta (destino, viewport,
     *   cull, planos de recorte, etapa 0, TFACTOR, mezcla, z) y, con pisar_vs=2 (de fábrica), sólo se pisa la NORMAL:
     *   al backbuffer, viewport entero, sin planos de recorte, cull no invertido, sin mezcla y la etapa 0 = la textura
     *   sola (sin TFACTOR ni color de vértice). */
    if (vs_ajeno) {
        int normal = fx_pasada_normal(dev, vt, motivo, mul, vert);
        if (!normal && g_fx_pisar_vs >= 2) { g_fx_salto[4]--; g_fx_salto[8]++; return 0; }
    }
    if (motivo) {
        g_fx_salto[7]++;
        if (!g_fx_motivo_visto[idx]) { g_fx_motivo_visto[idx] = 1; apuntar("  [isla_fx] «%s»: etapa 0 que no copiamos (motivo %d), va como siempre", g_fx_p.tex[idx], motivo); }
        return 0;
    }

    /* las matrices */
    float m[16], v[16], p[16], vp[16];
    if (((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 256, m) != 0 || ((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 2, v) != 0
        || ((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 3, p) != 0) return 0;
    fx_mul44(v, p, vp);
    if (vs_ajeno) {
        /* ★ turno 18e · MEDIDO en el selector: el VS ajeno trae c0..c3 = Mundo×Vista×Proy TRASPUESTA, con SU near (1),
         *   y la isla va en DOS pasadas. La nuestra con el near 100 de GetTransform no coincidía en el z con la otra
         *   pasada ⇒ la prueba de z la tiraba (la cuña negra, la ballena negra). Ahora: VP = Mundo⁻¹ × (c0..c3)ᵀ, así el
         *   punto en pantalla y su z son EXACTAMENTE los del juego en esa pasada. */
        float cs[16], mvp[16], minv[16];
        if (((HRESULT (WINAPI *)(void *, UINT, float *, UINT))vt[95])(dev, 0, cs, 4) == 0 && fx_inv44(m, minv)) {
            for (int i = 0; i < 4; i++)
                for (int j = 0; j < 4; j++) mvp[i * 4 + j] = cs[j * 4 + i];
            fx_mul44(minv, mvp, vp);
        }
    }
    CopyMemory(g_fx_isla_vp, vp, sizeof(g_fx_isla_vp));        /* ★ turno 14: para el resplandor */
    g_fx_isla_p11 = p[0]; g_fx_isla_p22 = p[5]; g_fx_hay_vp = 1;
    float vsc[36];
    CopyMemory(vsc, m, 64);
    CopyMemory(vsc + 16, vp, 64);
    vsc[32] = v[2]; vsc[33] = v[6]; vsc[34] = v[10]; vsc[35] = v[14];

    /* las del sombreador de píxel: c0..c15 */
    float pc[16][4];
    ZeroMemory(pc, sizeof(pc));
    pc[0][0] = fx_segundos(); pc[0][1] = g_fx_noche ? 1.0f : 0.0f; pc[0][2] = g_fx_p.mezcla; pc[0][3] = vert ? 1.0f : 0.0f;
    pc[1][0] = mul[0]; pc[1][1] = mul[1]; pc[1][2] = mul[2]; pc[1][3] = mul[3];
    for (int i = 0; i < 8; i++)
        for (int j = 0; j < 4; j++) pc[2 + i][j] = g_fx_p.ct[idx][i][j];
    /* ★ turno 18f · LA DERIVA DEL MAR (anonimo03: «el sentido del mar sigue hacia ABAJO, que sea hacia ARRIBA»): el oleaje
     *   corría hacia −z (hacia las cámaras del lobby y del selector, que miran a +z): en pantalla, hacia abajo, como si
     *   «naciera de la isla». Con [isla_fx] mar_deriva=1 (de fábrica) va al revés: hacia el horizonte. −1 = como antes.
     *   Las olas a la costa no cambian (van siempre hacia la costa). */
    if (sombra == FX_MAR && g_fx_mar_deriva >= 0) pc[2][2] = -pc[2][2];
    float cam[3];
    fx_camara(v, cam);
    DWORD niebla = fx_rs(vt, dev, FX_RS_FOGENABLE), modo = 0;
    if (niebla) {
        DWORD tm = fx_rs(vt, dev, FX_RS_FOGTABLEMODE), vm = fx_rs(vt, dev, FX_RS_FOGVERTEXMODE), k = tm ? tm : vm;
        modo = k == 3 ? 1 : k == 1 ? 2 : k == 2 ? 3 : 0;
    }
    /* ★ turno 18g · con un VS AJENO la niebla es SUYA (la calcula él, con sus unidades): la nuestra, hecha con las
     *   perillas de Direct3D, ponía NEGRO el mar lejano del selector (la cuña). Ahí, sin niebla nuestra. */
    if (vs_ajeno && modo) {
        if (!g_fx_niebla_ajena_anotada) {
            g_fx_niebla_ajena_anotada = 1;
            apuntar("  [isla_fx] con VS ajeno la niebla está prendida (modo %u, %d..%d, color %08X): la nuestra NO se aplica",
                    modo, (int)fx_f(fx_rs(vt, dev, FX_RS_FOGSTART)), (int)fx_f(fx_rs(vt, dev, FX_RS_FOGEND)),
                    (unsigned)fx_rs(vt, dev, FX_RS_FOGCOLOR));
        }
        modo = 0;
    }
    pc[10][0] = cam[0]; pc[10][1] = cam[1]; pc[10][2] = cam[2]; pc[10][3] = (float)modo;
    if (modo) {
        DWORD fc = fx_rs(vt, dev, FX_RS_FOGCOLOR);
        pc[11][0] = ((fc >> 16) & 0xFF) / 255.0f; pc[11][1] = ((fc >> 8) & 0xFF) / 255.0f; pc[11][2] = (fc & 0xFF) / 255.0f;
        pc[11][3] = fx_f(fx_rs(vt, dev, FX_RS_FOGDENSITY));
        float a = fx_f(fx_rs(vt, dev, FX_RS_FOGSTART)), b = fx_f(fx_rs(vt, dev, FX_RS_FOGEND));
        pc[12][0] = a; pc[12][1] = b; pc[12][2] = (b > a) ? 1.0f / (b - a) : 0.0f;
    }
    for (int j = 0; j < 4; j++) { pc[13][j] = g_fx_p.astro_dir[j]; pc[14][j] = g_fx_p.astro_col[j]; pc[15][j] = g_fx_p.cielo_col[j]; }
    pc[15][3] = (g_fx_p.sin_brillo[idx] && g_fx_p.excluir_modo == 1) ? g_fx_p.tope : 0.0f;   /* el tope de brillo */
    /* ★ turno 3: el astro PINTADO.
     *   · el CIELO de día centra su realce (y el halo, si se prende) en el sol pintado: la dirección cámara → sol
     *     pintado va en su c9 (x, y, z, 1), como si fuera c9_dia;
     *   · el mar y lo iluminado siguen con [astro] dir_* (el camino de luz de noche quedó aprobado así), salvo
     *     `reflejo_desde_pos = 1`: entonces cada píxel mira a la posición (reflejo geométrico). */
    if (g_fx_p.tiene_astro_pos) {
        if (sombra == FX_CIELO && !g_fx_noche) {
            float d[3] = { g_fx_astro_m[0] - cam[0], g_fx_astro_m[1] - cam[1], g_fx_astro_m[2] - cam[2] };
            float l2 = d[0] * d[0] + d[1] * d[1] + d[2] * d[2], x = 1.0f;
            if (l2 > 1e-6f) {
                float r = 1.0f / l2;
                for (int it = 0; it < 30; it++) x = 0.5f * (x + r / x);
                pc[9][0] = d[0] * x; pc[9][1] = d[1] * x; pc[9][2] = d[2] * x; pc[9][3] = 1.0f;
            }
        }
        if (g_fx_p.reflejo_desde_pos && sombra != FX_CIELO) {
            pc[13][0] = g_fx_astro_m[0]; pc[13][1] = g_fx_astro_m[1]; pc[13][2] = g_fx_astro_m[2];
            pc[12][3] = 1.0f;
        }
    }
    if (!g_fx_hay_ancla) {                                       /* sin ancla todavía: las luces tal cual el perfil */
        fx_luces_al_mundo(&g_fx_p, NULL, g_fx_lpos, g_fx_lcol);
        fx_punto_al_mundo(&g_fx_p, NULL, g_fx_p.astro_pos, g_fx_astro_m);
        g_fx_luces_nuevas = 1;
        g_fx_hay_ancla = -1;
    }

    FX_SETC_F vsf = (FX_SETC_F)vt[FX_SETVSCF], psf = (FX_SETC_F)vt[FX_SETPSCF];
    if (!g_fx_ps_ajeno) ((FX_GETSH_F)vt[FX_GETPS])(dev, &g_fx_ps_ajeno);      /* ★ turno 18: el ajeno (con su ref) */
    if (!g_fx_vs_ajeno) ((FX_GETSH_F)vt[FX_GETVS])(dev, &g_fx_vs_ajeno);      /* ★ turno 18b: ídem el de vértices */
    /* ★ turno 18f · MEDIDO con pisar_vs=3 (sólo mar y cielo): la ballena, que NO pisamos, salía negra. Era que al
     *   pisar el mar le cambiábamos al VS ajeno sus CONSTANTES (c0..c8: sus matrices y lo de la luz) y el juego no las
     *   vuelve a poner en el dibujo siguiente. Ahora se guardan antes y se devuelven después (y las del píxel, si el
     *   sombreador de píxel también era ajeno). */
    g_fx_k_vs_guardadas = 0;
    g_fx_k_ps_guardadas = 0;
    if (g_fx_vs_ajeno && ((HRESULT (WINAPI *)(void *, UINT, float *, UINT))vt[95])(dev, 0, &g_fx_k_vs[0][0], 10) == 0)
        g_fx_k_vs_guardadas = 1;
    if (g_fx_ps_ajeno && ((HRESULT (WINAPI *)(void *, UINT, float *, UINT))vt[110])(dev, 0, &g_fx_k_ps[0][0], 160) == 0)
        g_fx_k_ps_guardadas = 1;
    if (((FX_SETSH_F)vt[FX_SETVS])(dev, vs) != 0) {
        fx_soltar(g_fx_ps_ajeno); g_fx_ps_ajeno = NULL; fx_soltar(g_fx_vs_ajeno); g_fx_vs_ajeno = NULL;
        g_fx_k_vs_guardadas = g_fx_k_ps_guardadas = 0;
        return 0;
    }
    if (((FX_SETSH_F)vt[FX_SETPS])(dev, ps) != 0) {
        ((FX_SETSH_F)vt[FX_SETVS])(dev, g_fx_vs_ajeno);
        fx_soltar(g_fx_ps_ajeno); g_fx_ps_ajeno = NULL; fx_soltar(g_fx_vs_ajeno); g_fx_vs_ajeno = NULL;
        g_fx_k_vs_guardadas = g_fx_k_ps_guardadas = 0;
        return 0;
    }
    vsf(dev, 0, vsc, 9);
    psf(dev, 0, &pc[0][0], 16);
    {                                                           /* ★ turno 16 / 17: las extra e0..e7 → c144..c151 */
        float ex[8][4];
        CopyMemory(ex, g_fx_p.et[idx], sizeof(ex));
        if (sombra == FX_MAR && g_fx_mar_deriva >= 0) ex[7][3] = -ex[7][3];    /* ★ turno 18f: el ruido, hacia el horizonte */
        if (sombra == FX_MAR) {
            const float *an = g_fx_hay_ancla == 1 ? g_fx_ancla_m : NULL;
            float cm[3], q[3] = { ex[4][0], ex[5][3], ex[4][2] }, cq[3];
            fx_punto_al_mundo(&g_fx_p, an, ex[0], cm);
            ex[0][0] = cm[0]; ex[0][1] = cm[1]; ex[0][2] = cm[2];
            fx_punto_al_mundo(&g_fx_p, an, q, cq);                 /* el cilindro del cielo, al mundo */
            ex[4][0] = cq[0]; ex[4][2] = cq[2]; ex[5][3] = cq[1];
            /* ★ turno 17: la costa horneada en s1 y el cielo real en s2 (si no están, sus banderas en 0) */
            int costa = ex[6][0] > 0.0f && fx_mar_texturas(dev, vt, ex[6][1] > 0.0f);
            ex[6][0] = costa ? 1.0f : 0.0f;
            ex[6][1] = (costa && g_fx_mar_cielo_puesto) ? ex[6][1] : 0.0f;
        }
        if (sombra == FX_CIELO) {                                    /* ★ turno 24: el centro del cilindro, al mundo */
            const float *an = g_fx_hay_ancla == 1 ? g_fx_ancla_m : NULL;
            float cm[3];
            fx_punto_al_mundo(&g_fx_p, an, ex[4], cm);
            ex[4][0] = cm[0]; ex[4][1] = cm[1]; ex[4][2] = cm[2];
        }
        if (sombra == FX_CIELO && g_fx_noche) {                      /* ★ turno 23: la capa de la aurora en s1 */
            if (!(ex[0][0] > 0.0f && fx_aurora_poner(dev, vt, 1))) ex[0][0] = 0.0f;
        }
        psf(dev, 144, &ex[0][0], 8);
        if (sombra == FX_MAR) {                                      /* ★ turno 22: la aurora propia, para su reflejo */
            float au[6][4];                                  /* e0, e1, e2, e3, e6 y e7 (★ turno 24) de [cielo] → c152..c157 */
            CopyMemory(au, g_fx_p.e[FX_CIELO], 4 * sizeof(au[0]));
            CopyMemory(au[4], g_fx_p.e[FX_CIELO][6], 2 * sizeof(au[0]));
            /* de día no hay aurora; sin la capa (s3), tampoco; sin el cielo real no hay reflejo del cilindro */
            if (!g_fx_noche || !(au[0][0] > 0.0f && au[4][3] > 0.0f && ex[6][1] > 0.0f && fx_aurora_poner(dev, vt, 3)))
                au[0][0] = 0.0f;
            psf(dev, 152, &au[0][0], 6);
        }
    }
    static int s_entrando = 0;
    static float s_t_ant = -1.0f;
    float s_ahora = s_entrando ? fx_segundos() : 0.0f;
    if (g_fx_luces_nuevas || memcmp(v, g_fx_v_ult, sizeof(g_fx_v_ult))
        || (s_entrando && s_ahora - s_t_ant >= 0.008f)) {               /* la cámara se movió, cambiaron, o entran */
        /* ★ turno 8: con histéresis y las nuevas entrando suave (mientras alguna entra, ~120 veces por segundo) */
        static int ant[FX_MAX_LUCES];
        static float peso[FX_MAX_LUCES];
        float ahora = fx_segundos(), t_ant = s_t_ant, dt = t_ant < 0.0f || ahora < t_ant ? 1.0f : ahora - t_ant;
        if (dt > 1.0f) dt = 1.0f;
        s_t_ant = ahora;
        int antes[FX_MAX_LUCES];
        CopyMemory(antes, ant, sizeof(antes));
        s_entrando = fx_elegir_luces_suave(g_fx_lpos, g_fx_lcol, v, g_fx_nluz, g_fx_spos, g_fx_scol, ant, peso, dt);
        for (int i = 0; i < FX_MAX_LUCES; i++) if (antes[i] != ant[i]) g_fx_n_luz_cambios++;   /* ★ turno 10 */
        CopyMemory(g_fx_v_ult, v, sizeof(g_fx_v_ult));
        g_fx_luces_nuevas = 0;
    }
    if (g_fx_nluz >= 64) {                                  /* ★ turno 10: los 64 lugares */
        psf(dev, 16, &g_fx_spos[0][0], 64);
        psf(dev, 80, &g_fx_scol[0][0], 64);
    } else {
        psf(dev, 16, &g_fx_spos[0][0], 32);
        psf(dev, 48, &g_fx_scol[0][0], 32);
    }
    if (g_fx_sonda) g_fx_n_aplic++;
    g_fx_auto_dib++;                                            /* ★ turno 27: la isla se está viendo */
    return 1;
}

static void fx_despues(void *dev)
{
    void **vt = FXV(dev);
    if (g_fx_k_vs_guardadas) { ((FX_SETC_F)vt[FX_SETVSCF])(dev, 0, &g_fx_k_vs[0][0], 10); g_fx_k_vs_guardadas = 0; }   /* ★ 18f */
    if (g_fx_k_ps_guardadas) { ((FX_SETC_F)vt[FX_SETPSCF])(dev, 0, &g_fx_k_ps[0][0], 160); g_fx_k_ps_guardadas = 0; }
    ((FX_SETSH_F)vt[FX_SETVS])(dev, g_fx_vs_ajeno);              /* ★ turno 18b: el ajeno, o NULL */
    ((FX_SETSH_F)vt[FX_SETPS])(dev, g_fx_ps_ajeno);              /* ★ turno 18: el ajeno del selector, o NULL */
    fx_soltar(g_fx_ps_ajeno);
    g_fx_ps_ajeno = NULL;
    fx_soltar(g_fx_vs_ajeno);
    g_fx_vs_ajeno = NULL;
    fx_mar_texturas_sacar(dev);                                 /* ★ turno 17 */
    fx_aurora_sacar(dev);                                       /* ★ turno 23 */
}

static void fx_fallo(HRESULT hr)
{
    g_fx_fallos++;
    if (g_fx_fallos <= 5) apuntar("  [isla_fx] ⚠ un dibujo con sombreador falló (hr 0x%08X): se repitió sin él", (unsigned)hr);
    if (g_fx_fallos == 50) { g_fx_roto = 1; apuntar("  [isla_fx] ⛔ 50 dibujos fallados: la capa 4 se apaga sola"); }
}

/* ── las tablas: por cada tabla de métodos vista, los originales de 81..84 ──────────────────────────────── */
#define FX_TABLAS 8
static struct { void **vt; void *real[4]; int por_sala; } g_fx_t[FX_TABLAS];
static volatile LONG g_fx_nt = 0;

static int fx_tabla(void *dev)
{
    void **vt = FXV(dev);
    for (LONG i = 0; i < g_fx_nt; i++)
        if (g_fx_t[i].vt == vt) return (int)i;
    return -1;
}

static HRESULT WINAPI fx_d81(void *dev, DWORD tipo, UINT ini, UINT n);
static HRESULT WINAPI fx_d82(void *dev, DWORD tipo, INT base, UINT minimo, UINT nv, UINT ini, UINT n);
static HRESULT WINAPI fx_d83(void *dev, DWORD tipo, UINT n, const void *datos, UINT paso);
static HRESULT WINAPI fx_d84(void *dev, DWORD tipo, UINT minimo, UINT nv, UINT n, const void *idx, DWORD fmt, const void *datos, UINT paso);
static void fx_vigia_cuadro(const char *donde);         /* ★ 21-nov (más abajo) */

/* lo que tiene que haber en la entrada `k` (0..3 = 81..84) de la tabla para que el gancho esté puesto */
static void *fx_esperado(int t, int k)
{
    if (k < 2 && g_fx_t[t].por_sala) return k == 0 ? (void *)sa_dibujar : (void *)sa_dibujar_idx;
    return k == 0 ? (void *)fx_d81 : k == 1 ? (void *)fx_d82 : k == 2 ? (void *)fx_d83 : (void *)fx_d84;
}

static void fx_escribir(void **lugar, void *valor)
{
    DWORD viejo = 0;
    sa_candado_tomar();                                  /* ★ 21-nov: un solo escritor (ver sala_alfa.c) */
    if (VirtualProtect(lugar, sizeof(void *), PAGE_EXECUTE_READWRITE, &viejo)) {
        *lugar = valor;
        VirtualProtect(lugar, sizeof(void *), viejo, &viejo);
    }
    sa_candado_soltar();
}

/* con los sombreadores puestos: ¿Direct3D cambió la función de dibujo? ⇒ se llama a la nueva */
static void *fx_destino(int t, int k)
{
    void *ahora = g_fx_t[t].vt[FX_DP + k];
    if (ahora == fx_esperado(t, k)) return g_fx_t[t].real[k];
    g_fx_reescrituras++;
    return ahora;
}

/* sin los sombreadores: si Direct3D reescribió la entrada, el original nuevo queda anotado y el gancho vuelve */
static void fx_reponer(int t, int k)
{
    void *ahora = g_fx_t[t].vt[FX_DP + k], *esperado = fx_esperado(t, k);
    if (ahora == esperado) return;
    g_fx_t[t].real[k] = ahora;
    fx_escribir(&g_fx_t[t].vt[FX_DP + k], esperado);
}

/* ★ turno 5 · EL HALO: antes de guardar un dibujo diferido (la luna, el sol del cartel), se lo dibuja YA con la silueta
 *   de un color liso (ps_halo) y SIN escribir el z: el brillo la difumina alrededor. Después del brillo se dibuja la de
 *   siempre encima, nítida. Devuelve el ZWRITE de antes (+1) si quedó puesto, 0 si no (y no se dibuja el halo). */
static int fx_halo_poner(void *dev)
{
    void **vt = FXV(dev);
    int idx = g_fx_idx_diferido;
    if (idx < 0 || idx >= g_fx_p.ntex || g_fx_p.halo[idx][3] <= 0.0f || g_fx_roto || !g_fx_ps[FX_SH_PS_HALO]) return 0;
    if (g_fx_p.halo_radio[idx] > 0.0f) return 0;                 /* ★ turno 14: va el resplandor radial, no la silueta */
    void *vs0 = NULL, *ps0 = NULL;
    ((FX_GETSH_F)vt[FX_GETVS])(dev, &vs0);
    ((FX_GETSH_F)vt[FX_GETPS])(dev, &ps0);
    int libres = !vs0 && !ps0;
    fx_soltar(vs0);
    fx_soltar(ps0);
    if (!libres) return 0;
    DWORD fvf = 0;
    ((FX_GETF_F)vt[FX_GETFVF])(dev, &fvf);
    void *vs = fvf == 0x112 ? g_fx_vs[0] : fvf == 0x152 ? g_fx_vs[1] : fvf == 0x102 ? g_fx_vs[2] : NULL;
    if (!vs) return 0;
    float mat[17], mul[4];
    ZeroMemory(mat, sizeof(mat));
    ((FX_GETMAT_F)vt[FX_GETMATERIAL])(dev, mat);
    int vert = 0;
    if (fx_etapa0(fx_tss(vt, dev, FX_TSS_COLOROP), fx_tss(vt, dev, FX_TSS_COLORARG1), fx_tss(vt, dev, FX_TSS_COLORARG2),
                  fx_tss(vt, dev, FX_TSS_ALPHAOP), fx_tss(vt, dev, FX_TSS_ALPHAARG1), fx_tss(vt, dev, FX_TSS_ALPHAARG2),
                  fx_rs(vt, dev, FX_RS_TFACTOR), fx_rs(vt, dev, FX_RS_LIGHTING), fvf, mat[3], mul, &vert)) return 0;
    float m[16], v[16], p[16], vp[16], vsc[40], pc[4][4];
    if (((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 256, m) != 0 || ((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 2, v) != 0
        || ((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 3, p) != 0) return 0;
    fx_mul44(v, p, vp);
    CopyMemory(vsc, m, 64);
    CopyMemory(vsc + 16, vp, 64);
    vsc[32] = v[2]; vsc[33] = v[6]; vsc[34] = v[10]; vsc[35] = v[14];
    pc[0][0] = fx_segundos(); pc[0][1] = g_fx_noche ? 1.0f : 0.0f; pc[0][2] = 1.0f; pc[0][3] = vert ? 1.0f : 0.0f;
    for (int j = 0; j < 4; j++) { pc[1][j] = mul[j]; pc[2][j] = g_fx_p.halo[idx][j]; }
    pc[3][0] = g_fx_p.halo_op[idx]; pc[3][1] = pc[3][2] = pc[3][3] = 0.0f;
    /* ★ turno 8: la silueta AGRANDADA alrededor de su centro (sólo con el vértice de la isla, 0x112) */
    float hc[4] = { 0, 0, 0, 1 };
    if (fvf == 0x112 && g_fx_vs_halo && g_fx_p.halo_tiene_centro[idx] && g_fx_p.halo_esc[idx] > 1.0f) {
        fx_punto_al_mundo(&g_fx_p, g_fx_hay_ancla == 1 ? g_fx_ancla_m : NULL, g_fx_p.halo_centro[idx], hc);
        hc[3] = g_fx_p.halo_esc[idx];
        vs = g_fx_vs_halo;
    }
    if (((FX_SETSH_F)vt[FX_SETVS])(dev, vs) != 0) return 0;
    if (((FX_SETSH_F)vt[FX_SETPS])(dev, g_fx_ps[FX_SH_PS_HALO]) != 0) { ((FX_SETSH_F)vt[FX_SETVS])(dev, NULL); return 0; }
    vsc[36] = hc[0]; vsc[37] = hc[1]; vsc[38] = hc[2]; vsc[39] = hc[3];
    ((FX_SETC_F)vt[FX_SETVSCF])(dev, 0, vsc, 10);
    ((FX_SETC_F)vt[FX_SETPSCF])(dev, 0, &pc[0][0], 4);
    DWORD zw = fx_rs(vt, dev, FX_RS_ZWRITE);
    ((FX_SETRS_F)vt[FX_SETRS])(dev, FX_RS_ZWRITE, 0);
    g_fx_n_halos++;
    return (int)zw + 1;
}

static void fx_halo_sacar(void *dev, int zw1, HRESULT hr)
{
    void **vt = FXV(dev);
    ((FX_SETSH_F)vt[FX_SETVS])(dev, NULL);
    ((FX_SETSH_F)vt[FX_SETPS])(dev, NULL);
    ((FX_SETRS_F)vt[FX_SETRS])(dev, FX_RS_ZWRITE, (DWORD)(zw1 - 1));
    if (hr != 0 && g_fx_halo_fallos++ < 5) apuntar("  [isla_fx] ⚠ un halo falló (hr 0x%08X): sigue sin halo", (unsigned)hr);
}

/* ★ turno 11 · LA TRAZA DEL PARPADEO ([isla_fx] trazar=1). Medido en el juego (turno 10): con la cámara en movimiento
 *   una superficie ENTERA a la izquierda de la casita roja (y en el árbol de la tienda) se pinta distinta cuadro sí,
 *   cuadro no; las luces (0 cambios) y el near (0 dibujos con near ~1) quedaron descartados por la sonda. Hipótesis:
 *   el ORDEN de dibujo de cosas con transparencia que se superponen. La traza anota, desde que la cámara arranca a
 *   moverse (después de ≥ 1 s quieta) y durante `trazar_cuadros` cuadros, CADA dibujo que cae en el rectángulo
 *   `trazar_rect` (en píxeles de la pantalla del juego): su orden en el cuadro, la textura, la mezcla, el z, la prueba
 *   de alfa, el rectángulo que ocupa y si es nuestro (sombreador / diferido / repetido después del brillo).
 *   Lo lee t11/analizar_traza.py (qué dibujos cambian de orden o de aspecto con la paridad del cuadro). */
typedef HRESULT (WINAPI *FX_GETSS_F)(void *, UINT, void **, UINT *, UINT *);   /* GetStreamSource (101) */
typedef HRESULT (WINAPI *FX_VBLOCK_F)(void *, UINT, UINT, void **, DWORD);     /* IDirect3DVertexBuffer9::Lock (11) */
typedef HRESULT (WINAPI *FX_VBUNLOCK_F)(void *);                               /* Unlock (12) */
typedef HRESULT (WINAPI *FX_GETVP_F)(void *, DWORD *);                         /* GetViewport (48) */
#define FX_GETSTREAM 101
#define FX_GETVIEWPORT 48
static int  g_fx_traza_cuadros = 120, g_fx_traza_rect[4] = { 380, 240, 580, 480 }, g_fx_traza_rect2[4] = { 880, 440, 1120, 600 };
/* g_fx_traza_estado: 0 = esperando que la cámara arranque · 1 = trazando · 2 = listo */
static long g_fx_cuadro = 0, g_fx_traza_desde = 0, g_fx_dib_en_cuadro = 0, g_fx_traza_lineas = 0;
static float g_fx_traza_v[16];
static DWORD g_fx_traza_quieta = 0;
/* los nombres de TODAS las texturas cargadas (sólo con trazar=1): puntero → nombre corto */
#define FX_NOMBRES 4096
static void *g_fx_nom_k[FX_NOMBRES];
static char g_fx_nom_v[FX_NOMBRES][40];
static BYTE g_fx_nom_isla[FX_NOMBRES];                   /* ★ turno 12: 1 = de rnr_ui_bg/front/ */
static short g_fx_nom_color[FX_NOMBRES];                 /* ★ turno 12: su número de color falso (0 = sin dar) */
static int  g_fx_colores_dados = 0;
static void fx_nombre_anotar(void *tex, const char *base)
{
    DWORD h = fx_h(tex);
    for (int i = 0; i < FX_NOMBRES; i++, h = (h + 1) & (FX_NOMBRES - 1))
        if (!g_fx_nom_k[h] || g_fx_nom_k[h] == tex) {
            lstrcpynA(g_fx_nom_v[h], base, 40);
            g_fx_nom_isla[h] = (BYTE)(g_fx_nom_isla_ahora ? 1 : 0);
            g_fx_nom_color[h] = 0;
            g_fx_nom_k[h] = tex;
            return;
        }
}
static int fx_nombre_lugar(void *tex)
{
    if (!tex) return -1;
    DWORD h = fx_h(tex);
    for (int i = 0; i < FX_NOMBRES; i++, h = (h + 1) & (FX_NOMBRES - 1)) {
        if (g_fx_nom_k[h] == tex) return (int)h;
        if (!g_fx_nom_k[h]) break;
    }
    return -1;
}

/* ★ turno 12 · COLORES FALSOS: un dibujo con textura de la isla se pinta del color de su textura (y su orden en el
 *   cuadro), con el MISMO pipeline del juego (fixed-function: misma transformación, mismo z, cull, alfa y mezcla):
 *   sólo cambia de dónde sale el color de la etapa 0 (TFACTOR), se apaga la etapa 1 y la niebla. Se devuelve todo
 *   después del dibujo. La primera vez de cada textura, la sonda anota «color → textura». */
static void fx_falsos_poner(void *dev, void **vt)
{
    if (!g_fx_falsos || g_fx_falsos_puesto || g_fx_dentro) return;
    if (!g_fx_trazar) g_fx_dib_en_cuadro++;                     /* el orden de la llamada en el cuadro */
    void *tex = NULL;
    if (((FX_GETTEX_F)vt[FX_GETTEX])(dev, 0, &tex) != 0 || !tex) return;
    int h = fx_nombre_lugar(tex);
    fx_soltar(tex);
    if (h < 0 || !g_fx_nom_isla[h]) return;
    if (g_fx_cf_solo[0] && !fx_en_lista(g_fx_cf_solo, g_fx_nom_v[h])) return;     /* ★ turno 13 */
    if (g_fx_cf_menos[0] && fx_en_lista(g_fx_cf_menos, g_fx_nom_v[h])) return;
    void *vs = NULL, *ps = NULL;                                 /* sólo sobre el fixed-function del juego */
    ((FX_GETSH_F)vt[FX_GETVS])(dev, &vs);
    ((FX_GETSH_F)vt[FX_GETPS])(dev, &ps);
    int ff = !vs && !ps;
    fx_soltar(vs); fx_soltar(ps);
    if (!ff) return;
    if (!g_fx_nom_color[h]) {
        g_fx_nom_color[h] = (short)(++g_fx_colores_dados);
        apuntar("  [isla_fx] COLORES FALSOS: n.º %d = #%06X (brillo según el orden en el cuadro, n mod 4: 100/82/64/46 %%)"
                " → %s", g_fx_nom_color[h], (unsigned)(fx_color_falso(g_fx_nom_color[h], 0) & 0xFFFFFF), g_fx_nom_v[h]);
    }
    g_fx_falsos_ant[0] = fx_tss(vt, dev, FX_TSS_COLOROP);
    g_fx_falsos_ant[1] = fx_tss(vt, dev, FX_TSS_COLORARG1);
    { DWORD v1 = 0; ((FX_GETTSS_F)vt[FX_GETTSS])(dev, 1, FX_TSS_COLOROP, &v1); g_fx_falsos_ant[2] = v1; }
    g_fx_falsos_ant[3] = fx_rs(vt, dev, FX_RS_TFACTOR);
    g_fx_falsos_ant[4] = fx_rs(vt, dev, FX_RS_FOGENABLE);
    typedef HRESULT (WINAPI *FX_SETTSS_F)(void *, DWORD, DWORD, DWORD);
    FX_SETTSS_F ts = (FX_SETTSS_F)vt[67];
    if (g_fx_cf_color) {
        ((FX_SETRS_F)vt[FX_SETRS])(dev, FX_RS_TFACTOR, fx_color_falso(g_fx_nom_color[h], g_fx_dib_en_cuadro));
        ts(dev, 0, FX_TSS_COLOROP, FX_TOP_SELECTARG1);
        ts(dev, 0, FX_TSS_COLORARG1, FX_TA_TFACTOR);
    }
    if (g_fx_cf_etapa1) ts(dev, 1, FX_TSS_COLOROP, 1 /* DISABLE */);
    if (g_fx_cf_niebla) ((FX_SETRS_F)vt[FX_SETRS])(dev, FX_RS_FOGENABLE, 0);
    g_fx_falsos_puesto = 1;
}
static const char *fx_nombre_de(void *tex)
{
    if (!tex) return "-";
    DWORD h = fx_h(tex);
    for (int i = 0; i < FX_NOMBRES; i++, h = (h + 1) & (FX_NOMBRES - 1)) {
        if (g_fx_nom_k[h] == tex) return g_fx_nom_v[h];
        if (!g_fx_nom_k[h]) break;
    }
    return "?";
}

/* cuántos vértices usa un dibujo de `n` primitivas (lista de puntos, líneas, tira, triángulos, tira, abanico) */
static UINT fx_vertices_de(DWORD prim, UINT n)
{
    switch (prim) {
    case 1: return n;
    case 2: return 2 * n;
    case 3: return n + 1;
    case 4: return 3 * n;
    case 5: case 6: return n + 2;
    }
    return 0;
}

/* el rectángulo en pantalla de hasta 256 vértices (posición = los 3 primeros floats; XYZRHW ya viene en píxeles) */
static int fx_traza_rect(void *dev, void **vt, const BYTE *vx, UINT paso, UINT nv, DWORD fvf, int *r)
{
    float m[16], v[16], p[16], mv[16], mvp[16];
    DWORD vp[6];
    int rhw = (fvf & FX_FVF_POSMASK) == FX_FVF_XYZRHW, hay = 0;
    if (!rhw) {
        if (((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 256, m) || ((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 2, v)
            || ((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 3, p) || ((FX_GETVP_F)vt[FX_GETVIEWPORT])(dev, vp)) return 0;
        fx_mul44(m, v, mv);
        fx_mul44(mv, p, mvp);
    }
    UINT salto = nv > 256 ? nv / 256 : 1;
    r[0] = r[1] = 1 << 30; r[2] = r[3] = -(1 << 30);
    for (UINT i = 0; i < nv; i += salto) {
        const float *q = (const float *)(vx + (SIZE_T)i * paso);
        float sx, sy;
        if (rhw) { sx = q[0]; sy = q[1]; }
        else {
            float x = q[0] * mvp[0] + q[1] * mvp[4] + q[2] * mvp[8] + mvp[12];
            float y = q[0] * mvp[1] + q[1] * mvp[5] + q[2] * mvp[9] + mvp[13];
            float w = q[0] * mvp[3] + q[1] * mvp[7] + q[2] * mvp[11] + mvp[15];
            if (w <= 1e-3f) continue;
            sx = (float)vp[0] + (x / w * 0.5f + 0.5f) * (float)vp[2];
            sy = (float)vp[1] + (0.5f - y / w * 0.5f) * (float)vp[3];
        }
        int ix = (int)sx, iy = (int)sy;
        if (ix < r[0]) r[0] = ix;
        if (iy < r[1]) r[1] = iy;
        if (ix > r[2]) r[2] = ix;
        if (iy > r[3]) r[3] = iy;
        hay = 1;
    }
    return hay;
}

/* un dibujo, después de decidir qué hacemos con él (k: 0 como el juego · 1 con sombreador · 2 diferido) */
static void fx_trazar_dibujo(void *dev, int tipo, const DWORD *a, const void *datos, UINT paso_up, int k)
{
    void **vt = FXV(dev);
    g_fx_dib_en_cuadro++;
    if (g_fx_traza_estado != 1) return;
    if (g_fx_cuadro - g_fx_traza_desde >= g_fx_traza_cuadros) {
        g_fx_traza_estado = 2;
        apuntar("  [isla_fx] TRAZA fin: %ld cuadros, %ld líneas", (long)g_fx_traza_cuadros, g_fx_traza_lineas);
        return;
    }
    DWORD fvf = 0;
    ((FX_GETF_F)vt[FX_GETFVF])(dev, &fvf);
    int r[4] = { 0, 0, 0, 0 }, hay = 0;
    if (tipo >= 2) {                                                 /* los UP: los vértices vienen en la llamada */
        UINT nv = tipo == 2 ? fx_vertices_de(a[0], a[1]) : a[1];
        if (datos && nv) hay = fx_traza_rect(dev, vt, (const BYTE *)datos, paso_up, nv, fvf, r);
    } else {
        void *vb = NULL;
        UINT off = 0, paso = 0;
        if (((FX_GETSS_F)vt[FX_GETSTREAM])(dev, 0, &vb, &off, &paso) == 0 && vb && paso) {
            UINT ini = tipo == 0 ? a[1] : (UINT)((INT)a[1] + (INT)a[2]);   /* DP: el primero · DIP: base + mínimo */
            UINT nv = tipo == 0 ? fx_vertices_de(a[0], a[2]) : a[3];
            void *p = NULL;
            if (((FX_VBLOCK_F)FXV(vb)[11])(vb, off + ini * paso, nv * paso, &p, 0x10 /* READONLY */) == 0 && p) {
                hay = fx_traza_rect(dev, vt, (const BYTE *)p, paso, nv, fvf, r);
                ((FX_VBUNLOCK_F)FXV(vb)[12])(vb);
            }
        }
        fx_soltar(vb);
    }
    int en1 = !(r[2] < g_fx_traza_rect[0] || r[0] > g_fx_traza_rect[2] || r[3] < g_fx_traza_rect[1] || r[1] > g_fx_traza_rect[3]);
    int en2 = !(r[2] < g_fx_traza_rect2[0] || r[0] > g_fx_traza_rect2[2] || r[3] < g_fx_traza_rect2[1] || r[1] > g_fx_traza_rect2[3]);
    if (!hay || (!en1 && !en2)) return;                          /* ★ turno 13: dos rectángulos */
    /* ★ turno 13: la etapa 1, las coordenadas de textura (TEXCOORDINDEX con los bits TCI), TEXTURETRANSFORMFLAGS,
     *   la matriz de textura (≠ identidad) y la niebla */
    void *tex1 = NULL;
    ((FX_GETTEX_F)vt[FX_GETTEX])(dev, 1, &tex1);
    const char *nom1 = fx_nombre_de(tex1);
    fx_soltar(tex1);
    DWORD op1 = 0, tci0 = 0, tci1 = 0, ttf0 = 0, ttf1 = 0;
    ((FX_GETTSS_F)vt[FX_GETTSS])(dev, 1, FX_TSS_COLOROP, &op1);
    ((FX_GETTSS_F)vt[FX_GETTSS])(dev, 0, 11, &tci0);
    ((FX_GETTSS_F)vt[FX_GETTSS])(dev, 1, 11, &tci1);
    ((FX_GETTSS_F)vt[FX_GETTSS])(dev, 0, 24, &ttf0);
    ((FX_GETTSS_F)vt[FX_GETTSS])(dev, 1, 24, &ttf1);
    float tm0[16], tm1[16];
    int mat0 = 0, mat1 = 0;
    if (((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 16, tm0) == 0)
        for (int i = 0; i < 16; i++) mat0 |= tm0[i] != ((i % 5) == 0 ? 1.0f : 0.0f);
    if (((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 17, tm1) == 0)
        for (int i = 0; i < 16; i++) mat1 |= tm1[i] != ((i % 5) == 0 ? 1.0f : 0.0f);
    void *tex = NULL;
    ((FX_GETTEX_F)vt[FX_GETTEX])(dev, 0, &tex);
    const char *nom = fx_nombre_de(tex);
    fx_soltar(tex);
    float w[16];
    ZeroMemory(w, sizeof(w));
    ((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 256, w);
    g_fx_traza_lineas++;
    apuntar("  [isla_fx] TRAZA f=%ld n=%ld tex=%s dib=%d fvf=%X mezcla=%u %u-%u z=%u/%u/%u alfa=%u/%u cull=%u"
            " rect=%d,%d-%d,%d mundo=%d,%d,%d nuestro=%d%s",
            g_fx_cuadro - g_fx_traza_desde, g_fx_dib_en_cuadro, nom, 81 + tipo, fvf,
            fx_rs(vt, dev, FX_RS_ALPHABLEND), fx_rs(vt, dev, FX_RS_SRCBLEND), fx_rs(vt, dev, FX_RS_DESTBLEND),
            fx_rs(vt, dev, FX_RS_ZENABLE), fx_rs(vt, dev, FX_RS_ZWRITE), fx_rs(vt, dev, 23 /* ZFUNC */),
            fx_rs(vt, dev, FX_RS_ALPHATEST), fx_rs(vt, dev, 24 /* ALPHAREF */), fx_rs(vt, dev, FX_RS_CULL),
            r[0], r[1], r[2], r[3], (int)w[12], (int)w[13], (int)w[14], k, g_fx_reproduciendo ? " (repetido tras el brillo)" : "");
    apuntar("  [isla_fx] TRAZA+ f=%ld n=%ld zona=%s etapa1=%s op1=%u tci0=%08X tci1=%08X ttf0=%u ttf1=%u matriz_tex0=%d"
            " matriz_tex1=%d niebla=%u", g_fx_cuadro - g_fx_traza_desde, g_fx_dib_en_cuadro, en1 && en2 ? "las dos" : en1 ? "1" : "2",
            nom1, op1, tci0, tci1, ttf0, ttf1, mat0, mat1, fx_rs(vt, dev, FX_RS_FOGENABLE));
}

/* cada cuadro (Present): ¿arrancó la cámara? */
static void fx_traza_cuadro(void)
{
    g_fx_cuadro++;
    g_fx_dib_en_cuadro = 0;
}
/* en los dibujos de la isla: la cámara quieta ≥ 1 s y después se mueve ⇒ empieza la traza */
static void fx_traza_vista(const float *v)
{
    if (!g_fx_trazar || g_fx_traza_estado != 0) return;
    DWORD ahora = GetTickCount();
    if (memcmp(v, g_fx_traza_v, sizeof(g_fx_traza_v)) == 0) {
        if (!g_fx_traza_quieta) g_fx_traza_quieta = ahora ? ahora : 1;
        return;
    }
    CopyMemory(g_fx_traza_v, v, sizeof(g_fx_traza_v));
    if (g_fx_traza_quieta && fx_ms(ahora, g_fx_traza_quieta) >= 1000) {
        g_fx_traza_estado = 1;
        g_fx_traza_desde = g_fx_cuadro;
        apuntar("  [isla_fx] TRAZA empieza (la cámara arrancó después de %d ms quieta): %d cuadros, rectángulo %d,%d-%d,%d",
                (int)fx_ms(ahora, g_fx_traza_quieta), g_fx_traza_cuadros, g_fx_traza_rect[0], g_fx_traza_rect[1],
                g_fx_traza_rect[2], g_fx_traza_rect[3]);
    }
    g_fx_traza_quieta = 0;
}

/* ★ 21-nov · ¿este dibujo es del trineo y está «Elige tu personaje» a la vista? Dos maneras de saberlo:
 *   1) la textura 0 es una de la lista (marcada al cargarse) ⇒ se anota su MALLA (buffer de vértices + de índices +
 *      dónde empieza): medido en el espejo, sacar sólo las texturas dejaba las siluetas NEGRAS, que son la pasada del
 *      contorno: la misma malla otra vez, sin esa textura;
 *   2) la malla es una de las anotadas ⇒ también se salta (el contorno, venga antes o después). Sólo con el selector. */
#define FX_GETINDICES 105
typedef HRESULT (WINAPI *FX_GETIB_F)(void *, void **);
typedef struct { void *vb, *ib; INT base; UINT ini; } FX_MALLA;
static FX_MALLA g_fx_mallas_oc[64];
static LONG g_fx_n_mallas_oc = 0;
/* ★ 21-nov · sonda_selector=1: con el selector a la vista, cada 1 s, los dibujos 81 / 83 por textura: cuántos y DÓNDE
 *   (la traslación del WORLD: mín / máx) — y dónde está el trineo (c4..c6 .w del sombreador ajeno, al esconderlo) */
#define FX_GETVSCF 95
typedef HRESULT (WINAPI *FX_GETVSCF_F)(void *, UINT, float *, UINT);
static float g_fx_trineo_pos[3]; static DWORD g_fx_trineo_t = 0;
static void fx_sel_sonda(void *dev, int tipo, UINT n)
{
    static void *tx[24]; static LONG cu[24], pr[24]; static BYTE ti[24]; static float mn[24][3], mx[24][3];
    static LONG nt = 0, lineas = 0; static DWORD t0 = 0;
    if (lineas > 600) return;
    void *tex = NULL;
    float w[16];
    if (((FX_GETTEX_F)FXV(dev)[FX_GETTEX])(dev, 0, &tex) != 0) tex = NULL;
    fx_soltar(tex);
    if (((FX_GETTR_F)FXV(dev)[FX_GETTRANSFORM])(dev, 256, w) != 0) ZeroMemory(w, sizeof(w));
    LONG k = 0;
    while (k < nt && !(tx[k] == tex && ti[k] == (BYTE)tipo)) k++;
    if (k == nt && nt < 24) { tx[k] = tex; ti[k] = (BYTE)tipo; cu[k] = pr[k] = 0; for (int e = 0; e < 3; e++) mn[k][e] = mx[k][e] = w[12 + e]; nt++; }
    if (k < nt) {
        cu[k]++; pr[k] += (LONG)n;
        for (int e = 0; e < 3; e++) { if (w[12 + e] < mn[k][e]) mn[k][e] = w[12 + e]; if (w[12 + e] > mx[k][e]) mx[k][e] = w[12 + e]; }
    }
    DWORD ahora = GetTickCount();
    if (!t0) t0 = ahora;
    if (ahora - t0 < 1000) return;
    t0 = ahora;
    int hay = g_fx_trineo_t && ahora - g_fx_trineo_t < 300;
    apuntar("  [isla_fx] sonda_selector: trineo %s (%d, %d, %d)", hay ? "A LA VISTA" : "no",
            (int)g_fx_trineo_pos[0], (int)g_fx_trineo_pos[1], (int)g_fx_trineo_pos[2]);
    for (LONG q = 0; q < nt; q++, lineas++)
        apuntar("  [isla_fx]   %d %p %s ×%ld (%ld prim) WORLD x %d..%d y %d..%d z %d..%d", ti[q] == 3 ? 83 : 81, tx[q],
                fx_nombre_de(tx[q]), cu[q], pr[q], (int)mn[q][0], (int)mx[q][0], (int)mn[q][1], (int)mx[q][1], (int)mn[q][2], (int)mx[q][2]);
    nt = 0;
}

/* ★ 21-nov · LA ESTELA del trineo (anonimo03: «todo desapareció menos la estela»): son 23 efectos .pfx colgados de
 *   `xm_trineo` (ENTREGA_5 §3), con texturas COMPARTIDAS con la nieve y los brillos de la isla y cargadas por otro
 *   lado (sin nombre) ⇒ no se pueden esconder por textura. Y el trineo no trae su matriz al sombreador (c0..c3 son
 *   las de la isla entera: MEDIDO, fijas). MEDIDO (sonda_selector): cada emisor se dibuja con 81 y un WORLD propio;
 *   los de la isla están QUIETOS de un cuadro al otro y los de la estela VIAJAN con el trineo.
 *   ⇒ con el selector a la vista y el trineo en su vuelta (piezas escondidas hace < 150 ms), se salta todo dibujo 81
 *   con la cámara de la isla cuyo WORLD no estaba en el cuadro anterior. El cuadro lo marca la PROJ de la isla. */
static DWORD g_fx_tri_ult = 0;
static volatile LONG g_fx_isla_cuadro_n = 0;            /* sube con cada PROJ de la isla (fx_settr) */
static float g_fx_estela_p22 = 0.0f;
static void fx_trineo_anotar(void *dev, void **vt) { (void)dev; (void)vt; g_fx_tri_ult = GetTickCount(); }
static long g_fx_n_estela = 0;
static int fx_estela_ahora(void *dev)
{
    static float ant[160][3], act[160][3];
    static LONG nant = 0, nact = 0, cuadro = -1;
    if (!g_sp_visible || !g_fx_tri_ult || g_fx_dentro) return 0;
    if (GetTickCount() - g_fx_tri_ult > 150) return 0;   /* el trineo no anda: no hay estela que tapar */
    void **vt = FXV(dev);
    float wd[16], pj[16];
    if (((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 3, pj) != 0 || g_fx_estela_p22 <= 0.0f
        || pj[5] < g_fx_estela_p22 * 0.99f || pj[5] > g_fx_estela_p22 * 1.01f) return 0;      /* otra cámara (el muñeco) */
    if (((FX_GETTR_F)vt[FX_GETTRANSFORM])(dev, 256, wd) != 0) return 0;
    LONG c = g_fx_isla_cuadro_n;
    if (c != cuadro) {                                   /* cuadro nuevo: lo de este pasa a ser «el anterior» */
        CopyMemory(ant, act, sizeof(float) * 3 * nact);
        nant = cuadro == c - 1 ? nact : 0;
        nact = 0;
        cuadro = c;
    }
    if (nact < 160) { act[nact][0] = wd[12]; act[nact][1] = wd[13]; act[nact][2] = wd[14]; nact++; }
    if (!nant) return 0;                                 /* sin el anterior no se sabe: se dibuja */
    for (LONG i = 0; i < nant; i++)
        if (ant[i][0] == wd[12] && ant[i][1] == wd[13] && ant[i][2] == wd[14]) return 0;   /* quieto: de la isla */
    if (g_fx_n_estela++ == 0)
        apuntar("  [isla_fx] ★ la estela del trineo (sus partículas) tampoco se dibuja con «Elige tu personaje»");
    return 1;
}

static int fx_oculta_ahora(void *dev, INT base, UINT ini, int indexado)
{
    if (!g_sp_visible || !g_fx_n_ocultas || g_fx_dentro) return 0;
    void **vt = FXV(dev);
    void *tex = NULL;
    int si = 0;
    if (((FX_GETTEX_F)vt[FX_GETTEX])(dev, 0, &tex) == 0 && tex) {
        DWORD v = 0, n = sizeof(v);
        si = ((FX_PRIV_GET)FXV(tex)[5])(tex, &g_fx_guid_oculta, &v, &n) == 0 && v == 1;
        fx_soltar(tex);
    }
    FX_MALLA m = { NULL, NULL, base, ini };
    UINT off = 0, paso = 0;
    if (((FX_GETSS_F)vt[FX_GETSTREAM])(dev, 0, &m.vb, &off, &paso) != 0) m.vb = NULL;
    if (indexado && ((FX_GETIB_F)vt[FX_GETINDICES])(dev, &m.ib) != 0) m.ib = NULL;
    fx_soltar(m.vb);                                     /* sólo se comparan las direcciones */
    fx_soltar(m.ib);
    if (!m.vb) return si;
    LONG k = 0;
    while (k < g_fx_n_mallas_oc && memcmp(&g_fx_mallas_oc[k], &m, sizeof(m)) != 0) k++;
    if (si == 1) fx_trineo_anotar(dev, vt);                       /* ★ 21-nov: para la estela (sus partículas) */
    if (si && k >= g_fx_n_mallas_oc && g_fx_n_mallas_oc < 64) g_fx_mallas_oc[g_fx_n_mallas_oc++] = m;
    else if (!si && k < g_fx_n_mallas_oc) si = 2;                  /* el contorno de una pieza escondida */
    if (si && InterlockedIncrement(&g_fx_n_saltados) == 1)
        apuntar("  [isla_fx] ★ el trineo pasa con «Elige tu personaje» a la vista: no se dibuja (vuelve en el lobby)");
    if (si == 2 && g_fx_n_saltados < 1000000) {
        static LONG anotado = 0;
        if (!anotado) { anotado = 1; apuntar("  [isla_fx] ★ y su contorno (la misma malla sin la textura): tampoco"); }
    }
    return si;
}

static HRESULT WINAPI fx_d81(void *dev, DWORD tipo, UINT ini, UINT n)
{
    int t = fx_tabla(dev);
    if (t < 0 || !g_fx_t[t].real[0]) return E_FAIL;             /* no pasa: sólo se pone en tablas anotadas */
    if (g_fx_sonda_sel && g_sp_visible) fx_sel_sonda(dev, 1, n);
    if (fx_oculta_ahora(dev, 0, ini, 0) || fx_estela_ahora(dev)) return 0;   /* ★ 21-nov: el trineo y su estela */
    int k = fx_antes(dev, 0);
    if (g_fx_falsos) fx_falsos_poner(dev, FXV(dev));                     /* ★ turno 12 */
    if (g_fx_trazar) { DWORD ta[3] = { tipo, ini, n }; fx_trazar_dibujo(dev, 0, ta, NULL, 0, k); }   /* ★ turno 11 */
    if (k == 2) {                                                     /* excluido del brillo: se hace después */
        DWORD a[6] = { tipo, ini, n, 0, 0, 0 };
        int zw1 = fx_halo_poner(dev);                                     /* ★ turno 5: el halo, antes del brillo */
        if (zw1) {
            HRESULT hh = ((FX_D81)fx_destino(t, 0))(dev, tipo, ini, n);
            fx_halo_sacar(dev, zw1, hh);
            fx_reponer(t, 0);
        }
        if (fx_guardar(dev, 0, a)) { fx_samp_sacar(dev); return 0; }
        k = 0;
    }
    HRESULT hr = ((FX_D81)(k ? fx_destino(t, 0) : g_fx_t[t].real[0]))(dev, tipo, ini, n);
    if (k) {
        fx_despues(dev);
        fx_reponer(t, 0);
        if (hr != 0) { fx_fallo(hr); hr = ((FX_D81)g_fx_t[t].real[0])(dev, tipo, ini, n); }
    }
    fx_samp_sacar(dev);                                          /* ★ turno 9 */
    if (g_fx_activo && !g_fx_dentro) fx_vigia_cuadro("un dibujo");   /* ★ 21-nov: ¿lo reescribió ESTE dibujo? */
    return hr;
}

static HRESULT WINAPI fx_d82(void *dev, DWORD tipo, INT base, UINT minimo, UINT nv, UINT ini, UINT n)
{
    g_fx_d82_entradas++;                                 /* ★ 21-nov: el cuadro sin la capa 4 */
    int t = fx_tabla(dev);
    if (t < 0 || !g_fx_t[t].real[1]) return E_FAIL;
    if (fx_oculta_ahora(dev, base, ini, 1)) return 0;            /* ★ 21-nov */
    int k = fx_antes(dev, 1);
    if (g_fx_falsos) fx_falsos_poner(dev, FXV(dev));                     /* ★ turno 12 */
    if (g_fx_trazar) { DWORD ta[6] = { tipo, (DWORD)base, minimo, nv, ini, n }; fx_trazar_dibujo(dev, 1, ta, NULL, 0, k); }
    if (k == 2) {
        DWORD a[6] = { tipo, (DWORD)base, minimo, nv, ini, n };
        int zw1 = fx_halo_poner(dev);                                     /* ★ turno 5: el halo, antes del brillo */
        if (zw1) {
            HRESULT hh = ((FX_D82)fx_destino(t, 1))(dev, tipo, base, minimo, nv, ini, n);
            fx_halo_sacar(dev, zw1, hh);
            fx_reponer(t, 1);
        }
        if (fx_guardar(dev, 1, a)) { fx_samp_sacar(dev); return 0; }
        k = 0;
    }
    HRESULT hr = ((FX_D82)(k ? fx_destino(t, 1) : g_fx_t[t].real[1]))(dev, tipo, base, minimo, nv, ini, n);
    if (k) {
        fx_despues(dev);
        fx_reponer(t, 1);
        if (hr != 0) { fx_fallo(hr); hr = ((FX_D82)g_fx_t[t].real[1])(dev, tipo, base, minimo, nv, ini, n); }
    }
    fx_samp_sacar(dev);                                          /* ★ turno 9 */
    if (g_fx_activo && !g_fx_dentro) fx_vigia_cuadro("un dibujo");   /* ★ 21-nov: ¿lo reescribió ESTE dibujo? */
    return hr;
}

static HRESULT WINAPI fx_d83(void *dev, DWORD tipo, UINT n, const void *datos, UINT paso)
{
    int t = fx_tabla(dev);
    if (t < 0 || !g_fx_t[t].real[2]) return E_FAIL;
    if (g_fx_sonda_sel && g_sp_visible) fx_sel_sonda(dev, 3, n);
    int k = fx_antes(dev, 2);
    if (g_fx_falsos) fx_falsos_poner(dev, FXV(dev));                     /* ★ turno 12 */
    if (g_fx_trazar) { DWORD ta[2] = { tipo, n }; fx_trazar_dibujo(dev, 2, ta, datos, paso, k); }
    HRESULT hr = ((FX_D83)(k ? fx_destino(t, 2) : g_fx_t[t].real[2]))(dev, tipo, n, datos, paso);
    if (k) {
        fx_despues(dev);
        fx_reponer(t, 2);
        if (hr != 0) { fx_fallo(hr); hr = ((FX_D83)g_fx_t[t].real[2])(dev, tipo, n, datos, paso); }
    }
    fx_samp_sacar(dev);                                          /* ★ turno 9 */
    if (g_fx_activo && !g_fx_dentro) fx_vigia_cuadro("un dibujo");   /* ★ 21-nov: ¿lo reescribió ESTE dibujo? */
    return hr;
}

static HRESULT WINAPI fx_d84(void *dev, DWORD tipo, UINT minimo, UINT nv, UINT n, const void *idx, DWORD fmt, const void *datos, UINT paso)
{
    int t = fx_tabla(dev);
    if (t < 0 || !g_fx_t[t].real[3]) return E_FAIL;
    int k = fx_antes(dev, 3);
    if (g_fx_falsos) fx_falsos_poner(dev, FXV(dev));                     /* ★ turno 12 */
    if (g_fx_trazar) { DWORD ta[2] = { tipo, nv }; fx_trazar_dibujo(dev, 3, ta, datos, paso, k); }
    HRESULT hr = ((FX_D84)(k ? fx_destino(t, 3) : g_fx_t[t].real[3]))(dev, tipo, minimo, nv, n, idx, fmt, datos, paso);
    if (k) {
        fx_despues(dev);
        fx_reponer(t, 3);
        if (hr != 0) { fx_fallo(hr); hr = ((FX_D84)g_fx_t[t].real[3])(dev, tipo, minimo, nv, n, idx, fmt, datos, paso); }
    }
    fx_samp_sacar(dev);                                          /* ★ turno 9 */
    if (g_fx_activo && !g_fx_dentro) fx_vigia_cuadro("un dibujo");   /* ★ 21-nov: ¿lo reescribió ESTE dibujo? */
    return hr;
}

/* ── ★ turno 4 · SetTransform (44): el near de la isla ─────────────────────────────────────────────────── */
typedef HRESULT (WINAPI *FX_SETTR_F)(void *, DWORD, const float *);
#define FX_SETTRANSFORM 44
static FX_SETTR_F g_fx_settr_real = NULL;
static void **g_fx_settr_vt = NULL;

/* ★ turno 5 · una PROJ en el log: forma, near, far, fov vertical, aspecto, y el ojo de la VIEW puesta */
static void fx_sonda_proj(const char *que, const float *m, const float *v)
{
    float n = 0, f = 0, cam[3];
    int persp = fx_proj_perspectiva(m, &n, &f);
    fx_camara(v, cam);
    float d2 = cam[0] * cam[0] + cam[1] * cam[1] + cam[2] * cam[2], d = d2 > 1.0f ? d2 : 1.0f;
    for (int it = 0; it < 40; it++) d = 0.5f * (d + d2 / d);
    /* fov vertical en grados ×10 = 2·atan(1/_22): atan con una serie corta no alcanza; se da _22 ×1000 y el aspecto */
    apuntar("  [isla_fx] sonda: %s: %s · near ×100 %d · far %d · _11 ×1000 %d · _22 ×1000 %d (45° = 2414) · _34 ×1000 %d"
            " _44 ×1000 %d · ojo (%d, %d, %d) a %d del origen · mira (%d, %d, %d)/1000 · isla vista hace %d ms",
            que, persp ? "perspectiva" : "NO perspectiva (otra forma)", (int)(n * 100.0f), (int)f, (int)(m[0] * 1000.0f),
            (int)(m[5] * 1000.0f), (int)(m[11] * 1000.0f), (int)(m[15] * 1000.0f), (int)cam[0], (int)cam[1], (int)cam[2],
            d2 > 0.0f ? (int)d : 0, (int)(v[2] * 1000.0f), (int)(v[6] * 1000.0f), (int)(v[10] * 1000.0f),
            g_fx_isla_tick ? (int)(GetTickCount() - g_fx_isla_tick) : -1);
}

/* ★ 21-nov · sonda_selector: ¿Direct3D le CAMBIA la tabla al dispositivo (no sólo 81/82)? Un hilo mira cada 2 ms
 *   el puntero a la tabla del dispositivo y las entradas 81/82/57/65 de la nuestra, y anota cada cambio con su hora. */
static void *volatile g_fx_dev_ult = NULL;
static DWORD WINAPI fx_mira_tabla(LPVOID p)
{
    (void)p;
    void **vt0 = NULL, *e81 = NULL, *e82 = NULL, *e57 = NULL, *e65 = NULL;
    int n = 0;
    for (;;) {
        Sleep(2);
        void *dev = g_fx_dev_ult;
        if (!dev || IsBadReadPtr(dev, 4)) continue;
        void **vt = *(void ***)dev;
        if (!vt0) { vt0 = vt; e81 = vt[81]; e82 = vt[82]; e57 = vt[57]; e65 = vt[65]; continue; }
        if ((vt != vt0 || vt[81] != e81 || vt[82] != e82 || vt[57] != e57 || vt[65] != e65) && n < 60) {
            n++;
            apuntar("  [isla_fx] sonda_selector: t %lu · tabla del dispositivo %p%s · 81 %p · 82 %p · 57 %p · 65 %p",
                    GetTickCount(), (void *)vt, vt == g_fx_pr_vt ? " (la nuestra)" : " (OTRA)", vt[81], vt[82], vt[57], vt[65]);
        }
        vt0 = vt; e81 = vt[81]; e82 = vt[82]; e57 = vt[57]; e65 = vt[65];
    }
}
static void fx_fps_tic_isla(void);                       /* ★ turno 27b: el reloj de la isla (más abajo) */
static HRESULT WINAPI fx_settr(void *dev, DWORD estado, const float *m)
{
    g_fx_dev_ult = dev;                                  /* ★ 21-nov: para el vigía de la tabla (sonda_selector) */
    /* ★ 21-nov · la cadena del dibujo también se mira ACÁ: en el lobby y en «Elige tu personaje» ningún Present se
     *   entera (turno 27b), y el juego pone una matriz por objeto ⇒ si Direct3D reescribió 81/82 (MEDIDO: pasa cuando
     *   aparece el trineo), se rearma antes del próximo objeto, no 300-800 ms después (el cuadro sin aurora ni mar). */
    if (g_fx_activo && !g_fx_dentro) fx_vigia_cuadro("SetTransform");
    if (g_fx_sonda && estado == 3 && m && !g_fx_dentro) {
        g_fx_n_proj++;
        /* cada PROJ DISTINTA (por _11, _22, _33, _43), las primeras 24 */
        int vista = 0;
        for (int i = 0; i < g_fx_nproj_vistas && !vista; i++)
            vista = g_fx_proj_vistas[i][0] == m[0] && g_fx_proj_vistas[i][1] == m[5] && g_fx_proj_vistas[i][2] == m[10]
                    && g_fx_proj_vistas[i][3] == m[14];
        if (!vista && g_fx_nproj_vistas < 24) {
            float v[16];
            ZeroMemory(v, sizeof(v));
            ((FX_GETTR_F)FXV(dev)[FX_GETTRANSFORM])(dev, 2, v);
            g_fx_proj_vistas[g_fx_nproj_vistas][0] = m[0]; g_fx_proj_vistas[g_fx_nproj_vistas][1] = m[5];
            g_fx_proj_vistas[g_fx_nproj_vistas][2] = m[10]; g_fx_proj_vistas[g_fx_nproj_vistas][3] = m[14];
            g_fx_nproj_vistas++;
            char que[32];
            wsprintfA(que, "PROJ nueva #%d", g_fx_nproj_vistas);
            fx_sonda_proj(que, m, v);
        }
    }
    if (estado == 3 /* D3DTS_PROJECTION */ && m && g_fx_cercano > 0.0f && !g_fx_dentro) {
        float v[16], q[16], n = 0, f = 0, ojo = 0;
        ZeroMemory(v, sizeof(v));
        if (((FX_GETTR_F)FXV(dev)[FX_GETTRANSFORM])(dev, 2 /* VIEW */, v) == 0) {
            int r = fx_cercano_decide(m, v, GetTickCount(), g_fx_isla_tick, g_fx_cercano_ojo, g_fx_cercano, q, &n, &f, &ojo);
            if (r >= 2) fx_fps_tic_isla();                       /* ★ turno 27b: un cuadro de la isla (la PROJ de la isla) */
            if (r >= 2) { InterlockedIncrement(&g_fx_isla_cuadro_n); g_fx_estela_p22 = m[5]; }   /* ★ 21-nov: la estela */
            if (r >= 2) {                                    /* ★ 21-nov: ¿el cuadro anterior pasó por nosotros? */
                static LONG e0 = -1, i0 = 0, anot = 0;
                LONG e = g_fx_d82_entradas, il = g_fx_d82_isla;
                if (e0 >= 0 && il == i0 && anot < 40) {
                    void **vtd = FXV(dev);
                    LONG s = 0;
                    while (s < g_sa_ntablas && g_sa_tablas[s].vt != vtd) s++;
                    anot++;
                    apuntar("  [isla_fx] ⚠ CUADRO SIN LA ISLA por nosotros: fx_d82 entró %ld veces, isla 0 · t %lu · dentro %ld ·"
                            " marcas %ld · vt81 %s · vt82 %s · real81 %s · real82 %s · tabla %p (pr %p) · selector %d · roto %d",
                            e - e0, GetTickCount(), (long)g_fx_dentro, (long)g_fx_nmarcas,
                            vtd[SA_DRAWPRIMITIVE] == (void *)sa_dibujar ? "sala" : "OTRO",
                            vtd[SA_DRAWINDEXED] == (void *)sa_dibujar_idx ? "sala" : "OTRO",
                            s < g_sa_ntablas && g_sa_tablas[s].real81 == (SA_DIBUJAR)fx_d81 ? "fx" : "OTRO",
                            s < g_sa_ntablas && g_sa_tablas[s].real82 == (SA_DIBUJAR_IDX)fx_d82 ? "fx" : "OTRO",
                            (void *)vtd, (void *)g_fx_pr_vt, (int)g_sp_visible, g_fx_roto);
                }
                e0 = e; i0 = il;
            }
            if (r == 3) {
                if (g_fx_sonda) g_fx_n_cercano++;
                if (g_fx_cercano_total++ == 0)
                    apuntar("  [isla_fx] ★ near de la isla: PROJ near %d.%02d far %d → near %d (cámara a %d del origen)%s",
                            (int)(n * 100.0f + 0.5f) / 100, (int)(n * 100.0f + 0.5f) % 100, (int)f, (int)g_fx_cercano, (int)ojo,
                            g_fx_activo ? "" : " — SONDA: no se reescribe (activo=0)");
                if (g_fx_activo && !g_fx_roto) return g_fx_settr_real(dev, estado, q);
            } else if (r > 0) {
                if (g_fx_sonda) g_fx_n_cercano_no++;
                if (g_fx_sonda && g_fx_cercano_no_anotados < 8) {
                    g_fx_cercano_no_anotados++;
                    apuntar("  [isla_fx] sonda: una PROJ como la de la isla (near %d.%02d, far %d) que NO se toca: %s"
                            " (cámara a %d del origen)", (int)(n * 100.0f + 0.5f) / 100, (int)(n * 100.0f + 0.5f) % 100, (int)f,
                            r == 1 ? "la escena no es la isla" : "cámara cerca del origen (primer plano)", (int)ojo);
                }
            }
        }
    }
    return g_fx_settr_real(dev, estado, m);
}

static void fx_enganchar_settr(void **vt)
{
    if (g_fx_settr_vt == vt) {
        /* ya puesto: sólo si alguien DEVOLVIÓ el original (no si alguien se puso encima nuestro) */
        if (vt[FX_SETTRANSFORM] == (void *)g_fx_settr_real) fx_escribir(&vt[FX_SETTRANSFORM], (void *)fx_settr);
        return;
    }
    if (g_fx_settr_vt) return;                           /* otra tabla: no se engancha dos veces */
    if (vt[FX_SETTRANSFORM] == (void *)fx_settr) return;
    g_fx_settr_real = (FX_SETTR_F)vt[FX_SETTRANSFORM];
    g_fx_settr_real0 = (FX_SETTR0_F)g_fx_settr_real;
    g_fx_settr_vt = vt;
    fx_escribir(&vt[FX_SETTRANSFORM], (void *)fx_settr);
    apuntar("  [isla_fx] ★ enganchado SetTransform de la tabla %p: el near de la isla pasa a %d%s", (void *)vt,
            (int)g_fx_cercano, g_fx_activo ? "" : " (sonda: sólo se cuenta)");
}

/* ── Present y Reset (sólo con el brillo): una vez por tabla; no se envuelve a quien se puso encima ─────── */
static FX_PRESENT_F g_fx_present_real = NULL;
static FX_RESET_F g_fx_reset_real = NULL;

/* ★ turno 26 · los CUADROS POR SEGUNDO reales (pruebas de rendimiento en la laptop vieja): cada Present del dispositivo
 *   que dibuja, sea la escena que sea (lobby, selector, carrera) y con o sin brillo. Una línea por segundo con
 *   [isla_fx] sonda=1 o fps=1 (también con activo=0: la referencia sin efectos). */
static int  g_fx_fps = 0;
static LARGE_INTEGER g_fx_fps_frec, g_fx_fps_ant, g_fx_fps_seg;
static long g_fx_fps_n = 0;
static double g_fx_fps_suma = 0.0, g_fx_fps_peor = 0.0;

/* ★ turno 27 · LA CALIDAD AUTOMÁTICA (calidad=auto, de fábrica). A los `auto_espera` segundos de ver la isla (5) mide
 *   los cuadros por segundo `auto_medir` segundos (5); si la media da menos que `auto_umbral` (50), baja un escalón
 *   (alta → media → baja) y vuelve a medir; si en baja da menos que `auto_umbral_mar` (45), apaga el MAR con
 *   sombreador (queda el del juego). Lo deja en el log y en `isla_fx_auto.txt` (al lado de la dll): la próxima vez
 *   arranca desde ahí (nunca sube sola). `auto_olvidar=1` no lo lee; calidad=alta/media/baja la fuerza (sin medir). */
static int  g_fx_auto_umbral = 50, g_fx_auto_umbral_mar = 45, g_fx_auto_espera = 5, g_fx_auto_medir = 5;
static int  g_fx_auto_fase = 0, g_fx_auto_seg = 0, g_fx_auto_listo = 0;
static double g_fx_auto_suma = 0.0;
static char g_fx_auto_archivo[MAX_PATH];
static const char *const g_fx_cal_nombre[3] = { "baja", "media", "alta" };
static void fx_calidad_poner(int nivel);

static void fx_auto_guardar(int fps)
{
    if (!g_fx_auto_archivo[0]) return;
    char b[256];
    wsprintfA(b, "; isla_fx calidad=auto (turno 27): lo que midió la dll en ESTA PC. Borrar el archivo = volver a medir\r\n"
                 "calidad=%s\r\nmar=%d\r\nfps=%d\r\n", g_fx_cal_nombre[g_fx_calidad], g_fx_efecto[FX_MAR] ? 1 : 0, fps);
    HANDLE h = CreateFileA(g_fx_auto_archivo, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h != INVALID_HANDLE_VALUE) {
        DWORD n = 0;
        WriteFile(h, b, (DWORD)lstrlenA(b), &n, NULL);
        CloseHandle(h);
    }
}

/* una vez por segundo: ¿se vio la isla? ¿cuántos cuadros? */
static void fx_auto_segundo(int fps, int isla)
{
    if (!g_fx_auto || g_fx_auto_listo || !g_fx_activo) return;
    if (!isla) { g_fx_auto_fase = 0; g_fx_auto_seg = 0; g_fx_auto_suma = 0.0; return; }   /* se fue de la isla: de nuevo */
    if (g_fx_auto_fase == 0) {                                  /* esperar a que la isla se asiente */
        if (++g_fx_auto_seg >= g_fx_auto_espera) { g_fx_auto_fase = 1; g_fx_auto_seg = 0; g_fx_auto_suma = 0.0; }
        return;
    }
    g_fx_auto_suma += fps;
    if (++g_fx_auto_seg < g_fx_auto_medir) return;
    int media = (int)(g_fx_auto_suma / g_fx_auto_seg + 0.5);
    g_fx_auto_fase = 0;
    g_fx_auto_seg = 0;
    g_fx_auto_suma = 0.0;
    if (media >= g_fx_auto_umbral) {
        apuntar("  [isla_fx] ★ calidad auto: %d cuadros por segundo de media (≥ %d): queda en %s%s", media, g_fx_auto_umbral,
                g_fx_cal_nombre[g_fx_calidad], g_fx_efecto[FX_MAR] ? "" : " (sin el mar con sombreador)");
        g_fx_auto_listo = 1;
    } else if (g_fx_calidad > 0) {
        apuntar("  [isla_fx] ★ calidad auto: %d cuadros por segundo de media (< %d): %s → %s, y vuelvo a medir", media,
                g_fx_auto_umbral, g_fx_cal_nombre[g_fx_calidad], g_fx_cal_nombre[g_fx_calidad - 1]);
        fx_calidad_poner(g_fx_calidad - 1);
    } else if (g_fx_efecto[FX_MAR] && media < g_fx_auto_umbral_mar) {
        apuntar("  [isla_fx] ★ calidad auto: %d cuadros por segundo de media en BAJA (< %d): APAGO el mar con sombreador"
                " (queda el del juego)", media, g_fx_auto_umbral_mar);
        g_fx_efecto[FX_MAR] = 0;
    } else {
        apuntar("  [isla_fx] ★ calidad auto: %d cuadros por segundo de media: ya está en lo más liviano (%s%s)", media,
                g_fx_cal_nombre[g_fx_calidad], g_fx_efecto[FX_MAR] ? "" : ", sin el mar con sombreador");
        g_fx_auto_listo = 1;
    }
    fx_auto_guardar(media);
}

/* ★ turno 27b (medido en la laptop, d3d9 NATIVO): en el lobby NINGÚN Present enganchado se entera (ni el nuestro, ni el
 *   del swapchain, ni el del cartel de métricas: Direct3D vuelve a escribir la tabla al entrar). El reloj que sí anda es
 *   la PROJ de la isla: el juego la pone UNA vez por cuadro (es «near 100: N/s»). ⇒ dos relojes: `fuente` 1 = la
 *   isla (manda mientras la isla se dibuja) · 0 = Present (la intro, la carga, el selector, lo que no es la isla). Si
 *   hubo un tic de la isla hace menos de 300 ms, el de Present no cuenta (no se cuenta doble). */
static LARGE_INTEGER g_fx_fps_isla_ult;
static int g_fx_fps_fuente_seg = 0;                      /* la fuente que contó en este segundo (para el log) */
static void fx_fps_cuadro(int fuente)
{
    LARGE_INTEGER ahora;
    if (!g_fx_fps_frec.QuadPart && !QueryPerformanceFrequency(&g_fx_fps_frec)) return;
    QueryPerformanceCounter(&ahora);
    if (fuente == 1) g_fx_fps_isla_ult = ahora;
    else if (g_fx_fps_isla_ult.QuadPart
             && (double)(ahora.QuadPart - g_fx_fps_isla_ult.QuadPart) < 0.3 * (double)g_fx_fps_frec.QuadPart) return;
    g_fx_fps_fuente_seg |= 1 << fuente;
    if (!g_fx_fps_ant.QuadPart) { g_fx_fps_ant = g_fx_fps_seg = ahora; return; }
    double ms = (double)(ahora.QuadPart - g_fx_fps_ant.QuadPart) * 1000.0 / (double)g_fx_fps_frec.QuadPart;
    g_fx_fps_ant = ahora;
    g_fx_fps_n++;
    g_fx_fps_suma += ms;
    if (ms > g_fx_fps_peor) g_fx_fps_peor = ms;
    double seg = (double)(ahora.QuadPart - g_fx_fps_seg.QuadPart) / (double)g_fx_fps_frec.QuadPart;
    if (seg >= 1.0) {
        int medio10 = g_fx_fps_n ? (int)(g_fx_fps_suma / g_fx_fps_n * 10.0 + 0.5) : 0;
        int fps = (int)(g_fx_fps_n / seg + 0.5), isla = g_fx_auto_dib > 0;
        g_fx_auto_dib = 0;
        fx_auto_segundo(fps, isla);                                     /* ★ turno 27 */
        if (g_fx_fps) apuntar("  [isla_fx] cuadros %ld en %d,%02d s = %d por segundo (tiempo de cuadro medio %d,%d ms, peor %d ms)%s%s",
                g_fx_fps_n, (int)seg, (int)(seg * 100.0) % 100, (int)(g_fx_fps_n / seg + 0.5), medio10 / 10, medio10 % 10,
                (int)(g_fx_fps_peor + 0.5), g_fx_activo ? (g_fx_calidad == 2 ? (g_fx_brillo && g_fx_p.brillo_activo ? " · alta" : " · alta sin brillo")
                                                                             : g_fx_calidad == 1 ? " · media" : " · baja")
                                                        : " · SIN efectos (activo=0)",
                g_fx_fps_fuente_seg == 2 ? " · reloj: la isla" : g_fx_fps_fuente_seg == 1 ? " · reloj: Present" : " · reloj: los dos");
        g_fx_fps_fuente_seg = 0;
        g_fx_fps_seg = ahora;
        g_fx_fps_n = 0;
        g_fx_fps_suma = g_fx_fps_peor = 0.0;
    }
}

/* ★ turno 27 · EL PRESENT DEL SWAPCHAIN: en el LOBBY el juego presenta por el swapchain (d3d9_proxy.c, «el segundo
 *   camino»), no por el del dispositivo: por eso la línea de los cuadros sólo salía al arrancar. Se cuentan los dos
 *   (el del dispositivo marca que está adentro, para no contar dos veces si uno llama al otro). */
typedef HRESULT (WINAPI *FX_SCPRESENT_F)(void *, const void *, const void *, HWND, const void *, DWORD);
typedef HRESULT (WINAPI *FX_GETSC_F)(void *, UINT, void **);
static FX_SCPRESENT_F g_fx_scpresent_real = NULL;
static int g_fx_en_present = 0, g_fx_sc_intentado = 0;
static void fx_escribir(void **lugar, void *valor);
/* ★ 21-nov · LA INTERMITENCIA DEL ARRANQUE en d3d9 NATIVO (anonimo03: «microsegundos en los que el agua cambia por la
 *   básica»). MEDIDO con la sonda (espejo, compat, RTX 3090): en el segundo en que Direct3D vuelve a escribir 81/82
 *   de la tabla, «con sombreador» cae de 120 a 56 y los dibujos de la isla de 43.620 a 20.356 ⇒ ~32 cuadros SIN la
 *   capa 4. Eran DOS vigías sueltos: sala_alfa mira cada 500 ms y, al reenganchar, pone como «original» la función
 *   nueva de Direct3D (o sea: nos SACA de su cadena); isla_fx se vuelve a meter cada 300 ms. Con DXVK no pasa (DXVK
 *   no reescribe la tabla). ⇒ en CADA cuadro (los dos Present) se mira la cadena: dos punteros si está entera, y si
 *   no, se rearma ahí mismo ⇒ como mucho se pierde el resto de UN cuadro. Los vigías siguen (por las dudas). */
static void fx_enganchar_tabla(void **vt);
static long g_fx_n_rearmes = 0;
#define FX_N_TRAS_DECL 56
static int fx_tras_puesto(void **vt, int j);
static long fx_tras_n(int j);
static int fx_settr_puesto(void **vt);
static void fx_vigia_cuadro_(const char *donde)
{
    void **vt = g_fx_pr_vt;
    if (!vt || fx_grabando()) return;                     /* ★ 21-nov: no se rearma mientras el juego graba */
    LONG i = 0;
    while (i < g_fx_nt && g_fx_t[i].vt != vt) i++;
    if (i >= g_fx_nt) return;                            /* el vigía todavía no la anotó: es su trabajo */
    int sala = 0, cadena = 0;
    if (g_fx_t[i].por_sala) {
        if (vt[SA_DRAWPRIMITIVE] != (void *)sa_dibujar || vt[SA_DRAWINDEXED] != (void *)sa_dibujar_idx) {
            sa_enganchar_tabla(vt);
            sala = 1;
        }
        LONG s = 0;
        while (s < g_sa_ntablas && g_sa_tablas[s].vt != vt) s++;
        cadena = s < g_sa_ntablas && (g_sa_tablas[s].real81 != (SA_DIBUJAR)fx_d81 || g_sa_tablas[s].real82 != (SA_DIBUJAR_IDX)fx_d82);
    } else
        cadena = vt[FX_DP] != fx_esperado(i, 0) || vt[FX_DP + 1] != fx_esperado(i, 1);
    if (!sala && !cadena) return;
    fx_enganchar_tabla(vt);
    if (g_fx_n_rearmes++ < 20) {
        /* ★ 21-nov · ¿qué MÁS reescribió Direct3D? (los envoltorios de fx_enganchar_tras y SetTransform siguen?) */
        char q[160]; int o = 0;
        int pu = 0;
        for (int j = 0; j < FX_N_TRAS_DECL; j++) pu += fx_tras_puesto(vt, j);
        o = wsprintfA(q, "%d de %d · hilo %lu", pu, FX_N_TRAS_DECL, GetCurrentThreadId());
        q[o] = 0;
        apuntar("  [isla_fx] ★ rearmé la cadena del dibujo EN EL CUADRO (%s): visto justo después de %s · t %lu ·"
                " isla vista hace %d ms · envoltorios puestos %s · SetTransform %s",
                sala ? "Direct3D reescribió 81/82" : "sala_alfa nos había sacado de su cadena", donde, GetTickCount(),
                g_fx_isla_tick ? (int)(GetTickCount() - g_fx_isla_tick) : -1, q, fx_settr_puesto(vt) ? "sí" : "NO");
    }
}
static volatile LONG g_fx_vigia_candado = 0;
static void fx_vigia_cuadro(const char *donde)
{
    if (InterlockedCompareExchange(&g_fx_vigia_candado, 1, 0) != 0) return;   /* otro hilo ya está rearmando */
    fx_vigia_cuadro_(donde);
    InterlockedExchange(&g_fx_vigia_candado, 0);
}

static HRESULT WINAPI fx_present_cadena(void *sc, const void *a, const void *b, HWND h, const void *c, DWORD f)
{
    fx_vigia_cuadro("Present del swapchain");
    if ((g_fx_fps || g_fx_auto) && !g_fx_en_present) fx_fps_cuadro(0);
    return g_fx_scpresent_real(sc, a, b, h, c, f);
}
static void fx_enganchar_cadena(void *dev)
{
    if (g_fx_sc_intentado || !dev) return;
    g_fx_sc_intentado = 1;
    void *sc = NULL;
    if (((FX_GETSC_F)FXV(dev)[14])(dev, 0, &sc) != 0 || !sc) {
        apuntar("  [isla_fx] ⚠ no pude tomar el swapchain: en el lobby no se cuentan los cuadros");
        return;
    }
    void **vtc = FXV(sc);
    if (vtc[3] != (void *)fx_present_cadena) {
        g_fx_scpresent_real = (FX_SCPRESENT_F)vtc[3];
        fx_escribir(&vtc[3], (void *)fx_present_cadena);
        apuntar("  [isla_fx] enganchado también el Present del swapchain (%p): el que usa el lobby", (void *)vtc);
    }
    fx_soltar(sc);
}

static void fx_fps_tic_isla(void)
{
    if (g_fx_fps || g_fx_auto) fx_fps_cuadro(1);
}

static HRESULT WINAPI fx_present(void *dev, const void *a, const void *b, HWND h, const void *c)
{
    fx_vigia_cuadro("Present");
    if (g_fx_fps || g_fx_auto) { fx_enganchar_cadena(dev); fx_fps_cuadro(0); }     /* ★ turno 26 / 27 */
    if (g_fx_isla_cuadro && !g_fx_brillo_hecho && g_fx_p.brillo_en_present && g_fx_activo && g_fx_brillo
        && g_fx_p.brillo_activo && g_fx_creados > 0)
        fx_hacer_brillo(dev, 0);
    if (g_fx_ndif > 0) fx_reproducir_guardando(dev, 0);              /* no hubo brillo en el cuadro: igual se dibujan */
    g_fx_isla_cuadro = 0;
    g_fx_brillo_hecho = 0;
    if (g_fx_trazar || g_fx_falsos) fx_traza_cuadro();                  /* ★ turno 11 / 12 */
    g_fx_en_present = 1;
    HRESULT r = g_fx_present_real(dev, a, b, h, c);
    g_fx_en_present = 0;
    return r;
}

static HRESULT WINAPI fx_reset(void *dev, void *pp)
{
    fx_brillo_soltar();                                  /* lo de D3DPOOL_DEFAULT, ANTES del Reset */
    return g_fx_reset_real(dev, pp);
}

static void fx_enganchar_present(void **vt)
{
    if (g_fx_pr_vt == vt) {
        /* ya puesto: sólo si alguien DEVOLVIÓ el original (no si alguien se puso encima nuestro) */
        if (vt[FX_PRESENT] == (void *)g_fx_present_real) fx_escribir(&vt[FX_PRESENT], (void *)fx_present);
        if (vt[FX_RESET] == (void *)g_fx_reset_real) fx_escribir(&vt[FX_RESET], (void *)fx_reset);
        return;
    }
    if (g_fx_pr_vt) return;                              /* otra tabla: no se engancha dos veces */
    g_fx_present_real = (FX_PRESENT_F)vt[FX_PRESENT];
    g_fx_reset_real = (FX_RESET_F)vt[FX_RESET];
    g_fx_pr_vt = vt;
    fx_escribir(&vt[FX_RESET], (void *)fx_reset);
    fx_escribir(&vt[FX_PRESENT], (void *)fx_present);
    apuntar("  [isla_fx] enganchados Present y Reset de la tabla %p (el fin del cuadro y el brillo)", (void *)vt);
}

/* ── el vigía: engancha el dibujo del dispositivo que dibuja apenas aparece ─────────────────────────────── */
/* ★ 21-nov · DESPUÉS DE CADA LLAMADA que puede hacer que Direct3D reescriba 81/82 (anonimo03: «el glitch sigue en el
 *   mismo instante» aun sin dibujar nada del trineo): se mira la cadena ahí mismo ⇒ no se pierde ni el resto del
 *   cuadro. Y el log dice cuál fue. Nadie más engancha estas entradas (sólo las llaman: d3d9_proxy, estilos_texto). */
#define FX_N_TRAS 56
static void *g_fx_tras_real[FX_N_TRAS];
static void **g_fx_tras_vt = NULL;
static const int g_fx_tras_i[FX_N_TRAS] = { 3, 5, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 34, 35, 36, 37, 39, 41, 42, 43, 46, 47, 49, 51, 53, 55, 57, 59, 60, 61, 62, 65, 67, 69, 70, 75, 77, 79, 85, 86, 87, 89, 91, 92, 94, 96, 98, 100, 102, 104, 106, 107, 109, 111, 113, 118 };
static const char *const g_fx_tras_nom[FX_N_TRAS] = {
    "TestCooperativeLevel", "EvictManagedResources", "CreateTexture", "CreateVolumeTexture",
    "CreateCubeTexture", "CreateVertexBuffer", "CreateIndexBuffer", "CreateRenderTarget",
    "CreateDepthStencilSurface", "UpdateSurface", "UpdateTexture", "GetRenderTargetData",
    "StretchRect", "ColorFill", "CreateOffscreenPlainSurface", "SetRenderTarget",
    "SetDepthStencilSurface", "BeginScene", "EndScene", "Clear",
    "MultiplyTransform", "SetViewport", "SetMaterial", "SetLight",
    "LightEnable", "SetClipPlane", "SetRenderState", "CreateStateBlock",
    "BeginStateBlock", "EndStateBlock", "SetClipStatus", "SetTexture",
    "SetTextureStageState", "SetSamplerState", "ValidateDevice", "SetScissorRect",
    "SetSoftwareVertexProcessing", "SetNPatchMode", "ProcessVertices", "CreateVertexDeclaration",
    "SetVertexDeclaration", "SetFVF", "CreateVertexShader", "SetVertexShader",
    "SetVertexShaderConstantF", "SetVertexShaderConstantI", "SetVertexShaderConstantB", "SetStreamSource",
    "SetStreamSourceFreq", "SetIndices", "CreatePixelShader", "SetPixelShader",
    "SetPixelShaderConstantF", "SetPixelShaderConstantI", "SetPixelShaderConstantB", "CreateQuery",
};
static volatile LONG g_fx_tras_cuenta[FX_N_TRAS];
/* el control: UNA comparación (¿81 sigue siendo el nuestro?); si no, el rearme con el candado */
#define FX_TRAS_MIRA(j) do { g_fx_tras_cuenta[j]++;                                                        \
        void **v_ = g_fx_pr_vt;                                                                            \
        if (v_ && g_fx_activo && !g_fx_dentro && v_[SA_DRAWPRIMITIVE] != g_fx_esperado81)                \
            fx_vigia_cuadro(g_fx_tras_nom[j]); } while (0)
typedef HRESULT (WINAPI *FX_T0)(void *);
typedef HRESULT (WINAPI *FX_T1)(void *, DWORD);
typedef HRESULT (WINAPI *FX_T2)(void *, DWORD, DWORD);
typedef HRESULT (WINAPI *FX_T3)(void *, DWORD, DWORD, DWORD);
typedef HRESULT (WINAPI *FX_T4)(void *, DWORD, DWORD, DWORD, DWORD);
typedef HRESULT (WINAPI *FX_T5)(void *, DWORD, DWORD, DWORD, DWORD, DWORD);
typedef HRESULT (WINAPI *FX_T6)(void *, DWORD, DWORD, DWORD, DWORD, DWORD, DWORD);
typedef HRESULT (WINAPI *FX_T7)(void *, DWORD, DWORD, DWORD, DWORD, DWORD, DWORD, DWORD);
typedef HRESULT (WINAPI *FX_T8)(void *, DWORD, DWORD, DWORD, DWORD, DWORD, DWORD, DWORD, DWORD);
typedef HRESULT (WINAPI *FX_T9)(void *, DWORD, DWORD, DWORD, DWORD, DWORD, DWORD, DWORD, DWORD, DWORD);
static HRESULT WINAPI fx_tras0(void *d) { HRESULT r = ((FX_T0)g_fx_tras_real[0])(d); FX_TRAS_MIRA(0); return r; }   /* 3 TestCooperativeLevel */
static HRESULT WINAPI fx_tras1(void *d) { HRESULT r = ((FX_T0)g_fx_tras_real[1])(d); FX_TRAS_MIRA(1); return r; }   /* 5 EvictManagedResources */
static HRESULT WINAPI fx_tras2(void *d, DWORD a0, DWORD a1, DWORD a2, DWORD a3, DWORD a4, DWORD a5, DWORD a6, DWORD a7) { HRESULT r = ((FX_T8)g_fx_tras_real[2])(d, a0, a1, a2, a3, a4, a5, a6, a7); FX_TRAS_MIRA(2); return r; }   /* 23 CreateTexture */
static HRESULT WINAPI fx_tras3(void *d, DWORD a0, DWORD a1, DWORD a2, DWORD a3, DWORD a4, DWORD a5, DWORD a6, DWORD a7, DWORD a8) { HRESULT r = ((FX_T9)g_fx_tras_real[3])(d, a0, a1, a2, a3, a4, a5, a6, a7, a8); FX_TRAS_MIRA(3); return r; }   /* 24 CreateVolumeTexture */
static HRESULT WINAPI fx_tras4(void *d, DWORD a0, DWORD a1, DWORD a2, DWORD a3, DWORD a4, DWORD a5, DWORD a6) { HRESULT r = ((FX_T7)g_fx_tras_real[4])(d, a0, a1, a2, a3, a4, a5, a6); FX_TRAS_MIRA(4); return r; }   /* 25 CreateCubeTexture */
static HRESULT WINAPI fx_tras5(void *d, DWORD a0, DWORD a1, DWORD a2, DWORD a3, DWORD a4, DWORD a5) { HRESULT r = ((FX_T6)g_fx_tras_real[5])(d, a0, a1, a2, a3, a4, a5); FX_TRAS_MIRA(5); return r; }   /* 26 CreateVertexBuffer */
static HRESULT WINAPI fx_tras6(void *d, DWORD a0, DWORD a1, DWORD a2, DWORD a3, DWORD a4, DWORD a5) { HRESULT r = ((FX_T6)g_fx_tras_real[6])(d, a0, a1, a2, a3, a4, a5); FX_TRAS_MIRA(6); return r; }   /* 27 CreateIndexBuffer */
static HRESULT WINAPI fx_tras7(void *d, DWORD a0, DWORD a1, DWORD a2, DWORD a3, DWORD a4, DWORD a5, DWORD a6, DWORD a7) { HRESULT r = ((FX_T8)g_fx_tras_real[7])(d, a0, a1, a2, a3, a4, a5, a6, a7); FX_TRAS_MIRA(7); return r; }   /* 28 CreateRenderTarget */
static HRESULT WINAPI fx_tras8(void *d, DWORD a0, DWORD a1, DWORD a2, DWORD a3, DWORD a4, DWORD a5, DWORD a6, DWORD a7) { HRESULT r = ((FX_T8)g_fx_tras_real[8])(d, a0, a1, a2, a3, a4, a5, a6, a7); FX_TRAS_MIRA(8); return r; }   /* 29 CreateDepthStencilSurface */
static HRESULT WINAPI fx_tras9(void *d, DWORD a0, DWORD a1, DWORD a2, DWORD a3) { HRESULT r = ((FX_T4)g_fx_tras_real[9])(d, a0, a1, a2, a3); FX_TRAS_MIRA(9); return r; }   /* 30 UpdateSurface */
static HRESULT WINAPI fx_tras10(void *d, DWORD a0, DWORD a1) { HRESULT r = ((FX_T2)g_fx_tras_real[10])(d, a0, a1); FX_TRAS_MIRA(10); return r; }   /* 31 UpdateTexture */
static HRESULT WINAPI fx_tras11(void *d, DWORD a0, DWORD a1) { HRESULT r = ((FX_T2)g_fx_tras_real[11])(d, a0, a1); FX_TRAS_MIRA(11); return r; }   /* 32 GetRenderTargetData */
static HRESULT WINAPI fx_tras12(void *d, DWORD a0, DWORD a1, DWORD a2, DWORD a3, DWORD a4) { HRESULT r = ((FX_T5)g_fx_tras_real[12])(d, a0, a1, a2, a3, a4); FX_TRAS_MIRA(12); return r; }   /* 34 StretchRect */
static HRESULT WINAPI fx_tras13(void *d, DWORD a0, DWORD a1, DWORD a2) { HRESULT r = ((FX_T3)g_fx_tras_real[13])(d, a0, a1, a2); FX_TRAS_MIRA(13); return r; }   /* 35 ColorFill */
static HRESULT WINAPI fx_tras14(void *d, DWORD a0, DWORD a1, DWORD a2, DWORD a3, DWORD a4, DWORD a5) { HRESULT r = ((FX_T6)g_fx_tras_real[14])(d, a0, a1, a2, a3, a4, a5); FX_TRAS_MIRA(14); return r; }   /* 36 CreateOffscreenPlainSurface */
static HRESULT WINAPI fx_tras15(void *d, DWORD a0, DWORD a1) { HRESULT r = ((FX_T2)g_fx_tras_real[15])(d, a0, a1); FX_TRAS_MIRA(15); return r; }   /* 37 SetRenderTarget */
static HRESULT WINAPI fx_tras16(void *d, DWORD a0) { HRESULT r = ((FX_T1)g_fx_tras_real[16])(d, a0); FX_TRAS_MIRA(16); return r; }   /* 39 SetDepthStencilSurface */
static HRESULT WINAPI fx_tras17(void *d) { HRESULT r = ((FX_T0)g_fx_tras_real[17])(d); FX_TRAS_MIRA(17); return r; }   /* 41 BeginScene */
static HRESULT WINAPI fx_tras18(void *d) { HRESULT r = ((FX_T0)g_fx_tras_real[18])(d); FX_TRAS_MIRA(18); return r; }   /* 42 EndScene */
static HRESULT WINAPI fx_tras19(void *d, DWORD a0, DWORD a1, DWORD a2, DWORD a3, DWORD a4, DWORD a5) { HRESULT r = ((FX_T6)g_fx_tras_real[19])(d, a0, a1, a2, a3, a4, a5); FX_TRAS_MIRA(19); return r; }   /* 43 Clear */
static HRESULT WINAPI fx_tras20(void *d, DWORD a0, DWORD a1) { HRESULT r = ((FX_T2)g_fx_tras_real[20])(d, a0, a1); FX_TRAS_MIRA(20); return r; }   /* 46 MultiplyTransform */
static HRESULT WINAPI fx_tras21(void *d, DWORD a0) { HRESULT r = ((FX_T1)g_fx_tras_real[21])(d, a0); FX_TRAS_MIRA(21); return r; }   /* 47 SetViewport */
static HRESULT WINAPI fx_tras22(void *d, DWORD a0) { HRESULT r = ((FX_T1)g_fx_tras_real[22])(d, a0); FX_TRAS_MIRA(22); return r; }   /* 49 SetMaterial */
static HRESULT WINAPI fx_tras23(void *d, DWORD a0, DWORD a1) { HRESULT r = ((FX_T2)g_fx_tras_real[23])(d, a0, a1); FX_TRAS_MIRA(23); return r; }   /* 51 SetLight */
static HRESULT WINAPI fx_tras24(void *d, DWORD a0, DWORD a1) { HRESULT r = ((FX_T2)g_fx_tras_real[24])(d, a0, a1); FX_TRAS_MIRA(24); return r; }   /* 53 LightEnable */
static HRESULT WINAPI fx_tras25(void *d, DWORD a0, DWORD a1) { HRESULT r = ((FX_T2)g_fx_tras_real[25])(d, a0, a1); FX_TRAS_MIRA(25); return r; }   /* 55 SetClipPlane */
static HRESULT WINAPI fx_tras26(void *d, DWORD a0, DWORD a1) { HRESULT r = ((FX_T2)g_fx_tras_real[26])(d, a0, a1); FX_TRAS_MIRA(26); return r; }   /* 57 SetRenderState */
static HRESULT WINAPI fx_tras27(void *d, DWORD a0, DWORD a1) { HRESULT r = ((FX_T2)g_fx_tras_real[27])(d, a0, a1); FX_TRAS_MIRA(27); return r; }   /* 59 CreateStateBlock */
/* ★ 21-nov · MEDIDO (los 56 controles): lo que le resetea la tabla al dispositivo es la GRABACIÓN de un bloque de
 *   estado del juego: BeginStateBlock cambia la tabla entera por la «de grabación» y EndStateBlock la devuelve entera
 *   a la normal (sin nuestros enganches) ⇒ el micro cuadro de ~16 ms hasta que el vigía rápido se enteraba.
 *   ⇒ al EMPEZAR una grabación no se toca nada (rearmar ahí ensuciaría lo que el juego graba) salvo colgarse de su
 *   EndStateBlock; al TERMINAR, se rearma todo ahí mismo, en el mismo hilo, antes de volver al juego. */
static void *g_fx_fin_rec = NULL;
static long g_fx_n_grabaciones = 0;
static void fx_rearmar_todo(void **vt, const char *donde);
static HRESULT WINAPI fx_fin_grabar(void *d, DWORD a0)
{
    HRESULT r = ((FX_T1)g_fx_fin_rec)(d, a0);
    InterlockedExchange(&g_fx_grabando, 0);
    if (g_fx_activo && !g_fx_roto && g_fx_pr_vt) fx_rearmar_todo(g_fx_pr_vt, "EndStateBlock (el juego terminó de grabar un bloque)");
    return r;
}
static HRESULT WINAPI fx_tras28(void *d)                 /* 60 BeginStateBlock */
{
    HRESULT r = ((FX_T0)g_fx_tras_real[28])(d);
    g_fx_tras_cuenta[28]++;
    if (r == 0) {
        void **v = FXV(d);
        g_fx_grab_t = GetTickCount();
        InterlockedExchange(&g_fx_grabando, 1);
        if (v[61] != (void *)fx_fin_grabar) { g_fx_fin_rec = v[61]; fx_escribir(&v[61], (void *)fx_fin_grabar); }
        if (g_fx_n_grabaciones++ == 0)
            apuntar("  [isla_fx] ★ el juego graba un bloque de estado: me cuelgo de su EndStateBlock para rearmar al terminar");
    }
    return r;
}
static HRESULT WINAPI fx_tras29(void *d, DWORD a0) { HRESULT r = ((FX_T1)g_fx_tras_real[29])(d, a0); FX_TRAS_MIRA(29); return r; }   /* 61 EndStateBlock */
static HRESULT WINAPI fx_tras30(void *d, DWORD a0) { HRESULT r = ((FX_T1)g_fx_tras_real[30])(d, a0); FX_TRAS_MIRA(30); return r; }   /* 62 SetClipStatus */
static HRESULT WINAPI fx_tras31(void *d, DWORD a0, DWORD a1) { HRESULT r = ((FX_T2)g_fx_tras_real[31])(d, a0, a1); FX_TRAS_MIRA(31); return r; }   /* 65 SetTexture */
static HRESULT WINAPI fx_tras32(void *d, DWORD a0, DWORD a1, DWORD a2) { HRESULT r = ((FX_T3)g_fx_tras_real[32])(d, a0, a1, a2); FX_TRAS_MIRA(32); return r; }   /* 67 SetTextureStageState */
static HRESULT WINAPI fx_tras33(void *d, DWORD a0, DWORD a1, DWORD a2) { HRESULT r = ((FX_T3)g_fx_tras_real[33])(d, a0, a1, a2); FX_TRAS_MIRA(33); return r; }   /* 69 SetSamplerState */
static HRESULT WINAPI fx_tras34(void *d, DWORD a0) { HRESULT r = ((FX_T1)g_fx_tras_real[34])(d, a0); FX_TRAS_MIRA(34); return r; }   /* 70 ValidateDevice */
static HRESULT WINAPI fx_tras35(void *d, DWORD a0) { HRESULT r = ((FX_T1)g_fx_tras_real[35])(d, a0); FX_TRAS_MIRA(35); return r; }   /* 75 SetScissorRect */
static HRESULT WINAPI fx_tras36(void *d, DWORD a0) { HRESULT r = ((FX_T1)g_fx_tras_real[36])(d, a0); FX_TRAS_MIRA(36); return r; }   /* 77 SetSoftwareVertexProcessing */
static HRESULT WINAPI fx_tras37(void *d, DWORD a0) { HRESULT r = ((FX_T1)g_fx_tras_real[37])(d, a0); FX_TRAS_MIRA(37); return r; }   /* 79 SetNPatchMode */
static HRESULT WINAPI fx_tras38(void *d, DWORD a0, DWORD a1, DWORD a2, DWORD a3, DWORD a4, DWORD a5) { HRESULT r = ((FX_T6)g_fx_tras_real[38])(d, a0, a1, a2, a3, a4, a5); FX_TRAS_MIRA(38); return r; }   /* 85 ProcessVertices */
static HRESULT WINAPI fx_tras39(void *d, DWORD a0, DWORD a1) { HRESULT r = ((FX_T2)g_fx_tras_real[39])(d, a0, a1); FX_TRAS_MIRA(39); return r; }   /* 86 CreateVertexDeclaration */
static HRESULT WINAPI fx_tras40(void *d, DWORD a0) { HRESULT r = ((FX_T1)g_fx_tras_real[40])(d, a0); FX_TRAS_MIRA(40); return r; }   /* 87 SetVertexDeclaration */
static HRESULT WINAPI fx_tras41(void *d, DWORD a0) { HRESULT r = ((FX_T1)g_fx_tras_real[41])(d, a0); FX_TRAS_MIRA(41); return r; }   /* 89 SetFVF */
static HRESULT WINAPI fx_tras42(void *d, DWORD a0, DWORD a1) { HRESULT r = ((FX_T2)g_fx_tras_real[42])(d, a0, a1); FX_TRAS_MIRA(42); return r; }   /* 91 CreateVertexShader */
static HRESULT WINAPI fx_tras43(void *d, DWORD a0) { HRESULT r = ((FX_T1)g_fx_tras_real[43])(d, a0); FX_TRAS_MIRA(43); return r; }   /* 92 SetVertexShader */
static HRESULT WINAPI fx_tras44(void *d, DWORD a0, DWORD a1, DWORD a2) { HRESULT r = ((FX_T3)g_fx_tras_real[44])(d, a0, a1, a2); FX_TRAS_MIRA(44); return r; }   /* 94 SetVertexShaderConstantF */
static HRESULT WINAPI fx_tras45(void *d, DWORD a0, DWORD a1, DWORD a2) { HRESULT r = ((FX_T3)g_fx_tras_real[45])(d, a0, a1, a2); FX_TRAS_MIRA(45); return r; }   /* 96 SetVertexShaderConstantI */
static HRESULT WINAPI fx_tras46(void *d, DWORD a0, DWORD a1, DWORD a2) { HRESULT r = ((FX_T3)g_fx_tras_real[46])(d, a0, a1, a2); FX_TRAS_MIRA(46); return r; }   /* 98 SetVertexShaderConstantB */
static HRESULT WINAPI fx_tras47(void *d, DWORD a0, DWORD a1, DWORD a2, DWORD a3) { HRESULT r = ((FX_T4)g_fx_tras_real[47])(d, a0, a1, a2, a3); FX_TRAS_MIRA(47); return r; }   /* 100 SetStreamSource */
static HRESULT WINAPI fx_tras48(void *d, DWORD a0, DWORD a1) { HRESULT r = ((FX_T2)g_fx_tras_real[48])(d, a0, a1); FX_TRAS_MIRA(48); return r; }   /* 102 SetStreamSourceFreq */
static HRESULT WINAPI fx_tras49(void *d, DWORD a0) { HRESULT r = ((FX_T1)g_fx_tras_real[49])(d, a0); FX_TRAS_MIRA(49); return r; }   /* 104 SetIndices */
static HRESULT WINAPI fx_tras50(void *d, DWORD a0, DWORD a1) { HRESULT r = ((FX_T2)g_fx_tras_real[50])(d, a0, a1); FX_TRAS_MIRA(50); return r; }   /* 106 CreatePixelShader */
static HRESULT WINAPI fx_tras51(void *d, DWORD a0) { HRESULT r = ((FX_T1)g_fx_tras_real[51])(d, a0); FX_TRAS_MIRA(51); return r; }   /* 107 SetPixelShader */
static HRESULT WINAPI fx_tras52(void *d, DWORD a0, DWORD a1, DWORD a2) { HRESULT r = ((FX_T3)g_fx_tras_real[52])(d, a0, a1, a2); FX_TRAS_MIRA(52); return r; }   /* 109 SetPixelShaderConstantF */
static HRESULT WINAPI fx_tras53(void *d, DWORD a0, DWORD a1, DWORD a2) { HRESULT r = ((FX_T3)g_fx_tras_real[53])(d, a0, a1, a2); FX_TRAS_MIRA(53); return r; }   /* 111 SetPixelShaderConstantI */
static HRESULT WINAPI fx_tras54(void *d, DWORD a0, DWORD a1, DWORD a2) { HRESULT r = ((FX_T3)g_fx_tras_real[54])(d, a0, a1, a2); FX_TRAS_MIRA(54); return r; }   /* 113 SetPixelShaderConstantB */
static HRESULT WINAPI fx_tras55(void *d, DWORD a0, DWORD a1, DWORD a2) { HRESULT r = ((FX_T3)g_fx_tras_real[55])(d, a0, a1, a2); FX_TRAS_MIRA(55); return r; }   /* 118 CreateQuery */
static void *const g_fx_tras_fn[FX_N_TRAS] = {
    (void *)fx_tras0, (void *)fx_tras1, (void *)fx_tras2, (void *)fx_tras3, (void *)fx_tras4, (void *)fx_tras5,
    (void *)fx_tras6, (void *)fx_tras7, (void *)fx_tras8, (void *)fx_tras9, (void *)fx_tras10, (void *)fx_tras11,
    (void *)fx_tras12, (void *)fx_tras13, (void *)fx_tras14, (void *)fx_tras15, (void *)fx_tras16, (void *)fx_tras17,
    (void *)fx_tras18, (void *)fx_tras19, (void *)fx_tras20, (void *)fx_tras21, (void *)fx_tras22, (void *)fx_tras23,
    (void *)fx_tras24, (void *)fx_tras25, (void *)fx_tras26, (void *)fx_tras27, (void *)fx_tras28, (void *)fx_tras29,
    (void *)fx_tras30, (void *)fx_tras31, (void *)fx_tras32, (void *)fx_tras33, (void *)fx_tras34, (void *)fx_tras35,
    (void *)fx_tras36, (void *)fx_tras37, (void *)fx_tras38, (void *)fx_tras39, (void *)fx_tras40, (void *)fx_tras41,
    (void *)fx_tras42, (void *)fx_tras43, (void *)fx_tras44, (void *)fx_tras45, (void *)fx_tras46, (void *)fx_tras47,
    (void *)fx_tras48, (void *)fx_tras49, (void *)fx_tras50, (void *)fx_tras51, (void *)fx_tras52, (void *)fx_tras53,
    (void *)fx_tras54, (void *)fx_tras55,
};
static void fx_enganchar_tras(void **vt)
{
    if (g_fx_tras_vt == vt) {                            /* ya puestos: sólo si alguien DEVOLVIÓ el original */
        for (int j = 0; j < FX_N_TRAS; j++)
            if (vt[g_fx_tras_i[j]] == g_fx_tras_real[j]) fx_escribir(&vt[g_fx_tras_i[j]], g_fx_tras_fn[j]);
        return;
    }
    if (g_fx_tras_vt) return;                            /* otra tabla: no se engancha dos veces */
    static volatile LONG instalando = 0;                 /* ★ 21-nov: dos hilos no la instalan a la vez (real = nuestro) */
    if (InterlockedCompareExchange(&instalando, 1, 0) != 0) return;
    for (int j = 0; j < FX_N_TRAS; j++) g_fx_tras_real[j] = vt[g_fx_tras_i[j]];
    for (int j = 0; j < FX_N_TRAS; j++) fx_escribir(&vt[g_fx_tras_i[j]], g_fx_tras_fn[j]);
    g_fx_tras_vt = vt;                                   /* ★ 21-nov: anotada DESPUÉS (el vigía rápido) */
    apuntar("  [isla_fx] ★ la cadena del dibujo se mira también después de %d funciones de la tabla %p (las que cambian"
            " estado o crean recursos): si Direct3D la resetea adentro de una, se rearma ahí mismo", FX_N_TRAS, (void *)vt);
}
static long fx_tras_n(int j) { return g_fx_tras_cuenta[j]; }
static int fx_tras_puesto(void **vt, int j) { return g_fx_tras_vt == vt && vt[g_fx_tras_i[j]] == g_fx_tras_fn[j]; }
static int fx_settr_puesto(void **vt) { return vt[FX_SETTRANSFORM] == (void *)fx_settr; }
/* ★ 21-nov · EL VIGÍA RÁPIDO. MEDIDO (sonda_selector=2, un hilo que mira la tabla cada 2 ms): cuando aparece el
 *   trineo, Direct3D devuelve la tabla ENTERA del dispositivo a sus funciones (81, 82, 57, 65… todas a las de
 *   d3d9.dll): se caen TODOS los enganches a la vez — por eso ningún control del hilo de dibujo se enteraba — y
 *   ~220 ms de cuadros salían sin la capa 4 y con el trineo (el vigía de 300 ms volvía a poner SetTransform).
 *   ⇒ un hilo liviano mira la tabla cada 1 ms y, si se reseteó, vuelve a poner todo ahí mismo. Con DXVK no pasa nada
 *   (nunca la resetea): son dos comparaciones por milisegundo. */
/* ★ 21-nov · rearma TODO: 81/82 (por sala_alfa o directo), SetTransform, Present y los 56 controles */
static void fx_rearmar_todo(void **vt, const char *donde)
{
    fx_vigia_cuadro(donde);
    if (InterlockedCompareExchange(&g_fx_vigia_candado, 1, 0) != 0) return;
    if (g_fx_settr_vt == vt) fx_enganchar_settr(vt);         /* vuelven a ponerse si están los originales */
    if (g_fx_tras_vt == vt) fx_enganchar_tras(vt);
    if (g_fx_pr_vt == vt) fx_enganchar_present(vt);
    InterlockedExchange(&g_fx_vigia_candado, 0);
}
static DWORD WINAPI fx_vigia_rapido(LPVOID p)
{
    (void)p;
    long n = 0;
    for (;;) {
        Sleep(1);
        void **vt = g_fx_pr_vt;
        if (!vt || !g_fx_activo || g_fx_roto) continue;
        int caida = (g_fx_settr_vt == vt && vt[FX_SETTRANSFORM] != (void *)fx_settr)
                    || (g_fx_tras_vt == vt && vt[g_fx_tras_i[0]] != g_fx_tras_fn[0])
                    || vt[FX_PRESENT] == (void *)g_fx_present_real;
        if (fx_grabando()) continue;                         /* el juego está grabando un bloque: no se toca */
        fx_vigia_cuadro("el vigía rápido (1 ms)");              /* 81/82: por sala_alfa o directo */
        if (!caida) continue;
        fx_rearmar_todo(vt, "el vigía rápido (1 ms)");
        if (n++ < 12)
            apuntar("  [isla_fx] ★ vigía rápido: Direct3D reseteó la tabla del dispositivo (t %lu): enganches puestos de nuevo"                    " (SetTransform %s · envoltorios %s · Present %s)", GetTickCount(), fx_settr_puesto(vt) ? "sí" : "NO",
                    fx_tras_puesto(vt, 0) ? "sí" : "NO", vt[FX_PRESENT] == (void *)fx_present ? "sí" : "no");
    }
}

static void fx_enganchar_tabla(void **vt)
{
    LONG i = 0;
    while (i < g_fx_nt && g_fx_t[i].vt != vt) i++;
    if (i == g_fx_nt) {
        if (i >= FX_TABLAS) return;
        g_fx_t[i].vt = vt;
        g_fx_t[i].por_sala = g_sa_activo;
        InterlockedExchange(&g_fx_nt, i + 1);
        apuntar("  [isla_fx] ★ tabla %p del dispositivo que dibuja: 81/82 %s", (void *)vt,
                g_sa_activo ? "por la cadena de sala_alfa" : "directo");
    }
    /* 81/82 */
    if (g_fx_t[i].por_sala) {
        LONG s = 0;
        while (s < g_sa_ntablas && g_sa_tablas[s].vt != vt) s++;
        static int esperas = 0;
        if (s >= g_sa_ntablas && ++esperas == 20)
            apuntar("  [isla_fx] ⚠ sala_alfa todavía no enganchó la tabla %p (6 s): la capa 4 espera su cadena", (void *)vt);
        if (s < g_sa_ntablas) {
            if (g_sa_tablas[s].real81 && g_sa_tablas[s].real81 != (SA_DIBUJAR)fx_d81) {
                g_fx_t[i].real[0] = (void *)g_sa_tablas[s].real81;            /* el original ANTES de meternos */
                g_sa_tablas[s].real81 = (SA_DIBUJAR)fx_d81;
            }
            if (g_sa_tablas[s].real82 && g_sa_tablas[s].real82 != (SA_DIBUJAR_IDX)fx_d82) {
                g_fx_t[i].real[1] = (void *)g_sa_tablas[s].real82;
                g_sa_tablas[s].real82 = (SA_DIBUJAR_IDX)fx_d82;
            }
        }
    } else {
        for (int k = 0; k < 2; k++)
            if (vt[FX_DP + k] != fx_esperado(i, k)) {
                g_fx_t[i].real[k] = vt[FX_DP + k];
                fx_escribir(&vt[FX_DP + k], fx_esperado(i, k));
            }
    }
    /* 83/84 (los «UP»): con la sonda o el brillo (el disparo del brillo es el primer dibujo 2D) */
    if (g_fx_sonda || g_fx_brillo)
        for (int k = 2; k < 4; k++)
            if (vt[FX_DP + k] != fx_esperado(i, k)) {
                g_fx_t[i].real[k] = vt[FX_DP + k];
                fx_escribir(&vt[FX_DP + k], fx_esperado(i, k));
            }
    if ((g_fx_brillo && g_fx_activo) || g_fx_trazar || g_fx_falsos || g_fx_fps || g_fx_auto) fx_enganchar_present(vt);  /* ★ turno 11 / 12 / 26 / 27 */
    if (g_fx_cercano > 0.0f && g_fx_perfil_ok) fx_enganchar_settr(vt);      /* ★ turno 4 (con sonda: sólo cuenta) */
    g_fx_esperado81 = fx_esperado(i, 0);
    if (g_fx_activo) fx_enganchar_tras(vt);                                /* ★ 21-nov */
}

/* ★ turno 7 · el reinicio del front.ani = una visita al lobby. Las dos llamadas medidas (E8 rel32 → 0x655C20, con
 *   «rnr_ui_bg/front/front.ani» = 0x878ADC empujado justo antes: 68 DC 8A 87 00) se desvían a una cueva:
 *       FF 05 <&g_fx_ani_reinicios>     inc dword [contador]      (no toca registros ni la pila; las banderas no
 *       E9 <rel32 → 0x655C20>           jmp 0x655C20               se usan después de un call)
 *   Si los bytes no son los medidos, no se toca nada y las campanillas van por huecos de dibujo (≥ 2 s). */
static int fx_enganchar_ani(void)
{
    static const DWORD sitios[2] = { 0x49AB2B, 0x4C3FE0 };
    BYTE *base = (BYTE *)GetModuleHandleA(NULL);
    for (int i = 0; i < 2; i++) {
        BYTE *c = base + (sitios[i] - 0x400000);
        /* el push del nombre va justo antes (0x49AB26) o con un «mov ecx, eax» en medio (0x4C3FD9) */
        int con_push = !IsBadReadPtr(c - 7, 12)
                       && ((c[-5] == 0x68 && *(DWORD *)(c - 4) == 0x878ADC) || (c[-7] == 0x68 && *(DWORD *)(c - 6) == 0x878ADC));
        if (!con_push || c[0] != 0xE8 || (DWORD)(ULONG_PTR)(c + 5 + *(int *)(c + 1)) != (DWORD)(ULONG_PTR)(base + (0x655C20 - 0x400000))) {
            apuntar("  [isla_fx] campanillas: la llamada al front.ani (0x%X) no es la medida: van por huecos de dibujo", sitios[i]);
            return 0;
        }
    }
    /* ★ turno 8: una cueva por sitio (17 bytes): sube el total Y el de ese sitio (para saber cuál es la intro) */
    BYTE *cuevas = (BYTE *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!cuevas) return 0;
    for (int i = 0; i < 2; i++) {
        BYTE *cv = cuevas + 32 * i;
        cv[0] = 0xFF; cv[1] = 0x05; *(DWORD *)(cv + 2) = (DWORD)(ULONG_PTR)&g_fx_ani_reinicios;
        cv[6] = 0xFF; cv[7] = 0x05; *(DWORD *)(cv + 8) = (DWORD)(ULONG_PTR)&g_fx_ani_sitio[i];
        cv[12] = 0xE9;
        *(int *)(cv + 13) = (int)((DWORD)(ULONG_PTR)(base + (0x655C20 - 0x400000)) - ((DWORD)(ULONG_PTR)cv + 17));
    }
    FlushInstructionCache(GetCurrentProcess(), cuevas, 64);
    for (int i = 0; i < 2; i++) {
        BYTE *cueva = cuevas + 32 * i;
        BYTE *c = base + (sitios[i] - 0x400000);
        DWORD viejo = 0;
        if (!VirtualProtect(c, 5, PAGE_EXECUTE_READWRITE, &viejo)) return 0;
        *(int *)(c + 1) = (int)((DWORD)(ULONG_PTR)cueva - ((DWORD)(ULONG_PTR)c + 5));
        VirtualProtect(c, 5, viejo, &viejo);
        FlushInstructionCache(GetCurrentProcess(), c, 5);
    }
    apuntar("  [isla_fx] ★ campanillas: enganchado el reinicio del front.ani (0x49AB2B, 0x4C3FE0): una vez por visita");
    return 1;
}

typedef DWORD (__stdcall *FX_MCI_F)(const char *orden, char *ret, UINT n, HWND h);
static DWORD WINAPI fx_campanillas(LPVOID nada)
{
    (void)nada;
    HMODULE w = LoadLibraryA("winmm.dll");
    FX_MCI_F mci = w ? (FX_MCI_F)GetProcAddress(w, "mciSendStringA") : NULL;
    char ruta[MAX_PATH], orden[MAX_PATH + 64], cfg[MAX_PATH];
    DWORD n = GetTempPathA(MAX_PATH - 40, ruta);
    if (!mci || !n) { apuntar("  [isla_fx] ⚠ campanillas: sin winmm/MCI: mudas"); return 0; }
    lstrcatA(ruta, "r2beat_campanillas_trineo.mp3");
    HANDLE f = CreateFileA(ruta, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (f == INVALID_HANDLE_VALUE) { apuntar("  [isla_fx] ⚠ campanillas: no pude escribir %s: mudas", ruta); return 0; }
    DWORD escrito = 0;
    WriteFile(f, FX_CAMPANILLAS, sizeof(FX_CAMPANILLAS), &escrito, NULL);
    CloseHandle(f);
    wsprintfA(orden, "open \"%s\" type mpegvideo alias r2fx_campanillas", ruta);
    if (escrito != sizeof(FX_CAMPANILLAS) || mci(orden, NULL, 0, NULL) != 0) {
        apuntar("  [isla_fx] ⚠ campanillas: MCI no abrió el mp3: mudas");
        return 0;
    }
    lstrcpyA(cfg, g_carpeta);
    lstrcatA(cfg, "Config.ini");
    for (;;) {
        WaitForSingleObject(g_fx_camp_ev, INFINITE);
        if (!GetPrivateProfileIntA("SOUND", "EFFECT", 1, cfg)) continue;            /* el juego, con efectos mudos */
        DWORD t0 = GetTickCount();
        while (g_fx_camp_espera > 0 && fx_ms(GetTickCount(), t0) < g_fx_camp_espera) Sleep(20);
        if (fx_camp_cortar(&g_fx_cs, GetTickCount())) continue;                    /* ya no está en la isla */
    otra:
        mci("setaudio r2fx_campanillas volume to 1000", NULL, 0, NULL);
        mci("play r2fx_campanillas from 0", NULL, 0, NULL);
        g_fx_camp_veces++;
        if (g_fx_sonda) apuntar("  [isla_fx] sonda: campanillas: suenan (%ld.ª vez)", g_fx_camp_veces);
        t0 = GetTickCount();
        LONG ani_al_tocar = g_fx_cs.ani_visto;
        while (fx_ms(GetTickCount(), t0) < 14000) {
            Sleep(50);
            int nueva = WaitForSingleObject(g_fx_camp_ev, 0) == WAIT_OBJECT_0;    /* ★ turno 8: otro trineo ya */
            if (nueva || fx_camp_corte(&g_fx_cs, GetTickCount(), ani_al_tocar)) {
                /* fundido rápido (~150 ms) y parar */
                for (int v = 750; v >= 0; v -= 250) {
                    char o[64];
                    wsprintfA(o, "setaudio r2fx_campanillas volume to %d", v);
                    mci(o, NULL, 0, NULL);
                    Sleep(50);
                }
                mci("stop r2fx_campanillas", NULL, 0, NULL);
                if (g_fx_sonda)
                    apuntar("  [isla_fx] sonda: campanillas: cortadas (%s)", nueva ? "aparece otro trineo"
                            : g_fx_cs.ani_visto != ani_al_tocar ? "se reinició el .ani: otra escena del frente" : "salió de la isla");
                if (nueva) goto otra;
                break;
            }
        }
    }
    return 0;
}

static DWORD WINAPI fx_vigilar(LPVOID nada)
{
    (void)nada;
    BYTE *base = (BYTE *)GetModuleHandleA(NULL);
    for (;;) {
        Sleep(300);
        BYTE **pw = (BYTE **)(base + (FX_VA_WRAP - 0x400000));
        if (IsBadReadPtr(pw, sizeof(void *))) continue;
        BYTE *w = *pw;
        if (!w || IsBadReadPtr(w + 0xC0, sizeof(void *))) continue;
        void *dev = *(void **)(w + 0xC0);
        if (!dev || IsBadReadPtr(dev, sizeof(void *))) continue;
        void **vt = *(void ***)dev;
        if (!vt || IsBadReadPtr(vt, (FX_SETPSCF + 1) * sizeof(void *))) continue;
        fx_enganchar_tabla(vt);
    }
    return 0;
}

/* ★ turno 27 · poner la calidad (al arrancar o andando, con calidad=auto) */
static void fx_calidad_poner(int nivel)
{
    if (nivel < 0) nivel = 0;
    if (nivel > 2) nivel = 2;
    g_fx_calidad = nivel;
    if (nivel == 2) {
        g_fx_nluz = g_fx_luces_estables ? 64 : 32;
        if (g_fx_creados && g_fx_nluz >= 64 && (!g_fx_ps[FX_SH_PS_MAR_64] || !g_fx_ps[FX_SH_PS_LUCES_64] || !g_fx_ps[FX_SH_PS_NIEVE_64]))
            g_fx_nluz = 32;
    } else g_fx_nluz = nivel == 1 ? 16 : 8;
    g_fx_brillo = nivel == 0 ? 0 : g_fx_brillo_pedido;
    g_fx_luces_nuevas = 1;                                      /* que se vuelvan a elegir las luces */
}

/* ── el arranque (DllMain, después de isla_hora_iniciar) ─────────────────────────────────────────────────── */
/* ¿la isla que se VE es la de noche? isla_hora dice noche (g_ih_esconder = 1) ANTES de enganchar FindFirstFileA; si el
 * gancho no se pudo poner, se montan los dos paks y gana el del DÍA. ⇒ se mira la tabla de importaciones del exe
 * (0x873184, medido en isla_hora.c): si no tiene su gancho, es de día. Si no se puede leer (el banco), se le cree. */
static int fx_es_de_noche(void)
{
    if (!g_ih_esconder) return 0;
    void **iat = (void **)((BYTE *)GetModuleHandleA(NULL) + (0x873184 - 0x400000));
    if (IsBadReadPtr(iat, sizeof(void *))) return 1;
    if (*iat != (void *)ih_primero) {
        apuntar("  [isla_fx] ⚠ isla_hora dijo noche pero su gancho no está: se ve la isla de DÍA, uso los sombreadores de día");
        return 0;
    }
    return 1;
}

static int g_fx_vigia_puesto = 0;

static void isla_fx_iniciar(void)
{
    char ini[MAX_PATH], perfil[MAX_PATH], nom[MAX_PATH], hora[32];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    g_fx_activo = GetPrivateProfileIntA("isla_fx", "activo", 1, ini);   /* ★ 18-nov: de fábrica PRENDIDO (el launcher no pisa el d3d9_proxy.ini del jugador) */
    g_fx_sonda = GetPrivateProfileIntA("isla_fx", "sonda", 0, ini);
    g_fx_fps = g_fx_sonda || GetPrivateProfileIntA("isla_fx", "fps", 0, ini);       /* ★ turno 26 */
    if (!g_fx_activo && !g_fx_sonda && !g_fx_fps) {
        apuntar("  [isla_fx] APAGADO ([isla_fx] activo=0): la isla se dibuja como siempre, no se engancha nada");
        return;
    }
    for (int s = 0; s < FX_NSOMB; s++) g_fx_efecto[s] = GetPrivateProfileIntA("isla_fx", g_fx_nombre_sombra[s], 1, ini);
    g_fx_brillo = GetPrivateProfileIntA("isla_fx", "brillo", 1, ini);
    /* ★ turno 2 · la CALIDAD para PCs lentas · ★ turno 27: auto (de fábrica) / alta / media / baja (ver fx_calidad_poner) */
    {
        char cal[32];
        cal[0] = 0;
        g_fx_brillo_pedido = g_fx_brillo;
        g_fx_luces_estables = GetPrivateProfileIntA("isla_fx", "luces_estables", 1, ini);   /* ★ turno 10 */
        GetPrivateProfileStringA("isla_fx", "calidad", "auto", cal, sizeof(cal), ini);
        int nivel = 2;
        if (lstrcmpiA(cal, "baja") == 0) nivel = 0;
        else if (lstrcmpiA(cal, "media") == 0) nivel = 1;
        else if (lstrcmpiA(cal, "alta") == 0) nivel = 2;
        else {
            if (lstrcmpiA(cal, "auto") != 0) apuntar("  [isla_fx] ⚠ calidad=%s: no la conozco (auto / alta / media / baja): uso auto", cal);
            g_fx_auto = 1;
            g_fx_auto_umbral = GetPrivateProfileIntA("isla_fx", "auto_umbral", 50, ini);
            g_fx_auto_umbral_mar = GetPrivateProfileIntA("isla_fx", "auto_umbral_mar", 45, ini);
            g_fx_auto_espera = GetPrivateProfileIntA("isla_fx", "auto_espera", 5, ini);
            g_fx_auto_medir = GetPrivateProfileIntA("isla_fx", "auto_medir", 5, ini);
            if (g_fx_auto_medir < 1) g_fx_auto_medir = 1;
            lstrcpyA(g_fx_auto_archivo, g_carpeta);
            if (lstrlenA(g_fx_auto_archivo) + 20 < MAX_PATH) lstrcatA(g_fx_auto_archivo, "isla_fx_auto.txt");
            else g_fx_auto_archivo[0] = 0;
            if (g_fx_auto_archivo[0] && !GetPrivateProfileIntA("isla_fx", "auto_olvidar", 0, ini)) {
                char rc[16];
                rc[0] = 0;
                /* el archivo es «clave=valor» sin sección: se lee a mano */
                HANDLE h = CreateFileA(g_fx_auto_archivo, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
                if (h != INVALID_HANDLE_VALUE) {
                    char b[512];
                    DWORD n = 0;
                    if (ReadFile(h, b, sizeof(b) - 1, &n, NULL)) {
                        b[n] = 0;
                        for (char *q = b; *q; q++) {
                            if ((q == b || q[-1] == '\n') && q[0] == 'c' && q[1] == 'a' && q[7] == '=') {   /* calidad= */
                                int k = 0;
                                for (char *v = q + 8; *v && *v != '\r' && *v != '\n' && k < 15; v++) rc[k++] = *v;
                                rc[k] = 0;
                            }
                            if ((q == b || q[-1] == '\n') && q[0] == 'm' && q[1] == 'a' && q[2] == 'r' && q[3] == '=' && q[4] == '0')
                                g_fx_efecto[FX_MAR] = 0;
                        }
                    }
                    CloseHandle(h);
                }
                if (lstrcmpiA(rc, "media") == 0) nivel = 1;
                else if (lstrcmpiA(rc, "baja") == 0) nivel = 0;
                if (rc[0] || !g_fx_efecto[FX_MAR])
                    apuntar("  [isla_fx] calidad auto: arranco desde lo medido la otra vez (%s): %s%s", g_fx_auto_archivo,
                            g_fx_cal_nombre[nivel], g_fx_efecto[FX_MAR] ? "" : ", sin el mar con sombreador");
            }
        }
        fx_calidad_poner(nivel);
    }
    /* ★ turno 4 · el near de la isla (z-fighting): [isla_fx] cercano=100 (0 = apagado) · cercano_ojo=3000 */
    {
        char b[32];
        float x = 100.0f;
        b[0] = 0;
        GetPrivateProfileStringA("isla_fx", "cercano", "100", b, sizeof(b), ini);
        if (fx_numeros(b, &x, 1) != 1 || x < 0.0f || x > 1000.0f) {
            apuntar("  [isla_fx] ⚠ cercano=%s: tiene que ser un número de 0 a 1000: uso 100", b);
            x = 100.0f;
        }
        g_fx_cercano = x;
        b[0] = 0;
        x = 3000.0f;
        GetPrivateProfileStringA("isla_fx", "cercano_ojo", "3000", b, sizeof(b), ini);
        if (fx_numeros(b, &x, 1) != 1 || x < 0.0f) x = 3000.0f;
        g_fx_cercano_ojo = x;
    }
    {                                                                             /* ★ turno 10 */
        char b[32];
        float x = 0.5f;
        b[0] = 0;
        GetPrivateProfileStringA("isla_fx", "brillo_suave", "0.5", b, sizeof(b), ini);
        if (fx_numeros(b, &x, 1) != 1 || x < 0.0f || x > 0.9f) x = 0.5f;
        g_fx_brillo_suave = x;
    }
    {                                                                             /* ★ turno 16 */
        char es[16];
        es[0] = 0;
        GetPrivateProfileStringA("isla_fx", "mar_estilo", "a", es, sizeof(es), ini);
        g_fx_mar_estilo_b = (es[0] | 32) == 'b';
    }
    g_fx_pisar_ps = GetPrivateProfileIntA("isla_fx", "pisar_ps", 1, ini);         /* ★ turno 18 */
    g_fx_pisar_vs = GetPrivateProfileIntA("isla_fx", "pisar_vs", 3, ini);         /* ★ turno 18f: 3 = sólo mar y cielo, sin pisar sus constantes */
    g_fx_mar_deriva = GetPrivateProfileIntA("isla_fx", "mar_deriva", 1, ini);
    g_fx_falsos = GetPrivateProfileIntA("isla_fx", "colores_falsos", 0, ini);     /* ★ turno 12 */
    g_fx_zsesgo = GetPrivateProfileIntA("isla_fx", "zsesgo", 1, ini);
    g_fx_cf_color = GetPrivateProfileIntA("isla_fx", "cf_color", 1, ini);        /* ★ turno 13 */
    g_fx_cf_etapa1 = GetPrivateProfileIntA("isla_fx", "cf_etapa1", 1, ini);
    g_fx_cf_niebla = GetPrivateProfileIntA("isla_fx", "cf_niebla", 1, ini);
    GetPrivateProfileStringA("isla_fx", "cf_solo", "", g_fx_cf_solo, sizeof(g_fx_cf_solo), ini);
    GetPrivateProfileStringA("isla_fx", "cf_menos", "", g_fx_cf_menos, sizeof(g_fx_cf_menos), ini);
    if (g_fx_falsos) apuntar("  [isla_fx] COLORES FALSOS prendidos: cada textura de la isla de un color plano (la tabla"
                             " «n.º → textura» sale a medida que se dibujan); nuestros sombreadores, apagados");
    g_fx_trazar = GetPrivateProfileIntA("isla_fx", "trazar", 0, ini);              /* ★ turno 11 */
    g_fx_traza_cuadros = GetPrivateProfileIntA("isla_fx", "trazar_cuadros", 120, ini);
    if (g_fx_traza_cuadros < 1 || g_fx_traza_cuadros > 2000) g_fx_traza_cuadros = 120;
    {
        char b[64];
        float r[4];
        b[0] = 0;
        GetPrivateProfileStringA("isla_fx", "trazar_rect", "", b, sizeof(b), ini);
        if (b[0] && fx_numeros(b, r, 4) == 4) for (int i = 0; i < 4; i++) g_fx_traza_rect[i] = (int)r[i];
        b[0] = 0;
        GetPrivateProfileStringA("isla_fx", "trazar_rect2", "", b, sizeof(b), ini);    /* ★ turno 13 */
        if (b[0] && fx_numeros(b, r, 4) == 4) for (int i = 0; i < 4; i++) g_fx_traza_rect2[i] = (int)r[i];
    }
    if (g_fx_trazar) apuntar("  [isla_fx] TRAZA prendida: arranca cuando la cámara se mueva después de ≥ 1 s quieta");
    g_fx_mips = GetPrivateProfileIntA("isla_fx", "mips", 1, ini);                 /* ★ turno 9 */
    g_fx_aniso = GetPrivateProfileIntA("isla_fx", "aniso", 4, ini);
    if (g_fx_aniso < 1) g_fx_aniso = 1;
    if (g_fx_aniso > 16) g_fx_aniso = 16;
    g_fx_camp = GetPrivateProfileIntA("isla_fx", "campanillas", 1, ini);
    g_fx_camp_espera = GetPrivateProfileIntA("isla_fx", "campanillas_espera_ms", 0, ini);
    {
        char b[96];
        float o[4];
        b[0] = 0;
        GetPrivateProfileStringA("isla_fx", "campanillas_ojo", "", b, sizeof(b), ini);
        if (b[0] && fx_numeros(b, o, 4) == 4) for (int i = 0; i < 4; i++) g_fx_camp_ojo[i] = o[i];
        else if (b[0]) apuntar("  [isla_fx] ⚠ campanillas_ojo=%s: hacen falta x, y, z, radio: uso la del lobby", b);
    }
    if (g_fx_camp_espera < 0 || g_fx_camp_espera > 20000) g_fx_camp_espera = 0;
    hora[0] = 0;
    GetPrivateProfileStringA("isla_fx", "hora", "", hora, sizeof(hora), ini);
    int forzado = ih_forzado(hora);
    g_fx_noche = forzado == 1 ? 0 : forzado == 2 ? 1 : fx_es_de_noche();
    nom[0] = 0;
    GetPrivateProfileStringA("isla_fx", "perfil", "isla_fx.ini", nom, sizeof(nom), ini);
    if (nom[0] && (nom[1] == ':' || nom[0] == '\\' || nom[0] == '/')) lstrcpynA(perfil, nom, MAX_PATH);
    else { lstrcpyA(perfil, g_carpeta); if (lstrlenA(perfil) + lstrlenA(nom) < MAX_PATH) lstrcatA(perfil, nom); }
    g_fx_perfil_ok = fx_leer_perfil(perfil, g_fx_noche, &g_fx_p);
    if (!g_fx_perfil_ok) {
        apuntar("  [isla_fx] ⚠ sin perfil (%s): %s", perfil, g_fx_sonda ? "sólo la sonda (anota las texturas que carga)"
                                                                       : "la capa 4 NO se prende");
        if (!g_fx_sonda && !g_fx_fps) return;
        g_fx_activo = 0;
    } else {
        apuntar("  [isla_fx] perfil %s: %d texturas, %d luces%s, %s · brillo %s%s",
                perfil, g_fx_p.ntex, g_fx_p.nluces,
                g_fx_p.luces_de_mas ? " (sobran algunas: el perfil lleva 64)" : "", g_fx_noche ? "NOCHE" : "DÍA",
                g_fx_p.brillo_activo && g_fx_brillo ? "sí" : "no", g_fx_p.errores ? " · ⚠ con líneas mal escritas (ver arriba)" : "");
        /* ★ turno 28: el mar de 64 (calidad alta) lee 56 lugares de luces (para entrar en 4096 casillas en NVIDIA nativo) */
        if (g_fx_p.nluces > 56)
            apuntar("  [isla_fx] ⚠ el perfil trae %d luces: el MAR de calidad alta refleja sólo las 56 que más se ven"
                    " (FX_LUCES_USADAS de ps_mar_64)", g_fx_p.nluces);
    }
    apuntar("  [isla_fx] %s%s · calidad %s%s (%d luces por píxel%s) · near de la isla %d%s", g_fx_activo ? "ACTIVO" : "",
            g_fx_sonda ? (g_fx_activo ? " + SONDA" : "SONDA (sólo anota)") : "",
            g_fx_cal_nombre[g_fx_calidad], g_fx_auto ? (g_fx_auto_archivo[0] ? " (AUTO: mide a los pocos segundos de ver la isla)" : " (AUTO)") : "",
            g_fx_nluz, g_fx_brillo ? "" : ", sin brillo",
            (int)g_fx_cercano, g_fx_cercano > 0.0f ? "" : " (apagado: queda el del juego)");
    if (g_fx_activo) fx_ocultar_leer(ini);                     /* ★ 21-nov: antes de que se carguen las texturas */
    if (!fx_enganchar_carga()) { g_fx_activo = 0; g_fx_sonda = 0; return; }
    /* ★ turno 5 · las campanillas: la textura del trineo tiene que estar en el perfil (si no, no se sabe cuándo aparece) */
    if (g_fx_camp && g_fx_activo && g_fx_perfil_ok) {
        char tx[FX_LARGO_NOM * 2], base[FX_LARGO_NOM];
        GetPrivateProfileStringA("isla_fx", "campanillas_textura", "nocull_xm_trineo_cuerpo", tx, sizeof(tx), ini);
        fx_nombre_base(tx, base, sizeof(base));
        g_fx_camp_idx = fx_perfil_buscar(&g_fx_p, base);
        if (g_fx_camp_idx < 0) apuntar("  [isla_fx] ⚠ campanillas: «%s» no está en el perfil: mudas", base);
        else if ((g_fx_camp_ev = CreateEventA(NULL, FALSE, FALSE, NULL)) != NULL) {
            g_fx_cs.hay_gancho = fx_enganchar_ani();
            HANDLE hc = CreateThread(NULL, 0, fx_campanillas, NULL, 0, NULL);
            if (hc) { CloseHandle(hc); apuntar("  [isla_fx] campanillas: suenan cuando aparece «%s» (espera %d ms)", base, g_fx_camp_espera); }
            else { CloseHandle(g_fx_camp_ev); g_fx_camp_ev = NULL; }
        }
    }
    {   HANDLE hr = CreateThread(NULL, 0, fx_vigia_rapido, NULL, 0, NULL);      /* ★ 21-nov */
        if (hr) CloseHandle(hr); }
    HANDLE h = CreateThread(NULL, 0, fx_vigilar, NULL, 0, NULL);
    if (h) { CloseHandle(h); g_fx_vigia_puesto = 1; }
    else apuntar("  [isla_fx] ⚠ no pude crear el vigía: no se engancha el dibujo");
}
