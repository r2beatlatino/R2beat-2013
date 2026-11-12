/* estrellas.c — las canciones de MÁS DE 10★ (Level 21..26): la 2.ª fila de estrellas, «x 10.5 … x 13» en el picker y
 *               el sorteo de ítems como el de 10★ (05-nov-2026, (157))
 *
 *   anonimo03 (05-nov), al re-ubicar las canciones por estrellas ((156), taller/importador2013/reubicar_niveles.py): «lo del
 *   tope, tenemos que fabricar nuestras estrellas con la dll debajo de las que existen» · «1 sí, 2 sorteo de ítems no
 *   cambie, 3 profecías en 10». La investigación: _trabajo/estrellas_extra/INVESTIGACION.md. Doc: ESTRELLAS_EXTRA.md.
 *
 *   1 · LA 2.ª FILA. Las estrellas de la canción las dibuja UNA función, 0x413980 (thiscall sobre cMsgBox [0x9314B4],
 *       ret 0x18: x, y, nivel, paso, alfa, chica), desde 4 lugares: la sala (anfitrión 0x58F4F3 e invitado 0x58F643,
 *       que picker.c desvía pero llama a 0x413980 por su dirección), el resultado (0x538507) y el resultado boost
 *       (0x4148F8). Dibuja nivel/2 llenas + media + vacías hasta 10, SIN tope: con 26 salían 13 en una fila que se iba
 *       del cuadro. ⇒ trampolín en su ENTRADA (83 EC 08 53 55, el borde): con más de 20 se llama a la original con 20
 *       (la fila de fábrica llena) y debajo se dibujan las que sobran con el MISMO sprite ([this+0x244] = popup/003.spr)
 *       y la misma pieza del exe (0x684090, thiscall(spr, x, y, corte, color) ret 0x10), misma x y mismo paso, sin
 *       vacías. Cortes: chica 0x11 llena / 0x12 media; grande 0x0A / 0x0B (más de 17 es banda 7 = amarillas).
 *   2 · «x 10.5 … x 13» EN EL PANEL DEL PICKER. 0x5BD02A lee el Level y hace L+0x25 con tope 0x39 (= «x 10», el corte
 *       57 de music_select_host03). Se cambian los 13 bytes de 0x5BD031 (add · cmp · jl · mov) por un call a una cueva:
 *       ≤ 20 → L+0x25 (igual que hoy) · 21..26 → 61+(L−21), los cortes que agrega rnr_ui_lt_dificultad13.pak
 *       (herramientas/estrellas_extra_crear.py). ⛔ SÓLO si ese pak está en la carpeta del juego: sin él, el corte 61 no
 *       existe y el panel pediría un recorte que no hay.
 *   3 · EL SORTEO DE ÍTEMS NO CAMBIA. El sorteador (0x4F4EF1, mov al,[eax+0x574]) usa la fila (L−1)/2+0x12 de la tabla
 *       de pesos SIN tope: con 21..26 caía en filas de otro bloque. Se cambia por un call a una cueva que lee el Level y
 *       lo topa en 20 (= sortea como una de 10★, como hasta hoy). El test al,al que sigue rehace las banderas.
 *       ⚠ Cambia lo que sortea cada cliente ⇒ todos con la misma dll (como items.c).
 *   Perillas: [estrellas] activo=1 · fila=1 · picker=1 · sorteo=1 · dy_chica=15 · dy_grande=20 · sube_sala=10 · log=0
 */
#define ESV(x) (g_es_base + ((DWORD)(x) - 0x400000))
#define ES_TOPE 20                         /* Level de la fila de fábrica llena (10★) */
#define ES_MAX 26                          /* hasta dónde hay cortes «x 13» en el picker */
#define ES_PICKER_CORTE0 61                /* el corte de «x 10.5» (rnr_ui_lt_dificultad13.pak) */
#define ES_PAK "rnr_ui_lt_dificultad13.pak"   /* ⛔ NO «rnr_ui_lt_estrellas.pak»: ése es el de la Lluvia de Estrellas */

typedef void (__fastcall *F_ES_FILA)(void *self, void *edx, int x, int y, int nivel, int paso, int alfa, int chica);
typedef void (__fastcall *F_ES_PIEZA)(void *spr, void *edx, int x, int y, int corte, DWORD color);

static BYTE *g_es_base = NULL;
static F_ES_FILA g_es_real = NULL;         /* el trampolín de 0x413980 */
static int g_es_dy_chica = 15, g_es_dy_grande = 20, g_es_sube_sala = 10, g_es_log = 0, g_es_vistas = 0;
#define ES_ALFA_SALA 0xB4                  /* la sala dibuja las estrellas a 0xB4 (el resultado, a 0xFF) */

