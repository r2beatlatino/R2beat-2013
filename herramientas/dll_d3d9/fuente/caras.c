/* ═══════════════════════════════════════════════════════════════════════════
 * caras.c — LAS CARAS POR SEXO: el mismo número de cara sirve para una de chico
 *           y otra de chica (28-sep-2026)
 *
 *   ⛔ EL PROBLEMA. El 2013 guarda el número de cara ("Face Index") en UN BYTE: al
 *     cargar face.txt (0x523bbf), en el paquete de la sala (FF0C/FF15, 1 byte), en el
 *     ocupante (+0x1A5) y en la ruta. Hay 255 lugares y XYX trae ~230 caras más.
 *     El KR, el 2019 y XYX lo resolvieron recompilando con u16: portarlo son ~70
 *     lugares y cambiar el protocolo (medido; repo «Servidor R2Beat 2013 - traer del KR»,
 *     documentacion/TRAER_DEL_KR.md, "Caras").
 *
 *   ★ EL TRUCO: UN solo lugar. La función que arma la ruta de la carpeta
 *     (0x511B50) ya recibe el personaje que se dibuja (edi = char_id) y el objeto de
 *     tablas (esi), y el exe tiene GetGender (0x5105E0 = [hero+0x3C]: 0 chico, 1 chica).
 *     Las caras de chico y de chica son dibujos DISTINTOS (0 de 23 .dds iguales en los
 *     pares) ⇒ si la carpeta sale de (sexo, número), el mismo byte vale para DOS caras.
 *
 *     original, en 0x511BE6 (25 bytes):
 *         cmp bl,0x32 / jne / mov bl,0x31          ; la 50 se dibuja como la 49
 *         movzx ecx,bl / push ecx / push "rnr_char/FACE/%02d/" / push ebp
 *         call sprintf / add esp,0xC / jmp 0x511C20
 *     nuevo: jmp a una rutina propia que hace lo mismo, pero con
 *         carpeta = g_caras[sexo][bl]           (u16: la carpeta puede ser > 255)
 *
 *   ★ La tabla arranca en la IDENTIDAD (y la 50 -> 49, como el original): sin datos,
 *     el juego se comporta EXACTAMENTE igual que sin el parche. Las caras nuevas se
 *     declaran en `d3d9_caras.ini`, al lado de la dll:
 *         [chico]            [chica]
 *         17=300             17=301        ; el byte 17 dibuja la carpeta 300 / 301
 *   ⚠ Perilla: [caras] activo=0 en d3d9_proxy.ini lo apaga (ni engancha).
 *   ⚠ Se INCLUYE desde d3d9_proxy.c (después de `escribir_bytes`). No se compila suelta.
 * ═══════════════════════════════════════════════════════════════════════════ */

static WORD g_caras[2][256];

static void caras_cargar_seccion(const char *ini, const char *seccion, int sexo)
{
    static char buf[32768];
    DWORD n = GetPrivateProfileSectionA(seccion, buf, sizeof(buf), ini);
    int cuantas = 0;
    for (char *p = buf; p < buf + n && *p; p += lstrlenA(p) + 1) {
        /* "17=300" (se ignoran espacios y comentarios que empiecen con ; o #) */
        const char *q = p;
        while (*q == ' ' || *q == '\t') q++;
        if (*q == ';' || *q == '#') continue;
        int byte = 0, carpeta = 0, vio_igual = 0;
        for (; *q; q++) {
            if (*q >= '0' && *q <= '9') {
                if (vio_igual) carpeta = carpeta * 10 + (*q - '0');
                else byte = byte * 10 + (*q - '0');
            } else if (*q == '=') vio_igual = 1;
            else if (*q == ';' || *q == '#') break;
        }
        if (!vio_igual || byte < 1 || byte > 255 || carpeta < 1 || carpeta > 65535) {
            apuntar("  [caras] ⚠ [%s] renglón raro, lo ignoro: %s", seccion, p);
            continue;
        }
        g_caras[sexo][byte] = (WORD)carpeta;
        cuantas++;
    }
    apuntar("  [caras] [%s]: %d cara(s) movidas de carpeta", seccion, cuantas);
}

