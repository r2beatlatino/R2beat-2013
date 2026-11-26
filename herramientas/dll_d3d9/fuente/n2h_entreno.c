/* ═══════════════════════════════════════════════════════════════════════════
 * n2h_entreno.c — «Entreno» y «Tramos» de Ñ2Hock, ADENTRO de nuestra d3d9 (19-nov-2026)
 *
 *   Porta a C el motor nativo de práctica de Ñ2Hock (native-practice/engine.c + loop.c, ABI 1) y la orquestación
 *   que hacía su lado C# (NativePracticeModule/Session, PracticeClient, PracticeAudioClock, PracticeAntiFallSession,
 *   SpeedZones, TrainingSettings y la lógica de Form1.Training*.cs). Nada de cargar otra dll ni de leer el proceso
 *   desde afuera: vivimos adentro y leemos/escribimos directo.
 *
 *   ★ QUÉ HACE
 *     · Velocidad de práctica 50..150 % (pasos de 5): la música (AIL_set_sample_playback_rate de la muestra) y el
 *       reloj lógico del gestor (+0x18) se acoplan, y el origen del reloj de cuadros (0x931588) se corre lo que haga
 *       falta para que el juego fabrique menos (o más) cuadros. Corre en el MISMO hilo del reloj del juego.
 *     · Repetir un tramo A/B con cuenta atrás (el juego en pausa) y segundos previos sin notas.
 *     · Velocidad por tramos (hasta 6 filas «desde/hasta/%»), «marcar punto» A, B, C…
 *     · Moverse ±1/±5 s en la canción (sólo a segundos YA tocados: hay una foto por segundo, una hora de historia).
 *     · Anticaída (el choque del Latino): la rama de 2 bytes 0x50AC67 `75 43` -> `90 90`.
 *
 *   ★ DÓNDE TOCA EL EXE (VA, base 0x400000; validado contra R2BeatMultiTest.exe md5 0f79000e…, que es el
 *     SHA-256 7184FA94… que Ñ2Hock da por bueno, y mss32.dll F2099AAA…)
 *     · 0x410484  8 B  `8B C1 2B 05 <&0x931588>` (mov eax,ecx · sub eax,[origen])  -> `E9 <thunk reloj> 90 90 90`
 *     · 0x574080  8 B  `56 8B F1 E8 F8 FD FF FF` (push esi · mov esi,ecx · call 0x573E80) -> `E9 <thunk tempo> 90 90 90`
 *     · 0x50AC67  2 B  `75 43` -> `90 90` (Anticaída; se exigen los 11 B `75 43 80 BE 9C 02 00 00 00 75 3A`)
 *     · Se LLAMAN (firmas comprobadas antes): 0x56D3A0 buscar, 0x56D5E0 pausa, 0x56D1E0 seguir (thiscall del gestor)
 *       y el import [0x873554] = mss32!_AIL_set_sample_playback_rate@8.
 *     · Datos (páginas RW, el antitrampa no las mira): gestor+0x18, muestra+0x60 (vía Miles), [0x931588], las notas y
 *       el jugador local al reposicionar (igual que Ñ2Hock).
 *
 *   ★ EL ANTITRAMPA (antitrampa_envoltura.h): este archivo se compila DENTRO de d3d9_proxy.c, después de la envoltura,
 *     así que `VirtualProtect` acá es `at_virtual_protect`: al abrir la página vigilada queda «en nuestras manos» y al
 *     cerrarla se re-copia como lo esperado. Toda escritura al código pasa por ne_escribir_codigo() (abre con
 *     VirtualProtect, congela TODOS los hilos del proceso, mira que ninguno tenga el EIP adentro de los bytes, escribe,
 *     cierra con VirtualProtect). Los thunks son funciones naked de NUESTRA dll (no hay VirtualAlloc ejecutable).
 *     Ninguno de los tres sitios está en la lista de ganchos de at_revisar_ganchos().
 *
 *   ★ SEGURIDAD (como Ñ2Hock, más una guarda)
 *     · Sólo en carrera de práctica: cGame+0x0C (WORD) == 8 y fase cGame+8 < 4 (Anticaída: (modo & 0x7F) == 8 y
 *       fase == 3), con UN solo jugador en la carrera (NE_EXIGIR_UN_JUGADOR, guarda nuestra: Ñ2Hock confiaba en la
 *       casilla «Confirmo práctica offline»).
 *     · Audio a 44100 Hz, UNA muestra HSAM, vtable de sonido 0x889A04 con [+0x2C] == 0x66E910, MP3 MPEG1 L3 CBR.
 *     · Bytes esperados antes de enganchar; si no están, no se toca (¿Ñ2Hock ya enganchado? también se rechaza).
 *     · Semáforo «Local\ToolBitPracticeSession_<pid>_<ticks de inicio>»: el mismo nombre que usa Ñ2Hock, así no pueden
 *       controlar el entrenamiento los dos a la vez.
 *     · El motor (en el hilo del juego) se apaga solo y restaura las frecuencias si: la canción/recurso cambia o
 *       termina (1), % inválido (2), sin latido de ne_tick 2 s (3), el juego reinició su reloj (4), pausa > 1 s (6),
 *       contador de cuadros absurdo (7), resto fuera de rango (8). ne_tick lo ve y apaga TODO (quita los ganchos).
 *     · Vigilancia del desfase música/notas (PracticeAudioClock): envolvente de 1 s, cero calibrado 1 s, corta con
 *       > 200 ms sostenidos 1 s o un salto > 600 ms.
 *
 *   ★ API (todo static, prefijo ne_; las acciones devuelven 1 = hecho, 0 = rechazado — el porqué queda en los textos)
 *     void ne_tick(void)                        ⚠ cada 50 ms desde el hilo de la ventana, AUNQUE esté oculta: es el
 *                                                 «latido»; sin él el motor se restaura solo a los 2 s.
 *     (no hace falta ne_por_cuadro: lo que corre por cuadro va en el gancho del reloj, en el hilo del juego.)
 *     int  ne_listo(void)                       1 = hay canción de práctica donde se puede usar
 *     void ne_estado(wchar_t *s, int n)         el texto de «Velocidad»/general (practiceStatus de Ñ2Hock)
 *     int  ne_texto(int que, wchar_t *s, int n) NE_TX_*: VELOCIDAD, BUCLE, TRAMOS, MOVER, ANTICAIDA; devuelve 1 si es error
 *     int  ne_preparar(int on) / ne_preparado() «Habilitar»: el motor a 100 % grabando segundos (para A pasado y mover)
 *     int  ne_velocidad_activar(int on) · void ne_velocidad_poner(int pct) · int ne_velocidad(void) (la elegida)
 *     int  ne_velocidad_activa(void) · int ne_velocidad_aplicada(void) (la que corre ahora, tramos incluidos)
 *     int  ne_bucle_activar(int on)  (con on=1 estando activo = reconfigurar con los tiempos/opciones actuales)
 *     void ne_bucle_tiempos(int desde_ms, int hasta_ms)    hasta_ms <= 0 = hasta el final de la canción
 *     void ne_bucle_opciones(int cuenta_atras_s, int sin_notas_s)                 0..30 cada uno
 *     int  ne_bucle_marcar_a(void) · ne_bucle_marcar_b(void) · ne_bucle_reiniciar(void)
 *     int  ne_bucle_activo(void) · void ne_bucle_leer(int *desde, int *hasta, int *cuenta_s, int *sin_notas_s)
 *     int  ne_bucle_estado(int *estado, int *vueltas, int *restante_ms, int *pos_ms)   estado: 0 apagado, 1 esperando A,
 *                                                 2 en el tramo, 3 cuenta atrás, 4 antes de A sin notas, 6 error
 *     int  ne_bucle_puede_reiniciar(void)
 *     int  ne_anticaida(int on) · ne_anticaida_activa(void)
 *     int  ne_tramos(int on, const int *desde_ms, const int *hasta_ms, const int *pct, int n)   n <= 6; -1 = casilla
 *                                                 vacía; con arrays NULL usa las filas guardadas; on=1 estando activo =
 *                                                 «editar» (si no compila se mantienen los anteriores)
 *     int  ne_tramos_activos(void) · void ne_tramos_filas(int *desde, int *hasta, int *pct)  (6 cada uno)
 *     int  ne_marcar_punto(void)                A, B, C… (llena las filas como Ñ2Hock)
 *     int  ne_mover(int delta_s)                ±1, ±5 (hasta ±600). Si el motor no corre, la 1.ª vez sólo lo prepara.
 *     int  ne_tiempo_ms(void) · int ne_largo_ms(void)     -1 si no hay
 *     int  ne_apagar_todo(void)                 restaura todo (frecuencias, ganchos, Anticaída). 1 = todo restaurado.
 *     int  ne_posicion_de_texto(const wchar_t *s) ("m:ss" -> ms, -1 si no vale) · void ne_texto_de_posicion(int ms, wchar_t *s)
 *
 *   ⚠ Se INCLUYE desde herramienta.c justo antes de n2h_ventana.c: usa g_ht_base, g_ht_cs, ht_memoria_ok, apuntar.
 *   ⛔ No portado: la «recuperación de enlaces huérfanos» (RecoverInertHooks: aquí los ganchos son de esta misma dll),
 *     el simulador PracticeTimeline (sólo era una vista previa sin juego), las teclas (las maneja la ventana) y el
 *     mapa de la canción (Form1.SongMap.cs: es interfaz; ne_tiempo_ms / ne_largo_ms dan lo que necesita).
 * ═══════════════════════════════════════════════════════════════════════════ */
#include <tlhelp32.h>

#define NE_EXIGIR_UN_JUGADOR 0      /* ★ guarda nuestra: la carrera de práctica tiene UN jugador */

#define NE_U(a) (*(volatile DWORD *)(ULONG_PTR)(a))
#define NE_B(a) (*(volatile BYTE *)(ULONG_PTR)(a))
#define NE_W(a) (*(volatile WORD *)(ULONG_PTR)(a))
#define NE_F(a) (*(volatile float *)(ULONG_PTR)(a))

/* las RVA (VA - 0x400000), como las escribe Ñ2Hock */
#define NE_RVA_RELOJ        0x10484
#define NE_RVA_RELOJ_VUELTA 0x1048C
#define NE_RVA_TEMPO        0x174080
#define NE_RVA_TEMPO_VUELTA 0x174088
#define NE_RVA_TEMPO_VALIDA 0x173E80
#define NE_RVA_BUSCAR       0x16D3A0
#define NE_RVA_PAUSA        0x16D5E0
#define NE_RVA_SEGUIR       0x16D1E0
#define NE_RVA_ANTICAIDA    0x10AC67
#define NE_RVA_AIL_TASA     0x473554   /* el import _AIL_set_sample_playback_rate@8 */
#define NE_RVA_SONIDO_VT    0x489A04
#define NE_RVA_SONIDO_F2C   0x26E910
#define NE_RVA_GESTOR       0x5314C8
#define NE_RVA_RECURSOS     0x531578
#define NE_RVA_CUADRO       0x531584
#define NE_RVA_ORIGEN       0x531588
#define NE_RVA_PERFIL       0x531660
#define NE_RVA_ESCALA       0x5D45E4
#define NE_RVA_DESPL        0x5D45EC
#define NE_RVA_NOTA_X       0x5D45F0
#define NE_RVA_PERIODO      0x5D4CEC
#define NE_HSAM             0x4D415348  /* "HSAM" */
#define NE_TOPE_TRAMOS      12                  /* ★ 26-nov: 12 (antes 6), anonimo03: «más de 6 tramos» */

/* ═══ 1 · EL MOTOR (lado del juego) — engine.c, ABI 1 ═══════════════════════════════════════════════
 *   La ventana sólo escribe configuración, deseado, porcentaje, latido y orden; el resto lo escribe el gancho. */
typedef struct {
    DWORD imagen, gestor, pista, sonido, muestra, tasa_gestor, tasa_muestra;
    volatile DWORD deseado, porcentaje, latido, orden;
    volatile DWORD confirmada, activo, estado, origen, tick_anterior;
    volatile LONG resto;
    volatile DWORD pct_aplicado, cuadros, hilo;
} NE_MOTOR;
static NE_MOTOR g_ne_m;
static volatile LONG g_ne_pausas = 0;      /* ★ 25-nov: cuántas pausas del juego retomó el motor (antes: estado 6, todo apagado) */

/* lo que lee el thunk (nombres de ensamblador fijos: el thunk los usa por nombre) */
static volatile DWORD g_ne_vuelta_reloj   __asm__("ne_asm_vuelta_reloj") __attribute__((used));
static volatile DWORD g_ne_dir_origen     __asm__("ne_asm_origen") __attribute__((used));
static volatile DWORD g_ne_vuelta_tempo   __asm__("ne_asm_vuelta_tempo") __attribute__((used));
static volatile DWORD g_ne_validar_tempo  __asm__("ne_asm_validar_tempo") __attribute__((used));
static volatile DWORD g_ne_tempos_bloqueados;
/* las funciones del juego para el bucle y los saltos (0 = no validadas) */
static volatile DWORD g_ne_f_buscar, g_ne_f_pausa, g_ne_f_seguir;

static int ne_audio_propio(NE_MOTOR *s)
{
    DWORD recursos = NE_U(s->imagen + NE_RVA_RECURSOS), casilla = s->pista & 0xFFFF;
    if (!recursos) return 0;
    DWORD reg = NE_U(recursos + 12), fin = NE_U(recursos + 16);
    DWORD gen = NE_U(recursos + 0x24), gen_fin = NE_U(recursos + 0x28);
    if (!reg || fin <= reg || (fin - reg) % 36 || casilla >= (fin - reg) / 36 ||
        !gen || gen_fin <= gen || casilla >= (gen_fin - gen) / 4 ||
        NE_U(gen + casilla * 4) != s->pista >> 16 || NE_U(reg + casilla * 36 + 0x1C) != s->sonido) return 0;
    if (NE_U(s->sonido) != s->imagen + NE_RVA_SONIDO_VT) return 0;
    DWORD manijas = NE_U(s->sonido + 0x24);
    return manijas && NE_U(s->sonido + 0x28) == manijas + 4 && NE_U(manijas) == s->muestra && NE_U(s->muestra) == NE_HSAM;
}

static int ne_misma_cancion(NE_MOTOR *s)
{
    if (!s->gestor || NE_U(s->imagen + NE_RVA_GESTOR) != s->gestor ||
        NE_W(s->gestor + 12) != 8 || NE_B(s->gestor + 8) >= 4) return 0;
    DWORD ini = NE_U(s->gestor + 0xA64), fin = NE_U(s->gestor + 0xA68), indice = NE_U(s->gestor + 0xA70);
    if (!ini || fin <= ini || (fin - ini) % 28 || indice >= (fin - ini) / 28) return 0;
    return NE_U(ini + indice * 28) == s->pista && ne_audio_propio(s);
}

static DWORD ne_escala(DWORD valor, DWORD num, DWORD den) { return (valor * num + den / 2) / den; }

