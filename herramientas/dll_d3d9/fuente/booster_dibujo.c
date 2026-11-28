/* booster_dibujo.c — ★ 28-nov: EL AURA Y EL MARCO GRANDE DEL BOTÓN DEL BOOSTER, AFUERA DEL BOTÓN
 *
 *   anonimo03, con los ejemplos del AutoCtrl del ToolBit: el aura gira ALREDEDOR del botón y los marcos de 125 px
 *   (alas, corona…) salen por los costados. booster.c sólo reescribe los 81 × 81 del botón en la hoja del juego, así
 *   que esto se dibuja aparte, encima, en el cuadro del HUD de carrera (ht_por_cuadro), donde la cola 2D dijo que quedó
 *   el botón (g_bo_bx/by/bw, de bo_desplazar). Cada imagen se pasa a una textura propia de 256 × 256 (premultiplicada)
 *   cuando cambia de cuadro, y se dibuja con UN DrawPrimitiveUP (pb_quad_tam, escalada y suave).
 *     · aura: centrada en el botón, de g_bo_aura_pct % de su lado · marco grande: su tamaño / 81 del lado del botón.
 *   Se incluye desde d3d9_proxy.c después de pausa_barra.c (usa pb_dispositivo / pb_quad_tam y booster.c).
 */

#define BOD_LADO 256
static void  *g_bod_tex[2], *g_bod_dev;
static int    g_bod_pool = 1, g_bod_fallo, g_bod_cuadro[2] = { -1, -1 }, g_bod_visto;
static LONG   g_bod_ver[2];
static DWORD  g_bod_px[BOD_LADO * BOD_LADO];

static int bod_textura(void *dev, int k)
{
    if (dev != g_bod_dev) { g_bod_tex[0] = g_bod_tex[1] = NULL; g_bod_dev = dev; g_bod_cuadro[0] = g_bod_cuadro[1] = -1; }
    if (g_bod_tex[k]) return 1;
    if (g_bod_fallo) return 0;
    void **vt = *(void ***)dev;
    g_bod_pool = g_dispositivo_es_ex ? 0 : 1;
    long hr = ((D_CREARTEX)vt[23])(dev, BOD_LADO, BOD_LADO, 1, g_bod_pool ? 0 : 0x200, 21, (DWORD)g_bod_pool, &g_bod_tex[k], NULL);
    if (hr != 0 || !g_bod_tex[k]) {
        apuntar("  [booster] ⛔ no pude crear la textura del aura (hr=%08lX)", (unsigned long)hr);
        g_bod_fallo = 1;
        g_bod_tex[k] = NULL;
        return 0;
    }
    g_bod_cuadro[k] = -1;
    return 1;
}

/* un cuadro de la imagen → la textura (a 256 × 256, premultiplicado) */
static int bod_subir(int k, const BO_ANIM *a, int ci)
{
    for (int y = 0; y < BOD_LADO; y++)
        for (int x = 0; x < BOD_LADO; x++) {
            DWORD c = pdr_muestra(a->px[ci], a->w, a->h, (x + 0.5f) / BOD_LADO, (y + 0.5f) / BOD_LADO), al = c >> 24;
            g_bod_px[y * BOD_LADO + x] = (al << 24) | ((((c >> 16) & 0xFF) * al / 255) << 16)
                                         | ((((c >> 8) & 0xFF) * al / 255) << 8) | ((c & 0xFF) * al / 255);
        }
    void **vt = *(void ***)g_bod_tex[k];
    CALC_BLOQUEO b;
    if (((T_BLOQUEAR)vt[19])(g_bod_tex[k], 0, &b, NULL, g_bod_pool ? 0 : 0x2000) != 0) return 0;
    for (int y = 0; y < BOD_LADO; y++) CopyMemory((BYTE *)b.pBits + y * b.Pitch, g_bod_px + y * BOD_LADO, BOD_LADO * 4);
    ((T_SOLTAR)vt[20])(g_bod_tex[k], 0);
    return 1;
}

