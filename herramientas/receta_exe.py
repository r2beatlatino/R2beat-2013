#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""receta_exe — la lista de parches del R2Beat.exe 2013, byte por byte.

Esto NO se corre: lo usa `parchar_cliente.py`. Es la receta con la que el proyecto arma el cliente
que juega contra este servidor, copiada tal cual de su `aplicar_parches.py`:

    (offset_de_archivo, bytes_antes, bytes_despues, descripción)

★ Cada parche se VERIFICA antes de escribir: si los bytes "antes" no coinciden con tu exe, no se
  aplica nada. Un parche que no verifica es un parche de otro binario.
★ Los comentarios largos son la bitácora de por qué existe cada uno. Se quedan: son la única
  documentación de qué toca cada byte.
"""
import hashlib
import sys

MD5_PRISTINO = "b8f2517ffd70fd60341d0a24c069a78c"
# md5 del resultado esperado, CON los 8 parches de abajo aplicados.
# ⚠ Si agregás o sacás un parche, este valor cambia: actualizalo con lo que imprima el script.
#   `828e9fee82df1952826fa27929259372` = build sin el parche del Shift.
#   `79e5e82f61d4c79043e8e53ec84c3465` = build del 04-sep, con la máscara del Shift MAL (0x404).
#   `442d5e0777e4c2505f46b4a5713cd876` = build del 06-sep con el parche `0x0FB97C` (el slot con
#      el que se elige el ACTOR del grito del relevo, `0x4FC57C`). ⛔ REVERTIDO dos veces.
#      El desfasaje que corrige es REAL y esta medido en los dos sentidos (ver PARCHES_EXE.md),
#      pero NO es el sonido que molesta: el usuario escucho `fight-1.mp3` / `fight-1_girl.mp3`
#      y confirmo que esos andan bien. El grito que buscamos es OTRO sonido, todavia sin
#      identificar. ⇒ no re-aplicar sin una razon nueva.
#   `b522faf7f76eaf43ed76ff40b2b079fb` = build del 05-sep, antes del rickroll del botón de recarga.
#   `a3d0a9925297342680a66a8734959b92` = build del 05-sep que se subió a producción. ⛔ Ese es el
#      que dejó a jugadores de hardware modesto con "error al crear dispositivo de video": traía
#      los 6 parches que subían la resolución POR DEFECTO a 1920x1080. Ver el bloque comentado
#      más abajo. Si alguien vuelve a ver este md5 en un cliente, es un cliente viejo.
#   `0b7834a706273f5d722e4770d194d126` = build del 06-sep con los defaults de resolución ya
#      revertidos, pero SIN el guard del `0x6840E7`.
#   `07927a9125d39cb00a4c920831c1899c` = build del 07-sep, hasta el candado de dificultad. Es el
#      que estuvo en uso hasta el 13-sep, y el que hay en `R2Beat/R2Beat_local.exe` si nadie
#      regeneró desde entonces.
#   `3f3e8e9ade249dfd791f92703dca1ee9` = 1er intento del cave de milésimas, 13-sep. ⛔⛔ MATA AL
#      CLIENTE AL CRUZAR LA META: guardaba su tabla dentro del propio cave, o sea en `.text`,
#      que es R-X. La leía bien; al escribirla, violación de acceso. Si alguien ve este md5 en
#      un cliente, es un cliente roto — regenerar.
#   `ef52f13dcbe61ebf06e0f07e45b7e2da` = 14-sep, el recorrido entero pero dibujando los decimales
#      con la FUENTE DE TEXTO: finitos al lado del número grande. anonimo03 lo cazó de una mirada.
#   `5f66ac3ba54aff275ec0ef026c8dacec` = milésimas a medio camino, 13-sep: la tabla ya en `.data`
#      y el cartel dibujando el número inflado (`93789` de una tirada). Anda, pero se ve feo y no
#      les ponía decimales a los demás jugadores. Reemplazado el 14-sep.
#   `cce48021418b6fc1881476c558dc4e03` = 17-sep, hasta los 3 del ícono de licencia. El que se jugó
#      hasta el 29-sep.
#   `9a4fbc84faa84295eac915a544d0a48e` = 29-sep, 1er armado del menú de resolución. ⛔⛔ CIERRA EL
#      JUEGO AL ABRIR OPCIONES: el tramo de «abrir» seguía de largo a un relleno CC (int3). Nunca
#      se jugó: lo cazó `pruebas/probar_menu_resolucion.py` corriendo el tramo en un emulador.
#   `9def95874da91e08d335ea9571afc31e` = 29-sep, + el menú de resolución con 3 opciones (commit 364007b1).
#   `3115b797b13a7a8dfa486a073d3f163f` = 29-sep, + 2 parches de la tira de anuncios (repetir cada 3 s y mostrar
#      al llegar el FFBF). ⛔ DESCARTADOS por anonimo03 antes de jugarlos: *"no edites el exe, si funcionaba así
#      originalmente está bien como está"*. Ver TIRA_DE_ANUNCIOS.md §5.
#   `0b69946cb2bf5e5e22760b355507cd45` = 29-sep, + «Mi record» del picker con decimales (commit 6a8fc69a).
MD5_ESPERADO = "7b8626647231e715d3f2fe33eebe2c46"   # 2026-09-29: + Novato Sol y Sol desde el nivel 50

# ── LA RECETA ──────────────────────────────────────────────────────────────────────────────
# (offset_de_archivo, bytes_antes, bytes_despues, descripción)
# El offset de archivo se obtiene con  file_offset = VA − 0x400C00  (sección .text; comprobado
# contra la tabla de secciones del PE para las tres VAs de esta lista).
PARCHES = [
    # ★★★★★ EL CRASH DE LAS PLACAS VIEJAS — 2026-09-06. `0x006840E7`.
    #
    #   ⛔ EL SÍNTOMA, reportado y confirmado: en hardware modesto el juego ABRE (con DXVK sacado)
    #     pero se cae a los ~20 s, entrando al lobby, cargando texturas de efectos. Siempre en la
    #     misma dirección. Al jugador `jugador19` (Intel HD Graphics 500) le pasaba 10 de 10 veces.
    #
    #   ★ LA FUNCIÓN, que es un getter genérico con 132 llamadores:
    #         006840D0  mov eax,[esp+4]          ; el índice que le piden
    #         006840D4  cmp [ecx+0xA0],eax       ; ¿la CANTIDAD es mayor que el índice?
    #         006840DA  ja  0x6840E4             ;   sí -> a buscarlo
    #         006840DC  mov eax,1                ;   no -> ★ SALIDA SANA que el juego YA TIENE
    #         006840E1  ret 4
    #         006840E4  mov ecx,[ecx+0x40]       ; el puntero al arreglo
    #         006840E7  mov eax,[ecx+eax*8]      ; ⛔ acá revienta: el puntero viene en NULL
    #
    #     El volcado del jugador lo confirma: leyendo la dirección 0x68 = 13 × 8, o sea el
    #     elemento 13 de un arreglo que **nunca se creó**, con la cantidad diciendo 14 o más.
    #
    #   ★★ POR QUÉ SÓLO A ELLOS, y por qué NO es culpa del server: si mandáramos algo mal, se
    #     caerían todos. Medido el mismo día: de 105 jugadores, **83 juegan normal y 5 se caen
    #     siempre**. Un arreglo en NULL con la cantidad puesta es la firma de **una creación de
    #     recurso que FALLÓ y que el cliente no chequea**. DXVK —que es una reimplementación
    #     moderna y mucho más permisiva— acepta lo que el driver Intel de 2009 rechaza, así que
    #     en hardware moderno **esa creación nunca falla y el bug no existe**. Es un bug del
    #     cliente de 2013 que quedó tapado 13 años y que destapamos al sacarles DXVK.
    #
    #   ⇒ EL ARREGLO: preguntar si el puntero está vacío y, si lo está, mandarlo por **la salida
    #     que la propia función ya tiene** para el índice fuera de rango (`mov eax,1; ret 4`).
    #     No se inventa nada: se reusa su propio camino de "no hay dato".
    #
    #   ★★ ENTRA INLINE, Y GRACIAS A `jecxz`. El primer intento fue saltar a la cueva del final de
    #     `.text`, y **no se pudo: está llena al 100 %** — el stub de la voz del relevo usa los 274
    #     bytes justos. Eso obligó a mirar mejor, y salió algo más limpio:
    #         `test ecx,ecx` + `jz rel8` = 4 bytes  ⇒ hacen falta 13 y sólo hay 12 hasta la
    #                                                 función siguiente (`0x6840F0`). No entra.
    #         `jecxz rel8`               = 2 bytes  ⇒ 11 bytes. **Entra, y sobra uno.**
    #     `jecxz` es exactamente esto: saltar si ECX es cero, y ECX es justo el puntero que hay que
    #     comprobar. Sin cueva, sin depender del parche de cabecera, y sin tocar nada alrededor.
    #
    #   Queda así:
    #         006840E4  8b 49 40   mov ecx,[ecx+0x40]     ; el puntero al arreglo
    #         006840E7  e3 f3      jecxz 0x6840DC         ; ★ si es NULL -> a la salida sana
    #         006840E9  8b 04 c1   mov eax,[ecx+eax*8]    ; si no, lo de siempre
    #         006840EC  c2 04 00   ret 4
    #         006840EF  cc                                 ; el relleno que sobra, intacto
    #
    #   ⚠ TAPA EL CRASH, NO LA CAUSA. El recurso que esa placa no puede crear va a seguir sin
    #     crearse: es esperable que falte un efecto o se vea algo feo. Entrar y jugar con un
    #     efecto de menos le gana a no entrar.
    #
    #   ⛔⛔ PROBADO EL MISMO DIA EN LA PC DEL JUGADOR (opcion 6 del launcher de prueba):
    #     **NO ARREGLA NADA. Se sigue cayendo igual.**
    #     ⇒ el `mov eax,[ecx+eax*8]` con ECX en NULL no es la causa raiz: es una consecuencia mas
    #       abajo, o el crash se mudo a otro lado sin cambiar de sintoma. El razonamiento del
    #       arreglo (mandarlo por la salida sana que la funcion ya tiene) sigue siendo correcto
    #       COMO PARCHE; lo que estaba mal era el diagnostico de que ahi empezaba el problema.
    #
    #   ⚠ ESTE PARCHE NO ESTA EN PRODUCCION, y no deberia subir mientras no sirva: cambia el
    #     binario de 105 jugadores para arreglarle a cero. Si el proximo empaquetado no lo tiene
    #     que llevar, se saca de esta lista y se actualiza MD5_ESPERADO.
    #     El md5 de prod hoy (06-sep) es `aad32c679928acc56b6bc9dc3d44caed`, que es el pristino
    #     con estos parches MENOS el guard, y con la IP publica horneada.
    (0x2834E4, bytes.fromhex("8b49408b04c1c20400cccc"),
               bytes.fromhex("8b4940e3f38b04c1c20400"),
     "VA 0x6840E4 · el getter comprueba el puntero antes de usarlo (jecxz -> la salida que ya tenía)"),

    (0x0EA62B, b"\x00", b"\x01",
     "VA 0x4EB22A · `mov ecx, 0x400` -> `mov ecx, 0x401`. ★ EL INTERCAMBIO DE ÍTEMS CON SHIFT.\n"
     "     El bit 0x400 de `cGame+0x0C` es 'modo cooperativo' y `0x4EB22F test word [esi+0xc], cx`\n"
     "     descarta la tecla ANTES de leerla en cualquier otro modo. Con la máscara 0x401 el test\n"
     "     pasa además con el bit 0x01, que es 'este modo TIENE ítems'.\n"
     "     Sin ruta server-side: el flag lo calcula el cliente en `CalcGameFlags` (0x56B680).\n"
     "\n"
     "     ⚠⚠ CORRECCIÓN 2026-09-05: hasta hoy este parche escribía 0x04, y estaba MAL.\n"
     "     `CalcGameFlags` (0x56B680), desensamblada entera, arma la palabra así:\n"
     "         eax = 0x11 + (GameMode != 1)      ; GameMode 1 = ÍTEM · 2 = VELOCIDAD\n"
     "         CooperationMode == 2 -> eax |= 0x44   (RELEVO, que trae el bit de equipo)\n"
     "         CooperationMode == 0 -> eax |= 0x04   (EQUIPO)\n"
     "         GameMode 4 -> 0x413 (cooperativo)  ·  GameMode 5 -> 0x2017 (jefe)\n"
     "     ⇒ **el bit 0x04 es el de EQUIPO, no el de ítem**. La tabla real es:\n"
     "         0x11 solo+ítem · 0x12 solo+velocidad · 0x15 equipo+ítem · 0x16 equipo+velocidad\n"
     "         0x55 relevo+ítem · 0x56 relevo+velocidad · 0x413 cooperativo · 0x2017 jefe\n"
     "     Con la máscara 0x404 el Shift quedaba MUERTO en solo+ítem (0x11) y ENCENDIDO en\n"
     "     equipo+velocidad (0x16) y relevo+velocidad (0x56) — lo contrario de lo pedido.\n"
     "     Con 0x401 entra exactamente en los modos con ítem: 0x11 0x15 0x55 0x413 0x2017,\n"
     "     y en ninguno de velocidad. El cooperativo sigue pasando (0x413 tiene los dos bits).\n"
     "     Los valores GameMode/CooperationMode están confirmados por DOS caminos independientes:\n"
     "     el encoder C→S `0x46BC60` y el decoder S→C `0x46BBF0`."),

    (0x000240, b"\xee\x16\x47\x00", b"\x00\x18\x47\x00",
     "Cabecera de la seccion .text: VirtualSize 0x4716ee -> 0x471800. ★ HABILITA EL CODE CAVE.\n"
     "     Al final de .text hay 274 bytes de relleno (todos 00) que quedan FUERA del\n"
     "     VirtualSize, o sea que el cargador no garantiza mapearlos. Declarandolos, el hueco\n"
     "     pasa a ser codigo valido. Sin esto el cave podria ser ceros en ejecucion.\n"
     "     Es lo unico de todo el proyecto que toca la cabecera PE, y son 4 bytes."),

    (0x471aee, b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00", b"\xba\xce\xbd\xba\xc6\xae\x30\x34\x00\xba\xce\xbd\xba\xc6\xae\x30\x35\x00\xba\xce\xbd\xba\xc6\xae\x30\x36\x00\x60\xf6\x45\x0c\x40\x0f\x84\xa8\x00\x00\x00\xd9\xe8\x68\x54\xff\x01\x00\x51\xd9\x1c\x24\x68\xcc\xca\x87\x00\x68\xa8\xca\x87\x00\x89\xe9\xe8\x80\x55\xc8\xff\xd9\xe8\x68\x54\xff\x01\x00\x51\xd9\x1c\x24\x68\x9c\xca\x87\x00\x68\x78\xca\x87\x00\x89\xe9\xe8\x64\x55\xc8\xff\xd9\xe8\x68\x54\xff\x01\x00\x51\xd9\x1c\x24\x68\x6c\xca\x87\x00\x68\x48\xca\x87\x00\x89\xe9\xe8\x48\x55\xc8\xff\xd9\xe8\x68\x55\xff\x01\x00\x51\xd9\x1c\x24\x68\xee\x26\x87\x00\x68\xa8\xca\x87\x00\x89\xe9\xe8\x2c\x55\xc8\xff\xd9\xe8\x68\x55\xff\x01\x00\x51\xd9\x1c\x24\x68\xf7\x26\x87\x00\x68\x78\xca\x87\x00\x89\xe9\xe8\x10\x55\xc8\xff\xd9\xe8\x68\x55\xff\x01\x00\x51\xd9\x1c\x24\x68\x00\x27\x87\x00\x68\x48\xca\x87\x00\x89\xe9\xe8\xf4\x54\xc8\xff\x61\xe9\xee\x54\xc8\xff\x99\xb9\x03\x00\x00\x00\xf7\xf9\x42\x50\x52\xa1\xc8\x14\x93\x00\x85\xc0\x74\x26\xf6\x40\x0c\x40\x74\x20\x8b\x0d\x60\x16\x93\x00\x85\xc9\x74\x16\x0f\xb6\x50\x5d\x52\xe8\x90\x3b\xbc\xff\x3d\x55\xff\x01\x00\x75\x05\x5a\x83\xc2\x03\x52\x5a\x58\xc3\x00",
     "VA 0x8726ee .. 0x8727ff · EL CODE CAVE del sonido del impulsor (273 B de 274).\n"
     "     Generado por `taller/re2013/parche_impulsor.py` (keystone); ese archivo tiene el fuente en\n"
     "     asm y el porque. `--verificar-receta` re-ensambla y compara contra estos bytes.\n"
     "     Tres piezas:\n"
     "       0x8726ee  los nombres de evento nuevos: 부스트04 / 05 / 06 (cp949)\n"
     "       0x872709  cave_reg: registra los SEIS eventos con genero FIJO --\n"
     "                       01/02/03 = VARON (char 130900), 04/05/06 = MUJER (130901) --\n"
     "                       y termina con `jmp 0x4F7CB0` para que el registro original\n"
     "                       del juego siga su curso (queda ignorado: clave repetida).\n"
     "       0x8727b8  cave_num: rand()%3+1, y +3 si `[cGame+0x5d]` es mujer -> 4..6."),

    (0x0faaac, b"\xe8\xff\xc5\xff\xff", b"\xe8\x58\x70\x37\x00",
     "VA 0x4fb6ac · `call 0x4F7CB0` -> `call cave_reg`. El registro del PRIMER boost.\n"
     "     Se engancha aca porque cave_reg registra los seis ANTES de que el juego registre\n"
     "     los suyos, y asi el resultado es determinista: no depende de quien arranque."),

    (0x16c943, b"\x99\xb9\x03\x00\x00\x00\xf7\xf9\x42", b"\xe8\x7a\x52\x30\x00\x90\x90\x90\x90",
     "VA 0x56d543 · `cdq / mov ecx,3 / idiv ecx / inc edx` -> `call cave_num` + nops.\n"
     "     Es el sitio que arma el nombre del evento con sprintf(\"부스트%02d\") en 0x56D557.\n"
     "     Verificado que NADA salta al medio de esos 9 bytes ni a su inicio.\n"
     "     ★ EL BUG QUE ARREGLA: boost01/02/03 se registran UNA vez, en el init de la escena\n"
     "     (0x4FB668), con el genero del corredor activo de ESE momento. En relevo el corredor\n"
     "     cambia y nadie vuelve a registrar, asi que los tres tramos suenan con la voz del\n"
     "     primero. Re-registrar no sirve: 0x52EB20 es un map::insert que NO sobrescribe.\n"
     "     Probado antes en Frida (`frida_batuta.py --arreglar-boost`), tres carreras seguidas\n"
     "     cambiando de slot: V->M->V, M->V->V y V->V->M, todas correctas.\n"
     "     ⚠ El bug sigue vivo en el cliente chino de 2019: nunca lo arreglaron."),

    (0x484D08, b"216.177.209.25", b"192.168.31.100",
     "VA 0x885908 · LA IP HORNEADA del servidor, apuntada a la LAN.\n"
     "     ⚠ Es específica de esta máquina. `launcher2013.py` puede evitarla pasando `test:<ip>`\n"
     "     por línea de comandos, así que este parche es heredado y probablemente prescindible.\n"
     "     Las dos cadenas miden 14 bytes justos, por eso entra sin correr nada."),

    (0x2489B7, b"\x17", b"\x16",
     "VA 0x6495B5 · `cmp edx, 0x17` -> `cmp edx, 0x16`. ★ COLOR DE 32 BITS (1 de 2).\n"
     "     ✅ IDENTIFICADO el 2026-09-06. Los números son constantes **D3DFORMAT**:\n"
     "         0x14=R8G8B8(24) · 0x15=A8R8G8B8(32) · 0x16=X8R8G8B8(32)\n"
     "         0x17=R5G6B5(16) · 0x18=X1R5G5B5(16) · 0x19=A1R5G5B5(16)\n"
     "     `0x649550` recorre los modos de pantalla buscando uno que sirva, y se ramifica por\n"
     "     BITS POR PIXEL (`cmp bl,0x10` = 16 · `cmp bl,0x20` = 32). El byte parchado está en la\n"
     "     rama de 16 bits: donde el original aceptaba R5G6B5, ahora acepta X8R8G8B8.\n"
     "     ⇒ si el juego pide 16 bits, se le da uno de 32.\n"
     "     ★ Esto explica una nota que ya estaba en PARCHES_EXE.md §2 y que nadie había atado:\n"
     "     'los dos clientes ya presentan X8R8G8B8, confirmado en el log de DXVK'. Lo presentan\n"
     "     PORQUE está este parche. La observación era correcta; la causa estaba sin documentar."),

    # ✅✅ LOS DOS PARCHES DE COLOR ESTAN EXONERADOS — comprobado el 2026-09-06 contra CINCO
    #   binarios, buscando el sitio POR PATRON (no por offset, que solo vale para nuestro build):
    #
    #     pristino 2013 ............ 0x17 / 0x14   (sin parchar)
    #     CBT "DESNUDO" ............ 0x17 / 0x14   (sin parchar)
    #     NUESTRO exe de prod ...... 0x16 / 0x16
    #     el otro server privado ... 0x16 / 0x16   <- MISMO build base que nuestro pristino
    #     CBT (4 variantes) ........ 0x16 / 0x16   <- build DISTINTO, 3,5 MB
    #
    #   Tres bases de codigo independientes llegaron a los MISMOS DOS BYTES. Y el cliente del otro
    #   server, con estos mismos valores, **arranca bien en la maquina donde el nuestro se cae**.
    #   ⇒ El color de 32 bits no tiene nada que ver con el crash del hardware modesto. No tocar.
    (0x24A87F, b"\x14", b"\x16",
     "VA 0x64B47B · `mov [esp+0x58], 0x14` -> `0x16`. ★ COLOR DE 32 BITS (2 de 2).\n"
     "     ✅ IDENTIFICADO el 2026-09-06. `0x64B410` arma en la pila la lista de formatos que va a\n"
     "     pedirle a Direct3D, en orden de preferencia:\n"
     "         [esp+0x4c]=0x18  [esp+0x50]=0x19  [esp+0x54]=0x17  [esp+0x58]=0x14 -> 0x16\n"
     "     El último era R8G8B8 (24 bits, que las placas modernas ni exponen); ahora es\n"
     "     X8R8G8B8 (32). Va de la mano con el parche de 0x6495B5: los dos empujan al cliente a\n"
     "     color de 32 bits.\n"
     "     ⛔ NO revertir pensando que son basura heredada: sin ellos el cliente puede quedarse\n"
     "     pidiendo modos de 16/24 bits que el hardware actual no ofrece."),

    # ═══ RESOLUCIONES — 6 valores, y dos de ellos lo son todo (2026-09-05) ═══════════════
    # ★★ QUE HACE EL CLIENTE, desensamblado en 0x4087C9 (no supuesto):
    #
    #       mov eax, [0x904094]      ; el ANCHO que leyo del Config.ini
    #       cmp eax, ebx             ; ¿es el ancho por defecto?
    #       je  0x4087E0             ; <-- (1)
    #       cmp eax, 0x400           ; ¿es 1024?
    #       je  0x4087E0
    #       mov eax, ebx             ; <-- si no es NINGUNO de los dos, LO FUERZA
    #       mov [0x904094], eax
    #       ... y lo mismo con el alto contra edi y 0x300, con el je de (2)
    #
    #   ⇒ NO era un tope: era una LISTA BLANCA de DOS anchos y DOS altos. Poner 1920 en el
    #     Config.ini sin tocar esto no hacia nada — el cliente lo pisaba y arrancaba chico.
    #
    # ★★★ EL ARREGLO SON DOS BYTES: los dos `je` pasan a `jmp` (0x74 -> 0xEB). Con el salto
    #   incondicional nunca se llega al `mov eax, ebx`, asi que **el cliente acepta CUALQUIER
    #   resolucion** — que es lo que pidio el usuario: "las mas comunes, como las que trae el
    #   launcher de prod".
    #   ⇒ Se prefiere esto antes que ampliar la lista blanca a mano (que fue mi primer intento,
    #     y solo daba DOS resoluciones): menos bytes, y no hay que elegir cuales son las buenas.
    #
    # ⛔⛔ LA TRAMPA QUE EL USUARIO ATAJO A TIEMPO ("ten cuidado no sea el exe del cbt"):
    #   la receta de `D:\R2Beatackups\cliente-2013-parchado-20260805` trae offsets FIJOS.
    #   Su exe pesa lo mismo que el nuestro —5.506.048— pero **no es el mismo build**: donde el
    #   suyo tiene `20 03` (=800), el nuestro tiene `00 83`. Escribir ahi habria metido basura en
    #   medio del codigo. No era el del CBT (esos pesan 3,5 MB) pero igual era otro binario.
    #   ⇒ Todo esto se ubico POR PATRON sobre nuestro pristino, anclado en el global 0x904094.
    #     Y el mismo localizador corrido sobre el exe del respaldo devuelve EXACTAMENTE los
    #     offsets que su receta documenta: esa es la prueba de que no adivina.
    #
    # ⏳ SIN TOCAR, a proposito: `0x49558C` hace `cmp [0x904094], 1024` + `sete cl`, o sea una
    #   BANDERA ("¿es la resolucion chica?"), no un recorte. La receta vieja la movia a 1600
    #   porque ese era su preset grande; con la lista blanca eliminada ya no hay un unico valor
    #   grande, y no se sabe que decide esa bandera. Se deja como viene.
    #   ⇒ Si en alta resolucion algo de la interfaz se ve raro, EL SOSPECHOSO ES ESE, y es un byte.
    (0x007BD0, bytes.fromhex("74"), bytes.fromhex("eb"),
     "★ VA 0x4087D0 · `je` -> `jmp`: se saltea el forzado del ANCHO"),
    (0x007BE8, bytes.fromhex("74"), bytes.fromhex("eb"),
     "★ VA 0x4087E8 · `je` -> `jmp`: se saltea el forzado del ALTO"),
    # ⛔⛔⛔ SACADOS EL 2026-09-06 — SUBIR LOS *DEFAULTS* NO ERA PARTE DEL ARREGLO
    #
    #   (0x007B43) ancho por defecto  800  -> 1920      (0x0E4A28/32) preset 1 -> 1920x1080
    #   (0x007B5D) alto  por defecto  600  -> 1080      (0x0E4A3E/48) preset 2 -> 1280x720
    #
    #   Síntoma: jugadores que actualizaron y no pueden abrir el juego — *"error al crear
    #   dispositivo de video"*, en hardware modesto o viejo.
    #
    #   ★★★ QUÉ ES EL "DEFAULT", MEDIDO EN `0x408742` — NO es "la resolución del juego":
    #         mov  ebx, 0x320                    ; 800
    #         push ebx                           ; <- el nDefault de GetPrivateProfileIntA
    #         push "WIDTH" / push "VIDEO"
    #         call GetPrivateProfileIntA
    #       Es **el valor que se usa cuando el `Config.ini` NO TIENE la clave** (o no existe).
    #       O sea que lo subimos a 1920x1080 para todo el que arranque sin configuración — y el
    #       propio juego **reescribe su `Config.ini` al salir y a veces pierde claves** (ya está
    #       documentado con `FULLSCREEN` en `VIDEO_Y_RESOLUCIONES.md` §7).
    #       ⇒ En una máquina cuyo escritorio no llega a 1920x1080 —y más con DXVK, que sólo
    #         enumera los modos del escritorio— eso es un `CreateDevice` que falla. El cliente lo
    #         registra como `CreateDevice FAIL` (`0x64A52A`) y muestra el cartel del video.
    #
    #   ★★ Y la receta VIEJA del 2013, la que anduvo meses, **no hacía esto**: dejaba los
    #      defaults en 1366x900 y ampliaba la lista blanca en vez de sacarla. Fuimos más lejos en
    #      lo que servía (sacar la lista) y también en lo que no hacía falta (mover los defaults).
    #
    #   ⇒ Se vuelven a los originales. **La libertad de resolución NO se pierde**: la dan los dos
    #     `je -> jmp` de arriba, que son los que borran la lista blanca. Cualquiera puede poner
    #     1920x1080 en su `Config.ini` o desde el launcher; lo que cambia es que **el que no
    #     configuró nada arranca en 800x600, que anda en cualquier máquina**.

    # ── EL BOTON DE RECARGA -> UN RICKROLL (2026-09-05, a pedido del usuario) ───────────────
    # La pagina de recarga de Softnyx esta HORNEADA en el exe. Este server no cobra nada, asi
    # que el boton no lleva a ningun lado util; se cambia por el video, de broma.
    #
    #   VA 0x87A17C  (file off 0x478D7C)  "https://billing.softnyx.com/body.asp"
    #
    # ⚠ ESTE OFFSET **NO** SALE DE `VA − 0x400C00`: la cadena vive en una seccion de DATOS, y
    #   ahi el delta es `0x401400`. La formula de la cabecera es la de `.text`. Se comprobo al
    #   reves: buscando `push 0x87A17C` (68 7C A1 87 00) aparecen **6 sitios de uso**, o sea
    #   que la VA es esa y una sola cadena cubre los seis botones.
    #
    # ★ COMO SE USA — desensamblado en `0x4D1BA0`, uno de los seis:
    #       push 1            ; nShowCmd = SW_SHOWNORMAL
    #       push 0            ; lpDirectory
    #       push 0x87a17c     ; lpParameters  <- LA URL
    #       push 0x87462c     ; lpFile        = "iexplore.exe"
    #       push 0x874624     ; lpOperation   = "open"
    #       push 0
    #       call [0x873338]   ; SHELL32!ShellExecuteA
    #   ⇒ la URL viaja como PARAMETRO de `iexplore.exe`, no como archivo. Cambiarla es cambiar
    #     la cadena y nada mas: no hay largo hardcodeado en ninguno de los seis sitios.
    #
    # ⚠⚠ EL LARGO MANDA. La cadena vieja mide 36 y despues tiene 4 NUL de relleno. La nueva
    #   **tiene que entrar en 36**, por eso va la forma corta `youtu.be` (28) y no
    #   `https://www.youtube.com/watch?v=…` (43), que no entraba. Se rellena con NUL hasta 36
    #   para no dejar cola de la vieja ("…body.asp" asomando despues del NUL).
    #   ⛔ Y por eso tampoco va el `?si=…` del link que paso el usuario: es un token de
    #     compartir, no hace falta para que el video abra, y sumaba 19 caracteres.
    #
    # ⏳ Lo que NO se toca y puede morder: sigue abriendo con **`iexplore.exe`**. En Windows 11
    #   eso redirige a Edge y el video abre igual, pero si algun dia no abre, el sospechoso es
    #   el `lpFile` (0x87462C), no la URL.
    (0x478D7C,
     b"https://billing.softnyx.com/body.asp",
     b"https://youtu.be/dQw4w9WgXcQ" + b"\x00" * 8,
     "★ VA 0x87A17C · la pagina de recarga de Softnyx -> Rick Astley (los 6 botones)"),

    # ★★★★★ EL CANDADO DE LA DIFICULTAD DE SALA — 2026-09-07. UN BYTE.
    #
    #   ⛔ EL SÍNTOMA, pedido por el usuario: el anfitrión con licencia alta **no puede subir la
    #     dificultad si hay alguien con licencia más baja sentado**. Sale el cartel
    #     *"El tipo de sala elegida no corresponde a los usuarios en la sala"* y el cambio no se
    #     aplica. Lo quiere al revés: **que el master mande hasta SU licencia**, sin importar quién
    #     esté en la sala.
    #
    #   ★ ES 100 % DEL CLIENTE. Lo confirma el log del server: cuando el cartel sale, **no llega
    #     ningún `FFC9`** — el cliente decide solo y ni pregunta. Por eso no hay ruta server-side y
    #     esta vez el exe sí es el lugar (ver la filosofía del proyecto: el exe se parchea último,
    #     pero se parchea cuando el candado vive ahí).
    #
    #   ★ CÓMO SE ENCONTRÓ, sin adivinar: el texto es la entrada **651** de `system.csv` (947
    #     entradas, ver `taller/re2013/strings_cliente.py`). En TODO el binario hay **un solo**
    #     `push 0x28B`, en `0x5956F0`. La función que lo contiene (`0x5955B0`) recorre a los
    #     ocupantes y hace:
    #
    #         005956B8  movzx edx, [ebx+0x0C]        ; la licencia de ESE ocupante
    #         005956C3  call  0x44F260               ; -> su banda máxima
    #         005956C8  cmp   [esi+0x132B5], al      ; ¿la banda ELEGIDA es mayor que la suya?
    #         005956CE  jbe   0x5956D5               ;   no -> este ocupante está bien
    #         005956D0  mov   ebp, 1                 ; ★ sí -> marca "hay alguien que no llega"
    #         …
    #         005956EC  test  ebp, ebp
    #         005956EE  je    0x59571F               ; nadie marcado -> APLICA el cambio
    #         005956F0  push  0x28B                  ; alguien marcado -> el cartel y se descarta
    #
    #     `ebp` es la bandera "alguien no llega". Con `jbe` -> `jmp` el `mov ebp, 1` **nunca se
    #     ejecuta**, la bandera queda en 0 y siempre se toma la rama que aplica el cambio.
    #
    #   ⚠ NO hace falta code cave: es un byte in-place y el salto ya iba justo al destino que
    #     queremos (`0x5956D5`, la continuación del bucle). No se mueve nada ni se agrega código.
    #
    #   ★ Y NO abre la mano de más — que es lo que el usuario pidió: **el techo del propio master
    #     lo pone OTRO candado distinto**, el de la lista de opciones del diálogo, que se dibuja
    #     con la licencia de uno y acá no se toca. Se ve en pantalla: cuando el usuario era Luna,
    #     "Novato Solar" y "Sol" salían con ☒ y seguían inalcanzables. Este parche saca sólo la
    #     condición sobre LOS DEMÁS.
    #
    #   ⏳ Lo que queda por ver en pantalla: qué le pasa al invitado de licencia baja cuando la
    #     sala queda por encima de la suya (¿lo deja jugar? ¿lo echa? ¿no ve las canciones?). El
    #     server no lo impide, pero el cliente del invitado puede tener su propia opinión.
    (0x194ACE, b"\x76", b"\xEB",
     "★★ VA 0x5956CE · el candado de la dificultad de sala: `jbe` -> `jmp`.\n"
     "     El master sube hasta SU licencia sin importar quién esté sentado."),

    # ═══════════════════════════════════════════════════════════════════════════════════════
    # ★★★ LA PRECISIÓN CON MILÉSIMAS — completo (2026-09-14). 1 cave + 6 desvíos.
    # ═══════════════════════════════════════════════════════════════════════════════════════
    # Lo genera `taller/_analisis/armar_cave_milesimas.py`, que calcula los saltos y **desensambla lo
    # que produce**. ⛔ No editar estos bytes a mano: un salto mal contado no falla al aplicarse,
    # falla en el cartel. Ya pasó en la primera versión (un `jae` un byte corto que caía en medio
    # de otra instrucción); lo cazó leer el desensamblado, no el generador.
    #
    # EL RECORRIDO, de punta a punta. El objetivo de anonimo03, textual: *"que el valor viaje como era
    # nativamente al server y a los users + decimales"*.
    #
    #   1. `cuenta` 0x4FF4E8 — el juego hace `aciertos/notas` y mete el resultado en UN BYTE, y
    #                          ahí se pierden los decimales. El cave rehace la misma cuenta con un
    #                          cero más y guarda las milésimas en `MIL_MIA`.
    #   2. `envio`  0x5C8330 — el armador del paquete de 62 B las mete en los bytes 46..47.
    #        ── el server las lee, y se las reparte a TODOS en un renglón de bonus 0xFF01 ──
    #   3. `red`    0x5E8EC7 — donde la fila del cartel LLEGA entera: saca el renglón y lo anota
    #                          en `TABLA`, por asiento.
    #   4. `calc` + `stubA`/`stubB` (0x5374FA / 0x537802) — marcan `PEND` justo antes de dibujar.
    #   5. `dibujo` 0x53394E — si hay marca, escribe `.NNN` debajo del número.
    #
    # POR QUÉ TANTOS ENGANCHES Y NO UNO: el objeto que llega al DIBUJADO **no es** la estructura
    # de red. Mide 168 B y sólo trae escalares y dos strings (medido — ver
    # `documentacion/RBIT_DECIMALES_DE_PRECISION.md` §9). Las milésimas viajan en un renglón de
    # bonus, y ese renglón NO sobrevive. Así que hay que agarrarlas donde llegan y anotarlas.
    # ⚠ Los cinco escalares que sí sobreviven (`pos`, `rank_bonus`, `exp`, `pd`, `star`) se
    #   dibujan todos: ninguno se podía secuestrar para llevarlas de contrabando.
    #
    # ★★ EL CAMBIO DE DISEÑO DEL 14-sep, y por qué la versión anterior estaba mal.
    #   Antes `calc` devolvía `pd*1000 + milésimas` y el dibujador partía el número inflado,
    #   reconociendo la casilla **por su forma** (18x21, tira 0x28). Leyendo los dos sitios de
    #   dibujo aparecieron dos agujeros, los dos medidos:
    #     ⛔ la ESTRELLA se dibuja con la forma IDÉNTICA a la precisión (`0x537516`, justo tres
    #        instrucciones después): ningún filtro por forma las separa. Sólo las separaba un
    #        "valor >= 1000", que se cae solo si a alguien le sale 0% con decimales.
    #     ⛔ y las filas de LOS DEMÁS usan otra medida (17x18, tira 0x1E): el filtro por forma
    #        jamás les habría puesto los decimales — o sea que se perdía justo la mitad que a
    #        anonimo03 le importa, *"que todos reciban lo real de los demás"*.
    #   ⇒ Ahora la marca la pone el propio sitio de la precisión, que es el único que sabe que lo
    #     es, y el dibujador sólo pregunta si está puesta. No hay nada que adivinar.
    #   ★ Y de yapa: el número que el cartel dibuja **ya no se toca**. Antes se lo inflaba a
    #     `93789`; ahora se deja igual y sólo se agrega una línea debajo. Si algo fallara, lo peor
    #     que puede pasar es que no aparezcan los decimales.
    (0x000290, bytes.fromhex("682a1100"), bytes.fromhex("002c1100"),
     "★★ Encabezado de `.data`: VirtualSize 0x112A68 -> 0x112C00 (termina en 0xA16C00).\n"
     "     ⛔⛔ LA LECCIÓN CARA DEL 13-sep: `.text` es **R-X, no se puede escribir**. La primera\n"
     "     versión del cave guardaba su tabla adentro del propio cave, o sea en `.text`: la LEÍA\n"
     "     bien, pero al ESCRIBIRLA el cliente se moría — y escribe justo cuando llega el paquete\n"
     "     del cartel, o sea **al cruzar la meta**. Dos clientes muertos, síntoma exacto.\n"
     "     ⇒ La tabla se mudó a `.data` (RW), al hueco del final de la sección: 1.432 bytes que\n"
     "       no están declarados por nadie. Esto lo mete formalmente adentro, igual que el parche\n"
     "       0x000240 hace con `.text` para el cave del impulsor.\n"
     "     ⚠ La tabla NO ocupa bytes de archivo: vive más allá del SizeOfRawData, en la parte que\n"
     "       el cargador rellena con ceros. Por eso acá sólo se toca el encabezado."),

    (0x3E5495, b"\xCC" * 662,
     bytes.fromhex("500fb60683e0070fb70445806aa1000d00000100a3946aa100580fb64e08c3e8"
                   "dcffffff8b442438e94014d5ffe8ceffffff810d946aa100000002008b442438"
                   "e93017d5ff505652538b7424140fb60683e00733d28b5e303b5e340f831c0000"
                   "0066813b01ff0f85090000000fb75302e90800000083c304e9dbffffff668914"
                   "45806aa1005b5a5e58e9cd8ed0ff8b869c01000033c2505152bae8030000f7e2"
                   "3bd10f8310000000f7f133d2b9e8030000f7f1e90200000033d2668915906aa1"
                   "005a5958e99293d1ff50668b05906aa10066894610586a0c8d560ee9c021deff"
                   "60a1946aa10085c00f8439010000c705946aa10000000000b9e3627e00bab06a"
                   "a100a9000002000f840a000000b907637e00bae06aa1005033c08b1c81031c82"
                   "891c85106ba1004083f8090f82e9ffffff580fb7c033d2b964000000f7f1a298"
                   "6aa1008bc233d2b90a000000f7f1a2996aa10088159a6aa1008b54244c83ea10"
                   "0315186ba100295424448b5c244883eb04031d1c6ba1008bc30305306ba100a3"
                   "a06aa1008b7c244c83ef06033d206ba1008b7424408b44244883e8052bf00335"
                   "106ba1008b6c2444036c244c83c502032d146ba1000fb605986aa1008b542454"
                   "8bcee86b0000000fb605996aa1008b5424548b0da06aa10003cee8530000000f"
                   "b6059a6aa1008b5424548b0da06aa10003c903cee83900000003ef8bce2b0da0"
                   "6aa100030d246ba100bb04000000031d2c6ba1008bfb2beba1286ba1008d5022"
                   "33c0e80b000000618b4c243053e98cd6d4ffff742460ff742460525057535551"
                   "ff7424608b4c2440e85ed6d4ffc3020000000000000002000000000000000000"
                   "0000020000000000000002000000feffffff00000000feffffff040000000000"
                   "000000000000040000000000000002000000feffffff"),
     "★★★ VA 0x7E6095 .. 0x7E632B · EL CODE CAVE DE LAS MILÉSIMAS (662 B de 3.947).\n"
     "     0x7E6095  calc    deja PEND = tabla[asiento] | marca, y ecx = la precisión SIN tocar\n"
     "     0x7E60B4  stubA   «tu fila»        0x7E60C2  stubB   «las de los demás»\n"
     "     0x7E60D0  red     saca las milésimas del renglón de bonus 0xFF01 y las anota.\n"
     "                       Termina con `jmp 0x4EEFF0` (tail-call): la pila queda igual.\n"
     "     0x7E6119  cuenta  rehace `aciertos/notas` con un cero más -> MIL_MIA\n"
     "     0x7E6154  envio   MIL_MIA -> bytes 46..47 del paquete C→S\n"
     "     0x7E616B  dibujo  si hay marca, escribe `.NNN` debajo del número\n"
     "     ★ LOS DATOS viven en 0xA16A80..0xA16AA0, en `.data`, NO acá (TABLA, MIL_MIA, PEND,\n"
     "       BUF). Ver el parche de 0x000290 y la lección del 13-sep."),

    (0x0FE8E8, bytes.fromhex("8b869c010000"), bytes.fromhex("e9366c2e0090"),
     "★★ VA 0x4FF4E8 · `mov eax,[esi+0x19c]` -> `jmp cuenta`. LA CUENTA DE LA PRECISIÓN.\n"
     "     Diez bytes más adelante está el `div ecx` donde el juego tira los decimales:\n"
     "         004ff4da  mov ecx,[esi+0x1a0] / xor ecx,edx    ; denominador, descifrado\n"
     "         004ff4e8  mov eax,[esi+0x19c] / xor eax,edx    ; numerador,  descifrado\n"
     "         004ff4f2  div ecx                              ; ★ acá se pierden\n"
     "     El cave rehace la cuenta con un cero más y vuelve a 0x4FF4F0 (el `xor eax,edx` ya lo\n"
     "     hizo él). ⚠ Se desplazan 6 bytes: el `jmp` usa 5 y el sexto queda en `nop`.\n"
     "     ★ Comprobado en vivo antes de escribir un solo byte: 25886/276 = 93.789."),

    (0x1C7730, bytes.fromhex("6a0c8d560e"), bytes.fromhex("e929de2100"),
     "★★ VA 0x5C8330 · `push 0xc / lea edx,[esi+0xe]` -> `jmp envio`. EL ARMADOR DEL PAQUETE.\n"
     "     `0x5C8180` es el SendGameOver del 2013 y escribe los 62 bytes de a pedazos con\n"
     "     `0x5F7080(flujo, puntero, cuántos)`. El bloque de 12 sale de [esi+0x0e] y cae en los\n"
     "     bytes 44..55 ⇒ **[esi+0x10] es el byte 46**, el hueco que medimos libre en 16.624\n"
     "     paquetes reales de prod. Mapa completo en `documentacion/PLAN_DECIMALES.md` §3.\n"
     "     ★ El md5 anti-trampa se calcula ANTES (0x5C827C) y sólo cubre\n"
     "       frame/combo/precisión/estrella/rcoin ⇒ escribir acá NO lo rompe.\n"
     "     ★ Y es el embudo único: los 5 sitios que mandan reporte pasan todos por 0x5C8180."),

    (0x1E82C7, bytes.fromhex("e82461f0ff"), bytes.fromhex("e80ed21f00"),
     "★★ VA 0x5E8EC7 · `call 0x4EEFF0` -> `call red`. EL EMBUDO DE RED.\n"
     "     Es el único punto donde la fila del cartel está ENTERA (handler del FF28, 0x5E8C40).\n"
     "     ⚠ El cave termina saltando al 0x4EEFF0 original, así que esto NO saltea nada."),

    (0x1368FA, bytes.fromhex("0fb64e088b442438"), bytes.fromhex("e9b5eb2a00909090"),
     "★★ VA 0x5374FA · «el dibujado de TU fila»: `movzx ecx,[esi+8]` -> `jmp stubA`.\n"
     "     Se desplazan DOS instrucciones (8 B) porque un jmp necesita 5 y el movzx sólo da 4.\n"
     "     El stub las vuelve a ejecutar y salta a 0x537502."),

    (0x136C02, bytes.fromhex("0fb64e088b442438"), bytes.fromhex("e9bbe82a00909090"),
     "★★ VA 0x537802 · «el dibujado de LOS DEMÁS»: igual que el anterior, vuelve a 0x53780A.\n"
     "     ⚠ Esta fila NO se dibuja con la misma medida que la tuya: es de 17x18 con la tira\n"
     "       0x1E, contra 18x21 y tira 0x28. Por eso el dibujado NO puede reconocer la casilla\n"
     "       por su forma, y por eso existe la marca `PEND`."),

    (0x132D4E, bytes.fromhex("8b4c243053"), bytes.fromhex("e922282b00"),
     "★★ VA 0x53394E · `mov ecx,[esp+0x30] / push ebx` -> `jmp dibujo`. EL DIBUJADOR.\n"
     "     `0x533940(sprite, x, y, ancho, alto, VALOR, tira, ...)` dibuja CADA número del cartel\n"
     "     con figuritas, vía `_itoa`. El cave se cuelga del principio, pregunta si `calc` dejó\n"
     "     la marca y, si está, escribe `.NNN` debajo con el dibujador de TEXTO del propio juego\n"
     "     (`0x63A640`, el mismo que pinta el apodo) — que es de donde sale el punto, porque\n"
     "     figurita de punto NO hay: en `gr_music_02_02.spr` el corte 38 es un círculo amarillo.\n"
     "     ⚠ Corre para cada número de cada fila. Lo primero que hace es comparar contra cero.\n"
     "     ⚠ `0x63A640` es cdecl y VARIÁDICA: limpia el que llama (`add esp,0x1C`). Tratarla\n"
     "       como stdcall descuadra la pila y el cliente se cae a los pocos cuadros."),

    # ═══════════════════════════════════════════════════════════════════════════════════════════
    # ★★★ «PD VALOFE» — la tabla de puntaje del cliente moderno, prendible por sala (2026-09-14)
    # ═══════════════════════════════════════════════════════════════════════════════════════════
    #   Generado por `taller/_analisis/armar_cave_pd_valofe.py`. Ahí está el porqué de cada pieza.
    #
    #   ⚠⚠ NO ES UN ARREGLO: ES UNA REGLA DE JUEGO DISTINTA. Cada nota vale un escalón más
    #     (+10, con techo en 99). El número de precisión SUBE. Por eso lo decide LA SALA entera
    #     con `.pd on/off` y no cada jugador: si no, los números de dos jugadores no se pueden
    #     comparar y el cartel del final compara peras con manzanas.
    #     El análisis completo, incluida la escala del 2013 leída del binario, está en
    #     `documentacion/TOOLBIT_PD_VALOFE.md`.
    (0x3E5730, b"\xCC" * 128,
     bytes.fromhex("c605406ba10000606a0168406ba1008b8c2464000000e8b56ee9ff618b442418"
                   "8b0de4149300e9f046e0ff803d406ba100000f841a00000085c00f8412000000"
                   "83f85a0f830400000083c00ac3b863000000c38d048003c0e8ceffffffe9baf0"
                   "d1ff8d048003c0e8bfffffffe9eaf0d1ff8d048003c0e8b0ffffffe95aa7d6ff"),
     "★★★ EL CAVE DE LA «PD VALOFE» — 128 B, en 0x7E6330 (el mismo hueco de las milésimas,\n"
     "     que terminaba en 0x7E632B; quedan ~3.150 B libres después de éste).\n"
     "     5 piezas: `perilla` (lee el byte del server) · `ajuste` (la cuenta) · 3 sitios del ×10."),

    (0x1E9E41, bytes.fromhex("8b4424188b0de4149300"), bytes.fromhex("e9eab81f009090909090"),
     "★★ VA 0x5EAA41 · el final del handler del LOADGAME (FF25) -> `jmp perilla`.\n"
     "     Acá el handler ya terminó de leer magic/mapa/canciones, así que el cave pide UN BYTE\n"
     "     MÁS del flujo: la perilla que manda el server.\n"
     "     ★ Por qué un byte pegado al final y no un campo nuevo: el lector del cliente\n"
     "       (`0x67D200`) devuelve 0 y **no toca el destino** si no alcanzan los bytes. ⇒ el\n"
     "       server puede subir SOLO: cliente viejo ignora el byte, y cliente nuevo con server\n"
     "       viejo lee el 0 que el propio cave puso una línea antes = apagado.\n"
     "     ⚠ Se desplazan DOS instrucciones (10 B) porque el `mov eax,[esp+0x18]` sólo da 4."),

    (0x104847, bytes.fromhex("8d048003c0"), bytes.fromhex("e9370f2e00"),
     "★★ VA 0x505447 · `lea eax,[eax+eax*4] / add eax,eax` -> `jmp sitio1`. EL ×10.\n"
     "     Por cada nota el juego hace `eax = (10 - |desvío|) * 10` y lo suma al NUMERADOR de\n"
     "     la precisión (`[esi+0x19c]`, el mismo que leen las milésimas). El desvío 0 no pasa\n"
     "     por acá: vale 99 fijo (`lea eax,[edi+0x63]` en 0x505432), y 99 ya es el techo.\n"
     "     ★ Mide EXACTAMENTE 5 bytes, que es lo que ocupa un jmp: no se parte nada."),

    (0x104886, bytes.fromhex("8d048003c0"), bytes.fromhex("e9070f2e00"),
     "★★ VA 0x505486 · el mismo ×10 del acumulador de al lado (`[esi+0x260]`), 57 bytes\n"
     "     después. Va con el primero: son la misma cuenta sobre dos contadores paralelos."),

    (0x14FF05, bytes.fromhex("8d048003c0"), bytes.fromhex("e997582900"),
     "★★ VA 0x550B05 · el ×10 del número que se ve EN PANTALLA durante la carrera\n"
     "     (`mov byte [esi+0x9e1], al`, con su propio techo en 0x63 tres instrucciones después).\n"
     "     ⚠ Sin esto el número de la carrera y el del cartel final NO coincidirían."),

    # ═══════════════════════════════════════════════════════════════════════════════════════════
    # ★★★★★ EL ÍCONO DE LICENCIA DE LA LISTA DE SALAS — 2026-09-17
    # ═══════════════════════════════════════════════════════════════════════════════════════════
    # Pedido de anonimo03, sostenido tres sesiones: *"las salas deberían listarse para todos, sin
    # importar nivel ni licencia, y deberían salir con el ícono correcto del que creó la sala"*.
    # Y su objetivo final, dicho desde el principio: *"luego lo modificaremos a nuestro antojo
    # para que de todas formas puedan entrar a cualquier sala de X licencia"*.
    #
    # ⛔ POR QUÉ NO SE PUDO SERVER-SIDE, en una línea: el ícono y el candado **son el mismo byte**
    #   (el `L` de la fila del `FF6E`), y el candado compara contra la licencia del jugador, que el
    #   cliente se calcula solo. Se agotó la vía nativa y quedó medido por qué:
    #   **el login sólo sabe pronunciar 2 de las 5 licencias** (los requisitos `0x0F01/02/04` de
    #   estrella, luna y sol piden dos nibbles a la vez, y el bucle otorga de a uno).
    #   ⇒ Al intentarlo, a un jugador de LUNA el cliente le mostraba «novato sol» y lo mandaba a
    #     ese canal: `0x4863C0` no es «la licencia de la lista», es la licencia del jugador, y la
    #     consultan 20+ sitios. Se revirtió. Todo el hilo está en
    #     `documentacion/LICENCIA_DE_SALA_Y_SU_ICONO.md` §5-ter.
    #
    # ★★ ESTOS TRES PARCHES NO TOCAN `0x484A00` NI `0x4863C0`: la licencia del jugador queda
    #   intacta, y con ella su info, su canal y el gate de ingreso. Sólo se neutralizan los tres
    #   RECHAZOS, uno por uno. Es lo que hace que sea el camino que menos toca al jugador.
    # ★ Los tres offsets verificados en los tres exes (`.pristino`, `_local`, el vivo): mismos
    #   bytes, sin rebase.
    (0x09D85F, bytes.fromhex("0f84ac010000"), bytes.fromhex("909090909090"),
     "★★★★★ VA 0x49E45F · ALTA DE FILA: el `je` que salta el alta cuando `0x484A00` dice que no.\n"
     "     Seis NOPs ⇒ la sala se agrega SIEMPRE, con su `L` real ⇒ se dibuja el ícono.\n"
     "     ⚠ Mide 6 bytes porque es un `je` largo (`0F 84`); no se parte nada."),
    (0x09CFE7, bytes.fromhex("7525"), bytes.fromhex("eb25"),
     "★★★★ VA 0x49DBE7 · UPDATE DE FILA: el mismo rechazo en el camino del refresco.\n"
     "     Sin éste la sala aparece y desaparece al refrescar la lista."),
    (0x0A78C5, bytes.fromhex("7526"), bytes.fromhex("eb26"),
     "★★★ VA 0x4A84C5 · CLICK DE ENTRAR: `jne` -> `jmp`, se saltea el `push 0x54` = popup 84\n"
     "     «Su nivel no es adecuado para esta sala.»\n"
     "     ⇒ ESTE ES EL QUE DECIDE QUE CUALQUIERA PUEDA ENTRAR A CUALQUIER SALA. anonimo03 lo pidió\n"
     "       explícitamente: *«7 bytes, aceptar que cualquiera entre a cualquier sala»*.\n"
     "     ⚠ Es el único de los tres que cambia una REGLA DE JUEGO, no un dibujo. Si algún día se\n"
     "       quiere el candado de vuelta, se saca éste y los otros dos siguen dando el ícono:\n"
     "       son independientes a propósito."),

    # ═══════════════════════════════════════════════════════════════════════════════════════════
    # ★★★★ EL MENÚ DE RESOLUCIÓN CON TRES OPCIONES — 2026-09-29
    # ═══════════════════════════════════════════════════════════════════════════════════════════
    # anonimo03: *"el cliente moderno ofrece 3 resoluciones ... dentro del juego sólo ofrece 2"*.
    # El menú (Opción -> Gráfico -> Resolución) estaba escrito en el exe en CUATRO lugares, cada uno
    # con un «si es 0 ... si no ...». Los cuatro pasan a leer UNA tabla (la última entrada), y entran
    # en el lugar del código viejo: sin cave nuevo y sin DLL. El dibujo con el 3er botón va en
    # `R2Beat/rnr_ui_resolucion.pak` (pak NUEVO, tapa a `rnr_ui_LT006.pak`).
    # ⛔ ESTOS BYTES NO SE EDITAN A MANO: los arma `herramientas/menu_resolucion.py` (la x de cada
    #   puntito sale de dónde quedó cada círculo en el dibujo). `--control` avisa si quedaron viejos.
    # ★ De paso: «NINGUNA MARCADA». Con una resolución que no está en la tabla (el launcher deja
    #   cualquiera) no se dibuja el puntito y el OK NO la cambia; antes la bajaba a 800x600.
    # Doc: `documentacion/MENU_RESOLUCION.md`.
    (0x0E3F5C, bytes.fromhex("8b0d981493008b41043d20030000750cc787ac0c000000000000eb113d00040000750ac787ac0c000001000000"),
     bytes.fromhex("8b0d981493008b41048b490831d23b04d55854830075093b0cd55c54830074064283fa0372e88997ac0c000090"),
     "★★ VA 0x4E4B5C · menú de resolución, ABRIR: marca la fila con el ancho Y el alto de la pantalla\n"
     "     (o ninguna = N). Antes: 800 -> 0, 1024 -> 1, y cualquier otra dejaba el índice como estaba."),
    (0x0E1D83, bytes.fromhex("83beac0c0000006a006a05751b8b86f40c00008b8ef00c000005ad0000005081c15301000051eb198b96f40c00008b86f00c000081c2ad0000005205d201000050"),
     bytes.fromhex("8b86ac0c000083f803733e6a006a058b96f40c000081c2ad000000528b8ef00c0000030cc54054830051eb15909090909090909090909090909090909090909090"),
     "★★ VA 0x4E2983 · menú de resolución, DIBUJAR: el puntito en la x de la fila (nada si es «ninguna»)."),
    (0x0E2E62, bytes.fromhex("8b86f00c00008d88530100003bcb7f2e8d88c90100003bd97f248b8ef40c00008d91aa0000003bd77f1481c1c80000003bf97f0ac786ac0c0000000000008d90d20100003bd3557f2e8d883e0200003bd97f248b8ef40c00008da9aa0000003bef7f1481c1c80000003bf97f0ac786ac0c000001000000"),
     bytes.fromhex("8b86f00c0000558b8ef40c00008d91aa00000039fa7f3081c1c800000039cf7f2689d929c131d23b0cd5405483007c113b0cd5445483007f088996ac0c0000eb064283fa0372e08d90d2010000eb2890909090909090909090909090909090909090909090909090909090909090909090909090909090"),
     "★★ VA 0x4E3A62 · menú de resolución, CLIC: la fila cuya zona contiene al mouse (misma franja\n"
     "     de alto). ⚠ deja `push ebp`, eax = [esi+0xcf0] y edx = eax+0x1d2: el código de después los usa."),
    (0x0E4A19, bytes.fromhex("83beac0c0000007516c7059440900020030000c7059840900058020000eb14c7059440900000040000c7059840900000030000"),
     bytes.fromhex("8b86ac0c000083f80373288b0cc558548300890d944090008b0cc55c548300890d98409000eb0c909090909090909090909090"),
     "★★ VA 0x4E5619 · menú de resolución, OK: la fila -> ancho y alto (0x904094/0x904098).\n"
     "     Con «ninguna» NO toca la resolución (antes la bajaba a 800x600)."),
    (0x434840, bytes.fromhex("cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"),
     bytes.fromhex("530100009c010000ae010000f7010000090200004a020000200300005802000000040000000300008007000038040000"),
     "★★ VA 0x835440 · menú de resolución, LA TABLA (48 B): {x del puntito, fin del clic} ×3\n"
     "     y después {ancho, alto} ×3. Una opción más = una fila más (y un dibujo más en el pak)."),

    # ═══════════════════════════════════════════════════════════════════════════════════════════
    # ★★★★ «MI RECORD» DEL PICKER CON DECIMALES (94.354) — 2026-09-29
    # ═══════════════════════════════════════════════════════════════════════════════════════════
    # anonimo03, con su edición en Paint: *«592 Combo 94.354 %»*, todo en la misma fila. El número es un
    # `TextNumImg` que dibuja un TEXTO con figuritas; el cliente le ponía `SetValue(int)` (itoa). Ahora:
    #   · el server manda las milésimas en 2 B AL FINAL del FF139 (el lector no toca el destino si no
    #     alcanzan: server viejo = centinela 0xFFFF = el entero de siempre; cliente viejo las ignora);
    #   · viajan en la mitad alta del pd hasta el handler, que arma «94.354» y llama SetText.
    #   El dibujo (la tira de cifras al 75 % con el punto, el fondo con «Combo» corrido y el .rui) va en
    #   `R2Beat/rnr_ui_record.pak`. ⛔ Estos bytes los arma `herramientas/record_decimales.py`.
    # Doc: `documentacion/RECORD_DECIMALES.md`.
    (0x1DBA6A, bytes.fromhex("8b4c240c8b542410"),
     bytes.fromhex("e9018e2500909090"),
     "★★ VA 0x5DC66A · «Mi record» con decimales: el lector del FF139, tras su último campo -> CUEVA_RED\n"
     "     (reemplaza `mov ecx,[esp+0xc]` + `mov edx,[esp+0x10]`, que la cueva repite)"),
    (0x1DBAB7, bytes.fromhex("0fb74c240c"),
     bytes.fromhex("8b4c240c90"),
     "★★ VA 0x5DC6B7 · «Mi record» con decimales: `movzx ecx,word [esp+0xc]` -> `mov ecx,dword`: el pd\n"
     "     viaja al handler con las milésimas en la mitad alta (0xFFFF = no vinieron)"),
    (0x1B90B5, bytes.fromhex("8b8edc0200008b118b4424108b523c50ffd2"),
     bytes.fromhex("e9e6b7270090909090909090909090909090"),
     "★★ VA 0x5B9CB5 · «Mi record» con decimales: el SetValue del pd (TextNumImg_Acc) -> CUEVA_TXT\n"
     "     (reemplaza el tramo entero hasta el call, 18 B)"),
    (0x434870, bytes.fromhex("cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"),
     bytes.fromhex("66c7442406ffff6a028d44240a5089f1e87b7de4ff8b4c240c8b542410e9e071daffcccccccccccccccccccccccccccc8b8edc0200008b442410500fb7c08b1150ff523c5889c2c1ea1081fae7030000776f0fb7c083f86473675383ec0889e383f80a721a5231d2b90a000000f7f10430880380c2308853015a83c302eb050430880343c6032e89d031d2b964000000f7f1043088430189d031d2b90a000000f7f1043088430280c230885303c64304008b8edc0200008b1154ff524883c4085be99147d8ff"),
     "★★ VA 0x835470 · «Mi record» con decimales: las 2 CUEVAS (198 B) — CUEVA_RED lee 2 B\n"
     "     más del FF139 (centinela 0xFFFF) y CUEVA_TXT (0x8354A0) arma «94.354» en la PILA y llama\n"
     "     SetText (vtable +0x48). Sin milésimas o con 100: SetValue(pd) como siempre. No escribe en .text."),

    # ═══════════════════════════════════════════════════════════════════════════════════════════
    # ★★ LAS LICENCIAS «NOVATO SOL» Y «SOL» DESDE EL NIVEL 50 — 2026-09-29
    # ═══════════════════════════════════════════════════════════════════════════════════════════
    # anonimo03: *"que se puedan hacer ambas desde el nivel 50, sin quitarle sus otros requisitos"*.
    # El nivel de cada misión NO está en ningún script: lo hornea el constructor de la lista
    # (`0x492990`), un `call 0x48CC10` por misión con `push requisito / push capítulo / push NIVEL`,
    # y queda en `+0x04` del registro. Es el `%d` del cartel «Condiciones del Reto» ("carreras de
    # nivel %d o superior"), así que el texto cambia solo. La otra condición (la licencia anterior
    # completada) sale de la cadena de misiones, no de este byte: no se toca.
    #   Novato Sol = requisito 0x0100, capítulo 5, nivel 60 · Sol = 0x0F04, capítulo 6, nivel 70.
    # Doc: `documentacion/mapeo_misiones.md` §11.
    (0x0925BD, bytes.fromhex("6a3c"), bytes.fromhex("6a32"),
     "★★ VA 0x4931BD · misión «Licencia Canal Novato Sol» (0x0100): nivel requerido 60 -> 50 (`push 0x32`)"),
    (0x09262E, bytes.fromhex("6a46"), bytes.fromhex("6a32"),
     "★★ VA 0x49322E · misión «LICENCIA Sol» (0x0F04): nivel requerido 70 -> 50 (`push 0x32`)"),

]


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# ★★★ EL REGISTRO DE CODE CAVES — 2026-09-13
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# Pedido de anonimo03, textual: *"tenemos que tener cuidado documentando los parches, para evitar
# pisar uno más adelante por accidente"*.
#
# ⛔ EL PELIGRO, y por qué no alcanza con la lista de arriba: un code cave es **relleno**. Está
#   lleno de `CC` y desde afuera se ve idéntico a cualquier otro relleno libre. El día que alguien
#   busque "un hueco donde meter código" va a encontrar el nuestro y va a escribir encima — y el
#   parche pisado **no falla al aplicarse**: falla en el juego, meses después, y lejos.
#   La verificación `antes == prístino` NO protege de esto: los dos parches verifican bien contra
#   el prístino, porque los dos escriben sobre `CC`.
#
# ⇒ Acá se RESERVA cada tramo con dueño. `revisar_choques()` corre en cada aplicación y aborta
#   si dos parches se superponen o si alguno escribe en un cave ajeno.
#
# Los huecos libres de `.text` (rachas de `CC` de 48 bytes o más), medidos sobre el prístino:
#       0x7E5095   3.947 B      0x7E6095   3.947 B      0x835435   3.019 B
#       0x7EE47B   2.949 B      0x7E7676   2.442 B      0x7E4C87     889 B
#   ⚠ Y el tramo final `0x8726EE..0x872800` (274 B) **NO estaba dentro del VirtualSize** de la
#     sección: por eso el parche de `0x000240` lo agranda. Cualquier cave DENTRO de los tramos de
#     arriba no necesita tocar la cabecera.
# ⚠ El dueño se identifica por el **offset de archivo de su parche**, no por su texto. Atar dos
#   cosas por un texto que alguien va a reescribir es atarlas con hilo: la primera versión de esto
#   comparaba descripciones y daba falsa alarma en el primer intento.
CAVES = [
    # (va_inicio, va_fin_exclusivo, offset_del_parche_dueño, para qué es)
    (0x8726EE, 0x872800, 0x471AEE, "el sonido del impulsor — LLENO: 273 de 274 B"),
    (0x7E6095, 0x7E632B, 0x3E5495, "las MILÉSIMAS de la precisión — 662 B usados de 3.947. "
                                   "Queda libre 0x7E632B..0x7E7000 del mismo hueco."),
    # ⚠ Éste NO es un code cave de `.text`: son los DATOS del cave de arriba, y viven en
    #   `.data` porque el cave los ESCRIBE. Se anotan igual para que nadie los pise.
    (0x7E6330, 0x7E63B0, 0x3E5730, "la «PD VALOFE» — 128 B del MISMO hueco, pegados al cave de "
                                   "las milésimas. Quedan libres 0x7E63B0..0x7E7000."),
    (0xA16B40, 0xA16B41, 0x3E5730, "la perilla de la «PD VALOFE» — 1 byte en .data, RW. "
                                   "0 = tabla del 2013 · 1 = tabla Valofe. La escribe `perilla` "
                                   "con lo que manda el server en el LOADGAME."),
    (0xA16A80, 0xA16B34, 0x000290, "los datos de las milésimas — en .data, RW: "
                                   "TABLA 0xA16A80 (8 asientos x u16) · MIL_MIA 0xA16A90 (u16) · "
                                   "PEND 0xA16A94 (u32) · BUF 0xA16A98 (8 B) · dos bloques de 8 perillas: "
                                   "la fila propia en 0xA16AB0 y la ajena en 0xA16AE0"),
    (0x835440, 0x835470, 0x434840, "la TABLA del menú de resolución — 48 B: {x, fin del clic} ×3 y "
                                   "{ancho, alto} ×3. La leen 0x4E4B5C/0x4E2983/0x4E3A62/0x4E5619. "
                                   "Queda libre 0x835470..0x836000 del mismo hueco."),
    (0x835470, 0x835536, 0x434870, "las 2 CUEVAS de «Mi record» con decimales — CUEVA_RED (lee 2 B más "
                                   "del FF139) y CUEVA_TXT 0x8354A0 (arma «94.354» y llama SetText). "
                                   "Queda libre 0x835536..0x836000."),
]


def _va(off):
    """VA desde el offset de archivo. ⚠ Sólo vale para `.text`; los parches de datos (la IP, la
    URL de recarga) usan otro mapeo y por eso quedan fuera de la comprobación de caves."""
    return off + 0x400C00


def revisar_choques():
    """Aborta si dos parches se pisan, o si uno escribe dentro de un cave que no es suyo."""
    tramos = []
    for off, antes, _d, desc in PARCHES:
        tramos.append((off, off + len(antes), desc.splitlines()[0][:60]))
    tramos.sort()
    for (a1, b1, d1), (a2, b2, d2) in zip(tramos, tramos[1:]):
        if a2 < b1:
            sys.exit(f"⛔⛔ DOS PARCHES SE PISAN:\n"
                     f"   0x{a1:06X}..0x{b1:06X}  {d1}\n"
                     f"   0x{a2:06X}..0x{b2:06X}  {d2}\n"
                     "   Uno de los dos va a quedar a medias. No aplico nada.")
    # ★ Y que nadie escriba en un cave ajeno. Se compara por VA, que es como están declarados.
    for off, antes, _d, desc in PARCHES:
        va0, va1 = _va(off), _va(off + len(antes))
        for c0, c1, dueño_off, para_que in CAVES:
            if va0 < c1 and c0 < va1 and off != dueño_off:
                sys.exit(f"⛔⛔ EL PARCHE DE VA 0x{va0:06X} ESCRIBE EN UN CAVE AJENO\n"
                         f"   cave 0x{c0:06X}..0x{c1:06X} — es de 0x{dueño_off:06X} ({para_que})\n"
                         f"   parche intruso: {desc.splitlines()[0][:70]}\n"
                         "   Si de verdad querés compartir ese cave, anotalo en CAVES primero.")
    # ★ Y al revés: un cave reservado cuyo dueño ya no existe es una reserva fantasma que va a
    #   bloquear a otro sin razón. Se avisa.
    _offs = {o for o, *_ in PARCHES}
    for c0, c1, dueño_off, para_que in CAVES:
        if dueño_off not in _offs:
            print(f"  ⚠ el cave 0x{c0:06X}..0x{c1:06X} dice ser de 0x{dueño_off:06X}, "
                  f"que YA NO ESTÁ en la lista de parches ({para_que}). ¿Reserva vieja?")
    print(f"★ sin choques: {len(PARCHES)} parches · {len(CAVES)} cave(s) reservado(s)")


def mapa():
    """El mapa completo, para mirar antes de elegir dónde meter un parche nuevo."""
    print("\n══ PARCHES ══")
    print("  file_off    VA          bytes  qué es")
    for off, antes, _d, desc in sorted(PARCHES):
        print(f"  0x{off:06X}  0x{_va(off):06X}  {len(antes):6d}  {desc.splitlines()[0][:66]}")
    print("\n══ CODE CAVES RESERVADOS ══  (⛔ no meter nada acá sin cambiarle el dueño)")
    for c0, c1, dueño_off, para_que in CAVES:
        print(f"  0x{c0:06X}..0x{c1:06X}  ({c1 - c0:4d} B)  de 0x{dueño_off:06X} · {para_que}")
    print("\n══ HUECOS LIBRES conocidos de .text ══  (rachas de CC en el prístino)")
    for va, n in ((0x7E5095, 3947), (0x7E6095, 3947), (0x835435, 3019),
                  (0x7EE47B, 2949), (0x7E7676, 2442), (0x7E4C87, 889)):
        _usado = sum(min(c1, va + n) - max(c0, va) for c0, c1, _o, _p in CAVES
                     if va < c1 and c0 < va + n)
        print(f"  0x{va:06X}  {n:5d} B" +
              (f"   ⚠ {_usado} B ya reservados -> quedan {n - _usado}" if _usado else "   libre"))
    print()


def md5(b):
    return hashlib.md5(b).hexdigest()
