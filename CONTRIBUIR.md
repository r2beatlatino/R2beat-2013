# Contribuir

Gracias por querer ayudar con R2Beat 2013. Lo más útil es **arreglar algo que se ve jugando**: un
botón que no hace nada, un premio que no llega, un cartel mal armado. Si no programás, también sirve
un *issue* con una foto y lo que dice la consola del server.

## Las ramas

```
  tu rama  ──PR──▶  develop  ──(cuando anduvo bien)──▶  master
                       │                                   │
                       ▼                                   ▼
               server de PRUEBA                      server de PROD
               (se actualiza solo)                   (lo actualiza el dueño)
```

- **`master`** es lo estable. **Sólo el dueño** del repo fusiona ahí.
- **`develop`** es lo próximo, y es la rama por defecto. Ahí van **todos los PR**.
- **Tu trabajo** va en una rama tuya (`arreglo-cartel`, `tienda-alas`…), con un **PR contra `develop`**.

## Paso a paso

1. Si sos colaborador, cloná el repo; si no, hacé un **fork** (botón *Fork*) y cloná el tuyo.
2. Una rama desde `develop`:

   ```bash
   git checkout develop
   git pull
   git checkout -b mi-arreglo
   ```

3. Cambiá lo que haga falta y **corré las pruebas**:

   ```bash
   python pruebas/probar_login.py
   python pruebas/probar_nada_prohibido.py
   ```

   Las dos tienen que terminar en «→ TODO BIEN».
4. **Probalo jugando** si podés: `python correr_servidor.py` y `python jugar.py` (ver [EMPEZAR.md](EMPEZAR.md)).
5. `git push` y abrí el **PR contra `develop`** (no contra `master`). Contá qué arregla y cómo lo
   probaste.
6. GitHub corre las pruebas solo. Con todo en verde, se fusiona en `develop` y a los pocos minutos
   está en el server de prueba.

## Dónde va cada cosa

El server está partido por pantallas del juego: [servidor/MAPA.md](servidor/MAPA.md) dice qué
archivo abrir para cada cosa.

## Las reglas

- **Medir antes que deducir.** Si un campo de un paquete es una suposición, decilo en el comentario.
- **Toda prueba lleva su revés**: el caso que TIENE que fallar (la clave equivocada no entra). Una
  prueba que nunca puede fallar no prueba nada.
- ⛔ **Nada del cliente de Softnyx entra al repo**: ni `.pak`, ni `.exe`, ni música, ni gráficos, ni
  las notas de las canciones (`notes/*.bin`), ni las tablas que saca `extraer_datos.py`. La única
  excepción es nuestra `exe/d3d9.dll` (su fuente está en `herramientas/dll_d3d9/`). Ver
  [AVISO-LEGAL.md](AVISO-LEGAL.md).
- ⛔ **Nada de datos personales**: ni bases (`datos.db`), ni `gm.txt`/`admin.txt`/`streamers.txt`,
  ni nombres de jugadores reales, ni tu IP, ni rutas con tu usuario de Windows. En los comentarios,
  los jugadores son `jugador1`, `jugador2`…
- `probar_nada_prohibido.py` revisa las dos últimas en cada PR. Si salta, no es para molestar: un
  dato que entra al historial de git no sale más.
