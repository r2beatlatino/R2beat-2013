/*
 * d3d9_proxy.c — nuestras mejoras, permanentes, sin Frida y sin instalar nada.
 *
 * ★★★ POR QUE ESTO  (20-sep-2026)
 *   Todo lo que conseguimos en tres dias vive hoy en guiones de Frida: se evapora al
 *   cerrar la consola y no le sirve a ningun jugador. Y la restriccion de anonimo03 manda:
 *   *"los usuarios tienen pc modesta"* y *"sin pedirles instalar nada"*.
 *
 *   Windows carga el `d3d9.dll` que esta JUNTO AL EXE antes que el de System32. O sea
 *   que alcanza con dejar este archivo al lado del cliente: no hay instalador, no hay
 *   registro, no hay dependencias. Y es el MISMO mecanismo que ya usa DXVK en este
 *   proyecto (`d3d9.dxvk` -> `d3d9.dll`), asi que el launcher ya sabe ponerlo y sacarlo.
 *
 * ★★ Y ES CHICO PORQUE EL EXE PIDE UNA SOLA FUNCION
 *   Medido en la tabla de importaciones del cliente:  d3d9.dll -> Direct3DCreate9. Una.
 *   ⇒ No hay que reimplementar Direct3D: se exporta esa, se carga el d3d9 de verdad, y
 *     se le cambia UN puntero a la tabla de metodos para mirar `CreateDevice` al pasar.
 *
 * ★ QUE HACE HOY
 *   · pone MultiSampleType = 8x  (el antialiasing, lo unico que el ojo de anonimo03 nota)
 *   · saca LOCKABLE_BACKBUFFER y deja SwapEffect = DISCARD, que es lo que el MSAA exige
 *   ⚠ Si con eso `CreateDevice` falla, REINTENTA con los parametros originales. Nunca
 *     deja al jugador sin juego: hoy mismo vimos al cliente morir al arrancar por pedir
 *     MSAA en una ruta que no lo admitia.
 *
 * ⛔ LO QUE NO HACE TODAVIA (y donde iria)
 *   · el alt+enter propio, que reemplazaria al shim `DWM8And16BitMitigation`
 *   · la espera precisa, si la medicion de los cuatro modos dice que hace falta
 *   · el Sleep del gate y la siesta del foco -> esos son DOS BYTES del exe, mas simple
 *
 * Se compila con:   construir.bat      (usa Zig, que no instala nada)
 */

/* ═══════════════════════════════════════════════════════════════════════════
 *  d3d9_proxy — proxy de Direct3D 9 para el cliente R2Beat 2013
 *  Copyright (c) 2026 anonimo03  (proyecto R2Beat 2013 — servidor privado).
 *  ⚠ El autor prefiere no figurar con su nombre: usar SIEMPRE el seudonimo.
 *
 *  ⛔ TODOS LOS DERECHOS RESERVADOS. Este binario y su fuente NO son de dominio
 *     publico y NO se licencian para redistribucion, reutilizacion ni obra
 *     derivada. Se distribuye UNICAMENTE como parte del cliente de este servidor.
 *
 *  ⚠ El juego es gratis y el cliente se puede bajar libremente; **esta DLL no es
 *    parte del juego original**: es trabajo propio, de meses, y se comparte para
 *    jugar, no para copiar.
 *
 *  Para reutilizarlo, pedi permiso. Normalmente la respuesta es que si.
 * ═══════════════════════════════════════════════════════════════════════════ */

#include <windows.h>
#include <stdarg.h>

/* ── el layout de D3DPRESENT_PARAMETERS, a mano ───────────────────────────
 * Se escribe aca en vez de incluir <d3d9.h> para no arrastrar el SDK entero.
 * Los offsets estan verificados contra lo que mide `solo_createdevice.js`, que lee
 * esta misma estructura desde Frida y da valores coherentes con el juego. */
typedef struct {
    UINT  BackBufferWidth;          /* 0x00 */
    UINT  BackBufferHeight;         /* 0x04 */
    UINT  BackBufferFormat;         /* 0x08 */
    UINT  BackBufferCount;          /* 0x0C */
    UINT  MultiSampleType;          /* 0x10 */
    DWORD MultiSampleQuality;       /* 0x14 */
    UINT  SwapEffect;               /* 0x18 */
    HWND  hDeviceWindow;            /* 0x1C */
    BOOL  Windowed;                 /* 0x20 */
    BOOL  EnableAutoDepthStencil;   /* 0x24 */
    UINT  AutoDepthStencilFormat;   /* 0x28 */
    DWORD Flags;                    /* 0x2C */
    UINT  FullScreen_RefreshRateInHz;/* 0x30 */
    UINT  PresentationInterval;     /* 0x34 */
} PRESENT_PARAMS;

#define SWAP_DISCARD            1
#define FLAG_LOCKABLE_BACKBUFFER 1

/* ── ajustes, leidos de `d3d9_proxy.ini` al lado de la dll ───────────────── */

/* ⚠ Esta cadena existe para que quede DENTRO del .dll: un comentario del fuente no
 *   viaja al binario, y la nota de autoria solo sirve si esta donde se la encuentra.
 *   `volatile` + `used` para que el optimizador no la borre por no usarse. */
__attribute__((used)) static volatile const char AUTORIA[] =
    "d3d9_proxy para R2Beat 2013 - (c) 2026 anonimo03 - TODOS LOS DERECHOS RESERVADOS. "
    "No se licencia para redistribucion ni obra derivada. "
    "Trabajo propio de meses: si lo queres reutilizar, pedi permiso.";

static int g_msaa = 8;          /* 0 = no tocar nada */
static int g_activo = 1;
static int g_altenter = 1;      /* ★ nuestro alt+enter, el que reemplaza al shim */
static int g_log = 1;           /* deja `d3d9_proxy.log` al lado de la dll */
static int g_titulo = 1;        /* escribe en el titulo de la ventana que estamos cargados */

/* ═══════════════════════════════════════════════════════════════════════════
 * ★★★ LA PARTE MODERNA DE DIRECT3D 9 — «la ruta de Paladins»  (20-sep-2026)
 *
 *   Lo pidio anonimo03 asi: *«sigamos la ruta de paladins, de lograr hacer que nuestro
 *   juego soporte la parte moderna de direct9»*.
 *
 * ⚠ EL NOMBRE QUE CONFUNDE: `d3d9x` (D3DX9) **no es esto**. Esa es la libreria de
 *   utilidades —matematicas, cargar texturas, sprites, fuentes— y no toca la
 *   presentacion. La parte moderna se llama **Direct3D 9Ex** (Windows Vista, 2006),
 *   y es la unica que tiene `D3DSWAPEFFECT_FLIPEX`: el modo que saca al compositor
 *   de Windows del medio. En D3D9 clasico ese camino NO EXISTE — ningun valor,
 *   ninguna bandera, ninguna edicion del exe lo consigue.
 *
 * ★ POR QUE IMPORTA, medido el 20-sep con PresentMon:
 *       jugando en ventana -> `Composed: Copy with GPU GDI`  (100 %, 2041 imagenes)
 *   O sea que cada cuadro se lo entregamos al COMPOSITOR, y el compositor corre al
 *   ritmo del monitor PRINCIPAL. Por eso jugar en un monitor con otro Hz mete un lag
 *   que va y viene solo (el «caso 1»).
 *
 * ⛔ Y POR QUE VA APAGADO POR DEFECTO: ya se intento una vez y el cliente **moria a
 *   los tres cuadros**, sin pasar por ExitProcess. Se abandono tras cuatro intentos
 *   «por una via cuyo beneficio ni siquiera llegamos a medir» (EL_PROXY_D3D9.md §5.1).
 *   ⇒ Con `d3d9ex=0` esta DLL se comporta EXACTAMENTE como hasta hoy. Nada cambia
 *     para ningun jugador hasta que la medicion diga que conviene.
 *
 * ★★ LA HIPOTESIS DE POR QUE MURIO, y como se comprueba sin adivinar:
 *   En D3D9Ex **`D3DPOOL_MANAGED` no existe**: toda `CreateTexture` /
 *   `CreateVertexBuffer` / `CreateIndexBuffer` que lo pida devuelve `INVALIDCALL`.
 *   Un motor de 2013 usa MANAGED en todos lados; si no mira el codigo de error se
 *   queda con punteros nulos y se muere calladito — que es EXACTAMENTE el sintoma.
 *
 *   ⇒ `pool=0` NO arregla nada: solo CUENTA cuantas fallan y de que tipo.
 *      Esa corrida contesta si la hipotesis es cierta.
 *   ⇒ `pool=1` traduce MANAGED -> DEFAULT al pasar. Ese es el intento de arreglo.
 *   ★ Primero se mide, despues se arregla. Es la regla que este proyecto ya pago.
 * ═══════════════════════════════════════════════════════════════════════════ */
static int g_d3d9ex = 0;        /* 0 = D3D9 de toda la vida (lo de hoy) · 1 = 9Ex */
static int g_flipex = 0;        /* 1 = ademas pedir FLIPEX (necesita d3d9ex=1) */
static int g_pool   = 0;        /* 0 = solo contar los MANAGED · 1 = traducir a DEFAULT */

/* ═══ ★★★ EL PLANO DE HARDWARE (MPO)  ·  20-sep-2026, noche ═══════════════
 *
 * ⛔ LO QUE HABIA ESCRITO MAL, y esto lo corrige:
 *   El 20-sep a la tarde anote *"Independent Flip exige que la ventana cubra el
 *   monitor; en ventana chica no hay forma"*. **Esta mal dicho**, y la diferencia
 *   esta en el nombre que devuelve PresentMon:
 *
 *       "Hardware: Independent Flip"            <- ESE si exige cubrir la pantalla
 *       "Hardware Composed: Independent Flip"   <- ★ ESTE es MPO, y NO lo exige
 *
 *   **MPO (Multi-Plane Overlay)** es que el controlador de video le da a nuestra
 *   ventana un PLANO DE HARDWARE propio, otro al escritorio, y los mezcla el chip
 *   al escanear la imagen hacia el cable. DWM no toca los pixeles. Y se invento
 *   justo para el caso de anonimo03: **ventana chica, escritorio visible alrededor**.
 *
 * ⇒ O sea que en aquella corrida no es que DWM lo prohibiera: **no nos lo
 *   concedieron**, y hay motivos concretos y enumerables por los que se niega.
 *   ⚠ Y aquella corrida tenia los monitores a 165 y 60 Hz — mezclar refrescos es
 *   uno de los apagadores conocidos de MPO. O sea que **midio adentro de la
 *   condicion rota**, que es exactamente la leccion de `optimizar sobre un banco
 *   roto`. Por eso se vuelve a medir con todo limpio antes de creerle al negativo.
 *
 * ★ DE LOS APAGADORES, DOS SE ARREGLAN DESDE ACA:
 *
 *   1 · LAS ESQUINAS REDONDEADAS DE WINDOWS 11.  Un plano de hardware es un
 *       RECTANGULO. Para redondearle las esquinas a la ventana, DWM tiene que
 *       aplicarle una MASCARA — y una ventana enmascarada no entra en un plano.
 *       ⇒ `DwmSetWindowAttribute(DWMWA_WINDOW_CORNER_PREFERENCE, DONOTROUND)`.
 *
 *   2 · `WS_EX_LAYERED`.  Una ventana "en capas" se compone por definicion: Windows
 *       tiene que mezclarla con lo de atras. `camino.py` ya la marcaba como
 *       "★ EN CAPAS (obliga a componer)". Si esta puesta, se saca.
 *
 *   (Los otros tres son del entorno y los tiene que hacer anonimo03: los dos monitores
 *    al MISMO Hz, cerrar los overlays, y el escalado en 100 %. Los verifica
 *    `antes_de_medir.py`, que se corre ANTES de abrir el juego.)
 *
 * ⚠⚠ ESTO NO GARANTIZA NADA, y hay que decirlo: la placa decide. Lo unico que
 *   hacemos es sacarle los motivos para decir que no. Si aun asi sale
 *   "Composed: Flip" con todo limpio, ahi si es el techo — pero recien ahi.
 * ═══════════════════════════════════════════════════════════════════════════ */
static int g_esquinas = 1;      /* 1 = pedir esquinas SIN redondear (Win 11)      */
static int g_sincapas = 1;      /* 1 = sacar WS_EX_LAYERED si el juego lo tiene   */

/* ═══ ★★★ LAS METRICAS EN PANTALLA  ·  20-sep-2026 ═══════════════════════════
 *
 *   anonimo03: *"dxvk da metricas, nuestro d3d9 no da ni un aviso de fps"*. Y tiene
 *   razon: sin numero, comparar los dos modos era a ojo — que en este proyecto ya
 *   engaño tres veces en un dia.
 *
 * ★★★ COMO SE DIBUJA SIN FUENTES NI SHADERS, que es lo que lo hace barato
 *
 *   `IDirect3DDevice9::Clear` acepta **una lista de rectangulos** y los pinta de un
 *   color. O sea que es un "rellenar rectangulos" que YA esta en la interfaz.
 *   ⇒ Un digito de 7 segmentos son 7 rectangulos. Tres digitos y el grafico de
 *     barras entran en DOS llamadas a `Clear`. Sin vertices, sin shaders, sin
 *     texturas, sin `ID3DXFont` (que ademas nos ataria a la D3DX9 de Microsoft).
 *
 * ★ Y se dibuja en `EndScene`, no en `Present`:
 *   `Clear` tiene que pasar DENTRO de un Begin/EndScene. Enganchando EndScene
 *   estamos garantizado adentro, y ademas es lo ultimo que pasa antes de mostrar:
 *   lo nuestro queda ENCIMA de todo lo del juego.
 *
 * ⚠ NO CAMBIA NINGUN ESTADO del dispositivo: `Clear` no toca matrices, ni texturas,
 *   ni render states. Es la unica forma de dibujar que no puede dejarle al juego el
 *   estado cambiado — que es como se rompen los overlays caseros.
 *
 * ⚠ Respeta el VIEWPORT actual: si el juego lo dejo raro, el cartel se corre. Es el
 *   precio de no tocar estado, y se prefiere eso a un overlay que rompa el dibujo.
 * ═══════════════════════════════════════════════════════════════════════════ */
static int g_metricas = 0;      /* 0 = apagado (⚠ dibuja encima del juego)        */
static int g_met_escala = 3;    /* tamaño de los digitos                          */
static int g_met_grafico = 1;   /* 1 = ademas el grafico de tiempos de cuadro     */
/* ★★★ LA PRUEBA DE LAS CINCO ESQUINAS  (20-sep-2026, idea de anonimo03)
 *   *"quiza estas poniendo el medidor detras de una escena; ¿no podes poner 3 o 4 en
 *   distintas zonas y ver si alguno sobrevive?"*.
 *   ⇒ Mucho mejor que lo que yo iba a hacer (pintar todo de magenta para ver si
 *     llegaba): ademas de decir SI llega, dice DONDE — que es la mitad util.
 *   Cada zona con su color, para poder nombrarla sin ambiguedad. */
static int g_met_prueba = 0;

/* ═══ ★★★ EL MOTOR, DESDE LA DLL  ·  20-sep-2026 ═══════════════════════════
 *
 *   Hasta hoy estas piezas las ponia **Frida**, que un jugador no tiene. Van aca
 *   porque esta dll carga ANTES del bucle del juego y puede escribir su `.text`.
 *   ⇒ Sin tocar el `.exe`, sin cueva en el binario, y se revierte borrando la dll.
 *
 * ⚠ LO QUE SE MIDIO Y MANDA EL DISEÑO  (20-sep-2026, monitor a 60 Hz, en el intro):
 *
 *                         vueltas/s   PASOS/s
 *       de fabrica         118-120      60     ✔
 *       + el decouple       60          51     ⛔  -15 %
 *
 *   El motor fabrica pasos POR VUELTA del bucle, no por tiempo. Soltar el gate del
 *   dibujo ata el bucle al vsync ⇒ a 60 Hz quedan 60 vueltas y **no le alcanzan para
 *   sus 60 pasos**. A 120/165 sobra. ⇒ Por debajo de `hzminimo` el decouple NO se
 *   aplica: ahi no aporta nada y frena el mundo.
 */
/* ═══ ★★★ LOS VALORES DE FABRICA SON **LA RECETA**  ·  20-sep-2026 ═════════
 *
 *   Antes venian todos apagados, y el motivo era bueno: con el decouple a 60 Hz el
 *   intro iba lento. **Ese motivo ya no existe** — lo resuelve `hzminimo`.
 *
 * ⛔ Y dejarlos apagados tenia un problema peor: el CDN **no gestiona
 *   `d3d9_proxy.ini`** (es del usuario: si lo edita, el MD5 deja de coincidir y el
 *   updater se lo borraba). ⇒ Un jugador sin ini —o que lo borro— **no recibiria
 *   ninguna mejora, y el juego andaria igual de bien que antes**. Nadie se enteraria.
 *   Es justo el tipo de fallo que se queda meses.
 *
 * ★ Ahora: **sin ini, la receta entra igual**. El ini queda para AJUSTAR, no para
 *   habilitar. Y las protecciones viven en el codigo, no en el archivo:
 *       · el decouple no se aplica por debajo de `hzminimo`
 *       · el `sleep` no baja de 16 si la espera precisa esta apagada
 *       · cada escritura al `.text` tiene guarda: si no esta lo esperado, no toca nada
 *
 * ⚠ La vuelta atras para un jugador es una linea: `[video] activo=0`.
 */
static int g_sleep_ms  = 1;      /* ★ la receta. 16 = de fabrica del juego       */
static int g_nucleo_libre = 1;   /* ★ 14-oct: el hilo principal SIN clavar al nucleo 0 */
static int g_flu_fondo60 = 1;    /* ★ 14-oct: la ventana de fondo dibuja a 60 (la del frente, fluidez) */
static int g_siesta_ms = 0;      /* ★ al perder el foco. 1000 = de fabrica. 13-oct: 20 -> 0 (anonimo03: «al perder el foco el juego se re-alentiza y afecta el gameplay»: duerme DOS veces por vuelta = 40 ms = ~25 vueltas/s). 0 = 1 ms (mi_sleep), y la espera precisa ya frena al próximo paso */
static int g_hzminimo  = 61;     /* debajo de esto, el decouple no se aplica     */
static int g_gate      = 1;      /* ★ soltar el dibujo. Solo si supera hzminimo   */
static int g_mundo     = 1;      /* el update-gate viejo (si `fluidez` no entra)  */
static int g_fluidez   = 1;      /* ★★ 03-oct: la carrera a X Hz. Ver fluidez.c   */
static void *g_cueva   = NULL;   /* la memoria del update-gate, nuestra           */
static int g_ritmo     = 1;      /* ★ la espera precisa. De ella depende el sleep  */
static int g_giro_cfg  = 15;     /* decimas de ms del tramo a mano (15 = 1,5 ms)   */
static UINT g_ancho = 0, g_alto = 0;   /* del backbuffer, para no dibujar afuera  */
static void cielo_ajustar(UINT ancho, UINT alto);   /* cielo_ancho.c: el cielo de las pistas a la medida de la pantalla */

/* ── ★ DECIR QUE ESTAMOS ACA  (20-sep-2026, pedido de anonimo03) ──────────────
 *
 * ⚠ POR QUE HACIA FALTA: hasta hoy esta DLL no dejaba NINGUN rastro. Si el juego
 *   abria bien, no habia forma de saber si el `d3d9.dll` que se cargo era el
 *   nuestro, el de DXVK o el de Windows — y con tres motores que se turnan el
 *   mismo nombre de archivo, eso es justo lo que hay que poder mirar.
 *
 * Dos rastros, a proposito:
 *   · el LOG (`d3d9_proxy.log`) queda para revisar despues — es el equivalente al
 *     `<exe>_d3d9.log` que ya deja DXVK en esta misma carpeta;
 *   · el TITULO de la ventana se ve AL INSTANTE, sin abrir nada.
 *
 * ⚠ Se escribe con APIs de Windows (`wsprintfA`, `WriteFile`) y no con la libreria
 *   de C: esta DLL se carga en el arranque mismo del proceso y no conviene depender
 *   de nada que todavia no este inicializado.
 */
static char g_carpeta[MAX_PATH] = {0};   /* donde vive la dll (y el ini, y el log) */
static int  g_hay_ini = 0;               /* si habia ini o son los valores de fabrica */