static void caras_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("caras", "activo", 1, ini)) {
        apuntar("  [caras] apagado ([caras] activo=0)");
        return;
    }
    /* la identidad, con la 50 -> 49 del original */
    for (int s = 0; s < 2; s++)
        for (int b = 0; b < 256; b++)
            g_caras[s][b] = (WORD)(b == 50 ? 49 : b);
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_caras.ini");
    caras_cargar_seccion(ini, "chico", 0);
    caras_cargar_seccion(ini, "chica", 1);

    BYTE *base = (BYTE *)GetModuleHandleA(NULL);
#define CARAS_VA(va) ((DWORD)(base + ((va) - 0x400000)))
    BYTE *r = (BYTE *)VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!r) {
        apuntar("  [caras] ⛔ no pude reservar memoria para la rutina");
        return;
    }
    int i = 0;
    DWORD v;
#define B(x) (r[i++] = (BYTE)(x))
#define D(x) (v = (DWORD)(x), r[i++] = (BYTE)v, r[i++] = (BYTE)(v >> 8), \
              r[i++] = (BYTE)(v >> 16), r[i++] = (BYTE)(v >> 24))
    /* entra con: bl = cara (1..255), esi = objeto de tablas, edi = char_id, ebp = buffer */
    B(0x57);                                   /* push edi              ; char_id        */
    B(0x8B); B(0xCE);                          /* mov ecx, esi          ; this           */
    B(0xB8); D(CARAS_VA(0x005105E0));          /* mov eax, GetGender                     */
    B(0xFF); B(0xD0);                          /* call eax              ; al = sexo (ret 4) */
    B(0x84); B(0xC0);                          /* test al, al                            */
    B(0x0F); B(0x95); B(0xC0);                 /* setne al              ; 0 chico / 1 chica */
    B(0x0F); B(0xB6); B(0xC0);                 /* movzx eax, al                          */
    B(0xC1); B(0xE0); B(0x08);                 /* shl eax, 8                             */
    B(0x0F); B(0xB6); B(0xCB);                 /* movzx ecx, bl                          */
    B(0x01); B(0xC8);                          /* add eax, ecx          ; sexo*256 + cara */
    B(0xB9); D(&g_caras[0][0]);                /* mov ecx, g_caras                       */
    B(0x0F); B(0xB7); B(0x0C); B(0x41);        /* movzx ecx, word [ecx+eax*2]            */
    B(0x51);                                   /* push ecx              ; la carpeta     */
    B(0x68); D(CARAS_VA(0x0087DE60));          /* push "rnr_char/FACE/%02d/"             */
    B(0x55);                                   /* push ebp              ; el buffer      */
    B(0xB8); D(CARAS_VA(0x0074F4BA));          /* mov eax, sprintf                       */
    B(0xFF); B(0xD0);                          /* call eax                               */
    B(0x83); B(0xC4); B(0x0C);                 /* add esp, 0xC                           */
    B(0xB8); D(CARAS_VA(0x00511C20));          /* mov eax, 0x511C20     ; donde seguía   */
    B(0xFF); B(0xE0);                          /* jmp eax                                */
#undef B
#undef D

    /* el salto: 5 bytes sobre `cmp bl,0x32 / jne +2` (y la guarda mira los 25 que
     * reemplaza la rutina, para saber que el exe es el que creemos) */
    static const BYTE esp[25] = { 0x80, 0xFB, 0x32, 0x75, 0x02, 0xB3, 0x31, 0x0F, 0xB6, 0xCB,
                                  0x51, 0x68, 0x60, 0xDE, 0x87, 0x00, 0x55, 0xE8, 0xBE, 0xD8,
                                  0x23, 0x00, 0x83, 0xC4, 0x0C };
    BYTE nue[25];
    for (int k = 0; k < 25; k++) nue[k] = esp[k];
    DWORD sitio = CARAS_VA(0x00511BE6);
    DWORD rel = (DWORD)r - (sitio + 5);
    nue[0] = 0xE9;
    nue[1] = (BYTE)rel; nue[2] = (BYTE)(rel >> 8); nue[3] = (BYTE)(rel >> 16); nue[4] = (BYTE)(rel >> 24);
    if (escribir_bytes(0x00511BE6, esp, nue, 25, "caras por sexo"))
        apuntar("  [caras] ★ puesto: la carpeta de la cara sale de (sexo, número)");
    else
        VirtualFree(r, 0, MEM_RELEASE);
#undef CARAS_VA
}