static void __fastcall es_estrellas(void *self, void *edx, int x, int y, int nivel, int paso, int alfa, int chica)
{
    (void)edx;
    if (nivel <= ES_TOPE || nivel > 60 || !self) {
        g_es_real(self, NULL, x, y, nivel, paso, alfa, chica);
        return;
    }
    /* ★ 05-nov, anonimo03 (la vio en la sala con DDK Train): «hay que subir un poco las estrellas». La fila de fábrica va
     *   sobre el pie de la portada (y 0x10B) y la 2.ª caía afuera, sobre el borde del cuadro y pegada a «Pista». Medido
     *   en su captura: la portada termina en y 232, la 1.ª fila estaba centrada en 219 y la 2.ª en 235 ⇒ en la SALA
     *   (alfa 0xB4), con 2 filas, las dos suben `sube_sala` (10) y se juntan 1 px (dy 15): centros 209 y 224, la 2.ª
     *   entera adentro de la portada. Las de 10★ o menos quedan donde las pone el juego. */
    if ((BYTE)alfa == ES_ALFA_SALA) y -= g_es_sube_sala;
    g_es_real(self, NULL, x, y, ES_TOPE, paso, alfa, chica);           /* la fila de fábrica, llena */
    void *spr = *(void **)((BYTE *)self + 0x244);
    if (!spr) return;
    int extra = nivel - ES_TOPE, llenas = extra / 2, media = extra & 1;
    int corte = chica ? 0x11 : 0x0A;
    DWORD color = ((DWORD)(BYTE)alfa << 24) | 0xFFFFFF;
    int yy = y + (chica ? g_es_dy_chica : g_es_dy_grande), xx = x;
    F_ES_PIEZA pieza = (F_ES_PIEZA)ESV(0x684090);
    for (int i = 0; i < llenas; i++, xx += paso)
        pieza(spr, NULL, xx, yy, corte, color);
    if (media)
        pieza(spr, NULL, xx, yy, corte + 1, color);
    if (g_es_log && g_es_vistas < 40) {
        g_es_vistas++;
        apuntar("  [estrellas] nivel %d desde %p: fila de fábrica llena en (%d,%d) + %d%s abajo en y %d (paso %d, %s)",
                nivel, __builtin_return_address(0), x, y, llenas, media ? " y media" : "", yy, paso,
                chica ? "chicas" : "grandes");
    }
}

static int es_pisar(DWORD va, const void *nuevo, int n)
{
    DWORD viejo = 0;
    if (!VirtualProtect(ESV(va), n, PAGE_EXECUTE_READWRITE, &viejo)) return 0;
    CopyMemory(ESV(va), nuevo, n);
    VirtualProtect(ESV(va), n, viejo, &viejo);
    FlushInstructionCache(GetCurrentProcess(), ESV(va), n);
    return 1;
}

/* un call de 5 bytes a `cueva` en `va`, y nop hasta completar `n` */
static int es_llamar(DWORD va, BYTE *cueva, int n)
{
    BYTE b[16];
    if (n > 16) return 0;
    b[0] = 0xE8;
    *(int *)(b + 1) = (int)((DWORD)cueva - ((DWORD)ESV(va) + 5));
    for (int i = 5; i < n; i++) b[i] = 0x90;
    return es_pisar(va, b, n);
}

