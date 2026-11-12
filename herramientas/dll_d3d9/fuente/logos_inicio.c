/* logos_inicio.c — LOS LOGOS DEL ARRANQUE con «Eñeños bit» (16-oct-2026) · LOGOS_INICIO.md
 *
 * Las imágenes las arma `herramientas/logos_inicio.py` (pak `rnr_ui_logos.pak`); acá van los números del exe.
 * ⚠ Van JUNTOS: el pak sin la dll muestra la tira cortada, y la dll sin el pak, una tira de fábrica estirada.
 * Se INCLUYE desde d3d9_proxy.c (después de `escribir_bytes`).
 *
 * 1 · LA TIRA DE LA PANTALLA DE TÍTULO, MÁS ANCHA
 *   anonimo03: «a la tira añadir "Eñeños bit"; se hará más grande, así que hay que conservar su centrado». La dibuja
 *   0x49A5E0 desde `rnr_ui/title/title.tga` en DOS pedazos (la textura mide 512 y la tira 664): el 1.º (x 8 · y 408 ·
 *   476×45) en (mitad − 0x141, alto − 50) y el 2.º (x 14 · y 461 · 188×45) en (mitad + 0x9B, alto − 50). Su centro
 *   queda en mitad + 11. La nueva mide TIRA_ANCHO: el 1.º pedazo sigue de 476 y el 2.º pasa a TIRA_ANCHO − 476.
 *   Tres números, con guarda:
 *     0x49A6A5  add edx, −0x141      → 11 − TIRA_ANCHO/2               (dónde arranca el 1.º)
 *     0x49A6E7  push 0xBC            → TIRA_ANCHO − 476                (el ancho del 2.º)
 *     0x49A70B  add edx, 0x9B        → (dónde arranca el 1.º) + 476    (dónde arranca el 2.º)
 *
 * 2 · EL 1.er LOGO (Softnyx_CI.bmp) EN DOS PEDAZOS
 *   anonimo03: «Eñeños bit al centro · softnyx en la esquina inferior izquierda de la PANTALLA». El juego carga la imagen
 *   (0x580E02) con un solo recorte, la hoja entera de 512×512, y la dibuja CENTRADA (0x580F1F: `call 0x64F050` =
 *   posicionar el recorte n en (x, y) + dibujarlo; después tapa con el negro del fundido, que vale para todo).
 *   Ese call va a ls_dibujar: le agrega a la imagen dos recortes de la misma hoja y dibuja
 *     LS_MARCA    donde estaba (x + u, y + v)       → «Eñeños bit» sigue en el medio, en cualquier resolución
 *     LS_SOFTNYX  pegado a la esquina inferior izquierda (0, alto − h): el margen ya viene dibujado en la hoja
 *   Si algo no cuadra dibuja lo de fábrica (la hoja entera centrada, que también se ve bien).
 *   ⚠ Los recortes los comprueba logos_inicio.py contra estos #define (si se mueve uno, no arma el pak). */

#define TIRA_ANCHO 796
#define LS_MARCA_U 0                     /* «Eñeños bit»: una franja del medio de la hoja                     */
#define LS_MARCA_V 128
#define LS_MARCA_W 512
#define LS_MARCA_H 256
#define LS_SOFTNYX_U 0                   /* softnyx + el copyright: el rincón de abajo a la izquierda           */
#define LS_SOFTNYX_V 384
#define LS_SOFTNYX_W 256
#define LS_SOFTNYX_H 128

typedef void (__attribute__((thiscall)) *F_LS_RECORTE)(void *self, float x, float y, int u, int v, int w, int h,
                                                       float z);                                      /* 0x64EC40 */
typedef void (__attribute__((thiscall)) *F_LS_DIBUJAR)(void *self, int n, int x, int y, int banderas); /* 0x64F050 */

static BYTE *g_ls_base = NULL;
static void *g_ls_img = NULL;            /* la imagen a la que ya se le pusieron los dos recortes */
static int   g_ls_n0 = 0;                /* el número del 1.º de los nuestros (−100: no se pudo)  */
#define LSV(x) (g_ls_base + ((DWORD)(x) - 0x400000))

/* los recortes son una lista de 0x50 B en [img+0x18 … img+0x1C] (lo lee 0x64D990, que ignora un número fuera de rango) */
static int ls_cuantos(void *img) { return (int)((*(DWORD *)((BYTE *)img + 0x1C) - *(DWORD *)((BYTE *)img + 0x18)) / 0x50); }

