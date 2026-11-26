/* personalizacion_prueba.c — pruebas sin juego de lo de Personalización (25-nov-2026)
 *   · piedras.c: el lector de TGA (24/32 bits, sin comprimir y RLE, de arriba abajo y de abajo arriba), la validación
 *     y el muestreo bilineal.
 *   · la curva de AutoFar (ht_af_parsear / ht_af_curva, copiadas de herramienta.c con sus mismas reglas).
 *   Uso: personalizacion_prueba.exe [una_piedra.tga]   → «todo bien» y código 0, o los fallos y código 1.
 */
#include <windows.h>
#include <stdio.h>

/* lo mínimo que piedras.c espera de la dll */
static BYTE *g_ht_base = NULL;
static char g_carpeta[MAX_PATH] = ".\\", g_ht_ini[MAX_PATH] = ".\\no_existe.ini";
static int ht_memoria_ok(const void *p, int n, int w) { (void)p; (void)n; (void)w; return 1; }
static void apuntar(const char *f, ...) { (void)f; }
#include "../fuente/piedras.c"
#include "../fuente/booster.c"

static int g_fallos = 0;
#define OK(c, m) do { if (c) printf("  ok   %s\n", m); else { printf("  MAL  %s\n", m); g_fallos++; } } while (0)

static BYTE *tga(int tipo, int bpp, int arriba, int W, int H, const DWORD *px, DWORD *n)
{
    BYTE *b = (BYTE *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, 18 + W * H * 5 + 64);
    b[2] = (BYTE)tipo; b[12] = (BYTE)W; b[13] = (BYTE)(W >> 8); b[14] = (BYTE)H; b[15] = (BYTE)(H >> 8);
    b[16] = (BYTE)bpp; b[17] = (BYTE)(arriba ? 0x20 : 0) | (bpp == 32 ? 8 : 0);
    DWORD p = 18;
    int by = bpp / 8;
    for (int yy = 0; yy < H; yy++) {
        int y = arriba ? yy : H - 1 - yy;
        if (tipo == 10) {                                  /* una fila: 1 paquete repetido + el resto crudo */
            b[p++] = 0x80 | 1;                             /* 2 iguales */
            DWORD c = px[y * W];
            b[p++] = (BYTE)c; b[p++] = (BYTE)(c >> 8); b[p++] = (BYTE)(c >> 16); if (by == 4) b[p++] = (BYTE)(c >> 24);
            b[p++] = (BYTE)(W - 3);                        /* W-2 crudos */
            for (int x = 2; x < W; x++) { c = px[y * W + x]; b[p++] = (BYTE)c; b[p++] = (BYTE)(c >> 8); b[p++] = (BYTE)(c >> 16); if (by == 4) b[p++] = (BYTE)(c >> 24); }
        } else
            for (int x = 0; x < W; x++) { DWORD c = px[y * W + x]; b[p++] = (BYTE)c; b[p++] = (BYTE)(c >> 8); b[p++] = (BYTE)(c >> 16); if (by == 4) b[p++] = (BYTE)(c >> 24); }
    }
    *n = p;
    return b;
}

/* — la curva de AutoFar: la MISMA lógica que herramienta.c — */
#define HT_AF_MAX 16
static int ht_af_parsear(const wchar_t *t, float *pb, float *pf, int *n, wchar_t *err)
{
    float nums[HT_AF_MAX * 2 + 2];
    int k = 0;
    const wchar_t *p = t;
    while (*p) {
        while (*p && !((*p >= L'0' && *p <= L'9') || *p == L'.' || *p == L',')) p++;
        if (!*p) break;
        float v = 0, d = 0;
        int hay = 0;
        for (; *p; p++) {
            if (*p >= L'0' && *p <= L'9') { hay = 1; if (d) { v += (*p - L'0') * d; d /= 10; } else v = v * 10 + (*p - L'0'); }
            else if ((*p == L'.' || *p == L',') && !d && p[1] >= L'0' && p[1] <= L'9') d = 0.1f;
            else break;
        }
        if (!hay) { if (*p) p++; continue; }
        if (k >= HT_AF_MAX * 2) { wsprintfW(err, L"max"); return 1; }
        nums[k++] = v;
    }
    if (k < 2 || (k & 1)) { lstrcpyW(err, L"pares"); return 1; }
    int m = k / 2;
    for (int i = 0; i < m; i++) {
        pb[i] = nums[2 * i]; pf[i] = nums[2 * i + 1];
        if (pb[i] < 30 || pb[i] > 400) return 1;
        if (pf[i] < 1.0f || pf[i] > 22.0f) return 1;
    }
    for (int i = 1; i < m; i++)
        for (int j = i; j > 0 && pb[j - 1] > pb[j]; j--) { float tb = pb[j], tf = pf[j]; pb[j] = pb[j - 1]; pf[j] = pf[j - 1]; pb[j - 1] = tb; pf[j - 1] = tf; }
    for (int i = 1; i < m; i++) if (pb[i] == pb[i - 1]) return 1;
    *n = m;
    return 0;
}