/* el import validado de Miles: él se encarga de su candado; nada de escribir la muestra a mano */
static void ne_tasa_audio(NE_MOTOR *s, DWORD tasa)
{
    typedef void (__stdcall *NE_FTASA)(void *, int);
    ((NE_FTASA)(ULONG_PTR)NE_U(s->imagen + NE_RVA_AIL_TASA))((void *)(ULONG_PTR)s->muestra, (int)tasa);
}

/* ═══ 2 · EL BUCLE A/B Y LOS SALTOS (lado del juego) — loop.c ══════════════════════════════════════ */
typedef struct {
    volatile DWORD activo, desde_ms, hasta_ms, cuenta_ms, previo_ms, orden, confirmada;
    volatile DWORD estado, vueltas, generacion, restante_ms, error, posicion_ms;
    volatile DWORD reinicio_orden, reinicio_confirmado;
    volatile LONG salto_ms; volatile DWORD salto_orden, salto_confirmado, salto_resultado;
} NE_BUCLE;
enum { NE_SALTO_HECHO = 1, NE_SALTO_NO_TOCADO = 2, NE_SALTO_INVALIDO = 3, NE_SALTO_OCUPADO = 4,
       NE_SALTO_FALLO = 5, NE_SALTO_NO_DISPONIBLE = 6 };
static NE_BUCLE g_ne_b;

typedef struct {
    int valida, pausada;
    DWORD jugador, mapa, ini, fin, cabeza, cuadro, pausa_hasta;
    float posicion, x, y, z, vel, vel_y, base;
    DWORD valor_tiempo;
    WORD corto_a, corto_b;
    float cuadro_desde, cuadro_hasta, cuadro_captura;
    DWORD cuenta_ms;
} NE_INSTANTE;
static NE_INSTANTE g_ne_foto;
#define NE_HISTORIA 3600u
static NE_INSTANTE g_ne_hist[NE_HISTORIA];
static DWORD g_ne_hist_clave[NE_HISTORIA], g_ne_hist_epoca[NE_HISTORIA], g_ne_epoca = 1, g_ne_ult_clave = 0xFFFFFFFFu;
static void ne_historia_borrar(void) { g_ne_epoca++; g_ne_ult_clave = 0xFFFFFFFFu; }

static int ne_finito(float v)
{
    union { float f; DWORD u; } b; b.f = v;
    return (b.u & 0x7F800000u) != 0x7F800000u;
}

static DWORD ne_jugador(NE_MOTOR *s)
{
    DWORD perfil = NE_U(s->imagen + NE_RVA_PERFIL), ini = NE_U(s->gestor + 0xA14), fin = NE_U(s->gestor + 0xA18);
    if (!perfil || !ini || fin <= ini || (fin - ini) % 4 || (fin - ini) / 4 > 64) return 0;
    DWORD casilla = NE_B(perfil + 0x40);
    return casilla < (fin - ini) / 4 ? NE_U(ini + casilla * 4) : 0;
}

static void ne_bucle_seguir(NE_MOTOR *s)
{
    if (g_ne_foto.pausada) {
        if (ne_misma_cancion(s) && g_ne_f_seguir) {
            typedef void (__attribute__((thiscall)) *NE_FSEGUIR)(void *);
            ((NE_FSEGUIR)(ULONG_PTR)g_ne_f_seguir)((void *)(ULONG_PTR)s->gestor);
        }
        g_ne_foto.pausada = 0;
    }
}

static void ne_bucle_soltar(NE_MOTOR *s)
{
    ne_bucle_seguir(s);
    g_ne_foto.valida = 0;
    g_ne_b.activo = 0;
    g_ne_b.estado = 0;
    g_ne_b.restante_ms = 0;
    g_ne_b.confirmada = g_ne_b.orden;
}

static void ne_bucle_fallar(NE_MOTOR *s, DWORD error)
{
    ne_bucle_soltar(s); g_ne_b.error = error; g_ne_b.estado = 6;
}

static int ne_mapa(DWORD jugador, DWORD *mapa, DWORD *ini, DWORD *fin, DWORD *cabeza)
{
    *mapa = NE_U(jugador + 0x144); *cabeza = NE_U(jugador + 0x210);
    if (!*mapa || !*cabeza) return 0;
    *ini = NE_U(*mapa + 12); *fin = NE_U(*mapa + 16);
    return *ini && *fin > *ini && (*fin - *ini) % 12 == 0 && (*fin - *ini) / 12 <= 16384;
}

static int ne_capturar_en(NE_MOTOR *s, DWORD jugador, NE_INSTANTE *a)
{
    if (!ne_mapa(jugador, &a->mapa, &a->ini, &a->fin, &a->cabeza)) return 0;
    a->jugador = jugador; a->cuadro = NE_U(s->gestor + 0x878);
    a->posicion = NE_F(jugador + 0x18); a->base = NE_F(jugador + 0x1C);
    a->x = NE_F(jugador + 0x20); a->y = NE_F(jugador + 0x24); a->z = NE_F(jugador + 0x28);
    a->vel = NE_F(jugador + 0x58); a->vel_y = NE_F(jugador + 0x5C);
    a->valor_tiempo = NE_U(jugador + 0x60);
    a->corto_a = NE_W(jugador + 0x68);
    a->corto_b = NE_W(jugador + 0x6A);
    if (!ne_finito(a->posicion) || !ne_finito(a->x) || !ne_finito(a->y) || !ne_finito(a->z) ||
        !ne_finito(a->base) || a->base <= 0.01f || !ne_finito(a->vel) || a->vel <= 0.0f ||
        !ne_finito(a->vel_y)) return 0;
    a->valida = 1; return 1;
}

static void ne_copiar_instante(NE_INSTANTE *a, const NE_INSTANTE *de)
{
    for (DWORD i = 0; i < sizeof(NE_INSTANTE) / 4; i++) ((volatile DWORD *)a)[i] = ((const volatile DWORD *)de)[i];
}

static void ne_historia_grabar(NE_MOTOR *s, DWORD jugador, DWORD inicio)
{
    float pos = NE_F(jugador + 0x18);
    if (!ne_finito(pos) || pos < (float)inicio || pos > 216000.0f) return;
    DWORD clave = (DWORD)((pos - (float)inicio) / 60.0f);
    if (clave == g_ne_ult_clave) return;
    DWORD c = clave % NE_HISTORIA;
    if (!ne_capturar_en(s, jugador, &g_ne_hist[c])) return;
    g_ne_hist[c].pausada = 0; g_ne_hist_clave[c] = clave; g_ne_hist_epoca[c] = g_ne_epoca; g_ne_ult_clave = clave;
}

static int ne_historia_en(DWORD jugador, DWORD clave, NE_INSTANTE *a)
{
    DWORD c = clave % NE_HISTORIA, mapa, ini, fin, cabeza;
    if (g_ne_hist_epoca[c] != g_ne_epoca || g_ne_hist_clave[c] != clave || !g_ne_hist[c].valida ||
        g_ne_hist[c].jugador != jugador || !ne_mapa(jugador, &mapa, &ini, &fin, &cabeza) || mapa != g_ne_hist[c].mapa ||
        ini != g_ne_hist[c].ini || fin != g_ne_hist[c].fin || cabeza != g_ne_hist[c].cabeza) return 0;
    ne_copiar_instante(a, &g_ne_hist[c]); return 1;
}

/* Lleva la carrera al instante `a`: las notas antes de `cuadro_obj` se retiran, el resto se rearma, el audio busca.
 * Deja la generación IMPAR; quien llama termina lo suyo y la vuelve par. */
static int ne_reposicionar(NE_MOTOR *s, NE_INSTANTE *a, float cuadro_obj)
{
    DWORD jugador = ne_jugador(s), mapa, ini, fin, cabeza;
    if (!a->valida || jugador != a->jugador || !ne_mapa(jugador, &mapa, &ini, &fin, &cabeza) ||
        mapa != a->mapa || ini != a->ini || fin != a->fin || cabeza != a->cabeza) return 0;
    /* toda la cadena de notas activas se valida ANTES de tocar una sola */
    DWORD cur = NE_U(cabeza), cuenta = 0;
    while (cur && cur != cabeza && cuenta < 4096) { cur = NE_U(cur); cuenta++; }
    if (cur && cur != cabeza) return 0;
    float razon = NE_F(jugador + 0x1C) / a->base;
    float vel = a->vel * razon, escala = NE_F(s->imagen + NE_RVA_ESCALA), despl = NE_F(s->imagen + NE_RVA_DESPL);
    float x_obj = a->x + (cuadro_obj - a->posicion) * vel;
    if (!ne_finito(razon) || razon <= 0.0f || !ne_finito(vel) || vel <= 0.0f ||
        !ne_finito(escala) || escala <= 0.0f || !ne_finito(despl) || !ne_finito(x_obj)) return 0;
    DWORD entradas = (fin - ini) / 12, usables = entradas;
    if (NE_B(fin - 7) == 1) usables--;
    DWORD indice = 0;
    while (indice < usables && x_obj > (float)*(volatile LONG *)(ULONG_PTR)(ini + indice * 12) * escala + despl) indice++;
    g_ne_b.generacion++;                    /* impar: nadie combine posiciones de antes y de después */
    for (cur = NE_U(cabeza), cuenta = 0; cur && cur != cabeza && cuenta < 4096; cur = NE_U(cur), cuenta++) {
        DWORD nota = NE_U(cur + 8);
        if (!nota) continue;
        if (NE_B(nota + 9) == 1 && usables != entradas) NE_B(nota + 9) = 0;
        NE_B(nota + 11) |= 0x80;
        NE_F(nota) = NE_F(s->imagen + NE_RVA_NOTA_X) - a->x + 64.0f;
    }
    NE_F(jugador + 0x18) = a->posicion; NE_F(jugador + 0x20) = a->x; NE_F(jugador + 0x24) = a->y; NE_F(jugador + 0x28) = a->z;
    NE_U(jugador + 0x30) = indice; NE_F(jugador + 0x58) = vel; NE_F(jugador + 0x5C) = a->vel_y * razon;
    float periodo = NE_F(s->imagen + NE_RVA_PERIODO) / vel;
    NE_U(jugador + 0x60) = ne_finito(periodo) && periodo > 0.0f && periodo < 2147483000.0f ? (DWORD)periodo : a->valor_tiempo;
    NE_W(jugador + 0x68) = a->corto_a;
    NE_W(jugador + 0x6A) = a->corto_b;
    NE_U(s->gestor + 0x878) = a->cuadro;
    typedef void (__attribute__((thiscall)) *NE_FBUSCAR)(void *, DWORD);
    ((NE_FBUSCAR)(ULONG_PTR)g_ne_f_buscar)((void *)(ULONG_PTR)s->gestor, NE_B(NE_U(s->imagen + NE_RVA_PERFIL) + 0x40));
    return 1;
}

static int ne_volver_a_a(NE_MOTOR *s, DWORD ahora)
{
    NE_INSTANTE *a = &g_ne_foto;
    if (!ne_reposicionar(s, a, a->cuadro_desde)) return 0;
    if (a->cuenta_ms) {
        typedef void (__attribute__((thiscall)) *NE_FPAUSA)(void *, float);
        ((NE_FPAUSA)(ULONG_PTR)g_ne_f_pausa)((void *)(ULONG_PTR)s->gestor, a->posicion);
        a->pausada = 1; a->pausa_hasta = ahora + a->cuenta_ms;
        g_ne_b.estado = 3; g_ne_b.restante_ms = a->cuenta_ms;
    } else g_ne_b.estado = 4;
    g_ne_b.vueltas++; g_ne_b.generacion++;
    return 1;
}

/* salto relativo a un segundo ya tocado (con o sin el bucle; nunca toca la foto de A) */
static NE_INSTANTE g_ne_foto_salto;
static void ne_salto_tick(NE_MOTOR *s, DWORD jugador, DWORD inicio, DWORD fin)
{
    NE_BUCLE *c = &g_ne_b;
    if (c->salto_orden == c->salto_confirmado) return;
    c->salto_confirmado = c->salto_orden;
    if (!jugador || !g_ne_f_buscar) { c->salto_resultado = NE_SALTO_NO_DISPONIBLE; return; }
    if (g_ne_foto.pausada) { c->salto_resultado = NE_SALTO_OCUPADO; return; }
    float pos = NE_F(jugador + 0x18);
    LONG delta = c->salto_ms;
    if (!ne_finito(pos) || pos < (float)inicio || delta < -600000 || delta > 600000 || delta == 0) { c->salto_resultado = NE_SALTO_INVALIDO; return; }
    float obj = pos + (float)delta * 60.0f / 1000.0f;
    if (obj < (float)inicio) obj = (float)inicio;
    if (obj > (float)fin - 30.0f) { c->salto_resultado = NE_SALTO_INVALIDO; return; }
    DWORD clave = (DWORD)((obj - (float)inicio) / 60.0f);
    if (!ne_historia_en(jugador, clave, &g_ne_foto_salto)) { c->salto_resultado = NE_SALTO_NO_TOCADO; return; }
    if (!ne_reposicionar(s, &g_ne_foto_salto, g_ne_foto_salto.posicion)) { c->salto_resultado = NE_SALTO_FALLO; return; }
    g_ne_b.generacion++;
    g_ne_ult_clave = clave;
    c->salto_resultado = NE_SALTO_HECHO;
}