static void apuntar(const char *formato, ...)
{
    if (!g_log || !g_carpeta[0]) return;

    char linea[512];
    va_list args;
    va_start(args, formato);
    int n = wvsprintfA(linea, formato, args);
    va_end(args);
    if (n <= 0) return;
    linea[n] = '\r';
    linea[n + 1] = '\n';

    char ruta[MAX_PATH];
    lstrcpyA(ruta, g_carpeta);
    lstrcatA(ruta, "d3d9_proxy.log");

    /* ★ 31-oct: con VARIOS juegos en la misma carpeta (el lanzador múltiple) el log es de todos. Abierto sin
     * FILE_SHARE_WRITE, el que escribía al mismo tiempo que otro recibía «violación de uso compartido» y su línea SE
     * PERDÍA en silencio: en la carrera de 6, cada cliente dejó 1 a 3 de sus 6 poses. FILE_APPEND_DATA solo agrega al
     * final (atómico por WriteFile), así que compartir la escritura no mezcla líneas; y si igual choca, reintenta. */
    HANDLE h = INVALID_HANDLE_VALUE;
    for (int i = 0; i < 10 && h == INVALID_HANDLE_VALUE; i++) {
        h = CreateFileA(ruta, FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL,
                        OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
        if (h == INVALID_HANDLE_VALUE && GetLastError() != ERROR_SHARING_VIOLATION) break;
        if (h == INVALID_HANDLE_VALUE) Sleep(1);
    }
    if (h == INVALID_HANDLE_VALUE) return;
    DWORD escritos = 0;
    WriteFile(h, linea, (DWORD)(n + 2), &escritos, NULL);
    CloseHandle(h);
}

/* Cada arranque empieza su propio log: si no, crece para siempre y no se sabe que
 * lineas son de la corrida de recien. ★ 16-oct: el de la vez anterior NO se pisa — pasa a d3d9_proxy.anterior.log, y
 * lo que anotó la caja negra se le manda al server al llegar al lobby (cajanegra.c). */
static void cn_leer_anterior(const char *ruta);
static void cn_enviar_pendiente(void);
static void empezar_log(void)
{
    if (!g_log || !g_carpeta[0]) return;
    char ruta[MAX_PATH];
    lstrcpyA(ruta, g_carpeta);
    lstrcatA(ruta, "d3d9_proxy.log");
    cn_leer_anterior(ruta);
    HANDLE h = CreateFileA(ruta, GENERIC_WRITE, FILE_SHARE_READ, NULL,
                           CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h != INVALID_HANDLE_VALUE) CloseHandle(h);
}

/* El titulo dice que motor de video esta cargado. Se vuelve a poner en cada Reset
 * porque el juego reescribe el suyo cuando rehace la pantalla. */
static void marcar_titulo(HWND h)
{
    if (!g_titulo || !h) return;
    char titulo[256];
    char actual[160];
    if (!GetWindowTextA(h, actual, sizeof(actual))) actual[0] = 0;
    /* si ya lo marcamos, no volver a agregar la marca */
    if (actual[0] && lstrlenA(actual) > 8) {
        const char *p = actual;
        while (*p) {
            if (p[0] == '[' && p[1] == 'p' && p[2] == 'r' && p[3] == 'o') return;
            p++;
        }
    }
    if (g_msaa > 0)
        wsprintfA(titulo, "%s   [proxy R2B - MSAA %dx]", actual, g_msaa);
    else
        wsprintfA(titulo, "%s   [proxy R2B]", actual);
    SetWindowTextA(h, titulo);
}

/* ── ★★★ SACARLE A LA VENTANA LOS MOTIVOS PARA QUE LE NIEGUEN EL PLANO ────
 *
 * Se llama en cada `CreateDevice` y en cada `Reset`, porque el juego rehace la
 * ventana y Windows vuelve a redondearle las esquinas.
 *
 * ⚠ `dwmapi.dll` se carga a mano y no se enlaza: asi esta DLL sigue abriendo en
 *   un Windows donde no exista o donde el atributo no se entienda (en Win 10 el
 *   33 no existe y `DwmSetWindowAttribute` devuelve error — que se ignora, no se
 *   redondeaba nada de entrada).  */
#define ATRIB_ESQUINAS   33     /* DWMWA_WINDOW_CORNER_PREFERENCE (Win 11) */
#define ESQUINAS_RECTAS   1     /* DWMWCP_DONOTROUND                       */
#ifndef WS_EX_LAYERED
#define WS_EX_LAYERED 0x00080000L
#endif

typedef HRESULT (WINAPI *PONER_ATRIBUTO)(HWND, DWORD, const void *, DWORD);

static void preparar_para_plano(HWND h)
{
    if (!h || !IsWindow(h)) return;

    if (g_esquinas) {
        static PONER_ATRIBUTO poner = NULL;
        static int buscado = 0;
        if (!buscado) {
            buscado = 1;
            HMODULE m = LoadLibraryA("dwmapi.dll");
            if (m) poner = (PONER_ATRIBUTO)GetProcAddress(m, "DwmSetWindowAttribute");
            if (!poner) apuntar("  [plano] no hay DwmSetWindowAttribute: esquinas sin tocar");
        }
        if (poner) {
            DWORD v = ESQUINAS_RECTAS;
            HRESULT hr = poner(h, ATRIB_ESQUINAS, &v, sizeof(v));
            apuntar("  [plano] esquinas SIN redondear -> %s (hr=0x%x)",
                    hr == 0 ? "ok" : "no aplico (Win 10 no tiene el atributo)",
                    (unsigned)hr);
        }
    }

    LONG ex = GetWindowLongA(h, GWL_EXSTYLE);
    if (ex & WS_EX_LAYERED) {
        if (g_sincapas) {
            SetWindowLongA(h, GWL_EXSTYLE, ex & ~WS_EX_LAYERED);
            apuntar("  [plano] ⚠ la ventana estaba EN CAPAS (WS_EX_LAYERED): se la saque,"
                    " en capas nunca entra en un plano");
        } else {
            apuntar("  [plano] ⚠ la ventana esta EN CAPAS y sincapas=0: eso solo ya niega"
                    " el plano");
        }
    } else {
        apuntar("  [plano] exstyle 0x%x — no esta en capas ✔", (unsigned)ex);
    }
}

/* ── ★★★ EL ALT+ENTER PROPIO ─────────────────────────────────────────────
 * ⚠ POR QUE HACE FALTA ESTO, que es lo que lo justifica todo:
 *   El alt+enter del cliente sólo llena la pantalla si Windows le tiene puesto el shim
 *   `DWM8And16BitMitigation` (A/B medido el 11-sep). Pero el 20-sep se midió que **ese
 *   shim y el antialiasing 8x son incompatibles**: con los dos, `CreateDevice` falla y
 *   el juego muere al arrancar. Y anonimo03 puso las dos condiciones:
 *       *"el alt+enter no puede dejar de funcionar"*
 *       y el MSAA es lo unico que su ojo distingue.
 *   ⇒ Con el shim no se pueden tener las dos. Haciendolo nosotros, si.
 *
 * ★ Y ADEMAS QUEDA MEJOR QUE EL ORIGINAL
 *   El alt+enter de Direct3D va a pantalla completa EXCLUSIVA, que anonimo03 descarto
 *   (*"la mayoria de usuarios no usamos el juego en modo pantalla completa"*) y que
 *   ademas cambia el modo de video, tarda, y se pierde el dispositivo al salir.
 *   Esto estira la VENTANA al monitor donde esta: se ve igual de grande, el alt+tab es
 *   instantaneo y no hay cambio de modo.
 *
 * ⚠ Se atiende el mensaje y NO se lo pasa a Direct3D, para que no haga su cambio por
 *   su cuenta. Y se engancha DESPUES de que D3D9 preparo la ventana, asi el nuestro
 *   queda por encima del suyo.
 */
static WNDPROC g_wndproc_viejo = NULL;
static HWND    g_ventana = NULL;
static int     g_estirada = 0;
static LONG    g_estilo_previo = 0;
static LONG    g_estiloex_previo = 0;
static RECT    g_rect_previo;

/* ★★★ LO QUE MIDIÓ EL ESPÍA DEL `Reset`  (20-sep-2026, con anonimo03 apretando alt+enter)
 *
 *   RESET pedido:  1024x768  formato 22  banderas 1  enVentana TRUE  -> INVALIDCALL
 *   RESET pedido:  1024x768  formato 23  banderas 1  enVentana TRUE  -> ok
 *
 *   ⇒ DOS COSAS, las dos importantes:
 *
 *   1 · **El juego NUNCA pide pantalla completa.** En cada alt+enter rehace la pantalla
 *       pero sigue diciendo `enVentana = TRUE`: sólo se reposiciona, y por eso "la
 *       ventana se va a una esquina". El shim no arreglaba esto — le cambiaba a Windows
 *       la forma de tratar la ventana y de rebote quedaba llenando la pantalla.
 *
 *   2 · **`banderas = 1` es LOCKABLE_BACKBUFFER y `multisample = 0`.** O sea que en cada
 *       `Reset` el juego vuelve a pedir sus valores de fábrica y **borra el antialiasing
 *       que le pusimos al arrancar**. La mejora duraba hasta el primer cambio de pantalla.
 *
 *   ⇒ Las dos se arreglan en el mismo sitio: mirando también el `Reset`, no sólo la
 *     creación del dispositivo.
 */
typedef HRESULT (WINAPI *RESETEAR)(void *, PRESENT_PARAMS *);
static RESETEAR g_reset_real = NULL;
static int      g_quiere_pantalla_completa = 0;

/* ── ¿ese modo de video existe en el monitor donde está la ventana? ─────── */
static int modo_existe(HWND h, UINT an, UINT al)
{
    MONITORINFOEXA mi;
    mi.cbSize = sizeof(mi);
    if (!GetMonitorInfoA(MonitorFromWindow(h, MONITOR_DEFAULTTONEAREST),
                         (MONITORINFO *)&mi)) return 0;
    DEVMODEA dm;
    for (DWORD i = 0; ; i++) {
        ZeroMemory(&dm, sizeof(dm));
        dm.dmSize = sizeof(dm);
        if (!EnumDisplaySettingsA(mi.szDevice, i, &dm)) break;
        if (dm.dmPelsWidth == an && dm.dmPelsHeight == al && dm.dmBitsPerPel == 32)
            return 1;
    }
    return 0;
}

/* ── el modo que el escritorio tiene puesto AHORA en ese monitor ─────────── */
static void modo_actual(HWND h, UINT *an, UINT *al)
{
    MONITORINFOEXA mi;
    mi.cbSize = sizeof(mi);
    if (!GetMonitorInfoA(MonitorFromWindow(h, MONITOR_DEFAULTTONEAREST),
                         (MONITORINFO *)&mi)) return;
    DEVMODEA dm;
    ZeroMemory(&dm, sizeof(dm));
    dm.dmSize = sizeof(dm);
    if (EnumDisplaySettingsA(mi.szDevice, ENUM_CURRENT_SETTINGS, &dm)) {
        *an = dm.dmPelsWidth;
        *al = dm.dmPelsHeight;
    }
}

/* ── ★ nuestro Reset: rehace la pantalla SIN perder lo nuestro ──────────── */
static HRESULT WINAPI mi_reset(void *dev, PRESENT_PARAMS *pp)
{
    if (!g_activo || !pp) return g_reset_real(dev, pp);

    PRESENT_PARAMS copia = *pp;        /* ★ para poder volver atrás */

    if (g_msaa > 0) {
        pp->MultiSampleType    = (UINT)g_msaa;
        pp->MultiSampleQuality = 0;
        pp->SwapEffect         = SWAP_DISCARD;
        pp->Flags             &= ~FLAG_LOCKABLE_BACKBUFFER;
    }

    if (g_altenter && g_quiere_pantalla_completa && g_ventana) {
        /* ⚠ un modo que NO EXISTE hace fallar el Reset. Si el tamaño del juego no está
         *   entre los modos del monitor —1024x768 no existe en una pantalla vertical de
         *   1080x1920, por ejemplo— se usa el que el escritorio tiene puesto. */
        UINT an = pp->BackBufferWidth, al = pp->BackBufferHeight;
        if (!modo_existe(g_ventana, an, al)) modo_actual(g_ventana, &an, &al);
        pp->BackBufferWidth  = an;
        pp->BackBufferHeight = al;
        pp->Windowed = FALSE;
        pp->FullScreen_RefreshRateInHz = 0;   /* 0 = el que el monitor prefiera */
        if (!pp->hDeviceWindow) pp->hDeviceWindow = g_ventana;
    }

    HRESULT hr = g_reset_real(dev, pp);
    if (hr == 0) {
        apuntar("Reset OK: %dx%d  %s  msaa %d", (int)pp->BackBufferWidth,
                (int)pp->BackBufferHeight,
                pp->Windowed ? "en ventana" : "PANTALLA COMPLETA",
                (int)pp->MultiSampleType);
        marcar_titulo(g_ventana);   /* el juego reescribe su titulo al rehacer la pantalla */
        preparar_para_plano(g_ventana);   /* ★ y Windows le vuelve a redondear las esquinas */
        /* ⚠ el cartel recorta contra ESTE tamaño: si cambia y no se actualiza, `Clear`
         *   recibe un rect de mas y **no dibuja nada, ni los otros**. */
        g_ancho = pp->BackBufferWidth;
        g_alto = pp->BackBufferHeight;
        cielo_ajustar(g_ancho, g_alto);   /* ★ 26-oct: cambió la resolución -> el cielo a la nueva medida */
        return hr;
    }

    /* ★★ LA RED DE SEGURIDAD, igual que en CreateDevice:
     *   si algo de lo nuestro no se puede, se vuelve EXACTAMENTE a lo que pedía el juego.
     *   Y se apaga el pedido de pantalla completa, para no reintentar en bucle algo que
     *   ya se sabe que falla. */
    apuntar("  ! Reset rechazado (hr=0x%x): vuelvo a lo que pedia el juego", (unsigned)hr);
    g_quiere_pantalla_completa = 0;
    *pp = copia;
    hr = g_reset_real(dev, pp);
    marcar_titulo(g_ventana);
    return hr;
}

/* ⚠ declaradas aca porque el cartel de metricas se define mas abajo (necesita
 *   cosas que todavia no existen a esta altura) y `enganchar_dispositivo` es
 *   quien lo prende. */
typedef struct { LONG x1, y1, x2, y2; } RECTD3D;
typedef HRESULT (WINAPI *LIMPIAR)(void *, DWORD, const RECTD3D *, DWORD, DWORD,
                                  float, DWORD);
typedef HRESULT (WINAPI *FINESCENA)(void *);
static LIMPIAR   g_clear_real;
static FINESCENA g_endscene_real;
static LARGE_INTEGER g_frec, g_ant;
static HRESULT WINAPI mi_endscene(void *dev);

/* ⚠ `Clear` se recorta contra el viewport y la tijera; hay que neutralizarlos y
 *   devolverlos. Indices de IDirect3DDevice9, faciles de errar:
 *       43 Clear · 47 SetViewport · 48 GetViewport
 *       57 SetRenderState · 58 GetRenderState */
typedef struct { DWORD X, Y, Width, Height; float MinZ, MaxZ; } VISTA;
typedef HRESULT (WINAPI *PONERVISTA)(void *, const VISTA *);
typedef HRESULT (WINAPI *TRAERVISTA)(void *, VISTA *);
typedef HRESULT (WINAPI *PONERESTADO)(void *, DWORD, DWORD);
typedef HRESULT (WINAPI *TRAERESTADO)(void *, DWORD, DWORD *);
static PONERVISTA  g_setvp;
static TRAERVISTA  g_getvp;
static PONERESTADO g_setrs;
static TRAERESTADO g_getrs;
#define RS_TIJERA 174           /* D3DRS_SCISSORTESTENABLE */

/* ⚠ y lo que hace falta para forzar el BACKBUFFER antes de dibujar:
 *       18 GetBackBuffer · 37 SetRenderTarget · 38 GetRenderTarget · 41 BeginScene */
typedef HRESULT (WINAPI *TRAERTRASERO)(void *, UINT, UINT, DWORD, void **);
typedef HRESULT (WINAPI *PONERDESTINO)(void *, DWORD, void *);
typedef HRESULT (WINAPI *TRAERDESTINO)(void *, DWORD, void **);
typedef HRESULT (WINAPI *ESCENA)(void *);
typedef ULONG   (WINAPI *SOLTAR)(void *);
static TRAERTRASERO g_getbb;
static PONERDESTINO g_setrt;
static TRAERDESTINO g_getrt;
static ESCENA       g_beginscene_real;
static void dibujar_cartel(void *dev, LONG dx, LONG dy);
static void soltar_com(void *obj);

/* ⚠ `Present` (17) lo enganchan DOS cosas: el testigo del 9Ex y el cartel de metricas.
 *   Se declara aca arriba y lo instala el que llegue primero — engancharlo dos veces
 *   nos haria llamarnos a nosotros mismos, que es un cuelgue instantaneo. */
typedef HRESULT (WINAPI *PRESENTAR)(void *, const void *, const void *, HWND,
                                    const void *);
static PRESENTAR g_present_real;
static HRESULT WINAPI mi_present(void *dev, const void *origen, const void *destino,
                                 HWND ventana, const void *region);

/* ★★★ EL SEGUNDO CAMINO: el Present del SWAPCHAIN.
 *   Este juego presenta por los dos, y en el lobby usa este. Ver el comentario largo
 *   de `enganchar_dispositivo`.
 *   ⚠ `IDirect3DSwapChain9::Present` lleva un `dwFlags` DE MAS al final que el del
 *     dispositivo. Olvidarlo desalinea la pila y el juego se cae. */
typedef HRESULT (WINAPI *TRAERCADENA)(void *, UINT, void **);
typedef HRESULT (WINAPI *PRESENTARCADENA)(void *, const void *, const void *, HWND,
                                          const void *, DWORD);
static PRESENTARCADENA g_scpresent_real;
static void *g_dev_cartel;          /* el dispositivo, para dibujar desde el swapchain */
static HRESULT WINAPI mi_present_cadena(void *cadena, const void *origen,
                                        const void *destino, HWND ventana,
                                        const void *region, DWORD banderas);

static void sala_alfa_enganchar(void *dev);   /* sala_alfa.c (se incluye más abajo) */

static void enganchar_dispositivo(void *dev)
{
    if (!dev || g_reset_real) return;
    void **vt = *(void ***)dev;
    if (!vt) return;
    DWORD viejo = 0;
    if (!VirtualProtect(&vt[16], sizeof(void *), PAGE_EXECUTE_READWRITE, &viejo)) return;
    g_reset_real = (RESETEAR)vt[16];        /* 16 = IDirect3DDevice9::Reset */
    vt[16] = (void *)mi_reset;
    VirtualProtect(&vt[16], sizeof(void *), viejo, &viejo);

    /* ★ EL CARTEL DE METRICAS: EndScene para dibujar, y Clear para hacerlo.
     * ⚠ Los indices son de IDirect3DDevice9:  41 BeginScene · 42 EndScene · 43 Clear.
     *   Se guarda el Clear REAL, no el de la vtable, porque si algun dia enganchamos
     *   Clear tambien, llamarnos a nosotros mismos seria un bucle infinito. */
    /* ⚠ SE ENGANCHA `Present` (17), NO `EndScene` (42).
     *   `EndScene` corre VARIAS veces por cuadro y no siempre sobre el backbuffer: el
     *   cartel se dibujaba y despues el juego lo tapaba. Ver el comentario largo de
     *   `dibujar_cartel`. `Present` es una vez por cuadro y es lo ultimo. */
    if (g_metricas) {
        DWORD v2 = 0;
        g_clear_real = (LIMPIAR)vt[43];
        g_getbb  = (TRAERTRASERO)vt[18];
        g_setrt  = (PONERDESTINO)vt[37];
        g_getrt  = (TRAERDESTINO)vt[38];
        g_beginscene_real = (ESCENA)vt[41];
        g_endscene_real   = (FINESCENA)vt[42];
        g_setvp = (PONERVISTA)vt[47];
        g_getvp = (TRAERVISTA)vt[48];
        g_setrs = (PONERESTADO)vt[57];
        g_getrs = (TRAERESTADO)vt[58];
        if (!g_present_real
            && VirtualProtect(&vt[17], sizeof(void *), PAGE_EXECUTE_READWRITE, &v2)) {
            g_present_real = (PRESENTAR)vt[17];
            vt[17] = (void *)mi_present;
            VirtualProtect(&vt[17], sizeof(void *), v2, &v2);
            QueryPerformanceFrequency(&g_frec);
            apuntar("  [metricas] cartel de fps encendido (escala %d, grafico %d)",
                    g_met_escala, g_met_grafico);
        } else if (g_present_real) {
            QueryPerformanceFrequency(&g_frec);
            apuntar("  [metricas] cartel encendido (Present ya estaba enganchado)");
        } else {
            g_clear_real = NULL;
            apuntar("  [metricas] ⚠ no pude enganchar Present: cartel apagado");
        }

        /* ═══ ★★★ EL SEGUNDO CAMINO DE PRESENTACION  (20-sep-2026) ═══════════
         *
         *   Lo cazo anonimo03 de una observacion, no de un disasm: *"el punto en el que
         *   crasheaba 9Ex es el MISMO en el que nuestro medidor de fps se va"*.
         *
         *   ⇒ Y encaja con algo que ya estaba anotado desde antes: `pegados.js`
         *     enganchaba el Present **del dispositivo Y el del swapchain**, porque
         *     este juego presenta por los DOS.
         *
         *   ★ Durante la carga usa el del DISPOSITIVO — y el cartel se veia.
         *     Al llegar al lobby pasa al del SWAPCHAIN, y nuestro hook no se entera
         *     mas. **No era que el dibujo se tapara: es que dejaba de correr.**
         *     Por eso ninguna de las dos hipotesis anteriores dio en el blanco.
         *
         *   ⚠ Son vtables DISTINTAS. IDirect3DSwapChain9:
         *         0 QueryInterface · 1 AddRef · 2 Release · **3 Present**
         *     y `GetSwapChain` es el 14 del dispositivo.
         *   ⚠ `GetSwapChain` suma una referencia: hay que soltarla o se fuga.
         */
        g_dev_cartel = dev;
        TRAERCADENA traer = (TRAERCADENA)vt[14];
        void *cadena = NULL;
        if (traer && traer(dev, 0, &cadena) == 0 && cadena) {
            void **vtc = *(void ***)cadena;
            DWORD v3 = 0;
            if (vtc && !g_scpresent_real
                && VirtualProtect(&vtc[3], sizeof(void *), PAGE_EXECUTE_READWRITE, &v3)) {
                g_scpresent_real = (PRESENTARCADENA)vtc[3];
                vtc[3] = (void *)mi_present_cadena;
                VirtualProtect(&vtc[3], sizeof(void *), v3, &v3);
                apuntar("  [metricas] ★ enganchado TAMBIEN el Present del swapchain"
                        " (el 2do camino, el que usa el lobby)");
            }
            soltar_com(cadena);
        } else {
            apuntar("  [metricas] ⚠ no pude tomar el swapchain: si el cartel se va en"
                    " el lobby, la causa esta por aca");
        }
    }
    /* ★ 02-nov: las piezas con alfa de las escenas traídas (la sala Parque 2026), `sala_alfa.c` */
    sala_alfa_enganchar(dev);
}

static void alternar_estirada(HWND h)
{
    if (!g_estirada) {
        /* guardar TODO lo que se va a tocar, para poder volver exacto */
        g_estilo_previo   = GetWindowLongA(h, GWL_STYLE);
        g_estiloex_previo = GetWindowLongA(h, GWL_EXSTYLE);
        GetWindowRect(h, &g_rect_previo);

        HMONITOR mon = MonitorFromWindow(h, MONITOR_DEFAULTTONEAREST);
        MONITORINFO mi;
        mi.cbSize = sizeof(mi);
        if (!GetMonitorInfoA(mon, &mi)) return;

        /* ⚠ WS_POPUP y nada mas: sin borde, sin barra, sin marco de redimension */
        SetWindowLongA(h, GWL_STYLE, (g_estilo_previo & ~(WS_CAPTION | WS_THICKFRAME
                        | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU)) | WS_POPUP);
        SetWindowLongA(h, GWL_EXSTYLE, g_estiloex_previo
                        & ~(WS_EX_DLGMODALFRAME | WS_EX_WINDOWEDGE | WS_EX_CLIENTEDGE
                            | WS_EX_STATICEDGE));
        SetWindowPos(h, HWND_TOP, mi.rcMonitor.left, mi.rcMonitor.top,
                     mi.rcMonitor.right - mi.rcMonitor.left,
                     mi.rcMonitor.bottom - mi.rcMonitor.top,
                     SWP_NOOWNERZORDER | SWP_FRAMECHANGED);
        g_estirada = 1;
    } else {
        SetWindowLongA(h, GWL_STYLE, g_estilo_previo);
        SetWindowLongA(h, GWL_EXSTYLE, g_estiloex_previo);
        SetWindowPos(h, HWND_TOP, g_rect_previo.left, g_rect_previo.top,
                     g_rect_previo.right - g_rect_previo.left,
                     g_rect_previo.bottom - g_rect_previo.top,
                     SWP_NOOWNERZORDER | SWP_FRAMECHANGED);
        g_estirada = 0;
    }
}

/* ★ TOP 5 RANK (top5.c, incluido más abajo): con su ventana abierta se queda con el mouse y el Esc */
static int top5_mensaje(HWND h, UINT msg, WPARAM wp, LPARAM lp);
static int top5_quiere_ventana(void);
/* ★ «Elige tu personaje» (selector.c): con el selector a la vista, el mouse es suyo (la creación de abajo no se toca) */
static int selector_mensaje(HWND h, UINT msg, WPARAM wp, LPARAM lp);
static int selector_quiere_ventana(void);
/* ★ el buscador y el carrito de la tienda (tienda.c): sus clics, la ruedita y lo que se escribe en el buscador */
static int tienda_mensaje(HWND h, UINT msg, WPARAM wp, LPARAM lp);
static int tienda_quiere_ventana(void);

static LRESULT CALLBACK mi_wndproc(HWND h, UINT msg, WPARAM wp, LPARAM lp)
{
    /* alt+enter: WM_SYSKEYDOWN con Enter y el bit 29 (ALT) puesto.
     * ⚠ el bit 30 dice que la tecla ya venía apretada: se ignora la repetición.
     *
     * ★★ ACÁ NO SE HACE NADA MÁS QUE LEVANTAR LA MANO.
     *   El mensaje SÍ se le pasa al juego, porque es el juego el que rehace la pantalla
     *   (lo midió el espía: cada alt+enter dispara un `Reset`). Lo único que hacemos es
     *   anotar que esta vez queremos pantalla completa, y `mi_reset` se encarga cuando
     *   el juego llegue ahí.
     *   ⇒ Así el motor sigue su curso normal —libera sus texturas, rehace lo suyo— y
     *     nosotros sólo le corregimos el pedido al pasar. Mucho menos invasivo que
     *     manejar el cambio por nuestra cuenta. */
    if (g_altenter && msg == WM_SYSKEYDOWN && wp == VK_RETURN
        && (lp & (1 << 29)) && !(lp & (1 << 30))) {
        g_quiere_pantalla_completa = !g_quiere_pantalla_completa;
        apuntar("alt+enter: el jugador pide %s (lo aplica el Reset que viene)",
                g_quiere_pantalla_completa ? "PANTALLA COMPLETA" : "volver a ventana");
    }
    /* ⚠ y hay que soltar el "bip" que Windows manda con alt+enter */
    if (g_altenter && msg == WM_SYSCHAR && wp == VK_RETURN) return 0;
    /* ★ el juego lee el mouse y el teclado de ESTOS mensajes (0x647650): lo que es de TOP 5 RANK no le llega */
    if (top5_mensaje(h, msg, wp, lp)) return 0;
    if (selector_mensaje(h, msg, wp, lp)) return 0;
    if (tienda_mensaje(h, msg, wp, lp)) return 0;

    return CallWindowProcA(g_wndproc_viejo, h, msg, wp, lp);
}

static void enganchar_ventana(HWND h)
{
    if ((!g_altenter && !top5_quiere_ventana() && !selector_quiere_ventana() && !tienda_quiere_ventana())
        || !h || g_wndproc_viejo || !IsWindow(h)) return;
    g_ventana = h;
    g_wndproc_viejo = (WNDPROC)SetWindowLongPtrA(h, GWLP_WNDPROC,
                                                 (LONG_PTR)mi_wndproc);
}

/* ═══ ★ EL CARTEL DE METRICAS ═══════════════════════════════════════════════ */

#define LIMPIAR_COLOR 0x00000001        /* D3DCLEAR_TARGET */
#define MAX_RECTS 160

/* ★ Los 7 segmentos, en el orden  a b c d e f g:
 *
 *      aaa        a = arriba      d = abajo
 *     f   b       b = der-arriba  e = izq-abajo
 *     f   b       c = der-abajo   f = izq-arriba
 *      ggg        g = el del medio
 *     e   c
 *     e   c
 *      ddd
 */
static const unsigned char DIGITOS[10] = {
    /*0*/ 0x3F, /*1*/ 0x06, /*2*/ 0x5B, /*3*/ 0x4F, /*4*/ 0x66,
    /*5*/ 0x6D, /*6*/ 0x7D, /*7*/ 0x07, /*8*/ 0x7F, /*9*/ 0x6F
};

/* Mete en `r` los rectangulos de un digito. Devuelve cuantos metio. */
static int digito_a_rects(int d, int x, int y, int e, RECTD3D *r, int tope)
{
    if (d < 0 || d > 9) return 0;
    int an = 4 * e, al = 7 * e, gr = e;      /* ancho, alto, grosor del trazo */
    unsigned char s = DIGITOS[d];
    const RECTD3D seg[7] = {
        { x,           y,             x + an,      y + gr },            /* a */
        { x + an - gr, y,             x + an,      y + al / 2 + gr / 2 },/* b */
        { x + an - gr, y + al / 2,    x + an,      y + al },            /* c */
        { x,           y + al - gr,   x + an,      y + al },            /* d */
        { x,           y + al / 2,    x + gr,      y + al },            /* e */
        { x,           y,             x + gr,      y + al / 2 + gr / 2 },/* f */
        { x,           y + al / 2 - gr / 2, x + an, y + al / 2 + gr / 2 }/* g */
    };
    int n = 0;
    for (int i = 0; i < 7 && n < tope; i++)
        if (s & (1 << i)) r[n++] = seg[i];
    return n;
}

static int numero_a_rects(int v, int x, int y, int e, RECTD3D *r, int tope)
{
    char txt[8];
    wsprintfA(txt, "%d", v < 0 ? 0 : (v > 9999 ? 9999 : v));
    int n = 0, paso = 5 * e;                 /* 4e de ancho + 1e de separacion */
    for (int i = 0; txt[i] && n < tope; i++)
        n += digito_a_rects(txt[i] - '0', x + i * paso, y, e, r + n, tope - n);
    return n;
}

/* ⚠ Los rectangulos que se salgan del backbuffer se recortan: `Clear` con un rect
 *   fuera del render target devuelve error y NO dibuja NADA (ni los demas). */
static int recortar(RECTD3D *r, int n)
{
    int fuera = 0;
    for (int i = 0; i < n; i++) {
        if (r[i].x1 < 0) r[i].x1 = 0;
        if (r[i].y1 < 0) r[i].y1 = 0;
        if (g_ancho && r[i].x2 > (LONG)g_ancho) r[i].x2 = (LONG)g_ancho;
        if (g_alto && r[i].y2 > (LONG)g_alto) r[i].y2 = (LONG)g_alto;
        if (r[i].x2 <= r[i].x1 || r[i].y2 <= r[i].y1) { fuera = 1; r[i] = r[n - 1]; n--; i--; }
    }
    (void)fuera;
    return n;
}

/* los ultimos tiempos de cuadro, para el grafico */
#define MUESTRAS 64
static double g_ms[MUESTRAS];
static int g_ms_i = 0;
static int g_fps_visible = 0;
static HRESULT g_ultimo_hr = 0;   /* el resultado del ultimo Clear del cartel */
static double g_acum = 0.0;
/* ⚠ se llama `g_met_cuadros` y no `g_cuadros` porque ESE YA EXISTE mas
 *   abajo (cuenta los Present que sobrevivieron). El compilador lo caza,
 *   pero si los tipos hubieran coincidido habria pasado. */
static int g_met_cuadros = 0;

/* ═══ ⛔ POR QUE ESTO SE MUDO DE `EndScene` A `Present`  (20-sep-2026) ═══════
 *
 *   anonimo03: *"volvio a desaparecer entre la carga del intro y llegar al lobby"*.
 *
 *   ⚠ Y la primera hipotesis (que `Clear` se recortaba contra el viewport o la
 *     tijera) **era falsa**: el aviso que deje puesto para cazarla NO aparecio ni una
 *     vez en el log. Lo unico que salvo la tarde fue haber dejado el diagnostico
 *     adentro en vez de dar por buena la explicacion.
 *
 * ★★★ LO QUE PASA DE VERDAD: `EndScene` no es UNA vez por cuadro.
 *   El juego abre y cierra varias escenas por cuadro, y las ultimas no van al
 *   backbuffer sino a superficies intermedias. Dibujabamos en todas — y las que caian
 *   en el backbuffer quedaban TAPADAS por lo que el juego pintaba despues.
 *   ⇒ En el lobby, que dibuja mas capas que la pantalla de carga, no sobrevivia ninguna.
 *
 * ★ `Present` si es una sola vez por cuadro, y es **lo ultimo**. Ahi:
 *     1. se fuerza el render target al BACKBUFFER (por si quedo otro puesto)
 *     2. se abre una escena propia, se dibuja, y se cierra
 *     3. se devuelve el render target
 *   ⇒ Nadie puede taparlo, porque despues solo queda mostrar la imagen.
 */
static void soltar_com(void *obj)
{
    if (!obj) return;
    void **vt = *(void ***)obj;
    if (vt) ((SOLTAR)vt[2])(obj);        /* 2 = IUnknown::Release */
}

static void dibujar_cartel(void *dev, LONG dx, LONG dy)
{
    if (!g_clear_real) return;

    /* ── el reloj ─────────────────────────────────────────────────────────── */
    LARGE_INTEGER ahora;
    QueryPerformanceCounter(&ahora);
    if (g_ant.QuadPart && g_frec.QuadPart) {
        double ms = 1000.0 * (double)(ahora.QuadPart - g_ant.QuadPart)
                    / (double)g_frec.QuadPart;
        if (ms > 0.0 && ms < 1000.0) {
            g_ms[g_ms_i] = ms;
            g_ms_i = (g_ms_i + 1) % MUESTRAS;
            g_acum += ms;
            g_met_cuadros++;
            /* el numero se refresca cada ~500 ms: si parpadea no se puede leer */
            if (g_acum >= 500.0) {
                g_fps_visible = (int)(g_met_cuadros * 1000.0 / g_acum + 0.5);
                g_acum = 0.0;
                g_met_cuadros = 0;
            }
        }
    }
    g_ant = ahora;

    /* ═══ ★★★ POR QUE DESAPARECIA EN EL CAMBIO DE ESCENA  (20-sep-2026) ═══════
     *
     *   anonimo03: *"el contador aparecio durante la carga, pero desaparecio en el cambio
     *   de escena"*. El enganche seguia puesto — lo que fallaba era el DIBUJO.
     *
     *   ⚠ `Clear` NO pinta donde uno le dice y listo: se recorta contra **el viewport**
     *     y, si esta encendido el test de tijera, contra **el scissor rect**. El juego
     *     los mueve para su capa 2D y para las transiciones. Con un viewport chico o
     *     una tijera en otro lado, nuestros rectangulos caen afuera y no se dibuja NADA.
     *
     * ★ El arreglo: se GUARDA el viewport y el estado de tijera, se ponen los nuestros,
     *   se dibuja, y **se devuelven exactamente como estaban**. Es el unico estado que
     *   tocamos y se revierte en la misma llamada: el juego no puede notarlo.
     *
     * ⚠ Y se ANOTA lo que se encontro, una vez cada tanto: si la causa era otra, el log
     *   lo dice en vez de dejarnos con la suposicion. */
    /* ★ 1 · EL BACKBUFFER, pase lo que pase. Si el juego dejo otra superficie puesta,
     *   dibujar ahi es invisible — y es la sospecha que queda despues de descartar el
     *   viewport. Se guarda el destino anterior y se devuelve al final. */
    void *rt_previo = NULL, *trasero = NULL;
    int cambie_rt = 0;
    if (g_getrt && g_setrt && g_getbb
        && g_getbb(dev, 0, 0, 0 /* MONO */, &trasero) == 0 && trasero) {
        if (g_getrt(dev, 0, &rt_previo) == 0 && rt_previo != trasero) {
            if (g_setrt(dev, 0, trasero) == 0) cambie_rt = 1;
            static int avisado_rt = 0;
            if (!avisado_rt) {
                avisado_rt = 1;
                apuntar("  [metricas] ★ era esto: el juego presentaba con OTRA superficie"
                        " puesta, no el backbuffer. Forzado.");
            }
        }
    }

    /* ★ 2 · y una escena propia: `Clear` tiene que pasar dentro de Begin/EndScene, y
     *   en `Present` el juego ya cerro la suya. */
    int abri_escena = (g_beginscene_real && g_beginscene_real(dev) == 0);

    VISTA vp_previo;
    int tenia_vp = (g_getvp && g_getvp(dev, &vp_previo) == 0);
    DWORD tijera_previa = 0;
    int tenia_tijera = (g_getrs && g_getrs(dev, RS_TIJERA, &tijera_previa) == 0);

    if (tenia_tijera && tijera_previa && g_setrs) g_setrs(dev, RS_TIJERA, 0);
    if (tenia_vp && g_setvp) {
        VISTA full = { 0, 0, g_ancho ? g_ancho : vp_previo.Width,
                       g_alto ? g_alto : vp_previo.Height, 0.0f, 1.0f };
        g_setvp(dev, &full);
    }

    /* ── el cartel ────────────────────────────────────────────────────────── */
    RECTD3D r[MAX_RECTS];
    int e = g_met_escala < 1 ? 1 : (g_met_escala > 12 ? 12 : g_met_escala);
    int n = numero_a_rects(g_fps_visible, (int)dx + 8, (int)dy + 8, e, r, MAX_RECTS);
    n = recortar(r, n);
    /* ⛔⛔ EL AGUJERO QUE DEJE TRES VUELTAS: nunca comprobamos si `Clear` funciono.
     *   Si devuelve error no dibuja NADA y nadie se entera — y uno se pasa la tarde
     *   buscando por que "el dibujo no se ve", cuando el dibujo ni se hizo.
     *   ⇒ Ahora se mira el resultado y se anota UNA vez por tipo de fallo. */
    /* ═══ ★★★ prueba=2 : PINTAR TODO  (20-sep-2026) ═══════════════════════
     *   La prueba de las 5 esquinas dio que **no sobrevive ninguna**. ⇒ La posicion
     *   no era el problema, y eso deja UNA sola pregunta binaria:
     *
     *       ¿nuestro `Clear` llega a la pantalla, si o no?
     *
     *   Se contesta pintando el backbuffer ENTERO de magenta. Sin rectangulos, sin
     *   posiciones, sin nada que pueda estar mal puesto.
     *       la pantalla se pone MAGENTA  -> el Clear llega; el problema son los rects
     *       la pantalla se ve NORMAL     -> el Clear NO llega: la superficie sobre la
     *                                       que dibujamos no es la que se muestra,
     *                                       aunque GetRenderTarget diga que si
     *   ⚠ Con esto el juego no se puede jugar. Es para 10 segundos y se apaga. */
    /* ═══ ★★★ prueba=3 : DIBUJAR CON GDI  (20-sep-2026) ═══════════════════
     *
     *   LO QUE YA ESTA DESCARTADO POR MEDICION, y es casi todo:
     *       el hook corre 840 cuadros seguidos · Clear devuelve 0 siempre
     *       dev / rt / bb IDENTICOS toda la corrida · rt == bb · sin Reset
     *       sin rect de origen · sin ventana alternativa · un solo CreateDevice
     *   ⇒ Nuestro dibujo llega al backbuffer, correcto, en cada cuadro. Y el magenta
     *     **se ve en la carga y deja de verse en el lobby**.
     *
     * ★★★ ⇒ Lo que tapa el lobby NO PASA POR DIRECT3D.
     *   Y encaja con algo anotado hace dias y nunca conectado: el camino de
     *   presentacion medido es **`Composed: Copy with GPU GDI`**, y el 2013 arma parte
     *   de su ventana con GDI (su propia banda, su titulo). Si el lobby se pinta con
     *   GDI ENCIMA de la ventana, tapa lo que Direct3D acaba de presentar.
     *
     *   Se prueba dibujando por el mismo camino que el juego: GDI sobre el DC de la
     *   ventana. Si el cartel sobrevive aca, ademas ganamos TEXTO DE VERDAD gratis.
     *   ⚠ GDI sobre una ventana Direct3D puede parpadear. Si pasa, se mide y se decide. */
    if (g_met_prueba == 2) {
        g_clear_real(dev, 0, NULL, LIMPIAR_COLOR, 0x00FF00FF, 1.0f, 0);
        static int dicho2 = 0;
        if (!dicho2) {
            dicho2 = 1;
            apuntar("  [metricas] ★ prueba=2: pintando TODO de magenta. Si la pantalla"
                    " NO se pone magenta, nuestro Clear no llega a lo que se muestra.");
        }
    }

    /* ★★★ LA PRUEBA DE LAS CINCO ESQUINAS. Si alguna sobrevive, ahi se puede poner el
     *   cartel de verdad; y si NINGUNA sobrevive, el problema no es la posicion.
     *       blanco = arriba izq · rojo = arriba der · verde = abajo izq
     *       azul   = abajo der  · amarillo = el centro                       */
    if (g_met_prueba == 1 && g_ancho && g_alto) {
        const DWORD colores[5] = { 0x00FFFFFF, 0x00FF3030, 0x0030FF30,
                                   0x004060FF, 0x00FFFF30 };
        int anN = 4 * 5 * e, alN = 7 * e;        /* hasta 4 digitos */
        const int pos[5][2] = {
            { 8, 8 },
            { (int)g_ancho - anN - 8, 8 },
            { 8, (int)g_alto - alN - 8 },
            { (int)g_ancho - anN - 8, (int)g_alto - alN - 8 },
            { ((int)g_ancho - anN) / 2, ((int)g_alto - alN) / 2 }
        };
        for (int z = 0; z < 5; z++) {
            RECTD3D q[MAX_RECTS];
            int k = numero_a_rects(g_fps_visible, pos[z][0], pos[z][1], e, q, MAX_RECTS);
            k = recortar(q, k);
            if (k > 0) g_clear_real(dev, (DWORD)k, q, LIMPIAR_COLOR, colores[z], 1.0f, 0);
        }
        static int dicho = 0;
        if (!dicho) {
            dicho = 1;
            apuntar("  [metricas] ★ PRUEBA DE 5 ESQUINAS encendida. Colores:"
                    " blanco=arr-izq rojo=arr-der verde=ab-izq azul=ab-der"
                    " amarillo=centro. Deci cual sobrevive.");
        }
    }

    HRESULT hrc = 0;
    if (n > 0) {
        hrc = g_clear_real(dev, (DWORD)n, r, LIMPIAR_COLOR, 0x00FFFFFF, 1.0f, 0);
        g_ultimo_hr = hrc;
        static HRESULT ultimo = 1;
        static int vivo = 0;
        if (hrc != 0 && hrc != ultimo) {
            ultimo = hrc;
            apuntar("  [metricas] ⛔ el Clear del cartel FALLA: hr=0x%x  (%d rects,"
                    " backbuffer %ux%u)", (unsigned)hrc, n, g_ancho, g_alto);
        } else if (hrc == 0 && !vivo) {
            vivo = 1;
            apuntar("  [metricas] ✔ el Clear del cartel funciona (%d rects). Si aun asi"
                    " no se ve, algo lo redibuja DESPUES de nuestro Present.", n);
        }
    }

    /* ── el grafico de tiempos, debajo ────────────────────────────────────── */
    if (g_met_grafico) {
        int base = (int)dy + 8 + 7 * e + 6;    /* debajo del numero */
        int altoG = 6 * e;
        int m = 0;
        for (int i = 0; i < MUESTRAS && m < MAX_RECTS; i++) {
            double ms = g_ms[(g_ms_i + i) % MUESTRAS];
            if (ms <= 0.0) continue;
            /* ★ 33 ms (o sea 30 fps) llena la barra: asi un tiron se ve enseguida */
            int h = (int)(ms / 33.0 * altoG);
            if (h < 1) h = 1;
            if (h > altoG) h = altoG;
            r[m].x1 = (int)dx + 8 + i * 2;
            r[m].x2 = r[m].x1 + 1;
            r[m].y2 = base + altoG;
            r[m].y1 = r[m].y2 - h;
            m++;
        }
        m = recortar(r, m);
        if (m > 0) g_clear_real(dev, (DWORD)m, r, LIMPIAR_COLOR, 0x0000FF66, 1.0f, 0);
    }

    /* ★★ Y SE DEVUELVE TODO COMO ESTABA, en orden inverso al que se tomo. Si esto no
     *   corriera, el juego seguiria dibujando con NUESTRO viewport y en NUESTRO destino
     *   — y la pantalla siguiente saldria rota. */
    if (tenia_vp && g_setvp) g_setvp(dev, &vp_previo);
    if (tenia_tijera && tijera_previa && g_setrs) g_setrs(dev, RS_TIJERA, tijera_previa);
    if (abri_escena && g_endscene_real) g_endscene_real(dev);
    if (cambie_rt && g_setrt) g_setrt(dev, 0, rt_previo);
    /* ⚠ `GetRenderTarget` y `GetBackBuffer` SUMAN una referencia: sin estos dos
     *   `Release` se fuga una superficie por cuadro y el juego termina sin memoria. */
    soltar_com(rt_previo);
    soltar_com(trasero);
}

typedef void *(WINAPI *CREAR9)(UINT);
typedef HRESULT (WINAPI *CREAR9EX)(UINT, void **);   /* ★ la fabrica moderna */
static CREAR9EX g_crear_ex = NULL;
typedef HRESULT (WINAPI *CREARDISPOSITIVO)(void *, UINT, UINT, HWND, DWORD,
                                           PRESENT_PARAMS *, void **);

static HMODULE g_real = NULL;
static CREAR9  g_crear = NULL;
static CREARDISPOSITIVO g_createdevice_real = NULL;

static void leer_ajustes(HMODULE self)
{
    char ruta[MAX_PATH];
    if (!GetModuleFileNameA(self, ruta, MAX_PATH)) return;
    char *barra = strrchr(ruta, '\\');
    if (!barra) return;

    /* la carpeta, con la barra al final: la usan el ini y el log */
    int largo = (int)(barra - ruta) + 1;
    if (largo < MAX_PATH) {
        CopyMemory(g_carpeta, ruta, largo);
        g_carpeta[largo] = 0;
    }

    lstrcpyA(barra + 1, "d3d9_proxy.ini");
    if (GetFileAttributesA(ruta) == INVALID_FILE_ATTRIBUTES) return;   /* sin ini: por defecto */
    g_hay_ini = 1;
    g_msaa     = (int)GetPrivateProfileIntA("video", "msaa", g_msaa, ruta);
    g_activo   = (int)GetPrivateProfileIntA("video", "activo", g_activo, ruta);
    g_altenter = (int)GetPrivateProfileIntA("video", "altenter", g_altenter, ruta);
    g_log      = (int)GetPrivateProfileIntA("video", "log", g_log, ruta);
    g_titulo   = (int)GetPrivateProfileIntA("video", "titulo", g_titulo, ruta);
    g_d3d9ex   = (int)GetPrivateProfileIntA("moderno", "d3d9ex", g_d3d9ex, ruta);
    g_flipex   = (int)GetPrivateProfileIntA("moderno", "flipex", g_flipex, ruta);
    g_pool     = (int)GetPrivateProfileIntA("moderno", "pool", g_pool, ruta);
    g_esquinas = (int)GetPrivateProfileIntA("plano", "esquinas", g_esquinas, ruta);
    g_sincapas = (int)GetPrivateProfileIntA("plano", "sincapas", g_sincapas, ruta);
    g_metricas = (int)GetPrivateProfileIntA("metricas", "activo", g_metricas, ruta);
    g_met_escala = (int)GetPrivateProfileIntA("metricas", "escala", g_met_escala, ruta);
    g_met_grafico = (int)GetPrivateProfileIntA("metricas", "grafico", g_met_grafico, ruta);
    g_met_prueba = (int)GetPrivateProfileIntA("metricas", "prueba", g_met_prueba, ruta);
    g_sleep_ms  = (int)GetPrivateProfileIntA("motor", "sleep", g_sleep_ms, ruta);
    g_nucleo_libre = (int)GetPrivateProfileIntA("motor", "nucleo_libre", g_nucleo_libre, ruta);
    g_flu_fondo60 = (int)GetPrivateProfileIntA("motor", "fondo60", 1, ruta);
    g_siesta_ms = (int)GetPrivateProfileIntA("motor", "siesta", g_siesta_ms, ruta);
    g_hzminimo  = (int)GetPrivateProfileIntA("motor", "hzminimo", g_hzminimo, ruta);
    g_gate      = (int)GetPrivateProfileIntA("motor", "gate", g_gate, ruta);
    g_mundo     = (int)GetPrivateProfileIntA("motor", "mundo", g_mundo, ruta);
    g_fluidez   = (int)GetPrivateProfileIntA("motor", "fluidez", g_fluidez, ruta);
    g_ritmo     = (int)GetPrivateProfileIntA("motor", "ritmo", g_ritmo, ruta);
    g_giro_cfg  = (int)GetPrivateProfileIntA("motor", "giro", g_giro_cfg, ruta);
    /* ⚠ FLIPEX sin 9Ex no existe: pedirlo asi seria un Reset rechazado y nada mas. */
    if (!g_d3d9ex) g_flipex = 0;
}

/* ═══════════════════════════════════════════════════════════════════════════
 * ★★★ EL TESTIGO DE LA RUTA MODERNA — que se rompe, y cuanto aguanta
 *
 *   El intento anterior murio «a los tres cuadros» y nadie supo por que. Aca el
 *   juego deja dicho, el solo, que le paso:
 *
 *     · cuantos cuadros llego a dibujar antes de morir  (engancha `Present`)
 *     · cuantos recursos pidio en D3DPOOL_MANAGED       (lo prohibido en 9Ex)
 *     · cuantos de esos FALLARON                        (la prueba de la hipotesis)
 *
 * ⚠⚠ NO SE LOGUEA CADA LLAMADA: `CreateTexture` se llama cientos de veces y el
 *   `Present` sesenta veces por segundo. Escribir una linea por llamada frenaria el
 *   juego y falsearia justo lo que venimos a medir — la trampa que `carga.js` ya
 *   tiene anotada para el censo de dibujos. ⇒ Contadores, y un resumen cada tanto.
 * ═══════════════════════════════════════════════════════════════════════════ */
#define POOL_DEFAULT 0
#define POOL_MANAGED 1

static long g_cuadros      = 0;   /* cuantos Present sobrevivio */
static long g_pedidos_man  = 0;   /* recursos pedidos en MANAGED */
static long g_fallos_man   = 0;   /* ...y cuantos de esos fallaron */
static long g_traducidos   = 0;   /* MANAGED -> DEFAULT hechos por nosotros */
static long g_fallos_otros = 0;   /* recursos que fallaron sin ser MANAGED */
static long g_locks        = 0;   /* Lock de textura pedidos */
static long g_lock_buf = 0, g_lock_buf_malos = 0, g_discard_puestos = 0;
static long g_locks_malos  = 0;   /* ...y cuantos fallaron */
/* ⚠ EL PRIMER AVISO ERA EN EL CUADRO 60 Y ESO TAPO LA SEGUNDA MEDICION:
 *   con `pool=1` el juego murio ANTES de llegar ahi, asi que el log quedo mudo y no
 *   se supo ni cuantos cuadros aguanto. Ahora avisa temprano y se va espaciando. */
static long g_proximo_aviso = 1;

/* ⚠ declarada aca arriba porque la usan los ganchos de textura, que van antes */
static void *cambiar_metodo(void **vt, int indice, void *nuevo);

typedef HRESULT (WINAPI *CREARTEXTURA)(void *, UINT, UINT, UINT, DWORD, DWORD,
                                       DWORD, void **, HANDLE *);
typedef HRESULT (WINAPI *CREARVOLUMEN)(void *, UINT, UINT, UINT, UINT, DWORD,
                                       DWORD, DWORD, void **, HANDLE *);
typedef HRESULT (WINAPI *CREARCUBO)(void *, UINT, UINT, DWORD, DWORD, DWORD,
                                    void **, HANDLE *);
typedef HRESULT (WINAPI *CREARVB)(void *, UINT, DWORD, DWORD, DWORD, void **, HANDLE *);
typedef HRESULT (WINAPI *CREARIB)(void *, UINT, DWORD, DWORD, DWORD, void **, HANDLE *);

static CREARTEXTURA g_creartex_real = NULL;
static CREARVOLUMEN g_crearvol_real = NULL;
static CREARCUBO    g_crearcubo_real = NULL;
static CREARVB      g_crearvb_real  = NULL;
static CREARIB      g_crearib_real  = NULL;

/* ★ cuanta memoria de video queda. Es la OTRA sospecha del crash tardio: con
 *   MANAGED, Direct3D saca de la placa lo que no se usa; con DEFAULT **se queda
 *   todo**. Y en la escena de bienvenida ya iban 2184 recursos traducidos.
 * ⚠ `GetAvailableTextureMem` es el metodo 4 de IDirect3DDevice9. */
typedef UINT (WINAPI *MEMORIALIBRE)(void *);
static void *g_dev = NULL;

static UINT vram_libre_mb(void)
{
    if (!g_dev) return 0;
    void **vt = *(void ***)g_dev;
    if (!vt) return 0;
    return ((MEMORIALIBRE)vt[4])(g_dev) / (1024 * 1024);
}

static void resumen_moderno(const char *cuando)
{
    apuntar("  [9Ex] %s: %d cuadros | MANAGED pedidos %d, fallaron %d, traducidos %d"
            " | otros fallos %d | LockRect %d/%d | LockBuf %d/%d (discard %d)"
            " | VRAM libre %d MB",
            cuando, (int)g_cuadros, (int)g_pedidos_man, (int)g_fallos_man,
            (int)g_traducidos, (int)g_fallos_otros, (int)g_locks_malos,
            (int)g_locks, (int)g_lock_buf_malos, (int)g_lock_buf,
            (int)g_discard_puestos, (int)vram_libre_mb());
}

/* ═══════════════════════════════════════════════════════════════════════════
 * ★★★ EL TESTIGO DE LA MUERTE — 20-sep-2026
 *
 *   «murio a los tres cuadros», «renderizo la ventana y se cerro». Dos veces el
 *   mismo relato y cero datos, porque el proceso se va **sin pasar por
 *   ExitProcess ni por una excepcion que alguien atrape**.
 *
 *   ⇒ Un manejador VECTORIZADO se entera ANTES que el juego: Windows lo llama en
 *     cuanto ocurre la excepcion, antes de buscar quien la maneje. Asi queda
 *     anotado DONDE murio y leyendo QUE direccion, que es la diferencia entre
 *     «se cerro» y un dato con el que se puede trabajar.
 *
 * ⚠ NO CAMBIA EL COMPORTAMIENTO: devuelve CONTINUE_SEARCH siempre, o sea «yo solo
 *   miraba, seguí buscando quien la maneje». El juego muere igual, pero deja dicho.
 * ⚠ Solo las violaciones de acceso y solo las primeras: un motor tira excepciones
 *   de C++ como parte de su funcionamiento normal y el log se llenaria de ruido.
 * ═══════════════════════════════════════════════════════════════════════════ */
static long g_excepciones = 0;

/* ★★ Cuando el EIP esta en tierra de nadie, el unico rastro es LA PILA: las
 *   direcciones de retorno que quedaron ahi dicen por donde venia. Se recorre
 *   crudo y se anota lo que caiga DENTRO DEL EXE, que es lo unico que nos importa
 *   (del resto de modulos hay ruido de sobra).
 *
 * ⚠ Se valida cada pagina con `VirtualQuery` antes de leerla: a esta altura el
 *   proceso ya esta roto, y un manejador de excepciones que provoca OTRA excepcion
 *   se lleva puesto el poco rastro que habia. */
/* ═══════════════════════════════════════════════════════════════════════════
 * ★★★ EL CENSO DE BUFFERS — para dejar de teorizar sobre quien es `esi`
 *
 *   El crash es siempre el mismo `call` a traves de `[esi]`, y la vtable que lee
 *   vale SIEMPRE 0x3eb00000 — que como float es **0.34375**. Un objeto liberado
 *   daria basura distinta cada vez; un valor constante dice que `esi` apunta a
 *   DATOS, no a un objeto COM.
 *
 *   Dos explicaciones, y son muy distintas:
 *     a) `esi` ERA un buffer nuestro y le pisaron la memoria
 *     b) `esi` nunca fue un buffer: el juego lo saco de una estructura equivocada
 *
 *   ⇒ Se anotan los punteros de los buffers que creamos y en el crash se pregunta
 *     si `esi` es uno. Eso lo contesta sin adivinar — que es lo que hace falta
 *     despues de haberme equivocado ya una vez con el Lock.
 *
 * ⚠ Lista circular y chica: no es un gestor de recursos, es un testigo.
 * ═══════════════════════════════════════════════════════════════════════════ */
#define CUANTOS_BUFFERS 4096
static void *g_buffers[CUANTOS_BUFFERS];
static long g_buf_siguiente = 0;
static long g_buf_total = 0;

static void anotar_buffer(void *b)
{
    if (!b) return;
    g_buffers[g_buf_siguiente % CUANTOS_BUFFERS] = b;
    g_buf_siguiente++;
    g_buf_total++;
}

static int fue_buffer_nuestro(void *p)
{
    long n = g_buf_siguiente < CUANTOS_BUFFERS ? g_buf_siguiente : CUANTOS_BUFFERS;
    for (long i = 0; i < n; i++) if (g_buffers[i] == p) return 1;
    return 0;
}

static void rastrear_pila(CONTEXT *ctx)
{
    if (!ctx) return;
    /* ★ los registros primero: `esi` es el objeto por el que se llamo y `eax` la
     *   vtable que leyo. Con eso se sabe QUE se estaba usando, no solo donde. */
    apuntar("  [9Ex]     registros: eax=0x%x ecx=0x%x edx=0x%x esi=0x%x edi=0x%x",
            (unsigned)ctx->Eax, (unsigned)ctx->Ecx, (unsigned)ctx->Edx,
            (unsigned)ctx->Esi, (unsigned)ctx->Edi);
    apuntar("  [9Ex]     ★ el objeto `esi` (0x%x) %s de los buffers que creamos"
            "  (llevamos %d anotados)", (unsigned)ctx->Esi,
            fue_buffer_nuestro((void *)ctx->Esi) ? "SI ES UNO" : "NO es ninguno",
            (int)g_buf_total);

    HMODULE exe = GetModuleHandleA(NULL);
    if (!exe) return;
    MEMORY_BASIC_INFORMATION mbi;
    if (!VirtualQuery((void *)exe, &mbi, sizeof(mbi))) return;
    /* el rango del exe: desde su base hasta donde termine su imagen */
    ULONG_PTR ini_exe = (ULONG_PTR)exe;
    ULONG_PTR fin_exe = ini_exe + 0x1000000;   /* 16 MB de margen, sobra */

    ULONG_PTR *sp = (ULONG_PTR *)ctx->Esp;
    apuntar("  [9Ex]     pila (esp=0x%x  ebp=0x%x):", (unsigned)ctx->Esp,
            (unsigned)ctx->Ebp);
    int anotados = 0;
    for (int i = 0; i < 256 && anotados < 8; i++) {
        ULONG_PTR *p = sp + i;
        if (((ULONG_PTR)p & 0xFFF) == 0 || i == 0) {
            if (!VirtualQuery((void *)p, &mbi, sizeof(mbi)) ||
                mbi.State != MEM_COMMIT) break;
        }
        ULONG_PTR v = *p;
        if (v > ini_exe && v < fin_exe) {
            apuntar("  [9Ex]       [esp+0x%x] -> exe+0x%x   (volvia aca)",
                    (unsigned)(i * sizeof(ULONG_PTR)), (unsigned)(v - ini_exe));
            anotados++;
        }
    }
    if (!anotados) apuntar("  [9Ex]       (sin retornos del exe a la vista)");
}

static LONG CALLBACK mirar_excepcion(EXCEPTION_POINTERS *info)
{
    if (!info || !info->ExceptionRecord) return EXCEPTION_CONTINUE_SEARCH;
    DWORD codigo = info->ExceptionRecord->ExceptionCode;
    if (codigo != EXCEPTION_ACCESS_VIOLATION) return EXCEPTION_CONTINUE_SEARCH;
    g_excepciones++;
    if (g_excepciones <= 5) {
        void *donde = info->ExceptionRecord->ExceptionAddress;
        ULONG_PTR tipo = 0, dir = 0;
        if (info->ExceptionRecord->NumberParameters >= 2) {
            tipo = info->ExceptionRecord->ExceptionInformation[0];
            dir  = info->ExceptionRecord->ExceptionInformation[1];
        }
        /* de que modulo es la direccion que ejecutaba */
        char modulo[MAX_PATH] = "?";
        HMODULE m = NULL;
        if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                               GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                               (LPCSTR)donde, &m) && m) {
            char ruta[MAX_PATH];
            if (GetModuleFileNameA(m, ruta, MAX_PATH)) {
                char *barra = ruta;
                for (char *q = ruta; *q; q++) if (*q == '\\') barra = q + 1;
                lstrcpynA(modulo, barra, MAX_PATH);
            }
        }
        if (m) {
            apuntar("  [9Ex] !!! MURIO ACA: violacion de acceso al %s la direccion"
                    " 0x%x   (codigo en %s+0x%x)   cuadro %d",
                    tipo == 1 ? "ESCRIBIR" : "LEER", (unsigned)dir, modulo,
                    (unsigned)((ULONG_PTR)donde - (ULONG_PTR)m), (int)g_cuadros);
        } else {
            /* ★★★ EL CASO QUE APARECIO EL 20-sep EN LA ESCENA DE BIENVENIDA:
             *   el EIP **no pertenece a ningun modulo**. O sea que el juego SALTO A
             *   MEMORIA QUE NO ES CODIGO — casi siempre, una tabla de metodos de un
             *   objeto COM ya liberado, o un puntero pisado.
             *   ⇒ Ahi la direccion de la falla no dice nada util; lo que dice algo es
             *     QUIEN LLAMO, y eso esta en la pila. */
            apuntar("  [9Ex] !!! MURIO EN TIERRA DE NADIE: ejecutaba en 0x%x, que NO"
                    " es de ningun modulo   cuadro %d   (llamo por un puntero muerto)",
                    (unsigned)(ULONG_PTR)donde, (int)g_cuadros);
        }
        resumen_moderno("en el momento de morir");
        rastrear_pila(info->ContextRecord);
    }
    return EXCEPTION_CONTINUE_SEARCH;      /* ⚠ solo miramos */
}