static BYTE *es_cueva(const BYTE *c, int n)
{
    BYTE *p = (BYTE *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (p) CopyMemory(p, c, n);
    return p;
}

static void es_fila_poner(void)
{
    /* ⚠ las guardas ANTES de escribir: la entrada que se copia, el «10» de la fila, el sprite en +0x244, la pieza
     *   0x684090 y los dos ret 0x18 (6 argumentos: si cambian, la pila quedaría corrida) */
    static const BYTE e_entrada[12] = { 0x83, 0xEC, 0x08, 0x53, 0x55, 0x56, 0x8B, 0x74, 0x24, 0x20, 0x57, 0x8B };
    static const BYTE e_diez[5] = { 0xB9, 0x0A, 0x00, 0x00, 0x00 };
    static const BYTE e_spr[6] = { 0x8B, 0x8B, 0x44, 0x02, 0x00, 0x00 };
    static const BYTE e_ret[3] = { 0xC2, 0x18, 0x00 };
    BYTE *call = ESV(0x413A43);
    if (memcmp(ESV(0x413980), e_entrada, 12) || memcmp(ESV(0x413A04), e_diez, 5) || memcmp(ESV(0x413A3A), e_spr, 6)
        || call[0] != 0xE8 || (DWORD)(call + 5 + *(int *)(call + 1)) != (DWORD)ESV(0x684090)
        || memcmp(ESV(0x413AD4), e_ret, 3) || memcmp(ESV(0x413B16), e_ret, 3)) {
        apuntar("  [estrellas] ⛔ 0x413980 (la fila de estrellas) no es la de fábrica: sin 2.ª fila");
        return;
    }
    BYTE *t = (BYTE *)VirtualAlloc(NULL, 32, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!t) return;
    CopyMemory(t, e_entrada, 5);                                    /* sub esp,8 · push ebx · push ebp */
    t[5] = 0xE9;
    *(int *)(t + 6) = (int)((DWORD)ESV(0x413985) - (DWORD)(t + 10));
    g_es_real = (F_ES_FILA)t;
    BYTE s[5] = { 0xE9, 0, 0, 0, 0 };
    *(int *)(s + 1) = (int)((DWORD)es_estrellas - ((DWORD)ESV(0x413980) + 5));
    if (es_pisar(0x413980, s, 5))
        apuntar("  [estrellas] ok: más de 10★ = la fila de fábrica llena + una 2.ª fila debajo (sala, resultado, boost)");
}

static void es_picker_poner(const char *ini)
{
    (void)ini;
    char pak[MAX_PATH];
    lstrcpyA(pak, g_carpeta);
    lstrcatA(pak, ES_PAK);
    if (GetFileAttributesA(pak) == INVALID_FILE_ATTRIBUTES) {
        apuntar("  [estrellas] sin %s: el panel del picker sigue en «x 10» para más de 10★", ES_PAK);
        return;
    }
    /* 0x5BD02A movzx eax,[edi+0x574] · 0x5BD031 add eax,0x25 · cmp eax,0x39 · jl +5 · mov eax,0x39 · 0x5BD03E push eax */
    static const BYTE e_lee[7] = { 0x0F, 0xB6, 0x87, 0x74, 0x05, 0x00, 0x00 };
    static const BYTE e_tope[14] = { 0x83, 0xC0, 0x25, 0x83, 0xF8, 0x39, 0x7C, 0x05, 0xB8, 0x39, 0x00, 0x00, 0x00, 0x50 };
    if (memcmp(ESV(0x5BD02A), e_lee, 7) || memcmp(ESV(0x5BD031), e_tope, 14)) {
        apuntar("  [estrellas] ⛔ el tope del panel del picker (0x5BD031) no es el de fábrica: sigue en «x 10»");
        return;
    }
    /* cmp eax,20 · ja +4 · add eax,0x25 · ret · cmp eax,26 · jbe +5 · mov eax,26 · add eax,40 · ret */
    static const BYTE c[] = { 0x83, 0xF8, ES_TOPE, 0x77, 0x04, 0x83, 0xC0, 0x25, 0xC3,
                              0x83, 0xF8, ES_MAX, 0x76, 0x05, 0xB8, ES_MAX, 0x00, 0x00, 0x00,
                              0x83, 0xC0, ES_PICKER_CORTE0 - (ES_TOPE + 1), 0xC3 };
    BYTE *cueva = es_cueva(c, sizeof(c));
    if (cueva && es_llamar(0x5BD031, cueva, 13))
        apuntar("  [estrellas] ok: panel del picker — 10.5★ … 13★ con sus imágenes (cortes %d..%d de %s)",
                ES_PICKER_CORTE0, ES_PICKER_CORTE0 + ES_MAX - ES_TOPE - 1, ES_PAK);
}

static void es_sorteo_poner(void)
{
    /* 0x4F4EF1 mov al,[eax+0x574] · test al,al */
    static const BYTE e[8] = { 0x8A, 0x80, 0x74, 0x05, 0x00, 0x00, 0x84, 0xC0 };
    if (memcmp(ESV(0x4F4EF1), e, 8)) {
        apuntar("  [estrellas] ⛔ el sorteador (0x4F4EF1) no lee el Level como el de fábrica: no se topa");
        return;
    }
    /* mov al,[eax+0x574] · cmp al,20 · jbe +2 · mov al,20 · ret */
    static const BYTE c[] = { 0x8A, 0x80, 0x74, 0x05, 0x00, 0x00, 0x3C, ES_TOPE, 0x76, 0x02, 0xB0, ES_TOPE, 0xC3 };
    BYTE *cueva = es_cueva(c, sizeof(c));
    if (cueva && es_llamar(0x4F4EF1, cueva, 6))
        apuntar("  [estrellas] ok: el sorteo de ítems ve como máximo 10★ (una de 13★ sortea como una de 10★, como hoy)");
}

static void estrellas_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("estrellas", "activo", 1, ini)) {
        apuntar("  [estrellas] apagado ([estrellas] activo=0): más de 10★ se ve como el exe de fábrica");
        return;
    }
    g_es_base = (BYTE *)GetModuleHandleA(NULL);
    g_es_dy_chica = GetPrivateProfileIntA("estrellas", "dy_chica", 15, ini);
    g_es_sube_sala = GetPrivateProfileIntA("estrellas", "sube_sala", 10, ini);
    g_es_dy_grande = GetPrivateProfileIntA("estrellas", "dy_grande", 20, ini);
    g_es_log = GetPrivateProfileIntA("estrellas", "log", 0, ini);
    if (GetPrivateProfileIntA("estrellas", "fila", 1, ini)) es_fila_poner();
    if (GetPrivateProfileIntA("estrellas", "picker", 1, ini)) es_picker_poner(ini);
    if (GetPrivateProfileIntA("estrellas", "sorteo", 1, ini)) es_sorteo_poner();
}