/* 1 = la pausa de la cuenta atrás es nuestra (el reloj sigue, pero no se fabrican cuadros hasta que vuelva el audio) */
static int ne_bucle_tick(NE_MOTOR *s, DWORD ahora)
{
    NE_BUCLE *c = &g_ne_b; NE_INSTANTE *a = &g_ne_foto;
    DWORD jugador = ne_jugador(s);
    DWORD pista = NE_U(s->gestor + 0xA64) + NE_U(s->gestor + 0xA70) * 28;
    DWORD inicio = NE_U(pista + 8), fin = NE_U(pista + 16);
    if (jugador) ne_historia_grabar(s, jugador, inicio);
    ne_salto_tick(s, jugador, inicio, fin);
    if (!c->activo) {
        ne_bucle_seguir(s); a->valida = 0;
        if (c->estado != 6) c->estado = 0;
        c->confirmada = c->orden; return 0;
    }
    if (!jugador || !g_ne_f_buscar || !g_ne_f_pausa || !g_ne_f_seguir) { ne_bucle_fallar(s, 1); return 0; }
    float pos = NE_F(jugador + 0x18);
    if (!ne_finito(pos) || pos < 0 || pos > 216000.0f) { ne_bucle_fallar(s, 2); return 0; }
    c->posicion_ms = pos > (float)inicio ? (DWORD)((pos - (float)inicio) * 1000.0f / 60.0f) : 0;
    if (c->orden != c->confirmada) {
        ne_bucle_seguir(s); a->valida = 0; c->error = 0; c->vueltas = 0; c->restante_ms = 0;
        if (c->desde_ms > 3600000 || c->hasta_ms > 3600000 || c->cuenta_ms > 30000 || c->previo_ms > 30000 ||
            (c->hasta_ms && c->hasta_ms <= c->desde_ms)) { ne_bucle_fallar(s, 3); return 0; }
        float desde = (float)inicio + (float)c->desde_ms * 60.0f / 1000.0f;
        float hasta = c->hasta_ms ? (float)inicio + (float)c->hasta_ms * 60.0f / 1000.0f : (float)fin - 30.0f;
        float captura = desde - (float)c->previo_ms * 60.0f / 1000.0f;
        if (captura < (float)inicio) captura = (float)inicio;
        if (hasta > (float)fin - 30.0f || hasta <= desde) { ne_bucle_fallar(s, 3); return 0; }
        if (pos > captura + 2.0f) {
            DWORD clave = (DWORD)((captura - (float)inicio) / 60.0f);
            if (!ne_historia_en(jugador, clave, &g_ne_foto)) { ne_bucle_fallar(s, 4); return 0; }
        }
        a->cuadro_desde = desde; a->cuadro_hasta = hasta; a->cuadro_captura = captura;
        a->cuenta_ms = c->cuenta_ms; c->confirmada = c->orden; c->estado = a->valida ? 2 : 1;
    }
    if (!a->valida && pos >= a->cuadro_captura) {
        if (!ne_capturar_en(s, jugador, a)) {
            if (NE_U(s->gestor + 0x878) == 0) return 0;
            ne_bucle_fallar(s, 5); return 0;
        }
        c->estado = 2;
    }
    int reinicio = c->reinicio_orden != c->reinicio_confirmado;
    if (reinicio) c->reinicio_confirmado = c->reinicio_orden;
    if (a->pausada && !reinicio) {
        LONG resta = (LONG)(a->pausa_hasta - ahora);
        if (resta > 0) { c->restante_ms = (DWORD)resta; return 1; }
        ne_bucle_seguir(s); c->restante_ms = 0; c->estado = 4;
    }
    if (a->valida && (pos >= a->cuadro_hasta || (!c->hasta_ms && NE_U(s->gestor + 0x878) >= fin - 30) || reinicio)) {
        if (!ne_volver_a_a(s, ahora)) { ne_bucle_fallar(s, 6); return 0; }
        return a->pausada;
    }
    if (a->valida && pos >= a->cuadro_desde && c->estado == 4) c->estado = 2;
    return 0;
}

/* ═══ 3 · EL GANCHO DEL RELOJ Y EL DEL TEMPO (hilo del juego) ══════════════════════════════════════ */
static void ne_restaurar(NE_MOTOR *s, DWORD estado)
{
    ne_bucle_soltar(s);
    ne_historia_borrar();
    if (s->activo) {
        if (ne_audio_propio(s)) {
            DWORD tasa = NE_U(s->muestra + 0x60);
            if (tasa == ne_escala(s->tasa_muestra, s->pct_aplicado, 100)) ne_tasa_audio(s, s->tasa_muestra);
            else if (tasa != s->tasa_muestra) estado = 5;
        }
        if (NE_U(s->imagen + NE_RVA_GESTOR) == s->gestor) {
            DWORD tasa = NE_U(s->gestor + 0x18);
            if (tasa == ne_escala(s->tasa_gestor, 100, s->pct_aplicado)) NE_U(s->gestor + 0x18) = s->tasa_gestor;
            else if (tasa != s->tasa_gestor) estado = 5;
        }
    }
    s->activo = 0; s->deseado = 0; s->estado = estado; s->confirmada = s->orden;
}

static void __cdecl ne_antes_reloj(DWORD ahora) __asm__("ne_asm_antes_reloj") __attribute__((used));
static void __cdecl ne_antes_reloj(DWORD ahora)
{
    NE_MOTOR *s = &g_ne_m;
    if (!s->imagen) return;
    s->hilo = GetCurrentThreadId();
    s->cuadros++;
    if (!s->deseado) { ne_restaurar(s, s->estado); return; }
    if ((LONG)(ahora - s->latido) > 2000) { ne_restaurar(s, 3); return; }
    if (!ne_misma_cancion(s)) { ne_restaurar(s, 1); return; }
    DWORD pct = s->porcentaje;
    if (pct < 50 || pct > 150 || pct % 5) { ne_restaurar(s, 2); return; }
    /* ★ 25-nov: LA PAUSA DEL JUEGO (Esc). Si el reloj no pasó por acá en más de 1 s, Ñ2Hock lo tomaba como falla
     *   (estado 6: «el juego se pausó más de un segundo») y apagaba velocidad, tramo y moverse: justo lo que hace
     *   falta con la Pausa abierta (A/B en la barra, pausa_barra.c). Ahora es una pausa: se retoma desde donde el
     *   juego dejó su reloj, sin cobrar el hueco, y se sigue a la misma velocidad. */
    if (s->activo && (DWORD)(ahora - s->tick_anterior) > 1000) {
        g_ne_pausas++;
        s->tick_anterior = ahora; s->resto = 0; s->origen = NE_U(g_ne_dir_origen);
        return;
    }
    DWORD pct_tramo = s->activo ? s->pct_aplicado : pct;
    int primera = !s->activo;
    if (!s->activo || s->confirmada != s->orden) {
        if (s->activo && NE_U(g_ne_dir_origen) != s->origen) { ne_restaurar(s, 4); return; }
        ne_tasa_audio(s, ne_escala(s->tasa_muestra, pct, 100));
        NE_U(s->gestor + 0x18) = ne_escala(s->tasa_gestor, 100, pct);
        s->pct_aplicado = pct;
        if (primera) { s->tick_anterior = ahora; s->origen = NE_U(g_ne_dir_origen); s->resto = 0; ne_historia_borrar(); }
        s->activo = 1; s->estado = 0; s->confirmada = s->orden;
        if (primera) return;
    }
    if (NE_U(g_ne_dir_origen) != s->origen) { ne_restaurar(s, 4); return; }
    pct = pct_tramo;                        /* se compensa a la velocidad que de verdad sonó */
    int estaba_pausada = g_ne_foto.pausada;
    if (ne_bucle_tick(s, ahora) || estaba_pausada) pct = 0;
    DWORD delta = ahora - s->tick_anterior;
    if (delta > 1000) { ne_restaurar(s, 6); return; }
    LONG num = (LONG)delta * (100 - (LONG)pct) + s->resto;
    LONG correccion = num / 100;
    LONG resto = num - correccion * 100;
    if (correccion > 0) {
        DWORD pasado = ahora - s->origen, cuadro = NE_U(s->imagen + NE_RVA_CUADRO);
        if (cuadro > 4000000) { ne_restaurar(s, 7); return; }      /* el juego lo reinicia por sesión: sin desbordes */
        DWORD simulado = (cuadro * 1000 + 59) / 60;
        DWORD disponible = pasado > simulado ? pasado - simulado : 0;
        if ((DWORD)correccion > disponible) {
            resto += (correccion - (LONG)disponible) * 100;
            correccion = (LONG)disponible;
        }
    }
    if (resto > 10000 || resto < -10000) { ne_restaurar(s, 8); return; }
    s->resto = resto;
    s->origen += correccion;
    NE_U(g_ne_dir_origen) = s->origen;
    s->tick_anterior = ahora;
}

/* entra por JMP en 0x410484 con ECX = timeGetTime(). Guarda flags/registros/FPU, repite las dos instrucciones
 * pisadas (mov eax,ecx · sub eax,[origen]) y vuelve a 0x41048C. */
static void ne_thunk_reloj(void) __asm__("ne_asm_thunk_reloj");
__attribute__((naked, used)) static void ne_thunk_reloj(void)
{
    __asm__ volatile(
        "pushfl\n\tpushal\n\tcld\n\tmovl %esp,%ebx\n\tsubl $528,%esp\n\tandl $-16,%esp\n\tfxsave (%esp)\n\tfninit\n\t"
        "subl $16,%esp\n\tmovl %ecx,(%esp)\n\tcall ne_asm_antes_reloj\n\taddl $16,%esp\n\t"
        "fxrstor (%esp)\n\tmovl %ebx,%esp\n\tpopal\n\tpopfl\n\t"
        "movl %ecx,%eax\n\tpushl %edx\n\tmovl ne_asm_origen,%edx\n\tsubl (%edx),%eax\n\tpopl %edx\n\tjmp *ne_asm_vuelta_reloj\n\t");
}

static DWORD __cdecl ne_bloquear_tempo(DWORD reloj) __asm__("ne_asm_bloquear_tempo") __attribute__((used));
static DWORD __cdecl ne_bloquear_tempo(DWORD reloj)
{
    NE_MOTOR *s = &g_ne_m;
    if (s->activo && reloj == s->gestor + 0xA20 && ne_misma_cancion(s)) {
        g_ne_tempos_bloqueados++;
        return 1;
    }
    return 0;
}

/* el juego tiene sus cambios de tempo propios: durante la práctica su setter común (0x574080, thiscall, 1 arg)
 * devuelve 0 para NUESTRA canción, así ni su audio ni su gestor salen de la velocidad elegida. */
static void ne_thunk_tempo(void) __asm__("ne_asm_thunk_tempo");
__attribute__((naked, used)) static void ne_thunk_tempo(void)
{
    __asm__ volatile(
        "pushfl\n\tpushal\n\tcld\n\tmovl %esp,%ebx\n\tsubl $528,%esp\n\tandl $-16,%esp\n\tfxsave (%esp)\n\tfninit\n\t"
        "subl $16,%esp\n\tmovl %ecx,(%esp)\n\tcall ne_asm_bloquear_tempo\n\taddl $16,%esp\n\ttestl %eax,%eax\n\tjnz 1f\n\t"
        "fxrstor (%esp)\n\tmovl %ebx,%esp\n\tpopal\n\tpopfl\n\t"
        "pushl %esi\n\tmovl %ecx,%esi\n\tcall *ne_asm_validar_tempo\n\tjmp *ne_asm_vuelta_tempo\n\t"
        "1:\n\tfxrstor (%esp)\n\tmovl %ebx,%esp\n\tpopal\n\tpopfl\n\txorl %eax,%eax\n\tret $4\n\t");
}

/* ═══ 4 · LECTURAS DESDE LA VENTANA (con guarda: la memoria del juego puede irse) ═══════════════════ */
enum { NE_TX_VELOCIDAD, NE_TX_BUCLE, NE_TX_TRAMOS, NE_TX_MOVER, NE_TX_ANTICAIDA, NE_TX_N };
static wchar_t g_ne_tx[NE_TX_N][320];
static int g_ne_tx_error[NE_TX_N];
static wchar_t g_ne_err[1100];              /* el porqué del último rechazo («la excepción»); wvsprintfW escribe hasta 1024 */

static void ne_poner_tx(int que, int es_error, const wchar_t *t)
{
    lstrcpynW(g_ne_tx[que], t, 320);
    g_ne_tx_error[que] = es_error;
}

static void ne_log_w(const char *pre, const wchar_t *t)
{
    char u[700];
    int n = WideCharToMultiByte(CP_UTF8, 0, t, -1, u, sizeof(u) - 1, NULL, NULL);
    if (n <= 0) u[0] = 0;
    apuntar("  [entreno] %s%s", pre, u);
}

/* «falla»: guarda el mensaje y devuelve 0 (es el `throw` de Ñ2Hock) */
static int ne_falla(const wchar_t *formato, ...)
{
    va_list a;
    va_start(a, formato);
    wvsprintfW(g_ne_err, formato, a);
    va_end(a);
    return 0;
}

static int ne_lee(DWORD dir, DWORD *v)
{
    if (!dir || !ht_memoria_ok((const void *)(ULONG_PTR)dir, 4, 0)) return 0;
    *v = NE_U(dir);
    return 1;
}
static int ne_lee8(DWORD dir, BYTE *v)
{
    if (!dir || !ht_memoria_ok((const void *)(ULONG_PTR)dir, 1, 0)) return 0;
    *v = NE_B(dir);
    return 1;
}

typedef struct { DWORD dir, tasa; } NE_MUESTRA;
typedef struct {
    DWORD gestor, pista, sonido, fase, cuadro, cuadro_fin, tasa_gestor, cuadro_reloj, origen_reloj, inicio, jugador;
    double pos_ms;
    NE_MUESTRA muestras[8]; int n_muestras;
} NE_CAPTURA;

static DWORD ne_imagen(void) { return (DWORD)(ULONG_PTR)g_ht_base; }

static int ne_leer_audio(DWORD id, DWORD *sonido_out, NE_MUESTRA *m, int *nm)
{
    DWORD img = ne_imagen(), recursos, reg, reg_fin, gen, gen_fin, g, casilla = id & 0xFFFF, sonido, vt, f2c;
    if (!ne_lee(img + NE_RVA_RECURSOS, &recursos) || !recursos) return ne_falla(L"Recursos de audio no disponibles.");
    if (!ne_lee(recursos + 12, &reg) || !ne_lee(recursos + 16, &reg_fin) || !ne_lee(recursos + 0x24, &gen) ||
        !ne_lee(recursos + 0x28, &gen_fin) || !reg || reg_fin <= reg || (reg_fin - reg) % 36 ||
        !gen || gen_fin <= gen || casilla >= (reg_fin - reg) / 36 || casilla >= (gen_fin - gen) / 4 ||
        !ne_lee(gen + casilla * 4, &g) || g != id >> 16)
        return ne_falla(L"El recurso de música cambió.");
    if (!ne_lee(reg + casilla * 36 + 0x1C, &sonido) || !sonido || !ne_lee(sonido, &vt) || vt != img + NE_RVA_SONIDO_VT ||
        !ne_lee(vt + 0x2C, &f2c) || f2c != img + NE_RVA_SONIDO_F2C)
        return ne_falla(L"Este tipo de audio todavía no está soportado.");
    DWORD man, man_fin;
    if (!ne_lee(sonido + 0x24, &man) || !ne_lee(sonido + 0x28, &man_fin) || !man || man_fin <= man ||
        (man_fin - man) % 4 || (man_fin - man) / 4 > 8)
        return ne_falla(L"La música no tiene un stream válido.");
    *nm = 0;
    for (DWORD c = man; c < man_fin; c += 4) {
        /* esta vtable llama a AIL_set_sample_playback_rate: son HSAMPLE (no HSTREAM); +0x0C es el MP3, no un handle */
        DWORD mu, firma, tasa;
        if (!ne_lee(c, &mu) || !mu || !ne_lee(mu, &firma) || firma != NE_HSAM) return ne_falla(L"La muestra de audio no está lista.");
        if (!ne_lee(mu + 0x60, &tasa) || tasa < 4000 || tasa > 384000) return ne_falla(L"Frecuencia de audio no válida.");
        int ya = 0;
        for (int i = 0; i < *nm; i++) ya |= m[i].dir == mu;
        if (!ya) { m[*nm].dir = mu; m[*nm].tasa = tasa; (*nm)++; }
    }
    *sonido_out = sonido;
    return 1;
}