/* ═══════════════════════════════════════════════════════════════════════════
 * ★★★ EL CORAZON DE LA TRADUCCION — y por que `pool=1` no alcanzo
 *
 *   MEDIDO el 20-sep con el testigo de la muerte, traduciendo MANAGED -> DEFAULT
 *   a secas (`pool=1`). El juego murio en el cuadro 0, en la PRIMERA traduccion:
 *
 *       MURIO ACA: violacion de acceso al ESCRIBIR la direccion 0x0
 *       codigo en R2Beat_local.exe+0x35dcec
 *
 *   Y ese sitio, desensamblado, es un memcpy con SSE:
 *
 *       mov    edi, [ebp+8]          ; el DESTINO
 *       movdqa xmm0, [esi]           ; lee del origen
 *       movdqa [edi], xmm0           ; <<< murio, edi = 0
 *
 *   ⇒ El juego pide un buffer para escribirle los datos, NO LO CONSIGUE, **no mira
 *     el codigo de error** y copia igual. Esa es la otra mitad de lo que MANAGED
 *     hacia y que DEFAULT no da:
 *
 *       MANAGED -> vive en RAM, se puede bloquear y escribir; D3D lo sube solo
 *       DEFAULT -> vive en la placa; bloquear FALLA, salvo que sea DYNAMIC
 *
 * ⇒ `pool=2` agrega `D3DUSAGE_DYNAMIC`, que es lo que devuelve el permiso de
 *   escritura. Es el arreglo barato, y si funciona nos ahorra el caro.
 * ⚠ El caro, por si hace falta: replicar MANAGED de verdad — una copia en
 *   SYSTEMMEM que el juego llena y un `UpdateTexture` a la de DEFAULT.
 * ⚠ Y DYNAMIC tiene sus limites (no con mipmaps autogenerados, y la placa tiene
 *   que declarar D3DCAPS2_DYNAMICTEXTURES). Por eso se mide, no se supone.
 * ═══════════════════════════════════════════════════════════════════════════ */