/* ★ 28-nov · EL BRILLO de lleno: un halo redondo, suave, en su propia textura (se arma una vez y se tiñe al dibujarlo) */
static void *g_bod_halo, *g_bod_halo_dev;
static int bod_halo(void *dev)
{
    if (g_bod_halo && dev == g_bod_halo_dev) return 1;
    if (g_bod_fallo) return 0;
    void **vt = *(void ***)dev;
    g_bod_halo = NULL;
    if (((D_CREARTEX)vt[23])(dev, BOD_LADO, BOD_LADO, 1, g_bod_pool ? 0 : 0x200, 21, (DWORD)g_bod_pool, &g_bod_halo, NULL) != 0
        || !g_bod_halo) { g_bod_halo = NULL; return 0; }
    g_bod_halo_dev = dev;
    for (int y = 0; y < BOD_LADO; y++)
        for (int x = 0; x < BOD_LADO; x++) {
            float dx = (x + 0.5f) / BOD_LADO * 2 - 1, dy = (y + 0.5f) / BOD_LADO * 2 - 1, r = dx * dx + dy * dy;
            float a = r >= 1 ? 0 : 1 - r;                             /* ★ 28-nov: más lleno (antes, (1-r)²) */
            DWORD v = (DWORD)(a * 255);
            g_bod_px[y * BOD_LADO + x] = (v << 24) | (v << 16) | (v << 8) | v;   /* premultiplicado */
        }
    void **vh = *(void ***)g_bod_halo;
    CALC_BLOQUEO b;
    if (((T_BLOQUEAR)vh[19])(g_bod_halo, 0, &b, NULL, g_bod_pool ? 0 : 0x2000) != 0) return 0;
    for (int y = 0; y < BOD_LADO; y++) CopyMemory((BYTE *)b.pBits + y * b.Pitch, g_bod_px + y * BOD_LADO, BOD_LADO * 4);
    ((T_SOLTAR)vh[20])(g_bod_halo, 0);
    return 1;
}

/* ★ 28-nov (anonimo03: «¿no debería ser morado?», con la amatista): sin teñido, el brillo toma el color PRINCIPAL de la
 *   imagen del lleno (el promedio de sus píxeles con color, pesado por cuánto color tienen), llevado a brillo pleno. */
static COLORREF g_bod_col = CLR_INVALID;
static LONG g_bod_col_ver = -1;
static COLORREF bod_color_lleno(void)
{
    if (g_bod_col_ver == g_bo_version) return g_bod_col;
    g_bod_col_ver = g_bo_version;
    g_bod_col = CLR_INVALID;
    const BO_ANIM *a = &g_bo_img[1];
    if (!a->n || !a->px || !a->px[0]) return g_bod_col;
    double sr = 0, sg = 0, sb = 0, sp = 0;
    for (int i = 0; i < a->w * a->h; i++) {
        DWORD c = a->px[0][i];
        double al = (c >> 24) / 255.0, r = (c >> 16) & 255, g = (c >> 8) & 255, bl = c & 255;
        double mx = r > g ? (r > bl ? r : bl) : (g > bl ? g : bl), mn = r < g ? (r < bl ? r : bl) : (g < bl ? g : bl);
        double peso = al * (mx - mn) / 255.0;                  /* lo gris o transparente casi no cuenta */
        sr += r * peso; sg += g * peso; sb += bl * peso; sp += peso;
    }
    if (sp < 1) return g_bod_col;
    double r = sr / sp, g = sg / sp, bl = sb / sp, mx = r > g ? (r > bl ? r : bl) : (g > bl ? g : bl);
    if (mx < 1) return g_bod_col;
    g_bod_col = RGB((int)(r * 255 / mx), (int)(g * 255 / mx), (int)(bl * 255 / mx));
    return g_bod_col;
}