/* PracticeClientReader.Capture (+ la guarda de un solo jugador) */
static int ne_capturar(NE_CAPTURA *f)
{
    DWORD img = ne_imagen(), gestor, ini, fin, indice;
    BYTE fase;
    if (!img) return ne_falla(L"La herramienta todavía no arrancó.");
    WORD modo = 0;
    if (!ne_lee(img + NE_RVA_GESTOR, &gestor) || !gestor || !ht_memoria_ok((const void *)(ULONG_PTR)(gestor + 8), 8, 0))
        return ne_falla(L"No hay una carrera de práctica activa.");
    modo = NE_W(gestor + 12); fase = NE_B(gestor + 8);
    if (modo != 8 || fase >= 4) return ne_falla(L"No hay una carrera de práctica activa.");
    if (!ne_lee(gestor + 0xA64, &ini) || !ne_lee(gestor + 0xA68, &fin) || !ne_lee(gestor + 0xA70, &indice) ||
        !ini || fin <= ini || (fin - ini) % 28 || (fin - ini) / 28 > 64 || indice >= (fin - ini) / 28)
        return ne_falla(L"La canción activa no está disponible.");
    DWORD entrada = ini + indice * 28, id, cuadro_fin, cuadro, inicio;
    if (!ne_lee(entrada, &id) || !ne_lee(entrada + 16, &cuadro_fin) || !ne_lee(gestor + 0x878, &cuadro) ||
        !ne_lee(entrada + 8, &inicio) || !id || !cuadro_fin || cuadro_fin > 60 * 60 * 60 || cuadro >= cuadro_fin)
        return ne_falla(L"La canción terminó o no tiene audio activo.");
    if (!ne_leer_audio(id, &f->sonido, f->muestras, &f->n_muestras)) return 0;
    DWORD tasa;
    if (!ne_lee(gestor + 0x18, &tasa) || tasa < 8000 || tasa > 192000) return ne_falla(L"Reloj de audio no reconocido.");
    DWORD j_ini, j_fin, perfil;
    if (!ne_lee(gestor + 0xA14, &j_ini) || !ne_lee(gestor + 0xA18, &j_fin) || !ne_lee(img + NE_RVA_PERFIL, &perfil) ||
        !perfil || !j_ini || j_fin <= j_ini || (j_fin - j_ini) / 4 > 64)
        return ne_falla(L"Jugador local no disponible.");
    BYTE casilla;
    if (!ne_lee8(perfil + 0x40, &casilla) || casilla >= (j_fin - j_ini) / 4) return ne_falla(L"Casilla local no válida.");
    DWORD jugador = 0;
    ne_lee(j_ini + casilla * 4, &jugador);
#if NE_EXIGIR_UN_JUGADOR
    int vivos = 0;
    for (DWORD c = j_ini; c + 4 <= j_fin; c += 4) { DWORD p; if (ne_lee(c, &p) && p) vivos++; }
    if (vivos != 1) return ne_falla(L"Hay %d jugadores en la carrera: sólo se permite en práctica offline, a solas.", vivos);
#endif
    DWORD bits;
    if (!jugador || !ne_lee(jugador + 0x18, &bits)) return ne_falla(L"Posición de notas no válida.");
    union { DWORD u; float f; } p; p.u = bits;
    if (!ne_finito(p.f) || p.f < -3600.0f || p.f > 216000.0f) return ne_falla(L"Posición de notas no válida.");
    DWORD cr = 0, orr = 0;
    ne_lee(img + NE_RVA_CUADRO, &cr); ne_lee(img + NE_RVA_ORIGEN, &orr);
    double ms = ((double)p.f - (double)inicio) * 1000.0 / 60.0;
    f->gestor = gestor; f->pista = id; f->fase = fase; f->cuadro = cuadro; f->cuadro_fin = cuadro_fin;
    f->tasa_gestor = tasa; f->cuadro_reloj = cr; f->origen_reloj = orr; f->inicio = inicio; f->jugador = jugador;
    f->pos_ms = ms > 0 ? ms : 0;
    return 1;
}

static int ne_misma(const NE_CAPTURA *a, const NE_CAPTURA *b)
{
    if (a->gestor != b->gestor || a->pista != b->pista || a->sonido != b->sonido || a->n_muestras != b->n_muestras) return 0;
    for (int i = 0; i < a->n_muestras; i++) if (a->muestras[i].dir != b->muestras[i].dir) return 0;
    return 1;
}

/* ═══ 5 · EL RELOJ DE LA MÚSICA (PracticeAudioClock: sólo lee) ══════════════════════════════════════
 *   La lectura del MP3 avanza por bloques (~130-160 ms): una lectura sola se atrasa y después salta. Se usa la
 *   envolvente superior del último segundo, con el cero calibrado el primer segundo tras arrancar/cambiar. */
#define NE_RA_VENTANA 1000u
#define NE_RA_CALIBRA 1000u
#define NE_RA_SOSTENIDO 1000u
#define NE_RA_LIMITE 200.0
#define NE_RA_SALTO 600.0
#define NE_RA_N 128
typedef struct {
    DWORD muestra, datos, largo, bufer;
    int kbps;
    double desfase_ini;
    DWORD t[NE_RA_N]; double d[NE_RA_N]; int ini, n;
    DWORD calibra_desde, fuera_desde;
    int calibrando, fuera;
    double base, ultimo;
} NE_RELOJ_AUDIO;
static NE_RELOJ_AUDIO g_ne_ra;

static int ne_ra_posicion(NE_RELOJ_AUDIO *r, double *ms)
{
    DWORD firma, buf, datos, largo, bytes;
    if (!ne_lee(r->muestra, &firma) || firma != NE_HSAM || !ne_lee(r->muestra + 0x40, &buf) || buf != r->bufer ||
        !ne_lee(r->muestra + 12 + r->bufer * 4, &datos) || datos != r->datos ||
        !ne_lee(r->muestra + 0x14 + r->bufer * 4, &largo) || largo != r->largo)
        return ne_falla(L"El búfer de música cambió; se detiene la velocidad.");
    if (!ne_lee(r->muestra + 0x1C + r->bufer * 4, &bytes) || bytes > r->largo) return ne_falla(L"Posición de audio fuera del recurso.");
    *ms = bytes * 8.0 / r->kbps;
    return 1;
}

static int ne_ra_iniciar(NE_RELOJ_AUDIO *r, const NE_CAPTURA *ini, DWORD ahora)
{
    static const int KBPS[16] = { 0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0 };
    static const int FREC[3] = { 44100, 48000, 32000 };
    ZeroMemory(r, sizeof(*r));
    if (ini->n_muestras != 1) return ne_falla(L"La vigilancia de audio requiere una muestra de música única.");
    r->muestra = ini->muestras[0].dir;
    if (!ne_lee(r->muestra + 0x40, &r->bufer) || r->bufer > 1) return ne_falla(L"Búfer de música no reconocido.");
    if (!ne_lee(r->muestra + 12 + r->bufer * 4, &r->datos) || !ne_lee(r->muestra + 0x14 + r->bufer * 4, &r->largo) ||
        r->datos == 0 || r->largo < 4096) return ne_falla(L"Música insuficiente para validar su reloj.");
    DWORD n = r->largo < 8192 ? r->largo : 8192;
    if (!ht_memoria_ok((const void *)(ULONG_PTR)r->datos, (int)n, 0)) return ne_falla(L"Música insuficiente para validar su reloj.");
    const BYTE *h = (const BYTE *)(ULONG_PTR)r->datos;
    DWORD et = n < 512 ? n : 512;
    for (DWORD i = 0; i + 4 <= et; i++)
        if ((h[i] == 'X' && h[i + 1] == 'i' && h[i + 2] == 'n' && h[i + 3] == 'g') ||
            (h[i] == 'V' && h[i + 1] == 'B' && h[i + 2] == 'R' && h[i + 3] == 'I'))
            return ne_falla(L"El reloj de música VBR todavía no está soportado.");
    int esperado = 0;
    DWORD off = 0;
    for (int cuadro = 0; cuadro < 8; cuadro++) {
        if (off + 4 > n || h[off] != 255 || (h[off + 1] & 0xFE) != 0xFA)
            return ne_falla(L"Formato de música no validado para vigilar sincronización.");
        int kb = KBPS[h[off + 2] >> 4], fi = (h[off + 2] >> 2) & 3;
        if (kb == 0 || fi == 3 || (esperado && esperado != kb)) return ne_falla(L"La música no tiene bitrate constante validado.");
        esperado = kb;
        off += (DWORD)(144000 * kb / FREC[fi] + ((h[off + 2] >> 1) & 1));
    }
    r->kbps = esperado;
    double pos;
    if (!ne_ra_posicion(r, &pos)) return 0;
    r->desfase_ini = pos - ini->pos_ms;
    r->calibra_desde = ahora; r->calibrando = 1;
    return 1;
}

static void ne_ra_recalibrar(NE_RELOJ_AUDIO *r, DWORD ahora)
{
    r->ini = r->n = 0; r->calibrando = 1; r->calibra_desde = ahora; r->fuera = 0; r->ultimo = 0;
}

/* 1 = en sincronía (r->ultimo = el desfase calibrado); 0 = desfase real y sostenido (o el búfer cambió) */
static int ne_ra_revisar(NE_RELOJ_AUDIO *r, double nota_ms, DWORD ahora)
{
    double pos;
    if (!ne_ra_posicion(r, &pos)) return 0;
    double crudo = pos - nota_ms - r->desfase_ini;
    if (r->n == NE_RA_N) { r->ini = (r->ini + 1) % NE_RA_N; r->n--; }
    int k = (r->ini + r->n) % NE_RA_N;
    r->t[k] = ahora; r->d[k] = crudo; r->n++;
    while (r->n > 0 && ahora - r->t[r->ini] > NE_RA_VENTANA) { r->ini = (r->ini + 1) % NE_RA_N; r->n--; }
    double env = crudo;
    for (int i = 0; i < r->n; i++) { double v = r->d[(r->ini + i) % NE_RA_N]; if (v > env) env = v; }
    if (r->calibrando) {
        if (ahora - r->calibra_desde < NE_RA_CALIBRA) { r->ultimo = 0; return 1; }
        r->calibrando = 0; r->base = env;
    }
    double d = r->ultimo = env - r->base;
    double ad = d < 0 ? -d : d;
    /* ★ 19-nov (anonimo03: «cuando pasan unos segundos vuelve a la velocidad de siempre»): en nuestra dll esta medida
     *   da desfases falsos (−264 ms al 100 %, −4483 ms…: la fluidez dibuja más cuadros que la lógica) y Ñ2Hock aquí
     *   APAGABA la velocidad. ⇒ Ya no se apaga: se anota (una vez cada 10 s) y se vuelve a calibrar. */
    if (ad <= NE_RA_LIMITE) { r->fuera = 0; return 1; }
    if (!r->fuera) { r->fuera = 1; r->fuera_desde = ahora; }
    if (ad > NE_RA_SALTO || ahora - r->fuera_desde >= NE_RA_SOSTENIDO) {
        static DWORD avisado = 0;
        if (!avisado || ahora - avisado > 10000) { avisado = ahora ? ahora : 1; apuntar("  [entreno] desfase audio/notas %d ms: se recalibra (no se detiene)", (int)d); }
        ne_ra_recalibrar(r, ahora);
    }
    return 1;
}

/* ═══ 6 · TRAMOS DE VELOCIDAD (SpeedZones) Y POSICIONES m:ss ════════════════════════════════════════ */
#define NE_POS_MAX ((999 * 60 + 59) * 1000)
typedef struct { int numero, desde, hasta, pct; } NE_TRAMO;
typedef struct { NE_TRAMO t[NE_TOPE_TRAMOS]; int n, incompletos; } NE_TRAMOS;

static int ne_posicion_de_texto(const wchar_t *s)
{
    if (!s) return -1;
    while (*s == ' ' || *s == '\t') s++;
    int m = 0, sg = 0, dm = 0, ds = 0;
    while (*s >= '0' && *s <= '9') { m = m * 10 + (*s - '0'); if (++dm > 3) return -1; s++; }
    if (!dm || *s != ':') return -1;
    s++;
    while (*s >= '0' && *s <= '9') { sg = sg * 10 + (*s - '0'); if (++ds > 2) return -1; s++; }
    while (*s == ' ' || *s == '\t') s++;
    if (!ds || *s || sg > 59) return -1;
    return (m * 60 + sg) * 1000;
}

static void ne_texto_de_posicion(int ms, wchar_t *s)       /* s: 16 */
{
    int sg = ms > 0 ? ms / 1000 : 0;
    wsprintfW(s, L"%d:%02d", sg / 60, sg % 60);
}

static int ne_tramos_compilar(const int *de, const int *ha, const int *pc, int n, NE_TRAMOS *out)
{
    if (n > NE_TOPE_TRAMOS) return ne_falla(L"Como máximo %d tramos de velocidad.", NE_TOPE_TRAMOS);
    NE_TRAMOS r; ZeroMemory(&r, sizeof(r));
    for (int i = 0; i < n; i++) {
        int a = de[i], b = ha[i], num = i + 1;
        if (a < 0 && b < 0) continue;
        if (a > NE_POS_MAX || b > NE_POS_MAX)
            return ne_falla(L"Tramo %d: escribe las posiciones en formato m:ss, por ejemplo 1:05.", num);
        if (pc[i] < 50 || pc[i] > 150 || pc[i] % 5)
            return ne_falla(L"Tramo %d: la velocidad debe estar entre 50 y 150 %%, en pasos de 5 %%.", num);
        if (a < 0 || b < 0) { r.incompletos++; continue; }
        if (b <= a) return ne_falla(L"Tramo %d: «Hasta» debe ser posterior a «Desde».", num);
        NE_TRAMO t = { num, a, b, pc[i] };
        int k = r.n++;                                  /* inserción estable, por «desde» */
        while (k > 0 && r.t[k - 1].desde > t.desde) { r.t[k] = r.t[k - 1]; k--; }
        r.t[k] = t;
    }
    for (int i = 1; i < r.n; i++)
        if (r.t[i].desde < r.t[i - 1].hasta)
            return ne_falla(L"Los tramos %d y %d se solapan.", r.t[i - 1].numero, r.t[i].numero);
    *out = r;
    return 1;
}

static const NE_TRAMO *ne_tramo_en(const NE_TRAMOS *z, double pos)
{
    if (!(pos == pos) || pos < 0) return NULL;     /* NaN / sin posición */
    for (int i = 0; i < z->n; i++) {
        if (pos < z->t[i].desde) return NULL;
        if (pos < z->t[i].hasta) return &z->t[i];
    }
    return NULL;
}

/* ═══ 7 · ESCRIBIR CÓDIGO DEL EXE: todos los hilos quietos y ninguno adentro de los bytes ════════════
 *   El VirtualProtect de acá es el de antitrampa_envoltura.h: lo nuestro queda como «lo esperado». Mientras los hilos
 *   están congelados no se llama a nada que tome candados (ni apuntar(), ni el heap). */