#define USO_DYNAMIC 0x00000200

static DWORD arreglar_pool(DWORD pool, DWORD *uso)
{
    if (pool != POOL_MANAGED) return pool;
    g_pedidos_man++;
    if (!g_pool) return pool;          /* modo diagnostico: dejar que falle */
    g_traducidos++;
    if (g_pool >= 2 && uso) *uso |= USO_DYNAMIC;
    return POOL_DEFAULT;
}

static void anotar_fallo(DWORD pool_pedido, HRESULT hr, const char *que)
{
    if (hr == 0) return;
    if (pool_pedido == POOL_MANAGED) {
        g_fallos_man++;
        /* ⚠ solo las primeras, para no inundar: el numero total va en el resumen */
        if (g_fallos_man <= 3)
            apuntar("  [9Ex] %s en MANAGED fallo (hr=0x%x)  <- lo esperado si la"
                    " hipotesis es cierta", que, (unsigned)hr);
    } else {
        g_fallos_otros++;
        if (g_fallos_otros <= 3)
            apuntar("  [9Ex] %s en pool %d fallo (hr=0x%x)  <- ESTO NO ES MANAGED,"
                    " es otra cosa", que, (int)pool_pedido, (unsigned)hr);
    }
}

/* ═══════════════════════════════════════════════════════════════════════════
 * ★★ POR QUE SE ESPIA EL `LockRect` DE LAS TEXTURAS
 *
 *   Traducir MANAGED -> DEFAULT hace que `CreateTexture` deje de fallar... y ahi
 *   aparece el SEGUNDO problema, que es la otra mitad de lo que MANAGED hacia:
 *
 *       MANAGED  -> el juego puede BLOQUEAR la textura y escribirle los pixeles;
 *                   Direct3D guarda una copia en RAM y la sube a la placa solo.
 *       DEFAULT  -> vive en la placa. `LockRect` **falla** salvo que sea DYNAMIC.
 *
 *   ⇒ Si el motor bloquea, no mira el codigo de error y escribe igual, se muere.
 *     Este espia cuenta cuantos Lock se piden y cuantos fallan: si fallan, la
 *     traduccion simple no alcanza y hace falta el gestor de copias.
 *
 * ★ Se engancha UNA SOLA VEZ y sirve para todas: en Direct3D 9 todas las texturas
 *   comparten la misma tabla de metodos. `LockRect` es el 19 de IDirect3DTexture9.
 * ═══════════════════════════════════════════════════════════════════════════ */
typedef HRESULT (WINAPI *BLOQUEAR)(void *, UINT, void *, const void *, DWORD);
static BLOQUEAR g_lockrect_real = NULL;