static void __fastcall ls_dibujar(void *img, void *nada, int n, int x, int y, int banderas)
{
    (void)nada;
    F_LS_DIBUJAR dib = (F_LS_DIBUJAR)LSV(0x64F050);
    if (n != 0) { dib(img, n, x, y, banderas); return; }
    if (img != g_ls_img || ls_cuantos(img) < g_ls_n0 + 2) {     /* 1.ª vez de esta imagen: los dos recortes */
        float z = *(float *)LSV(0x8750B8);                     /* la misma z que el recorte de fábrica (0,5) */
        F_LS_RECORTE rec = (F_LS_RECORTE)LSV(0x64EC40);
        int n0 = ls_cuantos(img);
        rec(img, 0, 0, LS_MARCA_U, LS_MARCA_V, LS_MARCA_W, LS_MARCA_H, z);
        rec(img, 0, 0, LS_SOFTNYX_U, LS_SOFTNYX_V, LS_SOFTNYX_W, LS_SOFTNYX_H, z);
        g_ls_img = img;
        g_ls_n0 = n0;
        if (ls_cuantos(img) != n0 + 2) {
            apuntar("  [logos] ⚠ la imagen del 1.er logo no tomó los recortes (%d → %d): va de una pieza", n0,
                    ls_cuantos(img));
            g_ls_n0 = -100;
        } else
            apuntar("  [logos] el 1.er logo en dos pedazos (recortes %d y %d): «Eñeños bit» al medio, softnyx en la"
                    " esquina (pantalla %dx%d)", n0, n0 + 1, 2 * *(int *)LSV(0x904084), 2 * *(int *)LSV(0x904088));
    }
    if (g_ls_n0 < 0) { dib(img, n, x, y, banderas); return; }
    int alto = 2 * *(int *)LSV(0x904088);
    dib(img, g_ls_n0, x + LS_MARCA_U, y + LS_MARCA_V, banderas);
    dib(img, g_ls_n0 + 1, 0, alto - LS_SOFTNYX_H, banderas);
}

static void logos_inicio_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    g_ls_base = (BYTE *)GetModuleHandleA(NULL);

    if (!GetPrivateProfileIntA("titulo", "tira_ancha", 1, ini)) {
        apuntar("  [logos] la tira ancha APAGADA ([titulo] tira_ancha=0)");
    } else {
        int x1 = 11 - TIRA_ANCHO / 2, w2 = TIRA_ANCHO - 476, x2 = x1 + 476;
        static const BYTE e1[6] = { 0x81, 0xC2, 0xBF, 0xFE, 0xFF, 0xFF };     /* add edx, -0x141 */
        static const BYTE e2[5] = { 0x68, 0xBC, 0x00, 0x00, 0x00 };           /* push 0xBC       */
        static const BYTE e3[6] = { 0x81, 0xC2, 0x9B, 0x00, 0x00, 0x00 };     /* add edx, 0x9B   */
        BYTE n1[6] = { 0x81, 0xC2 }, n2[5] = { 0x68 }, n3[6] = { 0x81, 0xC2 };
        for (int i = 0; i < 4; i++) {
            n1[2 + i] = (BYTE)((DWORD)x1 >> (8 * i));
            n2[1 + i] = (BYTE)((DWORD)w2 >> (8 * i));
            n3[2 + i] = (BYTE)((DWORD)x2 >> (8 * i));
        }
        int ok = escribir_bytes(0x0049A6A5, e1, n1, 6, "tira del título (1.º pedazo)")
              && escribir_bytes(0x0049A6E7, e2, n2, 5, "tira del título (ancho del 2.º)")
              && escribir_bytes(0x0049A70B, e3, n3, 6, "tira del título (2.º pedazo)");
        if (ok) apuntar("  [logos] ★ la tira ancha: %d px, centrada (1.º en mitad %d, 2.º de %d en mitad %d)",
                        TIRA_ANCHO, x1, w2, x2);
    }

    if (!GetPrivateProfileIntA("titulo", "logo_en_dos", 1, ini)) {
        apuntar("  [logos] el 1.er logo de una pieza ([titulo] logo_en_dos=0)");
        return;
    }
    /* 0x580F1F  call 0x64F050  →  call ls_dibujar */
    BYTE esp[5] = { 0xE8 }, nue[5] = { 0xE8 };
    DWORD r1 = 0x64F050 - (0x580F1F + 5);
    DWORD r2 = (DWORD)ls_dibujar - (DWORD)(LSV(0x580F1F) + 5);
    for (int i = 0; i < 4; i++) { esp[1 + i] = (BYTE)(r1 >> (8 * i)); nue[1 + i] = (BYTE)(r2 >> (8 * i)); }
    if (escribir_bytes(0x00580F1F, esp, nue, 5, "el 1.er logo (Softnyx_CI)"))
        apuntar("  [logos] ★ el 1.er logo va en dos pedazos (softnyx a la esquina)");
}