#define NE_MAX_HILOS 512
static int ne_escribir_codigo(DWORD rva, const BYTE *esp, const BYTE *nue, int n, const char *que)
{
    BYTE *s = g_ht_base + rva;
    if (!ht_memoria_ok(s, n, 0)) {
        apuntar("  [entreno] ⛔ %s: 0x%08X no existe en este exe. NO SE TOCA.", que, 0x400000 + rva);
        return 0;
    }
    for (int i = 0; i < n; i++) if (s[i] != esp[i]) {
        char hex[64]; hex[0] = 0;
        for (int j = 0; j < n && j < 12; j++) wsprintfA(hex + lstrlenA(hex), "%02X ", s[j]);
        apuntar("  [entreno] ⛔ %s: en 0x%08X hay [%s] y esperaba otra cosa. NO SE TOCA.", que, 0x400000 + rva, hex);
        return 0;
    }
    EnterCriticalSection(&g_ht_cs);
    DWORD viejo = 0;
    if (!VirtualProtect(s, n, PAGE_EXECUTE_READWRITE, &viejo)) {
        LeaveCriticalSection(&g_ht_cs);
        apuntar("  [entreno] ⛔ %s: no pude abrir la memoria en 0x%08X", que, 0x400000 + rva);
        return 0;
    }
    static HANDLE hs[NE_MAX_HILOS];
    static BYTE quieto[NE_MAX_HILOS];
    DWORD yo = GetCurrentThreadId(), pid = GetCurrentProcessId();
    int hecho = 0, ocupado_visto = 0, error = 0;
    for (int intento = 0; intento < 20 && !hecho && !error; intento++) {
        int nh = 0, ocupado = 0;
        HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
        if (snap == INVALID_HANDLE_VALUE) { error = 1; break; }
        THREADENTRY32 t;
        t.dwSize = sizeof(t);
        for (BOOL ok = Thread32First(snap, &t); ok; ok = Thread32Next(snap, &t)) {
            if (t.th32OwnerProcessID != pid || t.th32ThreadID == yo) continue;
            if (nh >= NE_MAX_HILOS) { error = 1; break; }
            HANDLE h = OpenThread(THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT | THREAD_QUERY_INFORMATION, FALSE, t.th32ThreadID);
            if (!h) continue;                               /* ya terminó: no puede ejecutar nada */
            hs[nh] = h; quieto[nh] = 0; nh++;
        }
        CloseHandle(snap);
        for (int i = 0; i < nh && !error; i++) {
            if (SuspendThread(hs[i]) == (DWORD)-1) continue;   /* terminó entre medio */
            quieto[i] = 1;
            CONTEXT c;
            ZeroMemory(&c, sizeof(c));
            c.ContextFlags = CONTEXT_CONTROL;
            if (!GetThreadContext(hs[i], &c)) { error = 1; break; }
            if (c.Eip > (DWORD)(ULONG_PTR)s && c.Eip < (DWORD)(ULONG_PTR)s + (DWORD)n) ocupado = 1;
        }
        if (!error && !ocupado) {
            for (int i = 0; i < n; i++) s[i] = nue[i];
            hecho = 1;
        }
        for (int i = nh - 1; i >= 0; i--) { if (quieto[i]) ResumeThread(hs[i]); CloseHandle(hs[i]); }
        if (ocupado) { ocupado_visto = 1; Sleep(2); }
    }
    VirtualProtect(s, n, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), s, n);
    LeaveCriticalSection(&g_ht_cs);
    if (!hecho) {
        apuntar("  [entreno] ⚠ %s: %s; NO SE TOCA (probar de nuevo)", que,
                error ? "no pude congelar los hilos del juego" : ocupado_visto ? "un hilo está justo adentro" : "falló");
        return error ? 0 : -1;
    }
    return 1;
}

/* el salto `E9 rel32 90 90 90` de `rva` a `destino` */
static void ne_salto(DWORD rva, void *destino, BYTE b[8])
{
    DWORD desde = ne_imagen() + rva;
    b[0] = 0xE9;
    *(DWORD *)(b + 1) = (DWORD)(ULONG_PTR)destino - (desde + 5);
    b[5] = b[6] = b[7] = 0x90;
}

static void ne_bytes_reloj(BYTE b[8])
{
    b[0] = 0x8B; b[1] = 0xC1; b[2] = 0x2B; b[3] = 0x05;
    *(DWORD *)(b + 4) = ne_imagen() + NE_RVA_ORIGEN;
}
static const BYTE NE_BYTES_TEMPO[8] = { 0x56, 0x8B, 0xF1, 0xE8, 0xF8, 0xFD, 0xFF, 0xFF };
static const BYTE NE_FIRMA_BUSCAR[16] = { 0x83, 0xEC, 0x08, 0x56, 0x8B, 0xF1, 0x8B, 0x86, 0x18, 0x0A, 0x00, 0x00, 0x2B, 0x86, 0x14, 0x0A };
static const BYTE NE_FIRMA_PAUSA[16]  = { 0x51, 0x56, 0x8B, 0xF1, 0x8D, 0x8E, 0x20, 0x0A, 0x00, 0x00, 0xE8, 0x31, 0x66, 0x00, 0x00, 0xA1 };
static const BYTE NE_FIRMA_SEGUIR[10] = { 0x81, 0xC1, 0x20, 0x0A, 0x00, 0x00, 0xE9, 0xA5, 0x69, 0x00 };
static const BYTE NE_FIRMA_ANTICAIDA[11] = { 0x75, 0x43, 0x80, 0xBE, 0x9C, 0x02, 0x00, 0x00, 0x00, 0x75, 0x3A };
static const BYTE NE_ANTICAIDA_NUEVO[2] = { 0x90, 0x90 };
static const BYTE NE_MSS_FIRMA[11] = { 0x85, 0xDB, 0x74, 0x07, 0x85, 0xFF, 0x7E, 0x03, 0x89, 0x7B, 0x60 };

static int ne_iguales(DWORD dir, const BYTE *b, int n)
{
    if (!ht_memoria_ok((const void *)(ULONG_PTR)dir, n, 0)) return 0;
    for (int i = 0; i < n; i++) if (NE_B(dir + i) != b[i]) return 0;
    return 1;
}

/* ═══ 8 · LA SESIÓN (NativePracticeModule + NativePracticeSession) — hilo de la ventana ══════════════ */
static DWORD (WINAPI *g_ne_tgt)(void);
static DWORD ne_ahora(void)
{
    if (!g_ne_tgt) {
        HMODULE w = LoadLibraryA("winmm.dll");
        g_ne_tgt = w ? (DWORD (WINAPI *)(void))GetProcAddress(w, "timeGetTime") : NULL;
        if (!g_ne_tgt) g_ne_tgt = GetTickCount;
    }
    return g_ne_tgt();
}

static int g_ne_instalado;                  /* los dos ganchos puestos */
static HANDLE g_ne_licencia;                /* el semáforo compartido con Ñ2Hock */
static int g_ne_sesion;                     /* practiceController != null */
static NE_CAPTURA g_ne_inicial;
static int g_ne_pct_actual = 100;           /* Percent de la sesión */
static DWORD g_ne_ult_audio, g_ne_gen_bucle, g_ne_silencio_hasta, g_ne_err_reconocido;
static double g_ne_pos_ms = -1, g_ne_largo_ms = -1;
static int g_ne_restaurar_pendiente;
static DWORD g_ne_ult_reintento;

/* lo que en Ñ2Hock son las casillas y los cuadros de texto */
static int g_ne_q_vel, g_ne_q_prep, g_ne_q_bucle, g_ne_q_tramos, g_ne_q_ac;
/* ★ 25-nov, «Se aplicará al entrar a entrenar» (ToolBit 0.6.40): la velocidad prendida es la INTENCIÓN del jugador.
 *   Fuera de la carrera queda ARMADA y ne_tick la aplica sola al haber canción de práctica; al terminar la canción
 *   (el motor se restaura, como siempre) vuelve a quedar armada para la próxima. Tras una falla de verdad espera a que
 *   se salga de esa carrera antes de volver a probar (no reintenta en bucle). */
static int g_ne_vel_quiere = 0, g_ne_vel_espera_salida = 0;
/* lo mismo con «Repetir un tramo»: armado se aplica al empezar la práctica (el motor graba desde el inicio, así se
 * corre hasta A y desde ahí sigue el bucle). Si A ya pasó y no está grabado, no se apaga: espera a la próxima carrera
 * (o a «Repetir» de la Pausa). */
static int g_ne_bucle_quiere = 0, g_ne_bucle_espera_salida = 0;
static DWORD g_ne_vel_reintento = 0;
static int g_ne_pct_elegido = 75;           /* el deslizador */
static int g_ne_pct_pedido = 75;            /* requestedPracticeSpeed */
static int g_ne_b_desde = 0, g_ne_b_hasta = 0, g_ne_b_cuenta = 3, g_ne_b_previo = 2;
static int g_ne_z_desde[NE_TOPE_TRAMOS] = { -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1 },
           g_ne_z_hasta[NE_TOPE_TRAMOS] = { -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1 };
static int g_ne_z_pct[NE_TOPE_TRAMOS] = { 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100 };
static NE_TRAMOS g_ne_tramos;               /* activeSpeedZones (válido si g_ne_q_tramos) */
static DWORD g_ne_ac_gestor;

static int ne_esperar(volatile DWORD *a, volatile DWORD *b, int igual_a_cero)
{
    if (g_ne_m.hilo && g_ne_m.hilo == GetCurrentThreadId()) return 0;    /* el gancho corre en ESTE hilo: no esperar */
    DWORD t0 = GetTickCount();
    while (GetTickCount() - t0 < 1500) {
        if (igual_a_cero ? *a == 0 : *a == *b) return 1;
        Sleep(5);
    }
    return igual_a_cero ? *a == 0 : *a == *b;
}

/* el bucle quedó apagado (estado 0) o en error (6): ya no tiene la pausa de la cuenta atrás */
static int ne_esperar_bucle_quieto(void)
{
    DWORD t0 = GetTickCount();
    for (;;) {
        DWORD e = g_ne_b.estado;
        if (e == 0 || e == 6) return 1;
        if ((g_ne_m.hilo && g_ne_m.hilo == GetCurrentThreadId()) || GetTickCount() - t0 >= 1500) return 0;
        Sleep(5);
    }
}

/* el semáforo de Ñ2Hock: «Local\ToolBitPracticeSession_<pid>_<StartTime.ToUniversalTime().Ticks>» */
static int ne_licencia_tomar(void)
{
    if (g_ne_licencia) return 1;
    FILETIME c, x, k, u;
    if (!GetProcessTimes(GetCurrentProcess(), &c, &x, &k, &u)) return ne_falla(L"No pude leer el inicio del proceso.");
    unsigned long long t = ((unsigned long long)c.dwHighDateTime << 32 | c.dwLowDateTime) + 504911232000000000ULL;
    wchar_t num[24], nombre[96];
    int i = 23; num[i] = 0;
    do { num[--i] = (wchar_t)(L'0' + (int)(t % 10)); t /= 10; } while (t && i > 0);
    wsprintfW(nombre, L"Local\\ToolBitPracticeSession_%u_%s", (unsigned)GetCurrentProcessId(), num + i);
    HANDLE h = CreateSemaphoreW(NULL, 1, 1, nombre);
    if (!h) return ne_falla(L"No pude crear el semáforo del entrenamiento.");
    if (WaitForSingleObject(h, 0) != WAIT_OBJECT_0) {
        CloseHandle(h);
        return ne_falla(L"Otra instancia (¿Ñ2Hock?) ya controla el entrenamiento de este cliente.");
    }
    g_ne_licencia = h;
    return 1;
}
static void ne_licencia_soltar(void)
{
    if (!g_ne_licencia) return;
    ReleaseSemaphore(g_ne_licencia, 1, NULL);
    CloseHandle(g_ne_licencia);
    g_ne_licencia = NULL;
}

/* WindowsPracticeMemory: ToolBitDLL fuera, mss32 validada, y el import de la frecuencia es el de Miles */
static int ne_cliente_ok(void)
{
    if (!g_ht_base) return ne_falla(L"La herramienta todavía no arrancó.");
    if (GetModuleHandleA("ToolBitDLL.dll")) return ne_falla(L"Cierra el motor ToolBitDLL antes de usar la velocidad independiente.");
    HMODULE mss = GetModuleHandleA("mss32.dll");
    if (!mss) return ne_falla(L"La biblioteca de audio aún no está cargada.");
    if (!ne_iguales((DWORD)(ULONG_PTR)mss + 0x1509B, NE_MSS_FIRMA, 11)) return ne_falla(L"La rutina de frecuencia del cliente cambió.");
    DWORD imp;
    FARPROC real = GetProcAddress(mss, "_AIL_set_sample_playback_rate@8");
    if (!ne_lee(ne_imagen() + NE_RVA_AIL_TASA, &imp) || !real || imp != (DWORD)(ULONG_PTR)real)
        return ne_falla(L"La importación de frecuencia de audio no es la validada.");
    return 1;
}

/* LinkLoopFunctions: las tres del juego, con firma */
static int ne_enlazar_bucle(void)
{
    DWORD img = ne_imagen();
    if (!ne_iguales(img + NE_RVA_BUSCAR, NE_FIRMA_BUSCAR, 16)) return ne_falla(L"La función del cliente para buscar no está validada.");
    if (!ne_iguales(img + NE_RVA_PAUSA, NE_FIRMA_PAUSA, 16)) return ne_falla(L"La función del cliente para pausar no está validada.");
    if (!ne_iguales(img + NE_RVA_SEGUIR, NE_FIRMA_SEGUIR, 10)) return ne_falla(L"La función del cliente para seguir no está validada.");
    g_ne_f_buscar = img + NE_RVA_BUSCAR; g_ne_f_pausa = img + NE_RVA_PAUSA; g_ne_f_seguir = img + NE_RVA_SEGUIR;
    return 1;
}

static int ne_quitar_ganchos(void)
{
    if (!g_ne_instalado) return 1;
    BYTE orig[8], salto[8];
    int ok = 1;
    if (g_ne_instalado & 1) {
        ne_bytes_reloj(orig); ne_salto(NE_RVA_RELOJ, (void *)ne_thunk_reloj, salto);
        if (ne_escribir_codigo(NE_RVA_RELOJ, salto, orig, 8, "entreno: quitar el gancho del reloj") > 0) g_ne_instalado &= ~1;
        else ok = 0;
    }
    if (g_ne_instalado & 2) {
        ne_salto(NE_RVA_TEMPO, (void *)ne_thunk_tempo, salto);
        if (ne_escribir_codigo(NE_RVA_TEMPO, salto, NE_BYTES_TEMPO, 8, "entreno: quitar el gancho del tempo") > 0) g_ne_instalado &= ~2;
        else ok = 0;
    }
    if (ok) apuntar("  [entreno] ganchos del reloj y del tempo retirados (bytes de fábrica)");
    return ok;
}