/* ═══════════════════════════════════════════════════════════════════════════
 * ★★★★ EL SEGUNDO CRASH, RESUELTO POR LA PILA — 20-sep-2026
 *
 *   Con `pool=2` el cliente llego a la escena de bienvenida y murio en el cuadro
 *   409, «en tierra de nadie»: el EIP no era de ningun modulo. El rastreo de pila
 *   dio la direccion de retorno, y desensamblada era esto:
 *
 *       mov  eax, [esi]          ; esi = objeto COM -> eax = su VTABLE
 *       mov  eax, [eax + 0x2c]   ; metodo 11  (0x2C / 4 = 11)
 *       push 0                   ; Flags = 0
 *       push ecx                 ; &salida
 *       push edx                 ; tamaño = [ecx+0x60] << 5
 *       push 0                   ; offset = 0
 *       push esi                 ; this
 *       call eax                 ; <<< murio aca
 *
 *   ⇒ Metodo 11 con esa firma es **`IDirect3DVertexBuffer9::Lock`**.
 *
 * ★★ Y EL DETALLE QUE LO EXPLICA: **`Flags = 0`**. Un buffer creado con
 *   `D3DUSAGE_DYNAMIC` NO se puede bloquear asi — Direct3D exige `DISCARD` o
 *   `NOOVERWRITE`. Y `pool=2` le puso DYNAMIC a los CINCO creadores, buffers
 *   incluidos. El buffer se crea bien, el Lock falla, el juego no lo mira, y
 *   termina llamando por un puntero que nunca se lleno.
 *
 * ⇒ `pool=3` corrige el Lock al pasar: si el juego pide Flags=0 sobre un buffer
 *   nuestro, se le agrega `DISCARD`.
 * ⚠ DISCARD tira el contenido anterior. Es correcto **si el juego reescribe el
 *   buffer entero**, que es lo que hace acá (bloquea desde el offset 0 y por el
 *   tamaño completo, se ve en el desensamblado). Si alguna vez bloqueara un
 *   pedazo, esto le comeria el resto — por eso queda anotado.
 * ═══════════════════════════════════════════════════════════════════════════ */
#define LOCK_DISCARD 0x00002000

typedef HRESULT (WINAPI *BLOQUEARBUF)(void *, UINT, UINT, void **, DWORD);
static BLOQUEARBUF g_lockvb_real = NULL;
static BLOQUEARBUF g_lockib_real = NULL;

static HRESULT WINAPI mi_lockvb(void *buf, UINT offset, UINT tam, void **datos,
                                DWORD banderas)
{
    g_lock_buf++;
    if (g_pool >= 3 && banderas == 0) { banderas = LOCK_DISCARD; g_discard_puestos++; }
    HRESULT hr = g_lockvb_real(buf, offset, tam, datos, banderas);
    if (hr != 0) {
        g_lock_buf_malos++;
        if (g_lock_buf_malos <= 3)
            apuntar("  [9Ex] VertexBuffer::Lock fallo (hr=0x%x) offset %d tam %d"
                    " banderas 0x%x", (unsigned)hr, (int)offset, (int)tam,
                    (unsigned)banderas);
    }
    return hr;
}

static HRESULT WINAPI mi_lockib(void *buf, UINT offset, UINT tam, void **datos,
                                DWORD banderas)
{
    g_lock_buf++;
    if (g_pool >= 3 && banderas == 0) { banderas = LOCK_DISCARD; g_discard_puestos++; }
    HRESULT hr = g_lockib_real(buf, offset, tam, datos, banderas);
    if (hr != 0) {
        g_lock_buf_malos++;
        if (g_lock_buf_malos <= 3)
            apuntar("  [9Ex] IndexBuffer::Lock fallo (hr=0x%x) offset %d tam %d"
                    " banderas 0x%x", (unsigned)hr, (int)offset, (int)tam,
                    (unsigned)banderas);
    }
    return hr;
}

/* ⚠ Lock es el metodo 11 de las dos interfaces (lo confirma el `[eax+0x2c]` del
 *   desensamblado). Y todos los buffers comparten tabla, asi que se engancha una
 *   vez cada tipo. */
static void enganchar_buffer(void *buf, int es_indice)
{
    if (!buf) return;
    if (es_indice ? (g_lockib_real != NULL) : (g_lockvb_real != NULL)) return;
    void **vt = *(void ***)buf;
    if (!vt) return;
    if (es_indice) {
        g_lockib_real = (BLOQUEARBUF)cambiar_metodo(vt, 11, (void *)mi_lockib);
        apuntar("  [9Ex] espio el Lock de los IndexBuffer");
    } else {
        g_lockvb_real = (BLOQUEARBUF)cambiar_metodo(vt, 11, (void *)mi_lockvb);
        apuntar("  [9Ex] espio el Lock de los VertexBuffer");
    }
}

static HRESULT WINAPI mi_lockrect(void *tex, UINT nivel, void *bloqueado,
                                  const void *rect, DWORD banderas)
{
    g_locks++;
    HRESULT hr = g_lockrect_real(tex, nivel, bloqueado, rect, banderas);
    if (hr != 0) {
        g_locks_malos++;
        if (g_locks_malos <= 3)
            apuntar("  [9Ex] LockRect fallo (hr=0x%x)  <- la textura esta en DEFAULT y"
                    " el juego quiere escribirle", (unsigned)hr);
    }
    return hr;
}

static void enganchar_textura(void *tex)
{
    if (!tex || g_lockrect_real) return;
    void **vt = *(void ***)tex;
    if (!vt) return;
    g_lockrect_real = (BLOQUEAR)cambiar_metodo(vt, 19, (void *)mi_lockrect);
    apuntar("  [9Ex] espio tambien el LockRect de las texturas");
}

static HRESULT WINAPI mi_creartex(void *dev, UINT an, UINT al, UINT niveles,
                                  DWORD uso, DWORD formato, DWORD pool,
                                  void **salida, HANDLE *compartido)
{
    DWORD pedido = pool;
    DWORD pool2 = arreglar_pool(pool, &uso);
    HRESULT hr = g_creartex_real(dev, an, al, niveles, uso, formato,
                                 pool2, salida, compartido);
    anotar_fallo(pedido, hr, "CreateTexture");
    if (hr == 0 && salida && *salida) enganchar_textura(*salida);
    return hr;
}

static HRESULT WINAPI mi_crearvol(void *dev, UINT an, UINT al, UINT prof, UINT niveles,
                                  DWORD uso, DWORD formato, DWORD pool,
                                  void **salida, HANDLE *compartido)
{
    DWORD pedido = pool;
    DWORD pool2 = arreglar_pool(pool, &uso);
    HRESULT hr = g_crearvol_real(dev, an, al, prof, niveles, uso, formato,
                                 pool2, salida, compartido);
    anotar_fallo(pedido, hr, "CreateVolumeTexture");
    return hr;
}

static HRESULT WINAPI mi_crearcubo(void *dev, UINT lado, UINT niveles, DWORD uso,
                                   DWORD formato, DWORD pool, void **salida,
                                   HANDLE *compartido)
{
    DWORD pedido = pool;
    DWORD pool2 = arreglar_pool(pool, &uso);
    HRESULT hr = g_crearcubo_real(dev, lado, niveles, uso, formato,
                                  pool2, salida, compartido);
    anotar_fallo(pedido, hr, "CreateCubeTexture");
    return hr;
}

static HRESULT WINAPI mi_crearvb(void *dev, UINT largo, DWORD uso, DWORD fvf,
                                 DWORD pool, void **salida, HANDLE *compartido)
{
    DWORD pedido = pool;
    DWORD pool2 = arreglar_pool(pool, &uso);
    HRESULT hr = g_crearvb_real(dev, largo, uso, fvf, pool2, salida, compartido);
    anotar_fallo(pedido, hr, "CreateVertexBuffer");
    if (hr == 0 && salida && *salida) { enganchar_buffer(*salida, 0);
                                        anotar_buffer(*salida); }
    return hr;
}

static HRESULT WINAPI mi_crearib(void *dev, UINT largo, DWORD uso, DWORD formato,
                                 DWORD pool, void **salida, HANDLE *compartido)
{
    DWORD pedido = pool;
    DWORD pool2 = arreglar_pool(pool, &uso);
    HRESULT hr = g_crearib_real(dev, largo, uso, formato, pool2, salida, compartido);
    anotar_fallo(pedido, hr, "CreateIndexBuffer");
    if (hr == 0 && salida && *salida) { enganchar_buffer(*salida, 1);
                                        anotar_buffer(*salida); }
    return hr;
}

/* ★★ El contador de cuadros: la respuesta a «murio a los tres cuadros» deja de ser
 *   un recuerdo y pasa a ser un numero en el log. */
static HRESULT WINAPI mi_present(void *dev, const void *origen, const void *destino,
                                 HWND ventana, const void *region)
{
    g_cuadros++;
    cn_enviar_pendiente();                    /* ★ 16-oct: la caja negra de la vez anterior, al server */
    /* ⚠ el resumen es del testigo del 9Ex: sin 9Ex no hay nada que resumir, y ahora
     *   este hook tambien lo usa el cartel de metricas. */
    if (g_d3d9ex && g_cuadros == g_proximo_aviso) {
        resumen_moderno("al vuelo");
        /* cada vez mas espaciado: 60, 300, 1500, 7500... para que el log no crezca */
        g_proximo_aviso *= 5;
    }
    /* ★ el cartel va ACA: una vez por cuadro, y lo ultimo antes de mostrar */
    if (g_metricas) {
        static int avisado = 0;
        if (!avisado) { avisado = 1; apuntar("  [metricas] presenta por el DISPOSITIVO"); }

        /* ═══ ★★★ EL PULSO  (20-sep-2026) ═══════════════════════════════════
         *   Las lineas de diagnostico salian UNA sola vez, asi que no sabiamos si el
         *   hook SEGUIA corriendo en el lobby o dejaba de hacerlo. Y esa era justo la
         *   pregunta que quedaba: el `Clear` funciona, pero ¿se sigue llamando?
         *   ⇒ Un renglon cada ~600 cuadros (unos 10 s): si en el lobby DEJA de
         *     aparecer, el hook murio. Si sigue apareciendo, el dibujo se hace y algo
         *     lo tapa. Son dos cazas distintas y hay que saber cual. */
        /* ⚠ cada ~1 segundo, no cada 10: la pantalla de carga **pasa sola** y con el
         *   pulso espaciado no entraba ni un renglon en ella. Lo dijo anonimo03.
         *   El log crece ~60 renglones por minuto, que para un diagnostico esta bien. */
        /* ═══ ★★★ EL RECTANGULO DE ORIGEN  (20-sep-2026) ═══════════════════
         *   Todo lo demas ya estaba descartado por medicion: el hook corre, el Clear
         *   devuelve 0, el render target es el backbuffer, el viewport esta entero.
         *   O sea que **los pixeles se escriben y no se ven**.
         *
         *   ⇒ Y quedaba un sospechoso sin mirar: el juego crea un backbuffer de
         *     1920x1080 pero se juega en una ventana mas chica. `Present` recibe un
         *     `pSourceRect`, y si el juego le pasa una SUB-ZONA, todo lo que este
         *     fuera de esa zona **existe en el backbuffer pero no se muestra**.
         *     Nuestra esquina (8,8) seria justo eso.
         *
         *   ★ Se anota lo que viene, y se usa como desplazamiento: asi el cartel cae
         *     ADENTRO de lo que el juego efectivamente muestra. */
        LONG dx = 0, dy = 0;
        if (origen) {
            const RECTD3D *o = (const RECTD3D *)origen;
            dx = o->x1;
            dy = o->y1;
        }
        static long pulso = 0;
        if (++pulso % 60 == 0) {
            if (origen) {
                const RECTD3D *o = (const RECTD3D *)origen;
                apuntar("  [metricas] pulso %ld · backbuffer %ux%u · hr=0x%x"
                        " · ★ ORIGEN (%ld,%ld)-(%ld,%ld)  <- el juego muestra SOLO esto",
                        pulso, g_ancho, g_alto, (unsigned)g_ultimo_hr,
                        o->x1, o->y1, o->x2, o->y2);
            } else {
                /* ★★★ EL DATO QUE FALTABA: QUIEN presenta y SOBRE QUE dibujamos.
                 *   El magenta se ve al principio y despues NO, con un solo
                 *   CreateDevice, cero Reset, Clear en 0 y el hook corriendo. ⇒ Lo
                 *   unico que queda es que el dispositivo o la superficie cambien sin
                 *   que nos enteremos. Si estos punteros CAMBIAN en el lobby, ahi
                 *   esta; si no cambian, el problema no es de identidad. */
                void *rt_ahora = NULL, *bb_ahora = NULL;
                if (g_getrt) g_getrt(dev, 0, &rt_ahora);
                if (g_getbb) g_getbb(dev, 0, 0, 0, &bb_ahora);
                apuntar("  [metricas] pulso %ld · %ux%u · hr=0x%x · ventana %p"
                        " · dev %p · rt %p · bb %p%s",
                        pulso, g_ancho, g_alto, (unsigned)g_ultimo_hr, (void *)ventana,
                        dev, rt_ahora, bb_ahora,
                        (rt_ahora && bb_ahora && rt_ahora != bb_ahora)
                            ? "   ⛔ EL RT NO ES EL BACKBUFFER" : "");
                soltar_com(rt_ahora);
                soltar_com(bb_ahora);

                /* ═══ ★★★ ¿ES ESTA LA VENTANA QUE SE VE?  (20-sep-2026) ═══════
                 *   Fallan los DOS caminos a la vez —Direct3D y GDI— sobre la misma
                 *   ventana, y justo en el mismo punto donde se caia el 9Ex.
                 *   ⇒ La explicacion que queda es que **la ventana que tenemos no es
                 *     la que se muestra**. Si `g_ventana` deja de ser la del frente, o
                 *     se vuelve invisible, o su rectangulo se va a cero: ahi esta. */
                RECT rc = { 0, 0, 0, 0 };
                if (g_ventana) GetWindowRect(g_ventana, &rc);
                HWND frente = GetForegroundWindow();
                apuntar("  [metricas]   ventana: nuestra %p (%ldx%ld, visible=%d)"
                        " · al frente %p%s",
                        (void *)g_ventana, rc.right - rc.left, rc.bottom - rc.top,
                        g_ventana ? IsWindowVisible(g_ventana) : -1, (void *)frente,
                        (g_ventana && frente && g_ventana != frente)
                            ? "   ⛔ NO ES LA MISMA" : "");
            }
        }
        dibujar_cartel(dev, dx, dy);
    }
    HRESULT hrp = g_present_real(dev, origen, destino, ventana, region);

    /* ═══ ★★★ prueba=3 : GDI, y AHORA DESPUES DEL PRESENT ══════════════════
     *   ⛔ La primera version dibujaba GDI ANTES de `g_present_real`, o sea que el
     *     propio Present volcaba el backbuffer encima y le borraba el texto. La prueba
     *     estaba mal armada y el negativo no valia nada.
     *   ★ GDI pinta sobre la ventana YA presentada: si el juego tapa con GDI, nosotros
     *     tapamos despues que el. */
    if (g_met_prueba == 3 && g_ventana) {
        HDC dc = GetDC(g_ventana);
        if (dc) {
            char txt[64];
            wsprintfA(txt, "%d fps", g_fps_visible);
            SetBkMode(dc, TRANSPARENT);
            SetTextColor(dc, RGB(255, 40, 255));
            TextOutA(dc, 12, 10, txt, lstrlenA(txt));
            ReleaseDC(g_ventana, dc);
            static int dicho3 = 0;
            if (!dicho3) {
                dicho3 = 1;
                apuntar("  [metricas] ★ prueba=3: GDI DESPUES del Present. Si esto"
                        " sobrevive, el juego tapa con GDI y por eso Direct3D no"
                        " alcanzaba.");
            }
        }
    }
    return hrp;
}

/* ★★★ EL PRESENT DEL SWAPCHAIN — el 2do camino, el que usa el lobby.
 *
 *   ⚠ Ojo con la firma: `IDirect3DSwapChain9::Present` lleva un `dwFlags` DE MAS al
 *     final que el del dispositivo. Si se declara igual que el otro, la pila queda
 *     desalineada y el juego se cae — y pareceria un bug del dibujo.
 *
 *   ⚠ Y el cartel se dibuja sobre el DISPOSITIVO (`g_dev_cartel`), no sobre la cadena:
 *     `Clear` es del dispositivo. La cadena solo nos dice CUANDO. */
static HRESULT WINAPI mi_present_cadena(void *cadena, const void *origen,
                                        const void *destino, HWND ventana,
                                        const void *region, DWORD banderas)
{
    cn_enviar_pendiente();                    /* ★ 16-oct: en el lobby se presenta por acá */
    if (g_metricas && g_dev_cartel) {
        static int avisado = 0;
        if (!avisado) {
            avisado = 1;
            apuntar("  [metricas] ★★ AHORA presenta por el SWAPCHAIN — era ESTO: el"
                    " cartel dejaba de dibujarse porque el hook del dispositivo ya no"
                    " corria (lo destapo el parecido con el crash de 9Ex).");
        }
        dibujar_cartel(g_dev_cartel, 0, 0);
    }
    return g_scpresent_real(cadena, origen, destino, ventana, region, banderas);
}

/* ── cambiar UN puntero de la tabla de metodos del dispositivo ────────────── */
static void *cambiar_metodo(void **vt, int indice, void *nuevo)
{
    DWORD viejo = 0;
    if (!VirtualProtect(&vt[indice], sizeof(void *), PAGE_EXECUTE_READWRITE, &viejo))
        return NULL;
    void *real = vt[indice];
    vt[indice] = nuevo;
    VirtualProtect(&vt[indice], sizeof(void *), viejo, &viejo);
    return real;
}

/* ⚠⚠ LOS INDICES NO SE ADIVINAN. Son los de IDirect3DDevice9, en orden de la
 *   interfaz COM (los tres primeros son IUnknown):
 *       16 Reset · 17 Present · 18 GetBackBuffer
 *       23 CreateTexture · 24 CreateVolumeTexture · 25 CreateCubeTexture
 *       26 CreateVertexBuffer · 27 CreateIndexBuffer
 *   ★ El 16 ya se usa hoy para el Reset y esta comprobado en pantalla: es el ancla
 *     que dice que la numeracion de esta tabla es la correcta. */
static void enganchar_recursos(void *dev)
{
    if (!dev || !g_d3d9ex || g_present_real) return;
    void **vt = *(void ***)dev;
    if (!vt) return;
    g_dev = dev;                      /* para poder preguntar la VRAM libre */
    g_present_real   = (PRESENTAR)cambiar_metodo(vt, 17, (void *)mi_present);
    g_creartex_real  = (CREARTEXTURA)cambiar_metodo(vt, 23, (void *)mi_creartex);
    g_crearvol_real  = (CREARVOLUMEN)cambiar_metodo(vt, 24, (void *)mi_crearvol);
    g_crearcubo_real = (CREARCUBO)cambiar_metodo(vt, 25, (void *)mi_crearcubo);
    g_crearvb_real   = (CREARVB)cambiar_metodo(vt, 26, (void *)mi_crearvb);
    g_crearib_real   = (CREARIB)cambiar_metodo(vt, 27, (void *)mi_crearib);
    apuntar("  [9Ex] testigo puesto: cuento cuadros y recursos MANAGED"
            "  (pool=%d -> %s)", g_pool,
            g_pool ? "TRADUZCO a DEFAULT" : "solo cuento, dejo que fallen");
}


/* ── ★ crear el dispositivo por el camino moderno o por el de siempre ─────
 *
 * ⚠ `CreateDeviceEx` es el metodo **20** de IDirect3D9Ex (los 17 primeros son los de
 *   IDirect3D9, y despues van GetAdapterModeCountEx, EnumAdapterModesEx,
 *   GetAdapterDisplayModeEx, y recien ahi CreateDeviceEx).
 *
 * ★★ Y ACA ESTA LA RED DE SEGURIDAD MAS BARATA QUE TENEMOS: aunque la fabrica sea
 *   Ex, su `CreateDevice` de toda la vida SIGUE FUNCIONANDO y devuelve un dispositivo
 *   clasico. O sea que si el camino moderno falla, el reintento de mas abajo cae solo
 *   en el viejo sin que haya que hacer nada especial. El jugador nunca queda afuera.
 */
typedef HRESULT (WINAPI *CREARDISPOSITIVOEX)(void *, UINT, UINT, HWND, DWORD,
                                             PRESENT_PARAMS *, void *, void **);
static int g_fabrica_es_ex = 0;
static int g_dispositivo_es_ex = 0;

/* D3DDISPLAYMODEEX: 6 UINT. Size va primero y tiene que valer sizeof(struct). */
typedef struct {
    UINT Size, Width, Height, RefreshRate, Format, ScanLineOrdering;
} MODO_EX;

#define SWAP_FLIPEX 5

static HRESULT crear_dispositivo(void *self, UINT adaptador, UINT tipo, HWND ventana,
                                 DWORD banderas, PRESENT_PARAMS *pp, void **salida,
                                 int *salio_ex)
{
    *salio_ex = 0;
    if (!g_d3d9ex || !g_fabrica_es_ex)
        return g_createdevice_real(self, adaptador, tipo, ventana, banderas, pp, salida);

    void **vt = *(void ***)self;
    CREARDISPOSITIVOEX crear_ex = (CREARDISPOSITIVOEX)vt[20];

    /* ⚠ En pantalla completa, 9Ex quiere el modo descrito aparte. En ventana
     *   TIENE que ir NULL, o devuelve INVALIDCALL. */
    MODO_EX modo;
    void *pmodo = NULL;
    if (!pp->Windowed) {
        modo.Size = sizeof(MODO_EX);
        modo.Width = pp->BackBufferWidth;
        modo.Height = pp->BackBufferHeight;
        modo.RefreshRate = pp->FullScreen_RefreshRateInHz;
        modo.Format = pp->BackBufferFormat;
        modo.ScanLineOrdering = 1;          /* progresivo */
        pmodo = &modo;
    }

    HRESULT hr = crear_ex(self, adaptador, tipo, ventana, banderas, pp, pmodo, salida);
    if (hr == 0) {
        *salio_ex = 1;
        return hr;
    }
    apuntar("  [9Ex] CreateDeviceEx fallo (hr=0x%x): pruebo el CreateDevice clasico",
            (unsigned)hr);
    return g_createdevice_real(self, adaptador, tipo, ventana, banderas, pp, salida);
}


/* ⚠ declaradas aca: las dos se definen mas abajo, junto a `DllMain`, y el decouple
 *   las necesita antes. */
static int escribir_bytes(DWORD va, const BYTE *espera, const BYTE *nuevo, int n,
                          const char *que);
static int hz_del_monitor(HWND h);
/* ★★ 03-oct: la fluidez vive en fluidez.c (incluido mas abajo, usa la espera precisa) */
static int fluidez_iniciar(void);
static int flu_espera(void);

