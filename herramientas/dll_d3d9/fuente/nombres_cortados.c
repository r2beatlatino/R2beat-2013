/* nombres_cortados.c — (127) los títulos y nombres se cortaban MUCHO antes de llegar a su pared (28-oct-2026)
 *
 * ★ POR QUÉ (anonimo03: «se cortan mucho antes de chocar con su pared»; en el picker «Musica..», «A Cros..», «The Dr..»):
 *   el que parte un texto a un ancho (0x441FB0, el de la lista del picker y otros) mide primero el texto entero; si no
 *   entra, busca cuántas letras entran así:
 *
 *       0x4420A3  i = 0, acum = 0
 *                 pedazo = texto.substr(0, i)          0x4099A0 — ⚠ el COMIENZO entero, no la letra i
 *       0x442101  w = ancho(pedazo)                    0x635350 (GDI, Verdana)
 *       0x442106  w += acum          ← 03 C5  add eax, ebp
 *       0x442108  si w > pared: corta en i             jg 0x44211B
 *                 acum = w, i++ y otra vuelta
 *
 *   O sea que suma el ancho de «M» + «Mu» + «Mus» + … (medido con Frida el 28-oct: «Musica 12 [Boyfriend]», 135 px en
 *   una columna de ~130: 9+17+24+28+36+42 = 156 ya pasa la pared en «Musica», que mide 42). El mismo bytes en el exe de
 *   fábrica (R2Beat.exe.pristino): es del juego, no nuestro.
 *
 * ★ (129) Y DE A LETRAS, NO DE A BYTES: con el catálogo en UTF-8 (126) el ♪ son 3 bytes, y el corte caía en el medio:
 *   «Girlfriend (♪) - Sakura Tange» salía «Girlfriend (â..» (medido el 28-oct, con la columna del artista a 84 px).
 *   ⇒ los 20 bytes de 0x442106..0x442119 pasan a un salto a NUESTRO tramo (abajo), que:
 *       - compara el ancho del comienzo contra la pared, SIN sumar, y contando los «..» (8 px de Verdana) que el juego
 *         agrega detrás del corte: este bucle sólo corre si el texto NO entra entero, así que siempre los lleva
 *         (sin eso, «Korean Pop [..» tocaba el número de BPM, 28-oct);
 *       - si entra, se acuerda de ese largo (ebp, que ya no hace falta para la suma) y avanza UNA LETRA entera
 *         (los bytes 10xxxxxx de UTF-8 son la continuación de la misma letra);
 *       - si no entra, corta en el último largo que sí entraba (siempre entre dos letras), y sale por 0x44211B;
 *       - el renglón nuevo (0x0A) sigue saliendo por 0x44211A, como antes.
 *   (En 1252 los bytes 0x80..0xBF también se saltean de a dos —«¡», «º»—: el corte es un poco más grueso, nunca roto.)
 *   [nombres_cortados] activo=0 lo apaga. */

static const BYTE NC_TRAMO[] = {
    0x83, 0xC0, 0x08,                            /*  0  add eax, 8               ★ los «..» que van detrás del corte */
    0x3B, 0x84, 0x24, 0x84, 0x00, 0x00, 0x00,    /*  3  cmp eax, [esp+0x84]      el comienzo (+«..») contra la pared */
    0x7E, 0x07,                                  /* 10  jle entra (19) */
    0x8B, 0xFD,                                  /* 12  mov edi, ebp             no entra: el último largo que entraba */
    0xE9, 0, 0, 0, 0,                            /* 14  jmp 0x44211B             (rel32 en 15) */
    0x8B, 0xEF,                                  /* 19  entra: mov ebp, edi */
    0x47,                                        /* 21  inc edi */
    0x8A, 0x04, 0x3E,                            /* 22  sigue: mov al, [esi+edi] */
    0x24, 0xC0,                                  /* 25  and al, 0xC0 */
    0x3C, 0x80,                                  /* 27  cmp al, 0x80             ¿continuación de la misma letra? */
    0x75, 0x03,                                  /* 29  jne fin_letra (34) */
    0x47,                                        /* 31  inc edi */
    0xEB, 0xF4,                                  /* 32  jmp sigue (22) */
    0x80, 0x3C, 0x3E, 0x0A,                      /* 34  fin_letra: cmp byte [esi+edi], 0x0A */
    0x0F, 0x85, 0, 0, 0, 0,                      /* 38  jne 0x4420A3             (rel32 en 40) otra vuelta */
    0xE9, 0, 0, 0, 0,                            /* 44  jmp 0x44211A             (rel32 en 45) renglón nuevo */
};
#define NC_REL_CORTA   15
#define NC_REL_VUELTA  40
#define NC_REL_RENGLON 45

static void nombres_cortados_iniciar(void)
{
    char ini[MAX_PATH];
    lstrcpyA(ini, g_carpeta);
    lstrcatA(ini, "d3d9_proxy.ini");
    if (!GetPrivateProfileIntA("nombres_cortados", "activo", 1, ini)) {
        apuntar("[nombres_cortados] apagado ([nombres_cortados] activo=0)");
        return;
    }
    static const BYTE esperado[20] = {
        0x03, 0xC5,                                  /* add eax, ebp            ← la suma de los comienzos */
        0x3B, 0x84, 0x24, 0x84, 0x00, 0x00, 0x00,    /* cmp eax, [esp+0x84] */
        0x7F, 0x0A,                                  /* jg 0x44211B */
        0x47,                                        /* inc edi */
        0x80, 0x3C, 0x3E, 0x0A,                      /* cmp byte [esi+edi], 0x0A */
        0x8B, 0xE8,                                  /* mov ebp, eax */
        0x75, 0x89 };                                /* jne 0x4420A3 */
    BYTE *base = (BYTE *)GetModuleHandleA(NULL);
    BYTE *t = (BYTE *)VirtualAlloc(NULL, sizeof(NC_TRAMO), MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!base || !t) return;
#define NC_VA(x) (base + ((DWORD)(x) - 0x400000))
    CopyMemory(t, NC_TRAMO, sizeof(NC_TRAMO));
    *(int *)(t + NC_REL_CORTA)   = (int)((DWORD)NC_VA(0x44211B) - (DWORD)(t + NC_REL_CORTA + 4));
    *(int *)(t + NC_REL_VUELTA)  = (int)((DWORD)NC_VA(0x4420A3) - (DWORD)(t + NC_REL_VUELTA + 4));
    *(int *)(t + NC_REL_RENGLON) = (int)((DWORD)NC_VA(0x44211A) - (DWORD)(t + NC_REL_RENGLON + 4));
    BYTE nuevo[20];
    int i;
    nuevo[0] = 0xE9;
    *(int *)(nuevo + 1) = (int)((DWORD)t - ((DWORD)NC_VA(0x442106) + 5));
    for (i = 5; i < 20; i++) nuevo[i] = 0x90;
#undef NC_VA
    if (escribir_bytes(0x00442106, esperado, nuevo, 20, "nombres cortados (el comienzo que entra, de a letras)"))
        apuntar("[nombres_cortados] puesto: el texto se corta en su pared, entre dos letras");
    else
        VirtualFree(t, 0, MEM_RELEASE);
}