/* Install: guardas, configuración y los dos saltos */
static int ne_instalar(const NE_CAPTURA *ini)
{
    if (g_ne_instalado == 3) return 1;
    if (ini->n_muestras != 1) return ne_falla(L"La sesión de música no es compatible con el motor nativo.");
    if (!ne_licencia_tomar()) return 0;
    if (g_ne_m.activo) return ne_falla(L"ABI del motor incompatible o sesión anterior todavía activa.");
    DWORD img = ne_imagen();
    BYTE reloj[8];
    ne_bytes_reloj(reloj);
    if (!(g_ne_instalado & 1) && !ne_iguales(img + NE_RVA_RELOJ, reloj, 8))
        return ne_falla(L"La rutina de reloj cambió o ya tiene otro enlace.");
    if (!(g_ne_instalado & 2) && !ne_iguales(img + NE_RVA_TEMPO, NE_BYTES_TEMPO, 8))
        return ne_falla(L"La rutina de tempo del cliente cambió o ya tiene otro enlace.");
    g_ne_dir_origen = img + NE_RVA_ORIGEN;
    g_ne_vuelta_reloj = img + NE_RVA_RELOJ_VUELTA;
    g_ne_vuelta_tempo = img + NE_RVA_TEMPO_VUELTA;
    g_ne_validar_tempo = img + NE_RVA_TEMPO_VALIDA;
    g_ne_m.deseado = 0;                     /* primero apagado: el gancho no hace nada hasta el pedido */
    MemoryBarrier();
    g_ne_m.imagen = img; g_ne_m.gestor = ini->gestor; g_ne_m.pista = ini->pista; g_ne_m.sonido = ini->sonido;
    g_ne_m.muestra = ini->muestras[0].dir; g_ne_m.tasa_gestor = ini->tasa_gestor; g_ne_m.tasa_muestra = ini->muestras[0].tasa;
    g_ne_m.porcentaje = 100; g_ne_m.latido = ne_ahora(); g_ne_m.orden = 0; g_ne_m.confirmada = 0;
    g_ne_m.estado = 0; g_ne_m.pct_aplicado = 100;
    g_ne_tempos_bloqueados = 0; g_ne_m.cuadros = 0; g_ne_m.hilo = 0;
    g_ne_b.activo = 0;
    MemoryBarrier();
    BYTE salto[8];
    if (!(g_ne_instalado & 1)) {
        ne_salto(NE_RVA_RELOJ, (void *)ne_thunk_reloj, salto);
        if (ne_escribir_codigo(NE_RVA_RELOJ, reloj, salto, 8, "entreno: gancho del reloj (0x410484)") <= 0)
            return ne_falla(L"No se pudo enlazar el reloj del cliente (está ocupado o cambió).");
        g_ne_instalado |= 1;
    }
    if (!(g_ne_instalado & 2)) {
        ne_salto(NE_RVA_TEMPO, (void *)ne_thunk_tempo, salto);
        if (ne_escribir_codigo(NE_RVA_TEMPO, NE_BYTES_TEMPO, salto, 8, "entreno: gancho del tempo (0x574080)") <= 0) {
            ne_quitar_ganchos();
            return ne_falla(L"No se pudo enlazar la rutina de tempo del cliente (está ocupada o cambió).");
        }
        g_ne_instalado |= 2;
    }
    apuntar("  [entreno] ★ ganchos puestos: reloj 0x410484 y tempo 0x574080 (gestor 0x%08X, muestra 0x%08X)",
            ini->gestor, ini->muestras[0].dir);
    return 1;
}

/* Request: el gancho aplica el % en el hilo del juego y lo confirma */
static int ne_pedir(int pct)
{
    if (g_ne_instalado != 3 || pct < 50 || pct > 150 || pct % 5) return ne_falla(L"Velocidad nativa no preparada o fuera de rango.");
    g_ne_m.latido = ne_ahora();
    g_ne_m.porcentaje = (DWORD)pct;
    MemoryBarrier();
    g_ne_m.orden++;
    g_ne_m.deseado = 1;
    if (!ne_esperar(&g_ne_m.confirmada, &g_ne_m.orden, 0)) return ne_falla(L"El reloj del cliente no confirmó la velocidad.");
    if (g_ne_m.activo != 1) return ne_falla(L"El motor rechazó la sesión (estado %u).", (unsigned)g_ne_m.estado);
    return 1;
}

/* Stop: el gancho restaura en su hilo y recién después se retiran los saltos */
static int ne_detener_motor(void)
{
    if (!g_ne_instalado) { ne_licencia_soltar(); return 1; }
    g_ne_m.deseado = 0;
    if (!ne_esperar(&g_ne_m.activo, NULL, 1))
        return ne_falla(L"El cliente aún no confirmó la restauración; se conserva el enlace para reintentar.");
    int alterado = g_ne_m.estado == 5;
    if (!ne_quitar_ganchos()) return ne_falla(L"No se pudo retirar el enlace del reloj; se reintentará.");
    ne_licencia_soltar();
    if (alterado) ne_log_w("", L"Se retiró el enlace; el cliente cambió las frecuencias y no se sobrescribieron.");
    return 1;
}

static int ne_poner_pct(int pct)            /* NativePracticeSession.SetPercent */
{
    if (pct < 50 || pct > 150 || pct % 5) return ne_falla(L"Velocidad fuera de rango.");
    NE_CAPTURA ahora;
    if (!ne_capturar(&ahora)) return 0;
    if (!ne_misma(&g_ne_inicial, &ahora)) return ne_falla(L"La canción cambió antes de preparar velocidad.");
    if (!ne_instalar(&g_ne_inicial)) return 0;
    if (!ne_pedir(pct)) return 0;
    g_ne_pct_actual = pct;
    g_ne_ult_audio = ne_ahora();
    ne_ra_recalibrar(&g_ne_ra, g_ne_ult_audio);
    return 1;
}

static int ne_parar_sesion(void)            /* StopLivePractice */
{
    g_ne_pos_ms = -1;
    if (!g_ne_sesion && !g_ne_instalado) { ne_licencia_soltar(); g_ne_restaurar_pendiente = 0; return 1; }
    if (!ne_detener_motor()) {
        g_ne_restaurar_pendiente = 1;
        wchar_t t[400];
        g_ne_err[300] = 0;
        wsprintfW(t, TR(L"Restauración pendiente: %s"), g_ne_err);
        lstrcpynW(g_ne_err, t, 400);
        ne_log_w("⚠ ", g_ne_err);
        return 0;
    }
    if (g_ne_sesion) apuntar("  [entreno] motor detenido; frecuencias originales restauradas");
    g_ne_sesion = 0;
    g_ne_restaurar_pendiente = 0;
    return 1;
}

/* EnsurePracticeEngine: captura, guardas, reloj de audio, ganchos y el primer % */
static int ne_asegurar_motor(int pct)
{
    if (g_ne_sesion) return 1;
    if (g_ne_restaurar_pendiente) return ne_falla(L"Hay una restauración pendiente; espera un momento.");
    if (!ne_cliente_ok()) return 0;
    NE_CAPTURA ini;
    if (!ne_capturar(&ini)) return 0;
    if (ini.tasa_gestor != 44100 || ini.n_muestras != 1 || ini.muestras[0].tasa != 44100)
        return ne_falla(L"Primero restaura el audio a 44100 Hz; la sesión nativa requiere esa configuración validada.");
    if (!ne_ra_iniciar(&g_ne_ra, &ini, ne_ahora())) return 0;
    g_ne_inicial = ini;
    g_ne_sesion = 1;
    g_ne_pos_ms = -1;
    g_ne_gen_bucle = g_ne_b.generacion; g_ne_silencio_hasta = ne_ahora(); g_ne_err_reconocido = 0;
    if (!ne_poner_pct(pct)) {
        wchar_t guardado[320];
        lstrcpynW(guardado, g_ne_err, 320);
        ne_parar_sesion();
        lstrcpynW(g_ne_err, guardado, 320);
        return 0;
    }
    g_ne_pct_pedido = pct;
    apuntar("  [entreno] ★ motor iniciado a %d %% (gestor 0x%08X, pista 0x%08X)", pct, ini.gestor, ini.pista);
    return 1;
}

/* LoopError / SeekError */
static const wchar_t *ne_error_bucle(DWORD e)
{
    static wchar_t t[96];
    switch (e) {
    case 4: return L"Sin captura de A. Habilita el motor al inicio de otra canción, o elige un A futuro.";
    case 3: return L"El tramo está fuera de la canción o sus tiempos no son válidos.";
    case 6: return L"El mapa de notas cambió; se detuvo el bucle antes de reposicionar.";
    default: wsprintfW(t, TR(L"El motor no pudo preparar el estado de notas del tramo (%u)."), (unsigned)e); return t;
    }
}
static const wchar_t *ne_error_salto(DWORD e, int delta_ms)
{
    static wchar_t t[96];
    switch (e) {
    case 2: return delta_ms < 0 ? L"Ese momento no está grabado: solo se puede volver a segundos tocados desde que activaste el motor."
                                : L"Todavía no has llegado ahí: hacia delante solo se vuelve a donde ya estuviste.";
    case 3: return L"El salto se sale de la canción.";
    case 4: return L"Espera a que termine la cuenta atrás del tramo.";
    case 5: return L"El mapa de notas cambió; no se movió nada.";
    default: wsprintfW(t, TR(L"El juego no está listo para saltar (%u)."), (unsigned)e); return t;
    }
}
static const wchar_t *ne_error_motor(DWORD e)
{
    static wchar_t t[96];
    switch (e) {
    case 1: return L"La canción terminó o cambió; el motor restauró la velocidad.";
    case 3: return L"Se perdió el latido de la herramienta; el motor restauró la velocidad.";
    case 4: return L"El juego reinició su reloj; se detuvo la velocidad.";
    case 6: return L"El juego se pausó más de un segundo; se detuvo la velocidad.";
    default: wsprintfW(t, TR(L"El motor detuvo la práctica (estado %u)."), (unsigned)e); return t;
    }
}

/* Step(): latido, misma canción, fallas del bucle y vigilancia del audio */
static int ne_paso(void)
{
    if (!g_ne_sesion) return ne_falla(L"La sesión nativa está detenida.");
    DWORD ahora = ne_ahora();
    g_ne_m.latido = ahora;
    if (g_ne_m.activo == 0) return ne_falla(L"%s", ne_error_motor(g_ne_m.estado));
    DWORD gen_antes = g_ne_b.generacion;
    NE_CAPTURA f;
    if (!ne_capturar(&f)) return 0;
    if (!ne_misma(&g_ne_inicial, &f)) return ne_falla(L"La canción cambió.");
    ahora = ne_ahora();
    DWORD gen = g_ne_b.generacion, est = g_ne_b.estado, err = g_ne_b.error;
    g_ne_pos_ms = f.pos_ms; g_ne_largo_ms = f.cuadro_fin * 1000.0 / 60.0;
    if (est == 6 && err != 0 && err != g_ne_err_reconocido) return ne_falla(L"%s", ne_error_bucle(err));
    if (gen_antes != gen || gen != g_ne_gen_bucle || (gen & 1)) {
        g_ne_gen_bucle = gen; g_ne_silencio_hasta = ahora + 300; ne_ra_recalibrar(&g_ne_ra, g_ne_silencio_hasta);
        return 1;
    }
    if ((LONG)(ahora - g_ne_silencio_hasta) >= 0 && ahora - g_ne_ult_audio >= 50) {
        if (!ne_ra_revisar(&g_ne_ra, f.pos_ms, ahora)) return 0;
        g_ne_ult_audio = ahora;
    }
    return 1;
}

static int ne_objetivo(void)                /* TargetPracticeSpeed */
{
    if (!g_ne_q_tramos) return g_ne_pct_pedido;
    const NE_TRAMO *t = ne_tramo_en(&g_ne_tramos, g_ne_pos_ms);
    return t ? t->pct : g_ne_pct_pedido;
}

/* el error del «trabajador»: se apaga TODO y se dice en cada cartel que estaba activo */
static void ne_fallo_trabajador(const wchar_t *msg)
{
    wchar_t m[320];
    lstrcpynW(m, msg, 300);
    ne_log_w("⛔ ", m);
    int bucle = g_ne_q_bucle, tramos = g_ne_q_tramos;
    if (!ne_parar_sesion()) { lstrcatW(m, TR(L" · Restauración pendiente.")); }
    g_ne_q_bucle = 0; g_ne_q_tramos = 0; g_ne_q_prep = 0; g_ne_q_vel = 0;
    if (g_ne_bucle_quiere) g_ne_bucle_espera_salida = 1;
    if (g_ne_vel_quiere) {                              /* sigue armada, pero no en ESTA carrera */
        g_ne_vel_espera_salida = 1;
        lstrcatW(m, TR(L" · La velocidad queda armada para la próxima práctica."));
    }
    ne_poner_tx(NE_TX_VELOCIDAD, 1, m);
    if (bucle) ne_poner_tx(NE_TX_BUCLE, 1, m);
    if (tramos) ne_poner_tx(NE_TX_TRAMOS, 1, m);
}

/* ═══ 9 · ANTICAÍDA (PracticeAntiFallSession) ══════════════════════════════════════════════════════ */
static int ne_carrera_ac(DWORD gestor)
{
    DWORD img = ne_imagen(), g;
    if (!img || !gestor || !ne_lee(img + NE_RVA_GESTOR, &g) || g != gestor ||
        !ht_memoria_ok((const void *)(ULONG_PTR)(gestor + 8), 8, 0)) return 0;
    if ((NE_W(gestor + 12) & 0x7F) != 8 || NE_B(gestor + 8) != 3) return 0;
#if NE_EXIGIR_UN_JUGADOR
    DWORD a, b; int vivos = 0;
    if (!ne_lee(gestor + 0xA14, &a) || !ne_lee(gestor + 0xA18, &b) || !a || b <= a || (b - a) / 4 > 64) return 0;
    for (DWORD c = a; c + 4 <= b; c += 4) { DWORD p; if (ne_lee(c, &p) && p) vivos++; }
    if (vivos != 1) return 0;
#endif
    return 1;
}

static int ne_ac_restaurar(void)
{
    if (!g_ne_q_ac) return 1;
    int r = ne_escribir_codigo(NE_RVA_ANTICAIDA, NE_ANTICAIDA_NUEVO, NE_FIRMA_ANTICAIDA, 2, "entreno: Anticaída (restaurar)");
    if (r <= 0) {
        ne_poner_tx(NE_TX_VELOCIDAD, 1, L"Anticaída: restauración pendiente; se reintentará.");
        return 0;
    }
    g_ne_q_ac = 0;
    ne_poner_tx(NE_TX_ANTICAIDA, 0, L"el choque del Latino");
    apuntar("  [entreno] Anticaída retirada (0x50AC67 = 75 43)");
    return 1;
}