static void bod_dibujar(void)
{
    if (!g_bo_activo || !g_bo_cs_lista || !g_bo_bt || GetTickCount() - g_bo_bt > 300 || g_bo_bw < 8) return;
    /* ★ 28-nov: el brillo de lleno, detrás de todo (aura incluida) */
    if (g_bo_brillo && g_bo_lleno_t && GetTickCount() - g_bo_lleno_t < 250) {
        void *dv = pb_dispositivo();
        if (dv && bod_halo(dv)) {
            DWORD t = GetTickCount();
            float fase = (float)((t % 900) / 900.0), lat = 0.55f + 0.45f * (fase < 0.5f ? fase * 2 : 2 - fase * 2);
            COLORREF c = g_bo_tenir != CLR_INVALID ? g_bo_tenir : bod_color_lleno();
            if (c == CLR_INVALID) c = RGB(255, 210, 60);       /* sin imagen propia: dorado, como el juego */
            DWORD a = (DWORD)(lat * 255);
            g_pb_quad_color = (a << 24) | ((GetRValue(c) * a / 255) << 16) | ((GetGValue(c) * a / 255) << 8) | (GetBValue(c) * a / 255);
            float lado = g_bo_bw * (2.3f + 0.3f * lat);          /* ★ 28-nov: más grande (antes 1,7 a 1,85) */
            float cx = g_bo_bx + g_bo_bw / 2, cy = g_bo_by + g_bo_bh / 2;
            g_pb_quad_sw = BOD_LADO; g_pb_quad_sh = BOD_LADO; g_pb_quad_suave = 1;
            pb_quad_tam(dv, g_bod_halo, (int)(cx - lado / 2), (int)(cy - lado / 2), (int)lado, (int)lado, BOD_LADO, BOD_LADO);
            /* … y una segunda pasada, más chica y entera, para que brille más en el centro */
            float l2 = lado * 0.7f;
            g_pb_quad_color = (a << 24) | ((GetRValue(c) * a / 255) << 16) | ((GetGValue(c) * a / 255) << 8) | (GetBValue(c) * a / 255);
            g_pb_quad_sw = BOD_LADO; g_pb_quad_sh = BOD_LADO; g_pb_quad_suave = 1;
            pb_quad_tam(dv, g_bod_halo, (int)(cx - l2 / 2), (int)(cy - l2 / 2), (int)l2, (int)l2, BOD_LADO, BOD_LADO);
            g_pb_quad_color = 0xFFFFFFFF;
        }
    }
    if (!g_bo_img[4].n && !bo_marco_afuera()) return;
    void *dev = pb_dispositivo();
    if (!dev || !TryEnterCriticalSection(&g_bo_cs)) return;
    DWORD t = GetTickCount();
    int lleno = g_bo_lleno_t && t - g_bo_lleno_t < 250;   /* ★ 28-nov: el aura, sólo lleno (si así está puesto) */
    const BO_ANIM *A[2] = { g_bo_img[4].n && (lleno || !g_bo_aura_lleno) ? &g_bo_img[4] : NULL,
                            bo_marco_afuera() ? &g_bo_img[2] : NULL };
    float lado[2] = { g_bo_bw * g_bo_aura_pct / 100.0f, A[1] ? g_bo_bw * (float)A[1]->w / 81.0f : 0 };
    float cx = g_bo_bx + g_bo_bw / 2, cy = g_bo_by + g_bo_bh / 2;
    for (int k = 0; k < 2; k++) {
        if (!A[k] || !bod_textura(dev, k)) continue;
        int ci = bo_anim_cuadro(A[k], t);
        if (ci != g_bod_cuadro[k] || g_bo_version != g_bod_ver[k]) {
            if (!bod_subir(k, A[k], ci)) continue;
            g_bod_cuadro[k] = ci; g_bod_ver[k] = g_bo_version;
        }
        int l = (int)(lado[k] + 0.5f), x = (int)(cx - lado[k] / 2), y = (int)(cy - lado[k] / 2);
        g_pb_quad_sw = BOD_LADO; g_pb_quad_sh = BOD_LADO; g_pb_quad_suave = 1;
        pb_quad_tam(dev, g_bod_tex[k], x, y, l, l, BOD_LADO, BOD_LADO);
        if (!(g_bod_visto & (1 << k))) {
            g_bod_visto |= 1 << k;
            apuntar("  [booster] ★ %s en pantalla: %d x %d en (%d, %d)", k ? "el marco grande" : "el aura", l, l, x, y);
        }
    }
    LeaveCriticalSection(&g_bo_cs);
}