int main(int argc, char **argv)
{
    /* una hoja de prueba 8×8 con alfa */
    DWORD px[64];
    for (int i = 0; i < 64; i++) px[i] = ((DWORD)(i * 4) << 24) | ((DWORD)i << 16) | ((DWORD)(255 - i) << 8) | (DWORD)(i * 3);
    static const struct { int tipo, bpp, arriba; const char *que; } C[6] = {
        { 2, 32, 1, "TGA 32 bits, sin comprimir, de arriba abajo" }, { 2, 32, 0, "TGA 32 bits, sin comprimir, de abajo arriba" },
        { 10, 32, 1, "TGA 32 bits RLE, de arriba abajo" },          { 10, 32, 0, "TGA 32 bits RLE, de abajo arriba" },
        { 2, 24, 0, "TGA 24 bits (alfa 255)" },                      { 10, 24, 1, "TGA 24 bits RLE (alfa 255)" },
    };
    for (int c = 0; c < 6; c++) {
        DWORD n = 0;
        BYTE *b = tga(C[c].tipo, C[c].bpp, C[c].arriba, 8, 8, px, &n);
        int w = 0, h = 0;
        DWORD *r = pdr_tga(b, n, &w, &h);
        int igual = r && w == 8 && h == 8;
        if (igual) {
            /* el 2.º píxel de cada fila es copia del 1.º en el RLE de prueba */
            for (int y = 0; y < 8 && igual; y++)
                for (int x = 0; x < 8; x++) {
                    DWORD e = px[y * 8 + (C[c].tipo == 10 && x == 1 ? 0 : x)];
                    if (C[c].bpp == 24) e |= 0xFF000000u;
                    if (r[y * 8 + x] != e) { igual = 0; break; }
                }
        }
        OK(igual, C[c].que);
    }
    {   /* cortado: no revienta */
        DWORD n = 0;
        BYTE *b = tga(2, 32, 1, 8, 8, px, &n);
        int w = 0, h = 0;
        OK(pdr_tga(b, n - 10, &w, &h) == NULL, "un TGA cortado se rechaza (sin leer de más)");
        b[2] = 1;
        OK(pdr_tga(b, n, &w, &h) == NULL, "un TGA con paleta se rechaza");
    }
    {   /* validar */
        wchar_t por[200];
        DWORD op[64 * 64], tr[64 * 64];
        for (int i = 0; i < 64 * 64; i++) { op[i] = 0xFF808080; tr[i] = i % 7 ? 0xFF808080 : 0x00000000; }
        OK(pdr_validar(tr, 64, 64, por) == 0, "una piedra cuadrada con transparencia sirve");
        OK(pdr_validar(op, 64, 64, por) != 0, "sin transparencia NO sirve");
        OK(pdr_validar(tr, 64, 32, por) != 0, "no cuadrada NO sirve");
        OK(pdr_validar(NULL, 0, 0, por) != 0, "sin imagen NO sirve");
        /* el muestreo: el mismo tamaño devuelve el mismo píxel; a medias, un promedio sin halo negro */
        DWORD dos[4] = { 0xFFFF0000, 0x00000000, 0xFFFF0000, 0x00000000 };
        DWORD m = pdr_muestra(dos, 2, 2, 0.5f, 0.5f);
        OK(((m >> 16) & 0xFF) == 0xFF && (m >> 24) > 100 && (m >> 24) < 160, "el bilineal premultiplica (sin halo oscuro en el borde)");
        OK(pdr_muestra(dos, 2, 2, 0.25f, 0.25f) == 0xFFFF0000, "al centro de un píxel da ese píxel");
    }
    {   /* ★ 26-nov: la piedra cambia las NOTAS, no la esquina de los números del combo */
        static DWORD orig[256 * 256], elegida[256 * 256], hoja[256 * 256];
        for (int i = 0; i < 256 * 256; i++) { orig[i] = 0xFF112233; elegida[i] = 0x80AABBCC; }
        pdr_componer(hoja, 256, 256, elegida, 256, 256, orig);
        OK(hoja[0] == 0x80AABBCC && hoja[100 * 256 + 200] == 0x80AABBCC, "las notas son las de la piedra elegida");
        OK(hoja[200 * 256 + 10] == 0xFF112233 && hoja[255 * 256 + 127] == 0xFF112233,
           "la esquina de los números del combo (abajo a la izquierda) queda la del juego");
        OK(hoja[200 * 256 + 128] == 0x80AABBCC && hoja[191 * 256 + 10] == 0x80AABBCC,
           "revés: justo fuera de la esquina ya es la elegida");
        static DWORD chica[128 * 128];
        for (int i = 0; i < 128 * 128; i++) chica[i] = 0xFF00FF00;
        pdr_componer(hoja, 256, 256, chica, 128, 128, orig);
        OK(hoja[50 * 256 + 50] == 0xFF00FF00 && hoja[250 * 256 + 5] == 0xFF112233, "también con una piedra de otro tamaño");
    }
    {   /* la curva */
        float pb[HT_AF_MAX], pf[HT_AF_MAX];
        int n = 0;
        wchar_t err[200];
        OK(!ht_af_parsear(L"148:18;180:17;277:11", pb, pf, &n, err) && n == 3 && pb[1] == 180 && pf[2] == 11, "la de fábrica se lee");
        OK(!ht_af_parsear(L"185 16,5\r\n170 17\r\n", pb, pf, &n, err) && n == 2 && pb[0] == 170 && pf[1] > 16.49f && pf[1] < 16.51f,
           "líneas, coma decimal y desordenada");
        OK(ht_af_parsear(L"170", pb, pf, &n, err) != 0, "un número suelto se rechaza");
        OK(ht_af_parsear(L"170 25", pb, pf, &n, err) != 0, "Far 25 se rechaza");
        OK(ht_af_parsear(L"170 17; 170 16", pb, pf, &n, err) != 0, "el mismo BPM dos veces se rechaza");
    }
    {   /* booster: la mezcla del marco y el reloj de los GIF */
        OK(bo_sobre(0xFF0000FF, 0x00FFFFFF) == 0xFF0000FF, "un marco transparente no tapa el botón");
        OK(bo_sobre(0xFF0000FF, 0xFFFF0000) == 0xFFFF0000, "un marco opaco tapa el botón");
        DWORD m = bo_sobre(0xFF000000, 0x80FFFFFF);
        OK((m >> 24) == 0xFF && ((m >> 16) & 0xFF) > 120 && ((m >> 16) & 0xFF) < 135, "medio transparente sobre opaco mezcla a la mitad");
        int ms[3] = { 100, 50, 200 };
        BO_ANIM a = { 3, 1, 1, 350, NULL, ms };
        OK(bo_anim_cuadro(&a, 0) == 0 && bo_anim_cuadro(&a, 120) == 1 && bo_anim_cuadro(&a, 160) == 2 && bo_anim_cuadro(&a, 360) == 0,
           "el reloj del GIF elige el cuadro por sus tiempos y da la vuelta");
    }
    if (argc > 2) {                                      /* un GIF animado de verdad */
        wchar_t w[MAX_PATH];
        MultiByteToWideChar(CP_ACP, 0, argv[2], -1, w, MAX_PATH);
        BO_ANIM a;
        int ok = bo_anim_cargar(w, &a);
        printf("  (%s: %d cuadros, %dx%d, %d ms)\n", argv[2], ok ? a.n : 0, ok ? a.w : 0, ok ? a.h : 0, ok ? a.total : 0);
        OK(ok && a.n > 1 && a.total > 0, "un GIF animado se lee con todos sus cuadros");
        if (ok) bo_anim_soltar(&a);
    }
    if (argc > 1) {                                      /* una piedra de verdad */
        wchar_t w[MAX_PATH];
        MultiByteToWideChar(CP_ACP, 0, argv[1], -1, w, MAX_PATH);
        int W = 0, H = 0;
        wchar_t por[200];
        DWORD *r = pdr_cargar(w, &W, &H);
        printf("  (%s: %dx%d)\n", argv[1], W, H);
        OK(r && pdr_validar(r, W, H, por) == 0, "la piedra de verdad se lee y sirve");
    }
    printf(g_fallos ? "\n%d fallo(s)\n" : "\ntodo bien\n", g_fallos);
    return g_fallos ? 1 : 0;
}