/* ═══ ★★★ EL DECOUPLE, DESDE LA DLL  ·  20-sep-2026 ═════════════════════════
 *
 * ⚠ POR QUE ACA Y NO EN `DllMain`:
 *   en `DllMain` todavia **no hay ventana**, y sin ventana no se sabe en que monitor
 *   se va a jugar. Y el decouple **depende del refresco**: a 60 Hz hay que NO ponerlo.
 *   ⇒ Se aplica en `CreateDevice`, que es el primer momento con ventana.
 *
 * ★ LAS DOS PIEZAS  (medidas con Frida el 20-sep; ver `el-decouple-son-tres-bytes`)
 *
 *   1. EL GATE DEL DIBUJO   0x004989B8   je 0x498b3e  ->  jmp 0x4989d4
 *      El motor descartaba las vueltas sin paso de logica. Soltarlo hace que dibuje
 *      en TODAS. ⛔ El `x60` (0x00410493) NO se toca: ese fabrica PASOS, no cuadros.
 *
 *   2. EL UPDATE-GATE       0x004989E8   -> cueva propia
 *      Con el dibujo suelto, `escena->vtbl[0x0C]()` (actualizar el mundo) corria 165
 *      veces por segundo y TODO lo que avanza "de a uno por llamada" se iba a 2,75x:
 *      el intro, el contador de combos, los fundidos. Gatearla los arregla juntos.
 *      ★ Y saltearla NO rompe el dibujo: pasa ANTES del `BeginScene` (0x00498A2E), y
 *        en Direct3D 9 no se puede dibujar fuera de Begin/EndScene.
 *
 * ⚠ LA CUEVA ES NUESTRA (`VirtualAlloc`), no del exe: la `0x0066B200` queda libre.
 */
static void escribir_u32(BYTE *d, DWORD v)
{
    d[0] = (BYTE)(v & 0xFF);         d[1] = (BYTE)((v >> 8) & 0xFF);
    d[2] = (BYTE)((v >> 16) & 0xFF); d[3] = (BYTE)((v >> 24) & 0xFF);
}

static void aplicar_decouple(HWND ventana)
{
    static int hecho = 0;
    if (hecho || !(g_gate || g_mundo || g_fluidez)) return;
    hecho = 1;

    int hz = hz_del_monitor(ventana);
    if (hz && hz < g_hzminimo) {
        apuntar("  [motor] el monitor esta a %d Hz (minimo %d): el decouple NO se"
                " aplica — ahi frena el mundo 15%% y no da nada", hz, g_hzminimo);
        return;
    }
    apuntar("  [motor] monitor a %d Hz: aplico el decouple", hz);

    /* ── 1 · el gate del dibujo ──────────────────────────────────────────── */
    /* ★ la fluidez lo NECESITA: sin el dibujo suelto no hay nada que extrapolar */
    if (g_gate || g_fluidez) {
        BYTE esp[6] = { 0x0F, 0x84, 0x80, 0x01, 0x00, 0x00 };   /* je  0x498b3e  */
        BYTE nue[6] = { 0xE9, 0x17, 0x00, 0x00, 0x00, 0x90 };   /* jmp 0x4989d4  */
        if (escribir_bytes(0x004989B8, esp, nue, 6, "gate del dibujo"))
            apuntar("  [motor] ★ el dibujo va en CADA vuelta del bucle");
    }

    /* ── 2 · ★★ 03-oct: LA FLUIDEZ (fluidez.c) reemplaza al update-gate ───────
     *   ⛔ el update-gate de abajo NO frenaba "el mundo": frenaba el DIBUJO DE LA
     *     ESCENA (vtbl[3] hace Clear+BeginScene+escena+EndScene; ver
     *     LA_MATEMATICA_DEL_MOTOR.md). Queda sólo de respaldo, si la fluidez no entra. */
    if (g_fluidez && fluidez_iniciar()) return;

    /* ── 2b · el update-gate viejo, con cueva propia ─────────────────────── */
    if (g_mundo) {
        g_cueva = VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE,
                               PAGE_EXECUTE_READWRITE);
        if (!g_cueva) { apuntar("  [motor] ⛔ no pude reservar la cueva"); return; }
        DWORD c = (DWORD)(ULONG_PTR)g_cueva;
        BYTE cuerpo[25];
        int i = 0;
        /* +0  cmp dword [0x009D43B4], 0   ¿hubo paso de logica en esta vuelta? */
        cuerpo[i++] = 0x83; cuerpo[i++] = 0x3D;
        escribir_u32(cuerpo + i, 0x009D43B4); i += 4;
        cuerpo[i++] = 0x00;
        /* +7  je +11  -> saltar */
        cuerpo[i++] = 0x74; cuerpo[i++] = 0x0B;
        /* +9  mov ecx,[ebp+0xaffc]   (lo que reemplazamos en el sitio) */
        cuerpo[i++] = 0x8B; cuerpo[i++] = 0x8D;
        cuerpo[i++] = 0xFC; cuerpo[i++] = 0xAF; cuerpo[i++] = 0x00; cuerpo[i++] = 0x00;
        /* +15 jmp 0x004989EE   (el camino de siempre) */
        cuerpo[i++] = 0xE9;
        escribir_u32(cuerpo + i, 0x004989EE - (c + 15 + 5)); i += 4;
        /* +20 saltar: jmp 0x004989FD
         * ⚠ 0x4989FD y NO 0x4989F5: es DESPUES del `test eax,eax / jl`. Si no se llamo
         *   a la funcion, `eax` trae basura y ese `jl` no se puede dejar corriendo. */
        cuerpo[i++] = 0xE9;
        escribir_u32(cuerpo + i, 0x004989FD - (c + 20 + 5)); i += 4;

        CopyMemory(g_cueva, cuerpo, sizeof(cuerpo));

        BYTE esp[6] = { 0x8B, 0x8D, 0xFC, 0xAF, 0x00, 0x00 };
        BYTE nue[6];
        nue[0] = 0xE9;
        escribir_u32(nue + 1, c - (0x004989E8 + 5));
        nue[5] = 0x90;
        if (escribir_bytes(0x004989E8, esp, nue, 6, "update-gate")) {
            apuntar("  [motor] ★ el mundo se actualiza 60 veces por segundo"
                    " (cueva en 0x%08X)", c);
        } else {
            /* ⚠ si el sitio no era el esperado, la cueva no sirve para nada: se suelta.
             *   Dejarla reservada seria una fuga silenciosa. */
            VirtualFree(g_cueva, 0, MEM_RELEASE);
            g_cueva = NULL;
        }
    }
}

/* ── nuestro CreateDevice: mira los parametros al pasar ──────────────────── */
static HRESULT WINAPI mi_createdevice(void *self, UINT adaptador, UINT tipo,
                                      HWND ventana, DWORD banderas,
                                      PRESENT_PARAMS *pp, void **salida)
{
    /* ★ la ventana del juego: la de los parametros si la trae, si no la del foco.
     * ⚠ Se engancha ACA y no antes porque recien en este momento existe, y porque asi
     *   nuestro WndProc queda POR ENCIMA del que instala Direct3D. */
    if (pp && pp->hDeviceWindow) enganchar_ventana(pp->hDeviceWindow);
    else if (ventana)            enganchar_ventana(ventana);

    /* ★ y le sacamos los motivos para que le nieguen el plano de hardware.
     * ⚠ va aparte de `enganchar_ventana` a proposito: aquella se va de largo si
     *   `altenter=0`, y esto no tiene nada que ver con el alt+enter. */
    preparar_para_plano(pp && pp->hDeviceWindow ? pp->hDeviceWindow : ventana);
    /* ★ el decouple depende del REFRESCO, y recien aca hay ventana con la que
     *   saber en que monitor se juega. */
    aplicar_decouple(pp && pp->hDeviceWindow ? pp->hDeviceWindow : ventana);

    if (pp)
        apuntar("CreateDevice: el juego pide %dx%d  formato %d  %s  msaa %d  refresco %d",
                (int)pp->BackBufferWidth, (int)pp->BackBufferHeight,
                (int)pp->BackBufferFormat,
                pp->Windowed ? "en ventana" : "PANTALLA COMPLETA",
                (int)pp->MultiSampleType, (int)pp->FullScreen_RefreshRateInHz);

    if (!g_activo || !pp) {
        apuntar("  (proxy apagado o sin parametros: pasa de largo)");
        return g_createdevice_real(self, adaptador, tipo, ventana, banderas, pp, salida);
    }

    /* ★★★ ARRANCAR SIEMPRE EN VENTANA  (20-sep-2026, y no es un capricho)
     *
     *   MEDIDO, y **sin nuestra DLL de por medio**: con `FULLSCREEN = 1` en el
     *   `Config.ini` y sin el shim `DWM8And16BitMitigation`, el cliente **no abre**.
     *   Sale un cuadro "ERROR" y la ventana del juego queda oculta para siempre.
     *
     *   ⇒ Y eso convierte al alt+enter en una trampa: entrás a pantalla completa, salís,
     *     el juego guarda `FULLSCREEN=1`, y la próxima vez **ya no abre** hasta que
     *     alguien edite el archivo a mano. Un jugador quedaría afuera sin saber por qué.
     *
     *   ★ Lo bueno: son DOS CAMINOS distintos de Direct3D y sólo uno está roto.
     *       CreateDevice con pantalla completa  -> falla sin el shim
     *       Reset a pantalla completa           -> funciona (es lo que hace el alt+enter,
     *                                              comprobado por anonimo03)
     *   ⇒ Se arranca siempre en ventana, y el que quiera pantalla completa la tiene con
     *     alt+enter, que sí anda. El juego nunca deja de abrir.
     */
    /* ⚠⚠ ACÁ HUBO UN FORZADO DE VENTANA Y SE SACÓ (20-sep-2026, misma noche).
     *   Se puso cuando parecía que arrancar en pantalla completa era imposible sin el
     *   shim. Después se encontró el motivo real —el juego pedía el modo a **16 bits**—
     *   y se corrigió más arriba, así que el arranque en pantalla completa ya funciona y
     *   forzar ventana sería pisarle al jugador su elección del `Config.ini`.
     *   ⇒ Si igual fallara, abajo está la red de seguridad que lo abre en ventana. */

    int salio_ex = 0;

    if (g_msaa <= 0) {
        HRESULT hr0 = crear_dispositivo(self, adaptador, tipo, ventana, banderas,
                                        pp, salida, &salio_ex);
        g_dispositivo_es_ex = salio_ex;
        if (hr0 == 0 && salida && *salida
            && pp->BackBufferWidth > 16 && pp->BackBufferHeight > 16) {
            if (salio_ex) enganchar_recursos(*salida);
            g_ancho = pp->BackBufferWidth;   /* ★ el cartel recorta contra esto */
            g_alto = pp->BackBufferHeight;
            cielo_ajustar(g_ancho, g_alto);   /* ★ 26-oct: el cielo de las pistas a la medida de la pantalla */
            enganchar_dispositivo(*salida);
        }
        return hr0;
    }

    PRESENT_PARAMS copia = *pp;     /* ★ para poder volver atras si falla */

    /* ★★★ FLIPEX: el modo que saca al compositor del medio. Solo existe en 9Ex.
     * ⛔⛔ Y CHOCA DE FRENTE CON EL MSAA, que es «lo unico que el ojo distingue»:
     *   FLIPEX **no admite backbuffer multisample**. Por eso se pide aparte y no
     *   viene con `d3d9ex=1`: primero hay que saber si el cliente sobrevive a 9Ex,
     *   y recien despues decidir que hacer con el antialiasing (se resuelve
     *   dibujando a un render target multisample y resolviendolo al backbuffer,
     *   pero eso es otro trabajo).
     * ⚠ FLIPEX ademas exige al menos 2 backbuffers y prohibe LOCKABLE. */
    if (g_flipex) {
        pp->SwapEffect = SWAP_FLIPEX;
        if (pp->BackBufferCount < 2) pp->BackBufferCount = 2;
        pp->Flags &= ~FLAG_LOCKABLE_BACKBUFFER;
        pp->MultiSampleType = 0;
        pp->MultiSampleQuality = 0;
        apuntar("  [9Ex] pido FLIPEX (%d backbuffers) — ⚠ el MSAA queda APAGADO,"
                " FLIPEX no lo admite", (int)pp->BackBufferCount);
    }

    /* ⚠ LAS TRES VAN JUNTAS, NO SON OPCIONALES:
     *   en Direct3D 9 un backbuffer LOCKABLE **prohibe** el multisampling, y pedir las
     *   dos cosas devuelve D3DERR_INVALIDCALL (0x8876086C) -> el juego muere al arrancar
     *   con "No se puede crear dispositivo de video". Ya pasó, está medido.
     * ⚠⚠ Y NO SE APLICAN SI SE PIDIO FLIPEX: le pisarian el SwapEffect y volveriamos
     *   al camino del compositor sin que nada lo avisara. */
    if (!g_flipex) {
        pp->MultiSampleType    = (UINT)g_msaa;
        pp->MultiSampleQuality = 0;
        pp->SwapEffect         = SWAP_DISCARD;
        pp->Flags             &= ~FLAG_LOCKABLE_BACKBUFFER;
    }

    HRESULT hr = crear_dispositivo(self, adaptador, tipo, ventana, banderas,
                                   pp, salida, &salio_ex);
    if (hr == 0) {
        g_dispositivo_es_ex = salio_ex;
        /* ★★ ESTA ES LA LINEA QUE CONTESTA "¿esta puesto el antialiasing?" */
        apuntar("  OK 1er intento: %s%s, SwapEffect %s, sin LOCKABLE_BACKBUFFER",
                g_flipex ? "SIN MSAA (lo pide FLIPEX)" : "MSAA aplicado",
                salio_ex ? "  ·  DISPOSITIVO 9Ex" : "  ·  dispositivo clasico",
                g_flipex ? "FLIPEX" : "DISCARD");
        marcar_titulo(g_ventana);
        if (salio_ex && salida && *salida
            && pp->BackBufferWidth > 16 && pp->BackBufferHeight > 16)
            enganchar_recursos(*salida);
        /* ★ y acá se engancha el Reset: sin esto, el juego borra el antialiasing la
         *   primera vez que rehace la pantalla.
         *
         * ⛔⛔ PERO SÓLO EL DISPOSITIVO DE VERDAD. Las herramientas de medición crean un
         *   dispositivo DE MENTIRA de 1x1 para poder leer la tabla de métodos (la
         *   "puerta de atrás" de `carga.js`). Si se engancha ése, el real queda sin
         *   enganchar y el `Reset` no pasa nunca por acá — que es exactamente lo que
         *   hizo fallar la primera prueba del alt+enter.
         *   ⚠ Y no alcanza con "el primero": el de mentira se crea ANTES. Se distingue
         *     por el tamaño. */
        if (salida && *salida && pp->BackBufferWidth > 16 && pp->BackBufferHeight > 16)
            g_ancho = pp->BackBufferWidth;   /* ★ el cartel recorta contra esto */
            g_alto = pp->BackBufferHeight;
            cielo_ajustar(g_ancho, g_alto);   /* ★ 26-oct: el cielo de las pistas a la medida de la pantalla */
            enganchar_dispositivo(*salida);
        return hr;
    }

    /* ★★ EL RESPALDO QUE NO PUEDE FALTAR
     * Si la placa no admite 8x —o cualquier otra cosa sale mal— se vuelve EXACTAMENTE a
     * lo que pedia el juego y se reintenta. Un jugador nunca se queda sin poder entrar
     * por culpa de una mejora nuestra. */
    apuntar("  ! %s fue rechazado (hr=0x%x): reintento con lo que pedia el juego",
            g_flipex ? "FLIPEX" : "el MSAA", (unsigned)hr);
    *pp = copia;
    hr = crear_dispositivo(self, adaptador, tipo, ventana, banderas, pp, salida,
                           &salio_ex);
    if (hr == 0) {
        g_dispositivo_es_ex = salio_ex;
        apuntar("  OK 2do intento: el juego abre SIN antialiasing%s",
                salio_ex ? "  ·  DISPOSITIVO 9Ex" : "");
        marcar_titulo(g_ventana);
        if (salida && *salida && pp->BackBufferWidth > 16 && pp->BackBufferHeight > 16) {
            if (salio_ex) enganchar_recursos(*salida);
            g_ancho = pp->BackBufferWidth;   /* ★ el cartel recorta contra esto */
            g_alto = pp->BackBufferHeight;
            cielo_ajustar(g_ancho, g_alto);   /* ★ 26-oct: el cielo de las pistas a la medida de la pantalla */
            enganchar_dispositivo(*salida);
        }
        return hr;
    }

    /* ★★★ EL TERCER INTENTO, Y ES EL QUE EVITA UN BLOQUEO GRAVE  (20-sep-2026)
     *   El juego guarda en `Config.ini` que salió en pantalla completa (`FULLSCREEN=1`),
     *   así que al abrir de nuevo pide pantalla completa **desde el arranque**. Si esa
     *   combinación no se puede crear, los dos intentos de arriba fallan y el jugador ve
     *   "error al crear video" — y **no puede volver a entrar nunca más**, porque el
     *   archivo sigue diciendo pantalla completa. Pasó acá mismo.
     *   ⇒ Último recurso: forzar VENTANA. Siempre se puede crear, el jugador entra, y
     *     desde adentro puede volver a pantalla completa con alt+enter si quiere. */
    if (!pp->Windowed) {
        apuntar("  ! tampoco: ultimo recurso, forzar VENTANA para que el juego abra");
        pp->Windowed = TRUE;
        pp->FullScreen_RefreshRateInHz = 0;
        pp->PresentationInterval = 0;
        hr = g_createdevice_real(self, adaptador, tipo, ventana, banderas, pp, salida);
        if (hr == 0 && salida && *salida
            && pp->BackBufferWidth > 16 && pp->BackBufferHeight > 16) {
            apuntar("  OK 3er intento: abrio en ventana");
            marcar_titulo(g_ventana);
            g_ancho = pp->BackBufferWidth;   /* ★ el cartel recorta contra esto */
            g_alto = pp->BackBufferHeight;
            cielo_ajustar(g_ancho, g_alto);   /* ★ 26-oct: el cielo de las pistas a la medida de la pantalla */
            enganchar_dispositivo(*salida);
        }
    }
    if (hr != 0) apuntar("  !! NO se pudo crear el dispositivo (hr=0x%x)", (unsigned)hr);
    return hr;
}

/* ── cambiar el puntero 16 de la tabla de metodos (CreateDevice) ─────────── */
static void enganchar_fabrica(void *fabrica)
{
    if (!fabrica || g_createdevice_real) return;
    void **vt = *(void ***)fabrica;
    if (!vt) return;

    /* ⚠ la tabla vive en memoria de SOLO LECTURA: hay que abrirla para escribir y
     *   dejarla como estaba. Sin esto, el proceso muere al tocarla. */
    DWORD viejo = 0;
    if (!VirtualProtect(&vt[16], sizeof(void *), PAGE_EXECUTE_READWRITE, &viejo)) return;
    g_createdevice_real = (CREARDISPOSITIVO)vt[16];
    vt[16] = (void *)mi_createdevice;
    VirtualProtect(&vt[16], sizeof(void *), viejo, &viejo);
}

/* ═══════════════════════════════════════════════════════════════════════════
 * ★★★★ EL 16 QUE QUEDÓ SIN PARCHEAR — lo que rompía la pantalla completa
 *
 *   MEDIDO el 20-sep-2026, espiando lo que el juego le pide a Windows al arrancar con
 *   `FULLSCREEN = 1`:
 *
 *       ChangeDisplaySettingsExA   1024x768  **16 BITS**  165Hz  ->  ⛔ BADMODE
 *       ChangeDisplaySettingsA     1024x768  **16 BITS**  165Hz  ->  ⛔ BADMODE
 *       ChangeDisplaySettingsExA   1024x768  **16 BITS**    0Hz  ->  ⛔ BADMODE
 *
 *   **El juego pide pantalla completa a 16 bits de color.** Windows moderno no tiene un
 *   solo modo de 16 bits —los 14 que el propio juego enumeró son todos de 32— así que lo
 *   rechaza, y el motor muestra "No se puede crear dispositivo de vídeo" **sin llegar a
 *   tocar Direct3D** (comprobado: ni un `CreateDevice`, ni una consulta).
 *
 * ★★ Y ESTO CIERRA UNA HISTORIA VIEJA DEL PROYECTO
 *   `documentacion/VIDEO_Y_RESOLUCIONES.md` dice: *"el exe NECESITABA el shim porque
 *   pedía color de 16 bits; eso ya está arreglado EN EL EXE (dos bytes de D3DFORMAT)"*.
 *   ⇒ **Ese arreglo quedó incompleto.** Se corrigió el `D3DFORMAT` de Direct3D, pero
 *     quedó **otro 16 sin tocar**: el `dmBitsPerPel` del cambio de modo de pantalla. Son
 *     dos rutas distintas y sólo se parcheó una. Por eso el shim seguía haciendo falta.
 *
 * ★ Acá se corrige al vuelo: 16 -> 32. Y se le saca el pedido de frecuencia, porque el
 *   primer intento pide **165 Hz** a 1024x768 y ese modo tampoco tiene por qué existir;
 *   sin ese campo, Windows elige la frecuencia que corresponda.
 *
 * ⚠ Se parchea la TABLA DE IMPORTACIONES del exe, no el código: `ChangeDisplaySettingsA`
 *   está ahí (IAT 0x8733cc). Es reversible y no escribe una sola instrucción.
 * ⚠ `ChangeDisplaySettingsExA` no hace falta engancharla: la versión sin `Ex` llama a la
 *   `Ex` por dentro de user32, así que la corrección ya va aplicada.
 * ═══════════════════════════════════════════════════════════════════════════ */

/* ⚠ `DM_BITSPERPEL` y `DM_DISPLAYFREQUENCY` ya vienen de <wingdi.h>: definirlos otra vez
 *   sólo genera ruido al compilar. Se usan los del sistema.
 *
 * offsets de DEVMODEA: dmDeviceName[32] CHAR ⇒ dmFields en 40, dmBitsPerPel en 104 */
#define DEVMODE_CAMPOS   40
#define DEVMODE_BITS    104
#define DEVMODE_HZ      120

typedef LONG (WINAPI *CAMBIARMODO)(void *, DWORD);
static CAMBIARMODO g_cambiar_real = NULL;
static int g_arreglos_de_bits = 0;

