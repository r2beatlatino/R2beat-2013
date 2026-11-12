# Despliegue — el server en un VPS, con Docker

Dos entornos en el mismo VPS (o en dos distintos), cada uno con **su rama**:

| entorno | rama | puertos | se actualiza |
|---|---|---|---|
| **prod** | `master` | login 48004, canales 48005…48095 | **a mano**, lo corre el dueño |
| **prueba** | `develop` | login 49004, canales 49005…49095 (`R2_PUERTOS=1000`) | **solo**, cada 5 minutos |

Lo que hay acá:

- `Dockerfile` — la imagen: el server + Python 3.12. Al armarla corre `pruebas/probar_login.py`; si
  falla, **no se arma** y sigue andando el contenedor anterior.
- `docker-compose.yml` — un solo archivo para los dos entornos (cada uno con su `.env`).
- `ejemplo.env` — de ahí salen `prod.env` y `prueba.env`.
- `arrancar.sh` — lo que corre adentro: copia las tablas de tu cliente y arranca el server.
- `actualizar.sh` — pone un entorno en lo último de su rama, sólo si cambió algo.

## Instalar (una vez por VPS)

```bash
sudo apt install -y docker.io docker-compose-v2 git
sudo mkdir -p /opt/r2b2013 && cd /opt/r2b2013
sudo git clone -b develop https://github.com/r2beatlatino/R2beat-2013.git prueba
sudo cp prueba/despliegue/ejemplo.env prueba.env      # y completalo
```

**Las tablas y las notas del juego no están en el repo** (son de Softnyx). Sacalas de tu cliente en
tu PC (`herramientas/extraer_datos.py` y el importador, ver [EMPEZAR.md](../EMPEZAR.md)) y subí esto a
`/opt/r2b2013/juego/`:

```
juego/
  shop_lt.txt
  notes_map_2013.json
  notes/              (los .bin de las canciones)
  tablas-cliente/     (los .txt y .xml que sacó extraer_datos.py)
```

Después:

```bash
sudo bash /opt/r2b2013/prueba/despliegue/actualizar.sh prueba --forzar
```

Y para que **prueba** se actualice solo, en el `crontab -e` de root:

```
*/5 * * * * bash /opt/r2b2013/prueba/despliegue/actualizar.sh prueba >> /opt/r2b2013/prueba.log 2>&1
```

## Las cuentas

Quedan en `R2_DATOS_DIR` (`/opt/r2b2013/prueba-datos/datos.db`), **afuera** del contenedor: sobreviven
a cada actualización y para mudarse de VPS alcanza con llevar esa carpeta. Ahí mismo van `gm.txt`,
`admin.txt` y `streamers.txt`.

⛔ `datos.db` tiene las contraseñas (hasheadas) de tu gente: nunca la subas al repo ni la compartas.
Para respaldarla con el server prendido usá `sqlite3 datos.db ".backup copia.db"`, no `cp`.

## El cortafuegos

Abrí sólo los puertos del entorno: `48004:48095/tcp` (prod) o `49004:49095/tcp` (prueba).