static int ne_anticaida(int on)
{
    if (!on) return ne_ac_restaurar();
    if (g_ne_q_ac) return 1;
    DWORD g = 0;
    if (!g_ht_base) { ne_poner_tx(NE_TX_VELOCIDAD, 1, L"La herramienta todavía no arrancó."); return 0; }
    ne_lee(ne_imagen() + NE_RVA_GESTOR, &g);
    if (!ne_carrera_ac(g)) {
        ne_poner_tx(NE_TX_VELOCIDAD, 1, L"Inicia una carrera de práctica (a solas) antes de activar Anticaída.");
        return 0;
    }
    if (!ne_iguales(ne_imagen() + NE_RVA_ANTICAIDA, NE_FIRMA_ANTICAIDA, 11)) {
        ne_poner_tx(NE_TX_VELOCIDAD, 1, L"La ruta Anticaída de este cliente no coincide con la validada.");
        return 0;
    }
    if (ne_escribir_codigo(NE_RVA_ANTICAIDA, NE_FIRMA_ANTICAIDA, NE_ANTICAIDA_NUEVO, 2, "entreno: Anticaída (0x50AC67)") <= 0) {
        ne_poner_tx(NE_TX_VELOCIDAD, 1, L"La ruta Anticaída está ocupada o cambió; no se tocó.");
        return 0;
    }
    g_ne_q_ac = 1; g_ne_ac_gestor = g;
    ne_poner_tx(NE_TX_ANTICAIDA, 0, L"Activa · choque Latino");
    apuntar("  [entreno] ★ Anticaída puesta (0x50AC67 = 90 90), gestor 0x%08X", g);
    return 1;
}
static int ne_anticaida_activa(void) { return g_ne_q_ac; }

/* ═══ 10 · LA API ══════════════════════════════════════════════════════════════════════════════════ */
static int ne_listo(void)
{
    NE_CAPTURA f;
    wchar_t guardado[320];
    lstrcpynW(guardado, g_ne_err, 320);
    int r = g_ht_base && ne_capturar(&f);
    lstrcpynW(g_ne_err, guardado, 320);
    return r;
}

static void ne_estado(wchar_t *s, int n)
{
    if (!s || n <= 0) return;
    lstrcpynW(s, g_ne_tx[NE_TX_VELOCIDAD][0] ? g_ne_tx[NE_TX_VELOCIDAD] : TR(L"Motor nativo · inicia una práctica offline."), n);
}

static int ne_texto(int que, wchar_t *s, int n)
{
    if (que < 0 || que >= NE_TX_N || !s || n <= 0) return 0;
    if (que == NE_TX_VELOCIDAD) { ne_estado(s, n); return g_ne_tx_error[que]; }
    static const wchar_t *const DEF[NE_TX_N] = { L"", L"Tramo desactivado.", L"Tramos desactivados.",
        L"Vuelve a un segundo ya tocado para ver dónde poner un tramo lento.", L"el choque del Latino" };
    lstrcpynW(s, g_ne_tx[que][0] ? g_ne_tx[que] : DEF[que], n);
    return g_ne_tx_error[que];
}

static int ne_preparado(void) { return g_ne_q_prep; }
static int ne_velocidad_activa(void) { return g_ne_q_vel || g_ne_vel_quiere; }
static int ne_velocidad(void) { return g_ne_pct_elegido; }
static int ne_velocidad_aplicada(void) { return g_ne_sesion ? g_ne_pct_actual : 100; }
static int ne_bucle_activo(void) { return g_ne_q_bucle || g_ne_bucle_quiere; }
static int ne_tramos_activos(void) { return g_ne_q_tramos; }
static int ne_tiempo_ms(void);

/* «Habilitar» (TogglePracticePreparation) */
static int ne_preparar(int on)
{
    if (on) {
        g_ne_q_prep = 1;
        if (!ne_asegurar_motor(g_ne_q_vel || g_ne_vel_quiere ? g_ne_pct_elegido : 100)) {
            g_ne_q_prep = 0;
            ne_parar_sesion();
            ne_poner_tx(NE_TX_VELOCIDAD, 1, g_ne_err);
            return 0;
        }
        ne_poner_tx(NE_TX_VELOCIDAD, 0, L"Motor habilitado; recuerda posiciones para los tramos.");
        return 1;
    }
    g_ne_q_prep = 0;
    if (!g_ne_q_vel && !g_ne_q_bucle && !g_ne_q_tramos) {
        if (ne_parar_sesion()) ne_poner_tx(NE_TX_VELOCIDAD, 0, L"Motor detenido; frecuencias originales restauradas.");
        else { ne_poner_tx(NE_TX_VELOCIDAD, 1, g_ne_err); return 0; }
    }
    return 1;
}

/* «Activar velocidad» (ToggleLivePractice) */
static int ne_velocidad_activar(int on)
{
    if (!on) {
        g_ne_q_vel = 0; g_ne_vel_quiere = 0; g_ne_vel_espera_salida = 0;
        if (g_ne_q_bucle || g_ne_q_prep || g_ne_q_tramos) {
            g_ne_pct_pedido = 100;
            ne_poner_tx(NE_TX_VELOCIDAD, 0, L"Entrenamiento preparado a velocidad normal.");
            return 1;
        }
        if (ne_parar_sesion()) ne_poner_tx(NE_TX_VELOCIDAD, 0, L"Velocidad detenida; frecuencias originales restauradas.");
        else { ne_poner_tx(NE_TX_VELOCIDAD, 1, g_ne_err); return 0; }
        return 1;
    }
    g_ne_vel_quiere = 1; g_ne_vel_espera_salida = 0;
    if (!g_ne_sesion && !ne_listo()) {                /* fuera de la práctica: armada */
        g_ne_q_vel = 0;
        wchar_t t[96];
        wsprintfW(t, TR(L"Velocidad armada al %d %%: se aplicará al entrar a entrenar."), g_ne_pct_elegido);
        ne_poner_tx(NE_TX_VELOCIDAD, 0, t);
        return 1;
    }
    if (!ne_asegurar_motor(g_ne_pct_elegido)) {
        wchar_t m[320]; lstrcpynW(m, g_ne_err, 320);
        g_ne_vel_quiere = 0;
        if (!g_ne_q_prep && !g_ne_q_bucle && !g_ne_q_tramos) ne_parar_sesion();
        g_ne_q_vel = 0;
        ne_poner_tx(NE_TX_VELOCIDAD, 1, m);
        return 0;
    }
    g_ne_q_vel = 1; g_ne_q_prep = 1;
    g_ne_pct_pedido = g_ne_pct_elegido;
    ne_poner_tx(NE_TX_VELOCIDAD, 0, L"Velocidad activa. Se restaurará al detenerla o cambiar de canción.");
    return 1;
}

static void ne_velocidad_poner(int pct)
{
    pct = (pct + 2) / 5 * 5;                /* al paso de 5, como el deslizador */
    if (pct < 50) pct = 50;
    if (pct > 150) pct = 150;
    g_ne_pct_elegido = pct;
    if (g_ne_q_vel) g_ne_pct_pedido = pct;
}

/* ── el bucle A/B (ToggleLiveLoop / ConfigureLoop) ── */
static void ne_bucle_tiempos(int desde_ms, int hasta_ms)
{
    g_ne_b_desde = desde_ms < 0 ? 0 : desde_ms;
    g_ne_b_hasta = hasta_ms > 0 ? hasta_ms : 0;
}
static void ne_bucle_opciones(int cuenta_atras_s, int sin_notas_s)
{
    g_ne_b_cuenta = cuenta_atras_s < 0 ? 0 : cuenta_atras_s > 30 ? 30 : cuenta_atras_s;
    g_ne_b_previo = sin_notas_s < 0 ? 0 : sin_notas_s > 30 ? 30 : sin_notas_s;
}
static void ne_bucle_leer(int *desde, int *hasta, int *cuenta_s, int *sin_notas_s)
{
    if (desde) *desde = g_ne_b_desde;
    if (hasta) *hasta = g_ne_b_hasta;
    if (cuenta_s) *cuenta_s = g_ne_b_cuenta;
    if (sin_notas_s) *sin_notas_s = g_ne_b_previo;
}

static int ne_bucle_configurar(int activo)
{
    if (!g_ne_sesion || g_ne_instalado != 3) return ne_falla(L"Primero inicia el motor nativo.");
    g_ne_b.activo = 0;
    if (!ne_esperar_bucle_quieto()) return ne_falla(L"El cliente no confirmó la salida de la cuenta atrás.");
    if (!activo) return 1;
    if (g_ne_b_cuenta < 0 || g_ne_b_cuenta > 30 || g_ne_b_previo < 0 || g_ne_b_previo > 30)
        return ne_falla(L"La cuenta atrás y el tramo sin notas deben estar entre 0 y 30 segundos.");
    if (g_ne_b_desde > NE_POS_MAX || g_ne_b_hasta > NE_POS_MAX) return ne_falla(L"Escribe el tramo en formato m:ss; por ejemplo, 0:30 o 2:15.");
    if (g_ne_b_hasta && g_ne_b_hasta <= g_ne_b_desde) return ne_falla(L"El final del tramo debe ser posterior al inicio.");
    if (!ne_enlazar_bucle()) return 0;
    g_ne_b.desde_ms = (DWORD)g_ne_b_desde; g_ne_b.hasta_ms = (DWORD)g_ne_b_hasta;
    g_ne_b.cuenta_ms = (DWORD)g_ne_b_cuenta * 1000; g_ne_b.previo_ms = (DWORD)g_ne_b_previo * 1000;
    g_ne_b.error = 0;
    MemoryBarrier();
    /* ⚠ `activo` ANTES de la orden: con la orden nueva y activo=0 el gancho la daría por vista sin aplicarla */
    g_ne_b.activo = 1;
    MemoryBarrier();
    DWORD orden = g_ne_b.orden + 1;
    g_ne_b.orden = orden;
    if (!ne_esperar(&g_ne_b.confirmada, &g_ne_b.orden, 0)) return ne_falla(L"El cliente no confirmó el tramo A/B.");
    if (g_ne_b.error) return ne_falla(L"%s", ne_error_bucle(g_ne_b.error));
    return 1;
}

static int ne_bucle_activar(int on)
{
    if (on) {
        g_ne_bucle_quiere = 1; g_ne_bucle_espera_salida = 0;
        if (!g_ne_sesion && !ne_listo()) {            /* fuera de la práctica: armado */
            g_ne_q_bucle = 0;
            ne_poner_tx(NE_TX_BUCLE, 0, L"Tramo armado: al entrar a entrenar corres hasta A y desde ahí sigue el bucle.");
            return 1;
        }
        int ok = ne_asegurar_motor(g_ne_q_vel || g_ne_vel_quiere ? g_ne_pct_elegido : 100);
        if (ok) {
            g_ne_q_prep = 1;
            ok = ne_bucle_configurar(1);
            /* ConfigurationFinished: un error de configuración ya mostrado no apaga el motor después */
            g_ne_err_reconocido = g_ne_b.estado == 6 ? g_ne_b.error : 0;
        }
        if (!ok) {
            wchar_t m[320]; lstrcpynW(m, g_ne_err, 320);
            ne_log_w("bucle: ", m);
            g_ne_q_bucle = 0;
            if (g_ne_b.estado == 6 && g_ne_b.error == 4) {    /* A ya pasó y no está grabado: a la próxima */
                g_ne_bucle_espera_salida = 1;
                ne_poner_tx(NE_TX_VELOCIDAD, 0, L"Entrenamiento preparado: desde ahora se graba cada segundo.");
                ne_poner_tx(NE_TX_BUCLE, 0, L"A ya pasó y no está grabado: sigues sin bucle hasta la meta. "
                                            L"En la próxima carrera (o con «Repetir» de la Pausa) corres hasta A y desde ahí sigue el bucle.");
                return 1;
            }
            g_ne_bucle_quiere = 0;
            ne_poner_tx(NE_TX_VELOCIDAD, 1, m);
            ne_poner_tx(NE_TX_BUCLE, 1, m);
            return 0;
        }
        g_ne_q_bucle = 1;
        ne_poner_tx(NE_TX_VELOCIDAD, 0, L"Repetición activa; la cuenta atrás se ejecuta en el juego.");
        return 1;
    }
    g_ne_q_bucle = 0; g_ne_bucle_quiere = 0; g_ne_bucle_espera_salida = 0;
    if (g_ne_sesion) { ne_bucle_configurar(0); g_ne_err_reconocido = g_ne_b.estado == 6 ? g_ne_b.error : 0; }
    if (!g_ne_q_vel && !g_ne_q_prep && !g_ne_q_tramos) ne_parar_sesion();
    ne_poner_tx(NE_TX_BUCLE, 0, L"Tramo desactivado.");
    return 1;
}

/* CapturePracticePosition */
static int ne_posicion_actual(double *ms)
{
    if (g_ne_sesion) {
        if (!ne_paso()) { ne_fallo_trabajador(g_ne_err); return 0; }
        *ms = g_ne_pos_ms;
        return 1;
    }
    NE_CAPTURA f;
    if (!ne_capturar(&f)) return 0;
    *ms = f.pos_ms;
    return 1;
}

static int ne_bucle_marcar(int a)
{
    double ms;
    if (!ne_posicion_actual(&ms)) { ne_poner_tx(NE_TX_VELOCIDAD, 1, g_ne_err); return 0; }
    int s = (int)(ms / 1000) * 1000;            /* m:ss: segundos enteros, como el cuadro de texto */
    if (a) g_ne_b_desde = s; else g_ne_b_hasta = s;
    if (g_ne_q_bucle) return ne_bucle_activar(1);
    wchar_t p[16], t[64];
    ne_texto_de_posicion(s, p);
    wsprintfW(t, TR(L"%s marcado en %s."), a ? TR(L"Inicio") : TR(L"Final"), p);
    ne_poner_tx(NE_TX_BUCLE, 0, t);
    return 1;
}
static int ne_bucle_marcar_a(void) { return ne_bucle_marcar(1); }
static int ne_bucle_marcar_b(void) { return ne_bucle_marcar(0); }

static int ne_bucle_reiniciar(void)
{
    if (!g_ne_sesion || !g_ne_q_bucle) { ne_poner_tx(NE_TX_VELOCIDAD, 1, L"Activa primero un tramo capturado."); return 0; }
    if (!g_ne_b.activo || g_ne_b.estado == 1) { ne_poner_tx(NE_TX_VELOCIDAD, 1, L"Todavía no se capturó el inicio del tramo."); return 0; }
    g_ne_b.reinicio_orden++;
    return 1;
}

static int ne_bucle_estado(int *estado, int *vueltas, int *restante_ms, int *pos_ms)
{
    int on = g_ne_sesion && g_ne_b.activo;
    if (estado) *estado = g_ne_sesion ? (int)g_ne_b.estado : 0;
    if (vueltas) *vueltas = (int)g_ne_b.vueltas;
    if (restante_ms) *restante_ms = (int)g_ne_b.restante_ms;
    if (pos_ms) *pos_ms = (int)g_ne_b.posicion_ms;
    return on;
}
static int ne_bucle_puede_reiniciar(void)
{
    DWORD e = g_ne_b.estado;
    return g_ne_q_bucle && g_ne_sesion && g_ne_b.activo && (e == 2 || e == 3 || e == 4);
}

/* ── los tramos de velocidad ── */
static void ne_describir_tramos(const NE_TRAMOS *z, wchar_t *t)
{
    wsprintfW(t, TR(L"%d tramo%s activo%s"), z->n, z->n == 1 ? L"" : L"s", z->n == 1 ? L"" : L"s");
    if (z->incompletos > 0)
        wsprintfW(t + lstrlenW(t), TR(L"; %d sin terminar (se ignora%s)."), z->incompletos, z->incompletos == 1 ? L"" : L"n");
    else lstrcatW(t, L".");
}