static LONG WINAPI mi_cambiar_modo(void *devmode, DWORD banderas)
{
    if (devmode && g_activo) {
        BYTE *p = (BYTE *)devmode;
        DWORD *campos = (DWORD *)(p + DEVMODE_CAMPOS);
        DWORD *bits   = (DWORD *)(p + DEVMODE_BITS);
        DWORD *hz     = (DWORD *)(p + DEVMODE_HZ);
        if ((*campos & DM_BITSPERPEL) && *bits > 0 && *bits < 32) {
            DWORD antes = *bits;
            *bits = 32;
            /* ⚠ y fuera la frecuencia: el juego pide 165 Hz a 1024x768 y eso puede no
             *   existir. Sin el campo, lo elige Windows. */
            *campos &= ~DM_DISPLAYFREQUENCY;
            *hz = 0;
            g_arreglos_de_bits++;
            /* ⚠ el log va en ASCII puro: se lee desde una consola que en esta maquina
             *   esta en cp949, y un simbolo raro la hace fallar. */
            apuntar("  * modo de pantalla: el juego pidio %d BITS de color -> se lo cambie "
                    "a 32 y le saque la frecuencia  (arreglo nro %d)",
                    (int)antes, g_arreglos_de_bits);
        }
    }
    LONG r = g_cambiar_real(devmode, banderas);
    if (r != 0) apuntar("  ! ChangeDisplaySettings devolvio %d", (int)r);
    return r;
}

/* ── cambiar un puntero de la tabla de importaciones del exe ─────────────── */
static void *parchear_iat(const char *dll, const char *funcion, void *nuevo)
{
    HMODULE base = GetModuleHandleA(NULL);
    if (!base) return NULL;
    BYTE *b = (BYTE *)base;
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER *)b;
    if (dos->e_magic != IMAGE_DOS_SIGNATURE) return NULL;
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(b + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE) return NULL;

    DWORD rva = nt->OptionalHeader
                  .DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT].VirtualAddress;
    if (!rva) return NULL;
    IMAGE_IMPORT_DESCRIPTOR *imp = (IMAGE_IMPORT_DESCRIPTOR *)(b + rva);

    for (; imp->Name; imp++) {
        const char *nombre = (const char *)(b + imp->Name);
        if (lstrcmpiA(nombre, dll) != 0) continue;
        IMAGE_THUNK_DATA *orig = (IMAGE_THUNK_DATA *)(b + imp->OriginalFirstThunk);
        IMAGE_THUNK_DATA *real = (IMAGE_THUNK_DATA *)(b + imp->FirstThunk);
        if (!imp->OriginalFirstThunk) orig = real;
        for (; orig->u1.AddressOfData; orig++, real++) {
            if (orig->u1.Ordinal & IMAGE_ORDINAL_FLAG) continue;
            IMAGE_IMPORT_BY_NAME *n =
                (IMAGE_IMPORT_BY_NAME *)(b + orig->u1.AddressOfData);
            if (lstrcmpA((const char *)n->Name, funcion) != 0) continue;
            DWORD prot = 0;
            if (!VirtualProtect(&real->u1.Function, sizeof(void *),
                                PAGE_READWRITE, &prot)) return NULL;
            void *viejo = (void *)real->u1.Function;
            real->u1.Function = (ULONG_PTR)nuevo;
            VirtualProtect(&real->u1.Function, sizeof(void *), prot, &prot);
            return viejo;
        }
    }
    return NULL;
}

/* ── la unica funcion que el exe le pide a d3d9.dll ──────────────────────── */
__declspec(dllexport) void *WINAPI Direct3DCreate9(UINT version)
{
    /* ★ Acá y no en DllMain: cuando el juego llama a esto, la tabla de importaciones ya
     *   está armada y el exe completamente cargado. En DllMain todavía no lo está. */
    if (!g_cambiar_real) {
        g_cambiar_real = (CAMBIARMODO)parchear_iat("USER32.dll",
                                                   "ChangeDisplaySettingsA",
                                                   (void *)mi_cambiar_modo);
    }
    void *fabrica = NULL;

    /* ★★★ LA PUERTA A LA PARTE MODERNA, y es una sola linea de idea:
     *   `IDirect3D9Ex` **hereda** de `IDirect3D9`. Sus 17 primeros metodos son los
     *   mismos, en el mismo orden. O sea que se le puede devolver al juego una
     *   fabrica Ex y el juego la usa como la de siempre, sin enterarse. Ahi es
     *   donde entra la parte moderna sin tocar un byte del exe.
     * ⚠ `Direct3DCreate9Ex` puede no existir (Windows XP) o fallar: si pasa
     *   cualquiera de las dos, se cae sola al camino de siempre. */
    if (g_d3d9ex && g_crear_ex) {
        void *fab_ex = NULL;
        HRESULT hr = g_crear_ex(version, &fab_ex);
        if (hr == 0 && fab_ex) {
            fabrica = fab_ex;
            g_fabrica_es_ex = 1;
            apuntar("Direct3DCreate9Ex(%d) -> ok  ★ FABRICA MODERNA"
                    "  (flipex=%d pool=%d)", version, g_flipex, g_pool);
        } else {
            apuntar("Direct3DCreate9Ex(%d) fallo (hr=0x%x): sigo con la de siempre",
                    version, (unsigned)hr);
        }
    } else if (g_d3d9ex && !g_crear_ex) {
        apuntar("⚠ este Windows no tiene Direct3DCreate9Ex: sigo con la de siempre");
    }

    if (!fabrica) {
        if (!g_crear) return NULL;
        fabrica = g_crear(version);
        apuntar("Direct3DCreate9(%d) -> %s", version, fabrica ? "ok" : "NULO");
    }
    if (fabrica) enganchar_fabrica(fabrica);
    return fabrica;
}


/* ═══ ★★★ LA ESPERA PRECISA, DESDE LA DLL  ·  20-sep-2026 ═══════════════════
 *
 *   Port de `ritmo.js` a C. Era la ultima pieza que seguia necesitando Frida.
 *
 * ⛔⛔ POR QUE NO ES OPCIONAL, y lo destapo anonimo03 probando el launcher offline:
 *   *"el local funciona perfecto en 60 y 120; el offline en 120 da tirones"*.
 *   La unica diferencia entre los dos era **esta pieza**.
 *   ⇒ **`Sleep(1)` SIN la espera precisa es PEOR que no tocar el Sleep**: el bucle
 *     gira mucho y despierta cuando Windows quiere. Coincide con dos cosas ya
 *     anotadas: `PARCHES_EXE.md §2` (un Sleep->1 revertido por jitter) y la memoria
 *     «el Sleep del motor lo frena a 57».
 *   ⇒ Por eso `aplicar_motor` se NIEGA a bajar el Sleep si el ritmo esta apagado.
 *
 * ★ QUE HACE: el motor duerme un rato FIJO en cada vuelta y se despierta cuando el
 *   planificador quiere. Aca se calcula **el instante exacto en que toca el proximo
 *   paso** y se espera hasta ahi: casi todo durmiendo, y el ultimo tramito a mano.
 *
 *       el paso N toca cuando   t >= inicio + techo(N * 1000 / 60)
 *
 * ★★ Y el tramo final espera **la condicion que el motor va a evaluar** —
 *   `timeGetTime()`, que avanza de a milisegundos enteros— y NO un instante del reloj
 *   fino. Los bordes de los dos relojes no estan alineados, y esperar el instante
 *   "matematicamente correcto" se comia parte de la precision ganada.
 *
 * ⚠ LA GUARDIA QUE APAGA EL PARCHE SOLO: si el motor se atrasa o el reloj se reinicia
 *   (el resync de 0x0040FA70), `falta` se va de rango. Ahi se deja pasar el Sleep de
 *   fabrica en vez de inventar. Se CUENTA, para poder cruzarlo con lo que ve el ojo.
 *
 * ⛔ Y solo se toca **el Sleep DEL GATE**: el juego duerme en otros lados y esos no
 *   son asunto nuestro. Se distinguen por la direccion de retorno.
 */
#define VA_TRAS_SLEEP_GATE 0x004104B4   /* la instruccion despues del Sleep del gate */
#define VA_TRAS_SLEEP_FOCO 0x004985CD   /* ... y despues del Sleep de perder el foco */
#define VA_HECHOS          0x00931584   /* el contador de pasos del motor            */
#define VA_INICIO          0x00931588   /* cuando arranco a contar                   */

typedef void  (WINAPI *DORMIR)(DWORD);
typedef DWORD (WINAPI *RELOJMS)(void);

static DORMIR   g_sleep_real = NULL;
static RELOJMS  g_timeGetTime = NULL;
static LARGE_INTEGER g_qpf;
static BYTE    *g_base_exe = NULL;
static double   g_giro_ms = 1.5;        /* el tramo final a mano. ⚠ girar quema CPU  */

/* contadores, para el log: dicen si el parche esta actuando o se apago solo */
static long g_r_veces = 0, g_r_tarde = 0, g_r_fuera = 0, g_r_foco = 0;

static double ms_fino(void)
{
    LARGE_INTEGER t;
    QueryPerformanceCounter(&t);
    return (double)t.QuadPart * 1000.0 / (double)g_qpf.QuadPart;
}

static void WINAPI mi_sleep(DWORD n)
{
    DWORD ra = (DWORD)(ULONG_PTR)__builtin_return_address(0);
    DWORD va = ra - (DWORD)(ULONG_PTR)g_base_exe + 0x400000;

    /* ★ el Sleep de perder el foco: son 1000 ms y corre DOS veces seguidas, o sea
     *   DOS SEGUNDOS congelado cada vez que se mira otra ventana. */
    if (va == VA_TRAS_SLEEP_FOCO) {
        g_r_foco++;
        g_sleep_real(g_siesta_ms > 0 ? (DWORD)g_siesta_ms : 1);
        return;
    }
    /* ⛔ cualquier otro Sleep del juego no es asunto nuestro */
    if (va != VA_TRAS_SLEEP_GATE) { g_sleep_real(n); return; }
    /* ★ 17-oct: la caja negra de la vez anterior, al server. Va ACÁ (el Sleep del bucle: el hilo del juego, una vez
     *   por vuelta, siempre): los Present sólo se enganchan con el cartel de fps o el 9Ex, y sin eso no salía nunca. */
    cn_enviar_pendiente();

    /* ★★ 03-oct: en la carrera con la fluidez, el bucle lo frena el Present (vsync),
     *   no el proximo paso. Ver fluidez.c, pieza 3. */
    if (flu_espera()) return;

    DWORD ahora  = g_timeGetTime();
    DWORD inicio = *(volatile DWORD *)(g_base_exe + (VA_INICIO - 0x400000));
    DWORD hechos = *(volatile DWORD *)(g_base_exe + (VA_HECHOS - 0x400000));
    /* el paso N toca cuando  t >= inicio + techo(N * 1000 / 60) */
    DWORD objetivo = inicio + (DWORD)(((hechos + 1) * 1000 + 59) / 60);
    long falta = (long)(objetivo - ahora);

    /* ⚠ la guardia: fuera de rango = el motor se atraso o hubo resync. No inventar. */
    if (falta < -1000 || falta > 1000) { g_r_fuera++; g_sleep_real(n); return; }

    g_r_veces++;
    if (falta <= 0) { g_r_tarde++; return; }      /* ya paso: volver ya mismo */

    long dormir = falta - (long)g_giro_ms;
    if (dormir > 0) g_sleep_real((DWORD)dormir);

    /* ★★ el tramo a mano: se espera LA CONDICION QUE EL MOTOR VA A EVALUAR.
     * ⚠ con red de seguridad por el reloj fino, para no girar de mas si algo se cuelga. */
    double t0 = ms_fino(), techo = t0 + (double)falta + 4.0;
    while (g_timeGetTime() < objetivo && ms_fino() < techo) { /* girando */ }
}

/* ★★ 13-oct: el juego SIN FOCO iba a ~35 pasos/s en vez de 60 (QA de 12 juegos: 9.052 pasos el que
 *   tenía foco contra ~5.750 los tapados, en la misma carrera; la siesta en 0 no alcanzó). Windows 11
 *   IGNORA la resolución del reloj de un proceso cuya ventana no se ve (tapada por otras, minimizada):
 *   cada Sleep(1) dura ~15,6 ms, y el bucle duerme DOS veces por vuelta = ~32 vueltas/s. Encima le baja
 *   la velocidad (EcoQoS). El interruptor oficial para no entrar en ese ahorro es ProcessPowerThrottling
 *   con StateMask 0: «este proceso respeta su reloj y su velocidad aunque no se vea».
 *   ⚠ Win7/8 no tienen SetProcessInformation: se busca a mano y si no está no pasa nada. */
typedef struct { ULONG Version, ControlMask, StateMask; } AHORRO_DE_FONDO;
typedef BOOL (WINAPI *PONER_INFO)(HANDLE, int, LPVOID, DWORD);
static void sin_ahorro_de_fondo(void)
{
    HMODULE k32 = GetModuleHandleA("kernel32.dll");
    PONER_INFO poner = k32 ? (PONER_INFO)GetProcAddress(k32, "SetProcessInformation") : NULL;
    if (!poner) { apuntar("  [motor] sin SetProcessInformation (Windows viejo): sin cambio de ahorro"); return; }
    /* 1 = EXECUTION_SPEED (EcoQoS) · 4 = IGNORE_TIMER_RESOLUTION; StateMask 0 = apagados los dos */
    AHORRO_DE_FONDO a = { 1, 0x1 | 0x4, 0 };
    BOOL ok = poner(GetCurrentProcess(), 4 /* ProcessPowerThrottling */, &a, sizeof a);
    if (!ok) { a.ControlMask = 0x1; ok = poner(GetCurrentProcess(), 4, &a, sizeof a); }  /* Win10 viejo: sin el 0x4 */
    apuntar("  [motor] %s el ahorro de fondo de Windows (reloj fino y velocidad sin foco): mascara 0x%lx",
            ok ? "★ apagado" : "⛔ NO pude apagar", ok ? a.ControlMask : (unsigned long)GetLastError());
}

static int poner_espera_precisa(void)
{
    g_base_exe = (BYTE *)GetModuleHandleA(NULL);
    if (!g_base_exe) return 0;
    if (!QueryPerformanceFrequency(&g_qpf) || g_qpf.QuadPart == 0) return 0;

    HMODULE wmm = LoadLibraryA("winmm.dll");
    if (wmm) g_timeGetTime = (RELOJMS)GetProcAddress(wmm, "timeGetTime");
    if (!g_timeGetTime) {
        apuntar("  [motor] ⛔ sin timeGetTime: la espera precisa NO se aplica");
        return 0;
    }
    /* ⚠ el Sleep real se toma de kernel32 ANTES de parchear la IAT: si se tomara
     *   despues, nos llamariamos a nosotros mismos y el juego se cuelga al instante. */
    HMODULE k32 = GetModuleHandleA("kernel32.dll");
    g_sleep_real = k32 ? (DORMIR)GetProcAddress(k32, "Sleep") : NULL;
    if (!g_sleep_real) return 0;

    if (!parchear_iat("KERNEL32.dll", "Sleep", (void *)mi_sleep)) {
        apuntar("  [motor] ⛔ no pude enganchar Sleep en la IAT");
        return 0;
    }
    return 1;
}

/* ── ★ escribir en el `.text` del exe, con guarda ─────────────────────────────
 *
 * ⚠ La guarda no es paranoia: si en ese sitio no esta lo que esperamos, **el exe no
 *   es el que creemos** y escribir seria romperlo sin avisar. Mejor no tocar y decirlo.
 * ⚠ Las direcciones son VA con imagen 0x400000, pero se calculan desde la base REAL:
 *   si alguna vez el exe se reubica, seguir usando 0x400000 escribiria en cualquier lado.
 */
static int escribir_bytes(DWORD va, const BYTE *espera, const BYTE *nuevo, int n,
                          const char *que)
{
    BYTE *base = (BYTE *)GetModuleHandleA(NULL);
    if (!base) return 0;
    BYTE *sitio = base + (va - 0x400000);
    DWORD viejo = 0;
    if (!VirtualProtect(sitio, n, PAGE_EXECUTE_READWRITE, &viejo)) {
        apuntar("  [motor] %s: no pude abrir la memoria en 0x%08X", que, va);
        return 0;
    }
    int igual = 1;
    for (int i = 0; i < n; i++) if (sitio[i] != espera[i]) { igual = 0; break; }
    if (!igual) {
        char hex[64]; hex[0] = 0;
        for (int i = 0; i < n && i < 8; i++)
            wsprintfA(hex + lstrlenA(hex), "%02X ", sitio[i]);
        VirtualProtect(sitio, n, viejo, &viejo);
        apuntar("  [motor] ⛔ %s: en 0x%08X hay [%s] y esperaba otra cosa. NO SE TOCA.",
                que, va, hex);
        return 0;
    }
    for (int i = 0; i < n; i++) sitio[i] = nuevo[i];
    VirtualProtect(sitio, n, viejo, &viejo);
    return 1;
}

/* ★★ LA CALCULADORA DEL 2019 (22-sep-2026) — en su propio archivo para no mezclarla
 *   con el video. Se incluye ACA porque usa `apuntar()` y `g_carpeta`. Ver calculadora.c. */
#include "idiomas.c"              /* ★ 28-oct: (126) chino, coreano y español con cualquier Windows: UTF-8 o 1252 (IDIOMAS.md) — ANTES que los módulos que dibujan texto: usan `id_a_ancho` */
#include "calculadora.c"
/* ★★ LAS CARAS POR SEXO (28-sep-2026): el mismo número de cara, una de chico y otra
 *   de chica. UN lugar del exe. Ver caras.c. */
#include "caras.c"
/* ★★★ LA FLUIDEZ A CUALQUIER Hz (03-oct-2026): la carrera a la frecuencia del monitor
 *   con la logica en 60. La llama `aplicar_decouple`. Ver fluidez.c. */
#include "fluidez.c"
/* ★★ «R2beat tool» (03-oct-2026): la herramienta del jugador que reemplaza a ToolBit,
 *   con su ventana (F12) y sus opciones en [herramienta]. Ver herramienta.c y
 *   documentacion/R2BEAT_TOOL.md. Va DESPUES de la calculadora: usa `calc_escribiendo`. */
#include "herramienta.c"
/* ★ «Repetir» en la Pausa (04-oct-2026): el 3er botón, como RBit, sólo jugando solo.
 *   Ver pausa.c y documentacion/PAUSA_REPETIR.md. */
#include "pausa.c"
/* ★ El picker con BPM, TIME y corazones (07-oct-2026): la columna «BPM» de la lista y el panel.
 *   Va con rnr_ui_picker.pak (las rayas). Ver picker.c y documentacion/PICKER_BPM.md. */
#include "picker.c"
/* ★ Los obstáculos de una pista, aparte de la pista (08-oct-2026): la carga de `backNNN.txt`.
 *   Ver obstaculos.c y documentacion/PISTA_OBSTACULOS_VICTORIA.md. */
/* ★ La carrera grande (10-oct-2026): más de 6 corredores en la misma pista, el 6vs6. Va ANTES de obstaculos.c
 *   (su salto del FF25 lee el campo 3 para grande.c). Ver grande.c y documentacion/MODO_6VS6.md. */
#include "grande.c"
#include "obstaculos.c"
/* ★ «Modo de 12 jugadores» en crear sala (10-oct-2026, el 6vs6). Ver sala12.c y documentacion/MODO_6VS6.md §11. */
#include "sala12.c"
/* ★ La pista propia (08-oct-2026): el invitado también abre la ventana de pistas. Ver pista_propia.c. */
#include "pista_propia.c"
/* ★ El panel de la sala con «Obstáculos» y «Victoria» (08-oct-2026). Ver panel_sala.c. */
#include "panel_sala.c"
/* ★ «TOP 5 RANK» en el picker (09-oct-2026): el ranking de la canción, pegado al FF139. Ver top5.c y
 *   documentacion/TOP5_RANK.md. Va DESPUÉS de picker.c (usa pk_raton y el Render de la lista). */
#include "top5.c"
/* ★ La sala de 12 estilo coreano (10-oct-2026, el 6vs6). Ver sala12_vista.c y documentacion/MODO_6VS6.md §12. */
#include "sala12_vista.c"
/* ★ El HUD de la carrera de 12 (10-oct-2026): la lista de la izquierda (los 5 primeros + yo), 7P..12P y 7TH..12TH.
 *   Ver carrera12.c y documentacion/MODO_6VS6.md §14. Va DESPUÉS de grande.c (usa g_gr_puesto). */
#include "carrera12.c"
/* ★ El cartel de resultado de la carrera de 12 (11-oct-2026): ver cartel12.c y documentacion/MODO_6VS6.md §17. */
#include "cartel12.c"
/* ★ El balance del modo ítem (11-oct-2026): la tabla del sorteo del «?» y cuántas cajas, como el CBT 2011.
 *   Ver items.c y documentacion/ITEMS_SORTEO.md. */
