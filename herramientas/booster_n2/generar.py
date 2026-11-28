"""Los diseños propios de Ñ2Hock para el botón del booster: botones, auras, marcos y teñidos (todo dibujado acá)."""
import colorsys
import math
import os
import random
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SAL = sys.argv[1]
S = 4                                    # se dibuja a 4× y se achica (bordes suaves)
for sub in ("Boton", "Aura", "Marcos", "Tenir"):
    os.makedirs(os.path.join(SAL, sub), exist_ok=True)


def fuente(t):
    for n in ("seguibl.ttf", "arialbd.ttf", "segoeuib.ttf"):
        try:
            return ImageFont.truetype(os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", n), t)
        except OSError:
            pass
    return ImageFont.load_default()


def achicar(im, lado):
    return im.resize((lado, lado), Image.LANCZOS)


def hsv(h, s, v, a=255):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return (int(r * 255), int(g * 255), int(b * 255), a)


def gif(cuadros, ruta, ms=60):
    """Cuadros RGBA → GIF con transparencia (el canal alfa se corta en 50 %, como cualquier GIF)."""
    pal = []
    for c in cuadros:
        a = c.getchannel("A")
        p = c.convert("RGB").quantize(colors=255, method=Image.Quantize.MEDIANCUT)
        p.putpalette(p.getpalette()[:765] + [0, 0, 0])
        mask = a.point(lambda v: 255 if v < 110 else 0)
        p.paste(255, mask=mask)
        pal.append(p)
    pal[0].save(ruta, save_all=True, append_images=pal[1:], duration=ms, loop=0, transparency=255, disposal=2)


# ── BOTONES (81 × 81): sin carga (apagado), lleno y lleno_2 (el brillo del parpadeo) ─────────────────────────────
def boton(nombre, c1, c2, simbolo, estilo):
    L = 81 * S
    for est, brillo in (("sin_carga", 0.45), ("lleno", 1.0), ("lleno_2", 1.25)):
        im = Image.new("RGBA", (L, L), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        m = 5 * S
        # el cuerpo: degradé vertical c1 → c2, redondeado
        cuerpo = Image.new("RGBA", (L, L))
        cd = ImageDraw.Draw(cuerpo)
        for y in range(L):
            t = y / L
            col = tuple(int((c1[i] * (1 - t) + c2[i] * t) * min(brillo, 1.0)) for i in range(3))
            if est == "sin_carga":
                g = int(sum(col) / 3)
                col = tuple(int(v * 0.35 + g * 0.65) for v in col)
            cd.line([(0, y), (L, y)], fill=col + (255,))
        masc = Image.new("L", (L, L), 0)
        if estilo == "redondo":
            ImageDraw.Draw(masc).ellipse([m, m, L - m, L - m], fill=255)
        else:
            ImageDraw.Draw(masc).rounded_rectangle([m, m, L - m, L - m], radius=16 * S, fill=255)
        im.paste(cuerpo, (0, 0), masc)
        # el brillo de arriba (caramelo)
        luz = Image.new("RGBA", (L, L), (0, 0, 0, 0))
        ImageDraw.Draw(luz).ellipse([m + 8 * S, m + 4 * S, L - m - 8 * S, L // 2], fill=(255, 255, 255, 70 if est != "sin_carga" else 30))
        im = Image.alpha_composite(im, Image.composite(luz, Image.new("RGBA", (L, L)), masc))
        d = ImageDraw.Draw(im)
        # el borde
        borde = (255, 255, 255, 230) if est != "sin_carga" else (170, 170, 180, 200)
        if estilo == "redondo":
            d.ellipse([m, m, L - m, L - m], outline=borde, width=3 * S)
        else:
            d.rounded_rectangle([m, m, L - m, L - m], radius=16 * S, outline=borde, width=3 * S)
        # el símbolo (las figuras se dibujan: la letra no trae ★ ni ⚡)
        blanco = (255, 255, 255, 255) if est != "sin_carga" else (200, 200, 210, 255)
        if simbolo in ("estrella", "rayo"):
            cx, cy, r = L / 2, L / 2, 22 * S
            if simbolo == "estrella":
                pts = [(cx + (r if k % 2 == 0 else r * 0.42) * math.cos(-math.pi / 2 + k * math.pi / 5),
                        cy + (r if k % 2 == 0 else r * 0.42) * math.sin(-math.pi / 2 + k * math.pi / 5)) for k in range(10)]
            else:
                pts = [(cx + 4 * S, cy - r), (cx - 12 * S, cy + 3 * S), (cx - 1 * S, cy + 3 * S), (cx - 5 * S, cy + r),
                       (cx + 12 * S, cy - 4 * S), (cx + 1 * S, cy - 4 * S)]
            d.polygon([(x + 2 * S, y + 2 * S) for x, y in pts], fill=(0, 0, 0, 150))
            d.polygon(pts, fill=blanco)
        else:
            f = fuente(40 * S)
            bb = d.textbbox((0, 0), simbolo, font=f)
            x, y = (L - (bb[2] - bb[0])) / 2 - bb[0], (L - (bb[3] - bb[1])) / 2 - bb[1]
            d.text((x + 2 * S, y + 2 * S), simbolo, font=f, fill=(0, 0, 0, 150))
            d.text((x, y), simbolo, font=f, fill=blanco)
        if est == "lleno_2":                                  # el destello del parpadeo: más claro y con halo
            a_ = im.getchannel("A")
            claro = Image.alpha_composite(im, Image.new("RGBA", (L, L), (255, 255, 255, 70)))
            claro.putalpha(a_)
            halo = claro.filter(ImageFilter.GaussianBlur(5 * S))
            im = Image.alpha_composite(halo, claro)
        achicar(im, 81).save(os.path.join(SAL, "Boton", f"{nombre}_{est}.png"))


boton("n2_rosa", (255, 70, 160), (150, 0, 90), "Ñ", "cuadro")
boton("n2_cian", (60, 220, 255), (0, 90, 170), "Ñ", "redondo")
boton("n2_galaxia", (120, 60, 220), (20, 0, 60), "estrella", "redondo")
boton("n2_oro", (255, 220, 90), (190, 110, 0), "rayo", "cuadro")
boton("n2_menta", (110, 255, 190), (0, 140, 110), "»", "cuadro")


# ── AURAS (256 × 256, GIF que gira alrededor del botón; el hueco del medio, libre) ──────────────────────────────
def aura_anillo(nombre, c_ini, c_fin, n=24):
    L = 256 * 2
    cuadros = []
    for f in range(n):
        im = Image.new("RGBA", (L, L), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        for k in range(180):
            a0 = (k / 180) * 360 + f * 360 / n
            t = (math.sin(math.radians(k * 2)) + 1) / 2
            col = tuple(int(c_ini[i] * (1 - t) + c_fin[i] * t) for i in range(3)) + (230,)
            d.arc([60, 60, L - 60, L - 60], a0, a0 + 2.2, fill=col, width=34)
        im = Image.alpha_composite(im.filter(ImageFilter.GaussianBlur(10)), im)
        cuadros.append(im.resize((256, 256), Image.LANCZOS))
    gif(cuadros, os.path.join(SAL, "Aura", f"{nombre}.gif"))


def aura_orbita(nombre, simbolo_fn, n=24, cuantos=8):
    L = 256 * 2
    cuadros = []
    for f in range(n):
        im = Image.new("RGBA", (L, L), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        for i in range(cuantos):
            ang = 2 * math.pi * (i / cuantos + f / (n * 2))
            r = L * 0.39 + math.sin(ang * 3 + f / n * 2 * math.pi) * 10
            x, y = L / 2 + r * math.cos(ang), L / 2 + r * math.sin(ang)
            simbolo_fn(d, x, y, i, f / n)
        im = Image.alpha_composite(im.filter(ImageFilter.GaussianBlur(6)), im)
        cuadros.append(im.resize((256, 256), Image.LANCZOS))
    gif(cuadros, os.path.join(SAL, "Aura", f"{nombre}.gif"))


def estrella(d, x, y, i, t):
    r = 22 + 6 * math.sin(2 * math.pi * (t * 2 + i / 3))
    pts = []
    for k in range(10):
        a = math.pi / 2 + k * math.pi / 5
        rr = r if k % 2 == 0 else r * 0.45
        pts.append((x + rr * math.cos(a), y - rr * math.sin(a)))
    d.polygon(pts, fill=hsv(0.85 + i * 0.04, 0.6, 1.0))


def corazon(d, x, y, i, t):
    s = 16 + 4 * math.sin(2 * math.pi * (t * 2 + i / 4))
    col = hsv(0.93, 0.75, 1.0)
    d.ellipse([x - s, y - s * 0.8, x, y + s * 0.2], fill=col)
    d.ellipse([x, y - s * 0.8, x + s, y + s * 0.2], fill=col)
    d.polygon([(x - s, y - s * 0.2), (x + s, y - s * 0.2), (x, y + s * 1.1)], fill=col)


def chispa(d, x, y, i, t):
    s = 10 + 8 * abs(math.sin(math.pi * (t * 3 + i / 5)))
    col = hsv(0.52, 0.5, 1.0)
    d.polygon([(x, y - s * 2), (x + s * 0.4, y), (x, y + s * 2), (x - s * 0.4, y)], fill=col)
    d.polygon([(x - s * 2, y), (x, y - s * 0.4), (x + s * 2, y), (x, y + s * 0.4)], fill=col)


aura_anillo("n2_anillo_rosa_cian", (255, 40, 150), (40, 220, 255))
aura_anillo("n2_anillo_dorado", (255, 210, 60), (255, 120, 0))
aura_orbita("n2_estrellas", estrella, cuantos=8)
aura_orbita("n2_corazones", corazon, cuantos=7)
aura_orbita("n2_chispas", chispa, cuantos=10)


def aura_pulso(nombre, col, n=20):
    L = 256 * 2
    cuadros = []
    for f in range(n):
        im = Image.new("RGBA", (L, L), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        for k in range(3):
            t = ((f / n) + k / 3) % 1.0
            r = L * (0.30 + 0.18 * t)
            a = int(230 * (1 - t))
            d.ellipse([L / 2 - r, L / 2 - r, L / 2 + r, L / 2 + r], outline=col + (a,), width=16)
        im = Image.alpha_composite(im.filter(ImageFilter.GaussianBlur(8)), im)
        cuadros.append(im.resize((256, 256), Image.LANCZOS))
    gif(cuadros, os.path.join(SAL, "Aura", f"{nombre}.gif"), ms=50)


aura_pulso("n2_pulso_neon", (60, 255, 220))


# ── MARCOS GRANDES (125 × 125: salen por los costados del botón de 81) ──────────────────────────────────────────
def marco_alas(nombre, col):
    L = 125 * S
    im = Image.new("RGBA", (L, L), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for lado in (-1, 1):
        for k in range(4):
            cx = L / 2 + lado * (L * 0.36 + k * 3 * S)
            cy = L * 0.42 + k * 7 * S
            w, h = 22 * S - k * 3 * S, 9 * S
            pts = [(cx, cy - h), (cx + lado * w, cy - h * 1.6), (cx + lado * w * 0.8, cy + h), (cx, cy + h * 0.6)]
            d.polygon(pts, fill=col + (235 - k * 30,), outline=(255, 255, 255, 220))
    im = Image.alpha_composite(im.filter(ImageFilter.GaussianBlur(3 * S)), im)
    achicar(im, 125).save(os.path.join(SAL, "Marcos", f"{nombre}.png"))


def marco_corona(nombre):
    L = 125 * S
    im = Image.new("RGBA", (L, L), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    base, alto = L * 0.18, L * 0.03
    x0, x1 = L * 0.30, L * 0.70
    pts = [(x0, base), (x0, alto + 8 * S), (L * 0.40, base - 9 * S), (L / 2, alto), (L * 0.60, base - 9 * S),
           (x1, alto + 8 * S), (x1, base)]
    d.polygon(pts, fill=(255, 205, 60, 255), outline=(255, 250, 200, 255))
    for px in (x0, L / 2, x1):
        d.ellipse([px - 4 * S, (alto + 8 * S if px != L / 2 else alto) - 4 * S, px + 4 * S,
                   (alto + 8 * S if px != L / 2 else alto) + 4 * S], fill=(255, 60, 160, 255))
    im = Image.alpha_composite(im.filter(ImageFilter.GaussianBlur(3 * S)), im)
    achicar(im, 125).save(os.path.join(SAL, "Marcos", f"{nombre}.png"))


def marco_rayos(nombre, n=12):
    L = 125 * 2
    cuadros = []
    rnd = random.Random(7)
    for f in range(n):
        im = Image.new("RGBA", (L, L), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        for k in range(6):
            ang = 2 * math.pi * (k / 6 + f / (n * 3))
            r0, r1 = L * 0.34, L * 0.48
            pts = [(L / 2 + r0 * math.cos(ang), L / 2 + r0 * math.sin(ang))]
            for j in range(1, 5):
                r = r0 + (r1 - r0) * j / 4
                a = ang + rnd.uniform(-0.12, 0.12)
                pts.append((L / 2 + r * math.cos(a), L / 2 + r * math.sin(a)))
            d.line(pts, fill=(120, 230, 255, 255), width=5)
        im = Image.alpha_composite(im.filter(ImageFilter.GaussianBlur(5)), im)
        cuadros.append(im.resize((125, 125), Image.LANCZOS))
    gif(cuadros, os.path.join(SAL, "Marcos", f"{nombre}.gif"), ms=70)


marco_alas("n2_alas_rosa", (255, 120, 190))
marco_alas("n2_alas_cian", (110, 220, 255))
marco_corona("n2_corona")
marco_rayos("n2_rayos")


# ── TEÑIDOS (81 × 81: multiplican los colores del botón) ─────────────────────────────────────────────────────────
def tenir_degrade(nombre, cols):
    im = Image.new("RGBA", (81, 81))
    for y in range(81):
        for x in range(81):
            t = (x + y) / 160
            i = min(int(t * (len(cols) - 1)), len(cols) - 2)
            u = t * (len(cols) - 1) - i
            im.putpixel((x, y), tuple(int(cols[i][k] * (1 - u) + cols[i + 1][k] * u) for k in range(3)) + (255,))
    im.save(os.path.join(SAL, "Tenir", f"{nombre}.png"))


def tenir_animado(nombre, n=24, sat=0.55):
    cuadros = []
    for f in range(n):
        im = Image.new("RGBA", (81, 81))
        for y in range(81):
            for x in range(81):
                im.putpixel((x, y), hsv((x + y) / 160 + f / n, sat, 1.0))
        cuadros.append(im)
    cuadros[0].save(os.path.join(SAL, "Tenir", f"{nombre}.gif"), save_all=True, append_images=cuadros[1:],
                    duration=60, loop=0)


tenir_degrade("n2_rosa_cian", [(255, 90, 180), (190, 140, 255), (90, 220, 255)])
tenir_degrade("n2_aurora", [(80, 255, 170), (80, 200, 255), (200, 120, 255)])
tenir_degrade("n2_atardecer", [(255, 220, 100), (255, 120, 90), (220, 60, 160)])
tenir_animado("n2_holografico")
print("listo")