static void ne_tramos_filas(int *desde, int *hasta, int *pct)
{
    for (int i = 0; i < NE_TOPE_TRAMOS; i++) {
        if (desde) desde[i] = g_ne_z_desde[i];
        if (hasta) hasta[i] = g_ne_z_hasta[i];
        if (pct) pct[i] = g_ne_z_pct[i];
    }
}

/* OnZoneRowsEdited: con los tramos activos, si las filas nuevas no compilan se mantienen las anteriores */
static int ne_tramos_editados(void)
{
    if (!g_ne_q_tramos) return 1;
    NE_TRAMOS z;
    wchar_t t[400];
    if (!ne_tramos_compilar(g_ne_z_desde, g_ne_z_hasta, g_ne_z_pct, NE_TOPE_TRAMOS, &z)) {
        g_ne_err[300] = 0;
        wsprintfW(t, TR(L"%s Se mantienen los tramos anteriores."), g_ne_err);
        ne_poner_tx(NE_TX_TRAMOS, 1, t);
        return 0;
    }
    g_ne_tramos = z;
    ne_describir_tramos(&z, t);
    ne_poner_tx(NE_TX_TRAMOS, 0, t);
    return 1;
}

static int ne_tramos(int on, const int *desde_ms, const int *hasta_ms, const int *pct, int n)
{
    if (desde_ms && hasta_ms && pct) {
        if (n > NE_TOPE_TRAMOS) { ne_falla(L"Como máximo %d tramos de velocidad.", NE_TOPE_TRAMOS); ne_poner_tx(NE_TX_TRAMOS, 1, g_ne_err); return 0; }
        for (int i = 0; i < NE_TOPE_TRAMOS; i++) {
            g_ne_z_desde[i] = i < n && desde_ms[i] >= 0 ? desde_ms[i] : -1;
            g_ne_z_hasta[i] = i < n && hasta_ms[i] >= 0 ? hasta_ms[i] : -1;
            g_ne_z_pct[i] = i < n ? pct[i] : 100;
        }
    }
    if (on && g_ne_q_tramos) return ne_tramos_editados();
    if (on) {
        NE_TRAMOS z;
        int ok = ne_tramos_compilar(g_ne_z_desde, g_ne_z_hasta, g_ne_z_pct, NE_TOPE_TRAMOS, &z);
        if (ok && z.n == 0) ok = ne_falla(L"Escribe al menos un tramo completo (Desde y Hasta).");
        if (ok) ok = ne_asegurar_motor(g_ne_q_vel || g_ne_vel_quiere ? g_ne_pct_elegido : 100);
        if (!ok) {
            g_ne_q_tramos = 0;
            ne_log_w("tramos: ", g_ne_err);
            ne_poner_tx(NE_TX_TRAMOS, 1, g_ne_err);
            return 0;
        }
        g_ne_q_prep = 1;
        g_ne_tramos = z; g_ne_q_tramos = 1;
        wchar_t t[160];
        ne_describir_tramos(&z, t);
        ne_poner_tx(NE_TX_TRAMOS, 0, t);
        return 1;
    }
    g_ne_q_tramos = 0;
    if (!g_ne_q_vel && !g_ne_q_prep && !g_ne_q_bucle) ne_parar_sesion();
    ne_poner_tx(NE_TX_TRAMOS, 0, L"Tramos desactivados.");
    return 1;
}

/* AddZonePoint: A, B, C… de izquierda a derecha; cada tramo nuevo empieza donde acaba el anterior */
static int ne_tramos_agregar_punto(int ms, wchar_t *msg)
{
    wchar_t p[16], q[16];
    ne_texto_de_posicion(ms, p);
    int punto = ne_posicion_de_texto(p);
    int ult = -1;
    for (int i = 0; i < NE_TOPE_TRAMOS; i++) if (g_ne_z_desde[i] >= 0) ult = i;
    int previo = ult < 0 ? -1 : g_ne_z_hasta[ult] < 0 ? g_ne_z_desde[ult] : g_ne_z_hasta[ult];
    if (ult >= 0 && previo >= 0 && punto <= previo) {
        ne_texto_de_posicion(previo, q);
        return ne_falla(L"Marca los puntos en orden: el siguiente debe ir después de %s.", q);
    }
    if (ult >= 0 && g_ne_z_hasta[ult] < 0) {
        g_ne_z_hasta[ult] = punto;
        wsprintfW(msg, TR(L"Tramo %d: final en %s."), ult + 1, p);
    } else if (ult + 1 < NE_TOPE_TRAMOS) {
        int fila = ult + 1;
        if (ult >= 0) {
            g_ne_z_desde[fila] = g_ne_z_hasta[ult]; g_ne_z_hasta[fila] = punto;
            ne_texto_de_posicion(g_ne_z_desde[fila], q);
            wsprintfW(msg, TR(L"Tramo %d: %s → %s."), fila + 1, q, p);
        } else {
            g_ne_z_desde[fila] = punto;
            wsprintfW(msg, TR(L"Tramo 1: inicio en %s. Marca otra vez en el final."), p);
        }
    } else return ne_falla(L"Ya no caben más tramos (máximo %d).", NE_TOPE_TRAMOS);
    return 1;
}

static int ne_marcar_punto(void)
{
    double ms;
    wchar_t msg[160];
    if (!ne_posicion_actual(&ms) || !ne_tramos_agregar_punto((int)ms, msg)) {
        ne_log_w("tramos: ", g_ne_err);
        ne_poner_tx(NE_TX_TRAMOS, 1, g_ne_err);
        return 0;
    }
    if (g_ne_q_tramos) ne_tramos_editados();
    else ne_poner_tx(NE_TX_TRAMOS, 0, msg);
    return 1;
}

/* ── moverse en la canción (SeekSong / Seek) ── */
static int ne_mover(int delta_s)
{
    int delta = delta_s * 1000;
    if (!g_ne_sesion) {
        if (!ne_asegurar_motor(g_ne_q_vel || g_ne_vel_quiere ? g_ne_pct_elegido : 100)) {
            ne_poner_tx(NE_TX_MOVER, 1, g_ne_err);
            return 0;
        }
        g_ne_q_prep = 1;
        ne_poner_tx(NE_TX_MOVER, 0, L"Motor preparado: desde ahora se graba cada segundo y podrás volver a él.");
        return 1;
    }
    int ok = 1;
    if (delta == 0 || delta > 600000 || delta < -600000) ok = ne_falla(L"Salto fuera de rango.");
    if (ok && g_ne_instalado != 3) ok = ne_falla(L"Primero activa la velocidad o los tramos: el salto usa el motor nativo.");
    if (ok) ok = ne_enlazar_bucle();
    if (ok) {
        g_ne_b.salto_ms = delta;
        MemoryBarrier();
        g_ne_b.salto_orden++;
        if (!ne_esperar(&g_ne_b.salto_confirmado, &g_ne_b.salto_orden, 0)) ok = ne_falla(L"El juego no confirmó el salto.");
        else if (g_ne_b.salto_resultado != NE_SALTO_HECHO) ok = ne_falla(L"%s", ne_error_salto(g_ne_b.salto_resultado, delta));
    }
    if (!ok) { ne_poner_tx(NE_TX_MOVER, 1, g_ne_err); return 0; }
    DWORD ahora = ne_ahora();
    ne_ra_recalibrar(&g_ne_ra, ahora + 300); g_ne_silencio_hasta = ahora + 300;
    wchar_t t[64];
    wsprintfW(t, L"%s %d s.", delta < 0 ? TR(L"Atrás") : TR(L"Adelante"), (delta < 0 ? -delta : delta) / 1000);
    ne_poner_tx(NE_TX_MOVER, 0, t);
    return 1;
}

static int ne_tiempo_ms(void)
{
    if (g_ne_sesion) return g_ne_pos_ms >= 0 ? (int)g_ne_pos_ms : -1;
    NE_CAPTURA f;
    wchar_t guardado[320];
    lstrcpynW(guardado, g_ne_err, 320);
    int r = g_ht_base && ne_capturar(&f) ? (int)f.pos_ms : -1;
    lstrcpynW(g_ne_err, guardado, 320);
    return r;
}
static int ne_largo_ms(void) { return g_ne_sesion && g_ne_largo_ms > 0 ? (int)g_ne_largo_ms : -1; }

/* ── los carteles vivos (UpdateLiveLoopStatus / UpdateSpeedZonesStatus) ── */
static void ne_carteles(void)
{
    wchar_t t[200], p[16];
    if (g_ne_q_bucle && g_ne_sesion) {
        DWORD e = g_ne_b.estado, v = g_ne_b.vueltas;
        ne_texto_de_posicion((int)g_ne_b.posicion_ms, p);
        switch (e) {
        case 1: lstrcpyW(t, TR(L"Esperando capturar el inicio del tramo…")); break;
        case 3: { DWORD d = (g_ne_b.restante_ms + 50) / 100;
                  wsprintfW(t, TR(L"Cuenta atrás: %u.%u s · vueltas %u"), (unsigned)(d / 10), (unsigned)(d % 10), (unsigned)v); break; }
        case 4: wsprintfW(t, TR(L"Antes del tramo, sin notas · %s · vueltas %u"), p, (unsigned)v); break;
        case 6: lstrcpynW(t, ne_error_bucle(g_ne_b.error), 200); break;
        default: wsprintfW(t, TR(L"Tramo en el juego · %s · vueltas %u"), p, (unsigned)v); break;
        }
        ne_poner_tx(NE_TX_BUCLE, 0, t);
    }
    if (g_ne_q_tramos && g_ne_sesion && g_ne_pos_ms >= 0) {
        const NE_TRAMO *z = ne_tramo_en(&g_ne_tramos, g_ne_pos_ms);
        ne_texto_de_posicion((int)g_ne_pos_ms, p);
        if (z) wsprintfW(t, TR(L"En el tramo %d · %d %% · %s"), z->numero, z->pct, p);
        else wsprintfW(t, TR(L"Fuera de los tramos · %d %% · %s"), g_ne_pct_pedido, p);
        ne_poner_tx(NE_TX_TRAMOS, 0, t);
    }
}

/* cada 50 ms desde la ventana: el trabajador de Ñ2Hock (velocidad objetivo + Step) y los carteles */
static void ne_tick(void)
{
    if (!g_ht_base) return;
    if (g_ne_sesion) {
        int obj = ne_objetivo();
        int ok = 1;
        if (g_ne_pct_actual != obj) ok = ne_poner_pct(obj);
        if (ok) ok = ne_paso();
        if (!ok) ne_fallo_trabajador(g_ne_err);
    } else if (g_ne_restaurar_pendiente && GetTickCount() - g_ne_ult_reintento > 1000) {
        g_ne_ult_reintento = GetTickCount();
        if (ne_parar_sesion()) ne_poner_tx(NE_TX_VELOCIDAD, 0, L"Restauración completada; frecuencias originales.");
    }
    {
        static LONG vistas = 0;
        LONG p = g_ne_pausas;
        if (p != vistas) { vistas = p; apuntar("  [entreno] ★ pausa del juego: el motor sigue a la misma velocidad (%ld)", p); }
    }
    if (g_ne_q_ac && !ne_carrera_ac(g_ne_ac_gestor)) ne_ac_restaurar();
    /* ★ la velocidad armada: al haber canción de práctica, se aplica sola (una prueba por segundo) */
    if (g_ne_vel_quiere && !g_ne_q_vel && !g_ne_restaurar_pendiente && GetTickCount() - g_ne_vel_reintento > 1000) {
        g_ne_vel_reintento = GetTickCount();
        int hay = g_ne_sesion || ne_listo();
        if (!hay) g_ne_vel_espera_salida = 0;
        else if (!g_ne_vel_espera_salida) {
            wchar_t guardado[320];
            lstrcpynW(guardado, g_ne_err, 320);
            if (ne_asegurar_motor(g_ne_pct_elegido)) {
                g_ne_q_vel = 1; g_ne_q_prep = 1;
                g_ne_pct_pedido = g_ne_pct_elegido;
                wchar_t t[96];
                wsprintfW(t, TR(L"Velocidad aplicada al entrar a entrenar (%d %%)."), g_ne_pct_elegido);
                ne_poner_tx(NE_TX_VELOCIDAD, 0, t);
                apuntar("  [entreno] ★ velocidad armada aplicada al %d %%", g_ne_pct_elegido);
            } else {
                g_ne_vel_espera_salida = 1;             /* no en esta carrera: se avisa una vez y se espera a la próxima */
                wchar_t t[400];
                g_ne_err[300] = 0;
                wsprintfW(t, TR(L"La velocidad armada no se pudo aplicar: %s"), g_ne_err);
                ne_poner_tx(NE_TX_VELOCIDAD, 1, t);
                ne_log_w("", t);
            }
            lstrcpynW(g_ne_err, guardado, 320);
        }
    }
    /* ★ el tramo armado: igual, una prueba por segundo (después de la velocidad, así arranca a la elegida) */
    {
        static DWORD reintento = 0;
        if (g_ne_bucle_quiere && !g_ne_q_bucle && !g_ne_restaurar_pendiente && GetTickCount() - reintento > 1000) {
            reintento = GetTickCount();
            int hay = g_ne_sesion || ne_listo();
            if (!hay) g_ne_bucle_espera_salida = 0;
            else if (!g_ne_bucle_espera_salida) {
                if (ne_bucle_activar(1) && g_ne_q_bucle) apuntar("  [entreno] ★ tramo armado aplicado al entrar a entrenar");
            }
        }
    }
    ne_carteles();
}

/* apaga y restaura TODO (al cerrar la herramienta o a pedido). 1 = todo quedó como de fábrica. */
static int ne_apagar_todo(void)
{
    if (!g_ht_base) return 1;
    g_ne_q_vel = g_ne_q_prep = g_ne_q_bucle = g_ne_q_tramos = 0;
    g_ne_vel_quiere = 0; g_ne_vel_espera_salida = 0;
    g_ne_bucle_quiere = 0; g_ne_bucle_espera_salida = 0;
    g_ne_pct_pedido = g_ne_pct_elegido;
    int ok = 1;
    if (g_ne_m.hilo && g_ne_m.hilo == GetCurrentThreadId() && g_ne_m.imagen) {
        /* desde el hilo del juego mismo: se restaura acá (no hay a quién esperar) */
        g_ne_m.deseado = 0;
        ne_restaurar(&g_ne_m, g_ne_m.estado);
    }
    if (g_ne_sesion || g_ne_instalado) ok &= ne_parar_sesion();
    if (g_ne_q_ac) ok &= ne_ac_restaurar();
    if (ok) ne_poner_tx(NE_TX_VELOCIDAD, 0, L"Todo restaurado.");
    else ne_poner_tx(NE_TX_VELOCIDAD, 1, g_ne_err);
    return ok;
}

#undef NE_U
#undef NE_B
#undef NE_W
#undef NE_F