#include "items.c"
/* ★ Los sets del armario en 2 columnas de 5 (12-oct-2026): ver ropero.c y documentacion/ARMARIO_CONJUNTOS.md §5. */
#include "ropero.c"
/* ★ «Invitar a los del vestíbulo» para todos (12-oct-2026): ver invitar.c y documentacion/INVITAR_VESTIBULO.md. */
#include "invitar.c"
/* ★ La caja negra (12-oct-2026): anota desde dónde se cierra el juego por un índice fuera de rango. Ver cajanegra.c. */
#include "chart_grande.c"         /* ★ 06-nov: (161) el chart del FF57 sin el techo de 4096 de la pila (CHART_TECHO_4096.md §7) — ANTES de cajanegra.c, que lo avisa */
#include "cajanegra.c"
/* ★ El modo transmisión del espectador (12-oct-2026): ver transmision.c y documentacion/MODO_ESPECTADOR.md §10. */
#include "transmision.c"
#include "repeticion.c"          /* ★ 17-oct: el que mira repite la posición REAL de los vecinos (la opción B) */
#include "dados12.c"            /* ★ 13-oct: 12 + ítem, la cola de dados de 6 */
#include "relevo12.c"           /* ★ 14-oct: el relevo de 12, el motor a 4 equipos (RELEVO_12.md) */
#include "globo_combo.c"        /* ★ 14-oct: el globo del combo sobre el que corre (relevo / espectador) */
#include "espectador12.c"        /* ★ 14-oct: el espectador en la sala de 12 (ESPECTADOR_12.md) */
#include "logos_inicio.c"         /* ★ 16-oct: la tira del título más ancha, con «Eñeños bit» (LOGOS_INICIO.md) */
#include "tarjeta_bruma.c"        /* ★ 17-oct: las tarjetas de nombre «Bruma», el humo que da vueltas (TARJETA_BRUMA.md) */
#include "sonido.c"               /* ★ 22-oct: (98) Miles con 6000 canales: el cooperativo no se queda sin lugar (CAJAS_NEGRAS_2026-10-22.md) */
#include "ventana_nula.c"         /* ★ 22-oct: (99) «Crear Sala» con el lobby a medio armar no cierra una ventana nula (CAJAS_NEGRAS_2026-10-22.md) */
#include "cuadros_nulos.c"        /* ★ 22-oct: (100) 0x6840F0 con la protección de su hermana (CAJAS_NEGRAS_2026-10-22.md) */
#include "segundo_juego.c"        /* ★ 22-oct: (102) el 2.º juego abierto avisa en vez de reventar (CAJAS_NEGRAS_2026-10-22.md) */
#include "estilos_texto.c"        /* ★ 23-oct: los estilos de letra (contorno grueso, arcoíris) — antes que los dos de abajo */
#include "circulo_color.c"        /* ★ 23-oct: los crayones de círculo — el nombre del círculo de color por una marca (CRAYONES_MAZINO.md) */
#include "crayones.c"             /* ★ 23-oct: los crayones del ID Mazino — 12 colores de apodo (CRAYONES_MAZINO.md) */
#include "selector.c"             /* ★ 25-oct: «Elige tu personaje» encima de la creación (SELECTOR_PERSONAJE.md) — después de top5.c */
#include "cielo_ancho.c"          /* ★ 26-oct: el cielo de las pistas en pantalla ancha, como Steam (CIELO_ANCHO.md) */
#include "nombres_cortados.c"     /* ★ 28-oct: (127) el corte de textos sumaba los comienzos: «Musica..» en vez de «Musica 12 [Boyfri..» */
#include "tienda.c"               /* ★ 28-oct: (132) el buscador y el carrito de la tienda (TIENDA_BUSCADOR.md) — después de top5.c */
#include "heroe_aleatorio.c"      /* ★ 29-oct: el quinto modo héroe, «Aleatorio», el del 2019 (MODO_ALEATORIO.md) — después de herramienta.c */
#include "flotar.c"               /* ★ 30-oct: flotar (fly.txt del 2019) en la sala, por la maquinaria del sRoomUser (FLOTAR.md) — ANTES de aura_suelo.c */
#include "monturas.c"             /* ★ 30-oct: (142) las MONTURAS 1 a 1 con el 2019 (MONTURAS.md) — después de flotar.c y selector.c */
#include "aura_suelo.c"           /* ★ 29-oct: las auras de suelo (<AuraWing> de VFUN) con la maquinaria de las alas (AURA_DE_SUELO.md) */
#include "pareja_poses.c"         /* ★ 30-oct: (141) las poses de pareja (coupleaction.xml del 2019) en la carrera (PAREJA_POSES.md) */
#include "mascotas_items.c"       /* ★ 31-oct: (147) cualquier mascota da 2 casilleros en la carrera de ítems (MASCOTAS_DOS_ITEMS.md) */
#include "sala_alfa.c"            /* ★ 02-nov: las piezas con alfa de las escenas traídas se ven (la sala Parque 2026) */
#include "estrellas.c"            /* ★ 05-nov: (157) más de 10★: la 2.ª fila, «x 10.5 … x 13» en el picker, el sorteo como 10★ (ESTRELLAS_EXTRA.md) */
#include "campanas.c"             /* ★ 06-nov: (160) 778/783 entran a la lista de campanas del exe + su cartel (CAMPANAS_PLUS_NUEVAS.md) */

/* ── ★★ el refresco del monitor donde esta la ventana ─────────────────────── */
static int hz_del_monitor(HWND h)
{
    MONITORINFOEXA mi;
    mi.cbSize = sizeof(mi);
    HMONITOR m = MonitorFromWindow(h ? h : GetForegroundWindow(),
                                   MONITOR_DEFAULTTOPRIMARY);
    if (!m || !GetMonitorInfoA(m, (MONITORINFO *)&mi)) return 0;
    DEVMODEA dm;
    ZeroMemory(&dm, sizeof(dm));
    dm.dmSize = sizeof(dm);
    if (!EnumDisplaySettingsA(mi.szDevice, ENUM_CURRENT_SETTINGS, &dm)) return 0;
    return (int)dm.dmDisplayFrequency;
}

/* ── ★★★ las piezas del motor ─────────────────────────────────────────────── */
static void aplicar_motor(void)
{
    sin_ahorro_de_fondo();   /* ★ 13-oct: sin foco, el reloj fino y la velocidad se mantienen */
    /* 0 · ★★ 14-oct · EL NUCLEO 0 (anonimo03: «todas están corriendo en el núcleo 0»). Al arrancar su motor de tiempo
     *   (0x0040FA90, una sola vez) el juego hace SetThreadAffinityMask(GetCurrentThread(), 1): el HILO PRINCIPAL (lógica
     *   y dibujo) queda clavado al núcleo 0. MEDIDO con 9 juegos abiertos (NtQueryInformationThread): en los 9 el hilo
     *   principal con afinidad 0x1 — se pelean UN núcleo; 4 se lo quedaban (~200 s de CPU) y 5 se morían de hambre
     *   (~50 s, 0 pasos/s: «trabados», con la PC lenta). ⛔ La memoria del 20-sep («la línea no corre») era FALSA.
     *   ⇒ el `push 1` (la máscara) pasa a `push -1`: con bits de núcleos que no existen SetThreadAffinityMask falla
     *     y el hilo queda como estaba: LIBRE. [motor] nucleo_libre=0 lo deja de fábrica. */
    if (g_nucleo_libre) {
        BYTE esp = 0x01, nue = 0xFF;
        if (escribir_bytes(0x0040FA92, &esp, &nue, 1, "afinidad del hilo principal"))
            apuntar("  [motor] ★ el hilo principal NO se clava al nucleo 0 (push 1 -> push -1 en 0x40FA91)");
    }
    /* ★ la espera precisa va PRIMERO: de ella depende si es seguro bajar el Sleep. */
    if (g_ritmo) {
        g_giro_ms = (double)g_giro_cfg / 10.0;
        if (poner_espera_precisa())
            apuntar("  [motor] ★ espera precisa puesta (tramo a mano %.1f ms,"
                    " siesta %d ms)", g_giro_ms, g_siesta_ms);
        else
            g_ritmo = 0;
    }

    /* ⛔⛔ LA RED QUE EVITA EL ERROR QUE YA COMETIMOS (20-sep-2026)
     *   anonimo03 probo el launcher offline: *"el local anda perfecto en 60 y 120, el
     *   offline en 120 da tirones"*. La unica diferencia era la espera precisa.
     *   ⇒ **`Sleep(1)` sin la espera precisa es PEOR que no tocar el Sleep**: el bucle
     *     gira mucho y despierta cuando Windows quiere.
     *   ⇒ Aca se niega, en vez de confiar en que quien edite el ini se acuerde. */
    if (g_sleep_ms < 16 && !g_ritmo) {
        apuntar("  [motor] ⛔ sleep=%d pedido SIN espera precisa: lo dejo en 16."
                " Bajarlo sin ritmo da TIRONES (medido el 20-sep).", g_sleep_ms);
        g_sleep_ms = 16;
    }
    /* 1 · EL SLEEP DEL BUCLE   0x004104AD   push 0x10 ; call [Sleep]
     *     ⚠ El byte del inmediato. Bajarlo da mas vueltas por segundo. */
    if (g_sleep_ms != 16 && g_sleep_ms >= 0 && g_sleep_ms <= 255) {
        BYTE esp = 0x10, nue = (BYTE)g_sleep_ms;
        if (escribir_bytes(0x004104AD, &esp, &nue, 1, "Sleep del bucle"))
            apuntar("  [motor] ★ el bucle duerme %d ms por vuelta (era 16)", g_sleep_ms);
    }

    /* 2 · LA SIESTA AL PERDER EL FOCO   0x004985C0   push 0x3E8   (1000 ms, x2)
     *
     * ⛔⛔ OJO CON LA DOC: `LA_RECETA_Y_DONDE_VA.md` dice que alcanza con cambiar UN
     *   byte "porque los otros tres ya son 00". **Es falso**: el inmediato es
     *   `E8 03 00 00`, y el segundo byte es `03`. Cambiando solo el primero queda
     *   `14 03 00 00` = **788 ms**, no 20. Son DOS bytes. */
    if (g_siesta_ms != 1000 && g_siesta_ms >= 0 && g_siesta_ms <= 65535) {
        BYTE esp[2] = { 0xE8, 0x03 };
        BYTE nue[2] = { (BYTE)(g_siesta_ms & 0xFF), (BYTE)((g_siesta_ms >> 8) & 0xFF) };
        if (escribir_bytes(0x004985C1, esp, nue, 2, "siesta al perder el foco"))
            apuntar("  [motor] ★ la siesta sin foco es de %d ms (era 1000)", g_siesta_ms);
    }
}

BOOL WINAPI DllMain(HINSTANCE self, DWORD razon, LPVOID reservado)
{
    (void)reservado;
    if (razon != DLL_PROCESS_ATTACH) return TRUE;
    DisableThreadLibraryCalls(self);

    /* ⚠ el d3d9 DE VERDAD, por ruta absoluta del sistema.
     *   Si se pusiera `LoadLibrary("d3d9.dll")` a secas, Windows encontraria ESTA misma
     *   —que esta junto al exe— y se cargaria a si misma para siempre.
     *   ★ En un proceso de 32 bits sobre Windows de 64, GetSystemDirectory ya devuelve
     *     SysWOW64, que es el correcto. */
    char sys[MAX_PATH];
    UINT n = GetSystemDirectoryA(sys, MAX_PATH);
    if (!n || n > MAX_PATH - 16) return FALSE;
    lstrcatA(sys, "\\d3d9.dll");

    /* ★★★ ENCADENARSE CON DXVK EN VEZ DE REEMPLAZARLO  (20-sep-2026, noche)
     *
     * ⛔ EL HALLAZGO QUE OBLIGA A ESTO, y es el que cierra meses de preguntas:
     *   el 2013 crea el dispositivo con **`D3DSWAPEFFECT_COPY` (3)** y
     *   **`LOCKABLE_BACKBUFFER`** (medido, `CREATEDEVICE_DE_LOS_CLIENTES.md`; el 2019
     *   y el r2musa piden DISCARD los dos).
     *   `COPY` significa literalmente *"conserva el backbuffer despues de presentar"*,
     *   y un **flip ENTREGA** el buffer a la pantalla: lo pierde.
     *   ⇒ **COPY prohibe el flip por definicion.** Por eso en ventana siempre salia
     *     `Composed: Copy with GPU GDI` por mucho que se limpiaran los apagadores de
     *     Windows: **el apagador estaba adentro del CreateDevice del juego**, no afuera.
     *
     * ★ Nosotros YA reescribimos ese campo a DISCARD (es lo que permite el MSAA: un
     *   backbuffer LOCKABLE no puede ser multisample). Pero el D3D9 clasico, aun con
     *   DISCARD, presenta por el modelo VIEJO. El que convierte un DISCARD en un flip
     *   de verdad es **DXVK**, porque presenta por Vulkan.
     *
     * ⇒ Y hasta hoy no se podian tener los dos: `d3d9.dll` es UN solo nombre y se lo
     *   peleaban. Encadenarlos lo resuelve — nosotros arriba arreglando los parametros,
     *   DXVK abajo presentando.
     *
     * ⚠ Se lee el ini a mano ACA porque `leer_ajustes()` corre mas abajo, y esta
     *   decision hay que tomarla ANTES del LoadLibrary. */
    {
        char rp[MAX_PATH], ini[MAX_PATH], valor[64];
        if (GetModuleFileNameA(self, rp, MAX_PATH)) {
            char *b = strrchr(rp, '\\');
            if (b) {
                int largo = (int)(b - rp) + 1;
                CopyMemory(ini, rp, largo);
                ini[largo] = 0;
                lstrcpyA(ini + largo, "d3d9_proxy.ini");
                valor[0] = 0;
                GetPrivateProfileStringA("video", "real", "", valor, sizeof(valor), ini);
                if (valor[0]) {
                    /* la ruta pedida, SIEMPRE junto a la dll: no se aceptan rutas sueltas */
                    CopyMemory(rp, ini, largo);
                    rp[largo] = 0;
                    lstrcpyA(rp + largo, valor);
                    if (GetFileAttributesA(rp) != INVALID_FILE_ATTRIBUTES)
                        lstrcpyA(sys, rp);
                }
            }
        }
    }

    g_real = LoadLibraryA(sys);
    if (!g_real) return FALSE;   /* ★ `sys` ya trae la ruta elegida: el log la imprime */
    g_crear = (CREAR9)GetProcAddress(g_real, "Direct3DCreate9");
    if (!g_crear) return FALSE;
    /* ⚠ esta puede no estar (Windows XP) y no es motivo para fallar: si no esta,
     *   la ruta moderna simplemente no se usa. */
    g_crear_ex = (CREAR9EX)GetProcAddress(g_real, "Direct3DCreate9Ex");

    leer_ajustes(self);
    empezar_log();

    /* ★ el testigo de la muerte, solo cuando estamos probando la ruta moderna:
     *   en el camino de siempre no hace falta y no se paga ni un ciclo. */
    if (g_d3d9ex) AddVectoredExceptionHandler(1, mirar_excepcion);

    char exe[MAX_PATH] = {0};
    GetModuleFileNameA(NULL, exe, MAX_PATH);
    apuntar("=== proxy d3d9 de R2Beat - cargado ===");
    apuntar("exe      : %s", exe);
    apuntar("d3d9 real: %s", sys);
    apuntar("ajustes  : msaa=%d altenter=%d activo=%d   (%s)",
            g_msaa, g_altenter, g_activo,
            g_hay_ini ? "leidos de d3d9_proxy.ini" : "de fabrica: NO habia ini al lado");

    /* ★★ EL PARCHE DEL MODO DE PANTALLA VA ACÁ, LO MÁS TEMPRANO POSIBLE.
     *   El juego puede pedir el cambio de modo ANTES de llamar a `Direct3DCreate9` —de
     *   hecho es lo natural: primero pone la pantalla, después crea el dispositivo—, así
     *   que hacerlo sólo ahí llegaría tarde.
     *   ⚠ Y acá ya se puede: cuando el cargador de Windows llama a este `DllMain`, las
     *     importaciones del exe **ya están resueltas** (por eso nos cargó a nosotros).
     *   ⚠ Si por lo que fuera fallara, `Direct3DCreate9` lo reintenta. */
    g_cambiar_real = (CAMBIARMODO)parchear_iat("USER32.dll",
                                               "ChangeDisplaySettingsA",
                                               (void *)mi_cambiar_modo);
    /* ★ el motor se parchea ACA: el exe ya esta mapeado y su bucle todavia no
     *   arranco — es el unico momento limpio. Y va DESPUES de la cabecera del log
     *   para que el archivo se lea en orden: antes salia arriba de todo, sin decir
     *   siquiera de que exe se trataba. */
    aplicar_motor();
    /* ★ (126) los idiomas: los textos del juego en UTF-8 o 1252, sea cual sea el Windows. Antes que el bucle del
     *   juego (lee los catálogos al arrancar). [idiomas] activo=0 lo apaga. */
    idiomas_iniciar();
    /* ★ (127) los nombres que se cortaban mucho antes de su pared. [nombres_cortados] activo=0 lo apaga. */
    nombres_cortados_iniciar();
    /* ★ la calculadora engancha el juicio, el HUD, el impulsor y el chat: tambien tiene
     *   que ser ANTES de que arranque el bucle del juego. [calculadora] activo=0 la apaga. */
    calculadora_iniciar();
    /* ★ las caras por sexo: también ANTES del bucle (la ruta de las caras se arma
     *   al entrar a la sala). [caras] activo=0 lo apaga. */
    caras_iniciar();
    /* ★ la R2beat tool: sus ganchos van ACA (antes del bucle) si `[herramienta] activo=1`;
     *   si no, sólo queda escuchando el aviso del launcher para prenderse en vivo. */
    herramienta_iniciar();
    /* ★ «Repetir» en la Pausa: 4 enganches, también antes del bucle. [pausa] repetir=0 lo apaga. */
    pausa_iniciar();
    /* ★ el picker: BPM en la lista y BPM/TIME en el panel. [picker] activo=0 lo apaga. */
    picker_iniciar();
    /* ★ los obstáculos de otra pista. [obstaculos] activo=0 lo apaga. */
    obstaculos_iniciar();
    /* ★ el Modo Aleatorio (quinto modo héroe). [aleatorio] activo=0 lo apaga. Después de la tool. */
    heroe_aleatorio_iniciar();
    /* ★ las auras de suelo: un efecto a los pies, con la maquinaria de las alas. [aura] activo=0 la apaga. */
    aura_suelo_iniciar();
    /* ★ flotar: la Carta Nube Flotante, 100 más arriba y con sus animaciones. [flotar] activo=0 lo apaga. */
    flotar_iniciar();
    /* ★ las poses de pareja: al largar, al ganar y al perder, juntos si corren al lado. [pareja_poses] activo=0 las apaga. */
    pareja_poses_iniciar();
    monturas_iniciar();                     /* ★ (142) después de flotar_iniciar (usa sus ganchos) */
    /* ★ (147) cualquier mascota da 2 casilleros en la carrera de ítems. [mascotas_items] activo=0 lo apaga. */
    mascotas_items_iniciar();
    /* ★ la carrera grande (6vs6). [grande] activo=0 lo apaga. */
    grande_iniciar();
    /* ★ la casilla «Modo de 12 jugadores» de crear sala. [sala12] activo=0 lo apaga. */
    sala12_iniciar();
    /* ★ la pista propia del invitado. [pista_propia] activo=0 lo apaga. */
    pista_propia_iniciar();
    /* ★ el panel de la sala nuevo. [panel_sala] activo=0 lo apaga. */
    panel_sala_iniciar();
    /* ★ TOP 5 RANK. [top5] activo=0 lo apaga. Después del picker: sin él no se prende. */
    top5_iniciar();
    /* ★ la sala de 12 estilo coreano. [sala12_vista] activo=0 lo apaga. */
    sala12_vista_iniciar();
    /* ★ el HUD de la carrera de 12. [carrera12] activo=0 lo apaga. */
    carrera12_iniciar();
    /* ★ el cartel de resultado de la carrera de 12. [cartel12] activo=0 lo apaga. */
    cartel12_iniciar();
    /* ★ el balance del modo ítem (la tabla del CBT y sus cajas). [items] activo=0 lo apaga. */
    items_iniciar();
    /* ★ los sets del armario en 2×5 (SET1..SET10). [ropero] activo=0 lo apaga. */
    ropero_iniciar();
    /* ★ el cartel de invitación (FF52) también al que no hizo el Tutorial. [invitar] todos=0 lo apaga. */
    invitar_iniciar();
    /* ★ la caja negra (el espectador que se cae en relevos). [cajanegra] activo=0 la apaga. */
    cajanegra_iniciar();
    /* ★ el modo transmisión: combos y golpes del que corre al que mira. [transmision] activo=0 lo apaga. */
    transmision_iniciar();
    repeticion_iniciar();
    dados12_iniciar();
    relevo12_iniciar();
    globo_combo_iniciar();
    espectador12_iniciar();
    logos_inicio_iniciar();
    tarjeta_bruma_iniciar();
    /* ★ 26-oct: el cielo de las pistas en pantalla ancha (lo escribe al crear el dispositivo). [cielo] ancho=0 lo apaga. */
    cielo_ancho_iniciar();
    /* ★ (98) los canales de Miles: ANTES de que el juego abra el sonido. [sonido] canales=0 lo deja de fábrica. */
    sonido_iniciar();
    /* ★ (99) la caja negra 0x6584E1: «Crear Sala» antes de que el lobby arme su ventana. [ventana_nula] activo=0 lo apaga. */
    ventana_nula_iniciar();
    /* ★ (100) la caja negra 0x684107: la tabla de cuadros de un dibujo sin cargar. [cuadros_nulos] activo=0 lo apaga. */
    cuadros_nulos_iniciar();
    /* ★ (102) la caja negra 0x433401: abrir el juego dos veces. ANTES del WinMain (el mutex es lo 1.º que mira). */
    segundo_juego_iniciar();
    /* ★ «Elige tu personaje»: la vtable de cCharSelect y el hilo del HOLA. [selector] activo=0 lo apaga. */
    selector_iniciar();
    /* ★ los crayones de círculo: el nombre del círculo de color (marca ^+letra que pone el server). [circulo_color] activo=0 */
    circulo_color_iniciar();
    /* ★ los estilos de letra de los crayones (contorno grueso, arcoíris animado). [estilos_texto] activo=0 lo apaga. */
    estilos_texto_iniciar();
    /* ★ los crayones del ID Mazino: 12 colores de apodo. [crayones] activo=0 lo apaga. */
    crayones_iniciar();
    /* ★ (132) el buscador y el carrito de la tienda. [tienda] activo=0 lo apaga. */
    tienda_iniciar();
    /* ★ 02-nov: las piezas con alfa y material en cero (la sala Parque 2026). [sala_alfa] activo=0 lo apaga. */
    sala_alfa_iniciar();
    /* ★ 05-nov: (157) las canciones de más de 10★ (Level 21..26). [estrellas] activo=0 lo apaga. */
    estrellas_iniciar();
    /* ★ 06-nov: (160) las campanas nuevas 778/783 funcionan como campanas. [campanas] activo=0 lo apaga. */
    campanas_iniciar();
    /* ★ 06-nov: (161) el chart del FF57 en una caja de 64 KB: entran los de más de 4096 B. [chart_grande] activo=0 lo apaga. */
    chart_grande_iniciar();

    apuntar("modo de pantalla: %s",
            g_cambiar_real ? "enganchado (el 16 -> 32 esta cubierto)"
                           : "NO enganchado todavia (se reintenta en Direct3DCreate9)");
    return TRUE;
}
