import html
import http.cookiejar
import io
import json
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont

# ==========================================
# BOT FABBRICA CAROSELLI (TIKTOK + INSTAGRAM)
# ==========================================
FILE_STATO = "caroselli_stato.json"
NOME_CANALE = "Radar Orologi & Offerte"
NUM_OROLOGI = 3
MAX_STORICO = 120

SCONTO_MINIMO_PCT = 12.0
PREZZO_MINIMO_EUR = 120.0   # Per i social scegliamo solo pezzi d'impatto >= 120€

# Palette coordinata al logo blu notte & oro champagne
COL_NAVY = (10, 22, 40)
COL_NAVY_CARD = (17, 34, 60)
COL_GOLD = (214, 180, 108)
COL_GOLD_SOFT = (158, 134, 84)
COL_RING = (28, 48, 78)
COL_WHITE = (255, 255, 255)
COL_MUTED = (168, 182, 204)
COL_RED = (217, 45, 32)
COL_GREEN_BG = (22, 101, 52)
COL_GREEN_TXT = (187, 247, 208)
COL_TG_BLUE = (38, 165, 228)

RADAR_FONTI = [
    {
        "negozio": "Orafo La Morgia",
        "base_url": "https://www.orafolamorgia.it",
        "collezioni": ["hamilton", "tissot", "seiko", "outlet"],
    },
    {
        "negozio": "Ferrari Luca Gioielli",
        "base_url": "https://ferrarilucagioielli.it",
        "collezioni": [
            "hamilton", "tissot", "seiko", "citizen",
            "orologi-longines", "bulova", "orologi-casio",
        ],
    },
    {
        "negozio": "Gioielleria Petrillo",
        "base_url": "https://gioielleriapetrillo.it",
        "collezioni": ["bulova-orologi"],
    },
    {
        "negozio": "2B Gioielli",
        "base_url": "https://2bgioielli.it",
        "collezioni": ["orologi-eleganti", "citizen", "festina"],
    },
]

MARCHE_TOP = [
    "hamilton", "tissot", "seiko", "longines", "tudor", "bulova", "citizen",
    "casio", "g-shock", "gshock", "orient", "mido", "certina", "oris",
    "frederique constant", "eberhard", "tag heuer", "omega", "festina",
    "d1 milano",
]

MARCHE_PRESTIGIO = {
    "hamilton", "tissot", "seiko", "longines", "tudor", "bulova", "citizen",
    "orient", "mido", "certina", "oris", "frederique constant", "eberhard",
    "tag heuer", "omega",
}

PAROLE_VIETATE = [
    "strap", "straps", "cinturino", "cinturini", "buckle", "clasp", "fibbia",
    "pouch", "watch roll", "roll", "travel case", "scatola", "astuccio",
    "tool", "collana", "collane", "anello", "anelli", "fedina", "solitario",
    "orecchini", "orecchino", "bracciale", "bracciali", "ciondolo", "charm",
    "pendente", "gemelli", "spilla", "pandora", "dodo", "miluna", "stroili",
    "gift card", "voucher", "buono regalo", "wallet", "portafoglio",
    "portachiavi", "sveglia", "parete", "muro", "penna",
]

HEADERS_WEB = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9",
}

FONT_CACHE = {}


# ==========================================
# STATO E UTILITY
# ==========================================
def data_italia():
    try:
        return datetime.now(ZoneInfo("Europe/Rome")).strftime("%d/%m/%Y")
    except Exception:
        return datetime.now().strftime("%d/%m/%Y")


def carica_stato():
    if not os.path.exists(FILE_STATO):
        return {"usati": []}
    try:
        with open(FILE_STATO, "r", encoding="utf-8") as f:
            dati = json.load(f)
        if isinstance(dati, dict):
            return {"usati": dati.get("usati", [])}
    except Exception as e:
        print(f"Errore lettura {FILE_STATO}: {e}")
    return {"usati": []}


def salva_stato(stato):
    stato["usati"] = stato.get("usati", [])[-MAX_STORICO:]
    with open(FILE_STATO, "w", encoding="utf-8") as f:
        json.dump(stato, f, indent=2, ensure_ascii=False)


def contiene_parola(testo, lista_parole):
    for parola in lista_parole:
        if re.search(r"\b" + re.escape(parola.strip()) + r"\b", testo, flags=re.IGNORECASE):
            return parola
    return None


def trova_marca(titolo, vendor=""):
    trovata = contiene_parola(f"{vendor} {titolo}", MARCHE_TOP)
    if not trovata:
        return None
    if trovata.lower() in ("g-shock", "gshock"):
        return "Casio G-Shock"
    if trovata.lower() == "d1 milano":
        return "D1 Milano"
    return trovata.title()


def pulisci_titolo(titolo, marca=""):
    t = re.sub(r"\s+_([A-Za-z0-9])", r" \1", titolo or "")
    t = re.sub(r"\s*[|•]+\s*", " - ", t)
    t = re.sub(r"\s+", " ", t).strip()
    # Rimuove asterischi o simboli sporchi all'inizio (es. "*SEIKO - ...")
    t = re.sub(r"^[\*\s\-:|]+", "", t)
    if marca:
        t = re.sub(r"^" + re.escape(marca) + r"\s*[-:|]?\s*", "", t, flags=re.IGNORECASE).strip()
    t = re.sub(r"^orologio\s+(?:uomo|donna|unisex)?\s*", "", t, flags=re.IGNORECASE).strip()
    t = re.sub(r"^[\*\s\-:|]+", "", t)
    if marca:
        t = re.sub(r"^" + re.escape(marca) + r"\s*[-:|]?\s*", "", t, flags=re.IGNORECASE).strip()
    return t or (titolo or "").strip()


def parse_numero(testo):
    if testo is None:
        return None
    s = str(testo).strip().replace("€", "").replace("$", "").strip()
    if not s:
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def formatta_euro(valore, interi_se_tondo=True):
    if interi_se_tondo and abs(valore - round(valore)) < 0.01:
        return f"{int(round(valore)):,}".replace(",", ".") + "€"
    return f"{valore:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + "€"


# ==========================================
# GESTIONE SESSIONE EUR SU SHOPIFY
# ==========================================
def estrai_valuta_shopify(html_text):
    if not html_text:
        return None, 1.0
    m = re.search(r"Shopify\.currency\s*=\s*(\{[^}]+\})", html_text)
    if m:
        try:
            info = json.loads(m.group(1))
            active = (info.get("active") or "").upper()
            rate = parse_numero(info.get("rate"))
            if active:
                return active, (rate if rate and rate > 0 else 1.0)
        except Exception:
            pass
    m_meta = re.search(
        r'(?:og:price:currency|product:price:currency)["\'][^>]+content=["\']([A-Z]{3})["\']',
        html_text,
        flags=re.IGNORECASE,
    )
    if m_meta:
        return m_meta.group(1).upper(), 1.0
    return None, 1.0


def crea_sessione_italia(base_url):
    cj = http.cookiejar.CookieJar()
    host = urllib.parse.urlparse(base_url).hostname or ""
    dominio = host[4:] if host.startswith("www.") else host

    for nome_cookie, valore in [("localization", "IT"), ("cart_currency", "EUR")]:
        for dom in {host, f".{dominio}"}:
            if not dom or dom == ".":
                continue
            cookie = http.cookiejar.Cookie(
                version=0, name=nome_cookie, value=valore,
                port=None, port_specified=False, domain=dom,
                domain_specified=True, domain_initial_dot=dom.startswith("."),
                path="/", path_specified=True, secure=True, expires=None,
                discard=True, comment=None, comment_url=None, rest={}, rfc2109=False,
            )
            cj.set_cookie(cookie)

    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    pagina_html = ""
    try:
        dati_loc = urllib.parse.urlencode({
            "form_type": "localization", "utf8": "✓", "_method": "put",
            "return_to": "/", "country_code": "IT", "language_code": "it",
        }).encode("utf-8")
        req_loc = urllib.request.Request(
            f"{base_url.rstrip('/')}/localization",
            data=dati_loc,
            headers={**HEADERS_WEB, "Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with opener.open(req_loc, timeout=14) as resp:
            pagina_html = resp.read().decode("utf-8", errors="ignore")
    except Exception:
        pass

    if not pagina_html:
        try:
            req_home = urllib.request.Request(f"{base_url.rstrip('/')}/?country=IT", headers=HEADERS_WEB)
            with opener.open(req_home, timeout=14) as resp:
                pagina_html = resp.read().decode("utf-8", errors="ignore")
        except Exception:
            pass

    valuta_attiva, tasso = estrai_valuta_shopify(pagina_html)
    return opener, (valuta_attiva or "EUR"), tasso


def verifica_prezzo_reale(item, opener, valuta_sess, tasso_sess):
    url_prod = item["url"]
    pagina_html = ""
    try:
        req = urllib.request.Request(url_prod, headers=HEADERS_WEB)
        with opener.open(req, timeout=15) as resp:
            pagina_html = resp.read().decode("utf-8", errors="ignore")
    except Exception:
        pass

    val_pag, tasso_pag = estrai_valuta_shopify(pagina_html)
    val_eff = val_pag or valuta_sess or "EUR"
    tasso_eff = tasso_pag if (val_pag and tasso_pag and tasso_pag > 0) else tasso_sess

    js_nuovo, js_vecchio = None, None
    try:
        req_js = urllib.request.Request(f"{url_prod}.js", headers=HEADERS_WEB)
        with opener.open(req_js, timeout=12) as resp:
            dati_js = json.loads(resp.read().decode("utf-8", errors="ignore"))
        varianti = dati_js.get("variants") or []
        disponibili = [v for v in varianti if v.get("available")]
        if not disponibili:
            return None
        v_ref = disponibili[0]
        if v_ref.get("price"):
            js_nuovo = round(float(v_ref["price"]) / 100.0, 2)
        if v_ref.get("compare_at_price"):
            js_vecchio = round(float(v_ref["compare_at_price"]) / 100.0, 2)
    except Exception:
        pass

    p_nuovo = js_nuovo if js_nuovo else item["prezzo_nuovo"]
    p_vecchio = js_vecchio if js_vecchio else item["prezzo_vecchio"]

    if val_eff == "USD":
        if tasso_eff and tasso_eff > 1.01:
            p_nuovo = round(p_nuovo / tasso_eff, 2)
            if p_vecchio:
                p_vecchio = round(p_vecchio / tasso_eff, 2)
        else:
            return None  # Sui social pubblichiamo solo prezzi in Euro

    if not p_vecchio or p_vecchio <= p_nuovo:
        return None

    item["prezzo_nuovo"] = p_nuovo
    item["prezzo_vecchio"] = p_vecchio
    item["risparmio"] = round(p_vecchio - p_nuovo, 2)
    item["sconto_pct"] = round(((p_vecchio - p_nuovo) / p_vecchio) * 100.0, 1)
    return item


def scarica_immagine(url):
    if not url:
        return None
    req = urllib.request.Request(url, headers=HEADERS_WEB)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        if len(data) < 2000:
            return None
        img = Image.open(io.BytesIO(data))
        if img.width < 150 or img.height < 150:
            return None
        return data
    except Exception:
        return None


# ==========================================
# RACCOLTA MIGLIORI OFFERTE DELLA GIORNATA
# ==========================================
def raccogli_candidati(usati_set):
    candidati = []
    sessioni = {}

    for fonte in RADAR_FONTI:
        nome_negozio = fonte["negozio"]
        base_url = fonte["base_url"].rstrip("/")
        opener, val_sess, tasso_sess = crea_sessione_italia(base_url)
        sessioni[nome_negozio] = (opener, val_sess, tasso_sess)

        if val_sess == "USD" and not (tasso_sess and tasso_sess > 1.01):
            continue

        visti = set()
        trovati = 0
        for col in fonte["collezioni"]:
            url_json = f"{base_url}/collections/{col}/products.json?limit=60"
            time.sleep(0.35)
            req = urllib.request.Request(url_json, headers=HEADERS_WEB)
            try:
                with opener.open(req, timeout=18) as resp:
                    dati = json.loads(resp.read().decode("utf-8", errors="ignore"))
            except Exception as e:
                print(f"  {nome_negozio} ({col}): errore {e}")
                continue

            for prod in dati.get("products", []):
                prod_id = prod.get("id")
                if not prod_id or prod_id in visti:
                    continue
                visti.add(prod_id)

                titolo_raw = (prod.get("title") or "").strip()
                handle = (prod.get("handle") or "").strip()
                vendor = (prod.get("vendor") or "").strip()
                ptype = (prod.get("product_type") or "").strip()

                if not titolo_raw or not handle:
                    continue
                if contiene_parola(f"{titolo_raw} {ptype}", PAROLE_VIETATE):
                    continue

                marca = trova_marca(titolo_raw, vendor)
                if not marca:
                    continue

                variants = prod.get("variants") or []
                disponibili = [v for v in variants if v.get("available")]
                if not disponibili:
                    continue
                v_ref = disponibili[0]

                p_nuovo = parse_numero(v_ref.get("price"))
                p_vecchio = parse_numero(v_ref.get("compare_at_price"))
                if not p_nuovo or not p_vecchio or p_vecchio <= p_nuovo:
                    continue

                # Normalizza in EUR già prima di confrontare i negozi tra loro
                if val_sess == "USD" and tasso_sess and tasso_sess > 1.01:
                    p_nuovo = round(p_nuovo / tasso_sess, 2)
                    p_vecchio = round(p_vecchio / tasso_sess, 2)

                if p_nuovo < PREZZO_MINIMO_EUR:
                    continue

                risparmio = p_vecchio - p_nuovo
                sconto_pct = round((risparmio / p_vecchio) * 100.0, 1)
                if sconto_pct < SCONTO_MINIMO_PCT:
                    continue

                images = prod.get("images") or []
                img_url = images[0].get("src") if images else None
                if not img_url:
                    continue

                pid = f"{nome_negozio}:{prod_id}"
                gia_usato = pid in usati_set

                # Punteggio oggettivo puro: premia le vere migliori offerte della giornata
                bonus_marca = 25.0 if marca.lower() in MARCHE_PRESTIGIO else 0.0
                punteggio = (
                    bonus_marca
                    + min(sconto_pct, 45.0) * 2.2
                    + min(risparmio, 600.0) * 0.45
                    + min(p_nuovo, 1800.0) * 0.02
                )

                trovati += 1
                candidati.append({
                    "id": pid,
                    "gia_usato": gia_usato,
                    "punteggio": punteggio,
                    "marca": marca,
                    "titolo_breve": pulisci_titolo(titolo_raw, marca),
                    "titolo_raw": titolo_raw,
                    "prezzo_nuovo": p_nuovo,
                    "prezzo_vecchio": p_vecchio,
                    "risparmio": round(risparmio, 2),
                    "sconto_pct": sconto_pct,
                    "url": f"{base_url}/products/{handle}",
                    "img_url": img_url,
                    "negozio": nome_negozio,
                })

        print(f"  {nome_negozio}: {trovati} candidati validi in EUR")

    return candidati, sessioni


def seleziona_orologi_carosello(candidati, sessioni, quantita=3):
    """Sceglie le 3 migliori offerte della giornata (3 marchi diversi), verificate in EUR."""
    candidati.sort(key=lambda x: (1 if x["gia_usato"] else 0, -x["punteggio"]))

    scelti = []
    marche_usate = set()

    for item in candidati:
        if len(scelti) >= quantita:
            break
        marca_k = item["marca"].lower()
        if marca_k in marche_usate:
            continue

        opener, val_s, tasso_s = sessioni[item["negozio"]]
        verificato = verifica_prezzo_reale(item, opener, val_s, tasso_s)
        if not verificato or verificato["sconto_pct"] < SCONTO_MINIMO_PCT:
            continue

        raw_img = scarica_immagine(verificato["img_url"])
        if not raw_img:
            continue

        verificato["raw_img"] = raw_img
        scelti.append(verificato)
        marche_usate.add(marca_k)
        print(
            f"  Scelto #{len(scelti)}: {verificato['marca']} | "
            f"{verificato['prezzo_nuovo']}€ (era {verificato['prezzo_vecchio']}€, -{verificato['sconto_pct']:.0f}%)"
        )

    return scelti


# ==========================================
# MOTORE GRAFICO (SLIDE 1080x1350 SAFE TIKTOK)
# ==========================================
def ottieni_font(size, bold=True):
    chiave = (size, bold)
    if chiave in FONT_CACHE:
        return FONT_CACHE[chiave]

    nome_file = "Poppins-Bold.ttf" if bold else "Poppins-Medium.ttf"
    percorso_tmp = f"/tmp/{nome_file}"
    if not os.path.exists(percorso_tmp):
        url_font = f"https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/{nome_file}"
        try:
            req = urllib.request.Request(url_font, headers=HEADERS_WEB)
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = resp.read()
            if len(data) > 10000:
                with open(percorso_tmp, "wb") as f:
                    f.write(data)
        except Exception:
            pass

    candidati_font = [
        percorso_tmp,
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidati_font:
        if os.path.exists(path):
            try:
                fnt = ImageFont.truetype(path, size=size)
                FONT_CACHE[chiave] = fnt
                return fnt
            except Exception:
                continue

    fnt = ImageFont.load_default()
    FONT_CACHE[chiave] = fnt
    return fnt


def misura_testo(draw, testo, font):
    bbox = draw.textbbox((0, 0), testo, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def ottieni_font_adattato(draw, testo, max_w, size_iniziale, size_min=26, bold=True):
    for sz in range(size_iniziale, size_min - 1, -2):
        fnt = ottieni_font(sz, bold=bold)
        tw, _ = misura_testo(draw, testo, fnt)
        if tw <= max_w:
            return fnt
    return ottieni_font(size_min, bold=bold)


def disegna_testo_centrato(draw, testo, cx, y, font, fill):
    w, h = misura_testo(draw, testo, font)
    draw.text((cx - w // 2, y), testo, font=font, fill=fill)
    return h


def spezza_righe(draw, testo, font, max_w, max_righe=2):
    parole = testo.split()
    righe = []
    corrente = ""
    for p in parole:
        prova = f"{corrente} {p}".strip()
        w, _ = misura_testo(draw, prova, font)
        if w <= max_w or not corrente:
            corrente = prova
        else:
            righe.append(corrente)
            corrente = p
            if len(righe) == max_righe - 1:
                break

    usate = sum(len(r.split()) for r in righe)
    resto = " ".join(parole[usate:])
    if resto:
        while True:
            w, _ = misura_testo(draw, resto, font)
            if w <= max_w or len(resto) <= 10:
                break
            resto = resto[:-4].rstrip() + "..."
        righe.append(resto)
    return righe[:max_righe]


def crea_sfondo_radar(w=1080, h=1350):
    img = Image.new("RGB", (w, h), COL_NAVY)
    draw = ImageDraw.Draw(img)

    cx, cy = w // 2, int(h * 0.40)
    for r in (250, 380, 510, 650):
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=COL_RING, width=2)

    draw.line([(cx - 650, cy), (cx + 650, cy)], fill=(20, 36, 60), width=2)
    draw.line([(cx, cy - 650), (cx, cy + 650)], fill=(20, 36, 60), width=2)

    draw.rounded_rectangle([28, 28, w - 28, h - 28], radius=32, outline=(52, 68, 96), width=2)
    return img, draw


def disegna_pill(draw, testo, cx, y, font, bg, fg, pad_x=34, pad_y=14, outline=None, outline_width=2):
    tw, th = misura_testo(draw, testo, font)
    x0 = cx - tw // 2 - pad_x
    x1 = cx + tw // 2 + pad_x
    y0 = y
    y1 = y + th + pad_y * 2
    draw.rounded_rectangle(
        [x0, y0, x1, y1],
        radius=(y1 - y0) // 2,
        fill=bg,
        outline=outline,
        width=outline_width if outline else 0,
    )
    draw.text((cx - tw // 2, y0 + pad_y - 2), testo, font=font, fill=fg)
    return y1


def incolla_orologio_in_card(canvas, draw, raw_bytes, box, radius=32, padding=34):
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=radius, fill=COL_WHITE, outline=COL_GOLD, width=3)

    foto = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
    max_w = (x1 - x0) - padding * 2
    max_h = (y1 - y0) - padding * 2
    foto.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)

    px = x0 + ((x1 - x0) - foto.width) // 2
    py = y0 + ((y1 - y0) - foto.height) // 2
    canvas.paste(foto, (px, py), foto)


def jpg_bytes(img):
    out = io.BytesIO()
    img.convert("RGB").save(out, format="JPEG", quality=93)
    return out.getvalue()


def scegli_gancio_copertina(orologi):
    max_pct = max(it["sconto_pct"] for it in orologi)
    max_save = max(it["risparmio"] for it in orologi)

    opzioni = [
        (f"FINO AL -{max_pct:.0f}% OGGI", "3 OROLOGI IN OFFERTA"),
        ("3 OROLOGI VERI", f"SCONTATI FINO AL -{max_pct:.0f}%"),
        ("SELEZIONE DEL RADAR", f"FINO A -{formatta_euro(max_save)} OGGI"),
    ]
    if max_save >= 100:
        opzioni.append((f"RISPARMI FINO A {formatta_euro(max_save)}", "3 AFFARI DI OGGI"))
    return random.choice(opzioni)


def genera_slide_copertina(orologi):
    img, draw = crea_sfondo_radar()
    cx = 540

    f_pill = ottieni_font(25, bold=True)
    f_sub = ottieni_font(29, bold=False)
    f_brand = ottieni_font(24, bold=True)
    f_badge = ottieni_font(25, bold=True)
    f_cta = ottieni_font(29, bold=True)

    disegna_pill(
        draw, f"RADAR OROLOGI  •  {data_italia()}", cx, 74, f_pill,
        COL_NAVY_CARD, COL_GOLD, pad_x=36, pad_y=13, outline=COL_GOLD_SOFT,
    )

    riga1, riga2 = scegli_gancio_copertina(orologi)
    f_r1 = ottieni_font_adattato(draw, riga1, max_w=950, size_iniziale=64, size_min=44, bold=True)
    f_r2 = ottieni_font_adattato(draw, riga2, max_w=950, size_iniziale=62, size_min=44, bold=True)

    disegna_testo_centrato(draw, riga1, cx, 174, f_r1, COL_WHITE)
    disegna_testo_centrato(draw, riga2, cx, 256, f_r2, COL_GOLD)

    disegna_testo_centrato(draw, "Solo orologeria vera • Prezzi verificati in Euro", cx, 352, f_sub, COL_MUTED)

    card_w, card_h = 300, 445
    gap = 30
    start_x = (1080 - (card_w * 3 + gap * 2)) // 2
    top_y = 442

    for idx, item in enumerate(orologi[:3]):
        x0 = start_x + idx * (card_w + gap)
        x1 = x0 + card_w
        y0 = top_y
        y1 = top_y + card_h

        draw.rounded_rectangle([x0, y0, x1, y1], radius=28, fill=COL_WHITE, outline=COL_GOLD, width=3)
        foto = Image.open(io.BytesIO(item["raw_img"])).convert("RGBA")
        foto.thumbnail((card_w - 36, 305), Image.Resampling.LANCZOS)
        px = x0 + (card_w - foto.width) // 2
        py = y0 + 24 + (305 - foto.height) // 2
        img.paste(foto, (px, py), foto)

        draw.rounded_rectangle([x0 + 12, y1 - 84, x1 - 12, y1 - 14], radius=18, fill=COL_NAVY)
        brand_label = item["marca"].upper()[:14]
        disegna_testo_centrato(draw, brand_label, (x0 + x1) // 2, y1 - 63, f_brand, COL_GOLD)

        sconto_txt = f"-{item['sconto_pct']:.0f}%"
        disegna_pill(draw, sconto_txt, x1 - 56, y0 - 20, f_badge, COL_RED, COL_WHITE, pad_x=18, pad_y=9)

    disegna_pill(draw, "SCORRI PER VEDERE I PREZZI  >>>", cx, 958, f_cta, COL_GOLD, COL_NAVY, pad_x=46, pad_y=20)
    disegna_testo_centrato(draw, "Link diretti sul canale Telegram", cx, 1062, ottieni_font(25, bold=False), COL_MUTED)

    return jpg_bytes(img)


def genera_slide_orologio(item, numero, totale=3):
    img, draw = crea_sfondo_radar()
    cx = 540

    f_num = ottieni_font(28, bold=True)
    f_badge = ottieni_font(36, bold=True)
    f_title = ottieni_font(34, bold=True)
    f_old = ottieni_font(34, bold=False)
    f_new = ottieni_font(64, bold=True)
    f_save = ottieni_font(25, bold=True)
    f_store = ottieni_font(25, bold=False)
    f_foot = ottieni_font(22, bold=False)

    # Intestazione: numero a sinistra, marchio a destra
    draw.rounded_rectangle([70, 66, 208, 122], radius=24, fill=COL_NAVY_CARD, outline=COL_GOLD_SOFT, width=2)
    disegna_testo_centrato(draw, f"0{numero} / 0{totale}", 139, 77, f_num, COL_GOLD)

    brand_txt = item["marca"].upper()
    f_brand = ottieni_font_adattato(draw, brand_txt, max_w=720, size_iniziale=40, size_min=28, bold=True)
    bw, _ = misura_testo(draw, brand_txt, f_brand)
    draw.text((1010 - bw, 71), brand_txt, font=f_brand, fill=COL_WHITE)

    # Card foto prodotto pulita (senza etichette extra sopra)
    card_box = (70, 152, 1010, 682)
    incolla_orologio_in_card(img, draw, item["raw_img"], card_box, radius=34, padding=34)

    # Badge rosso sconto in alto a destra
    sconto_txt = f"-{item['sconto_pct']:.0f}%"
    disegna_pill(draw, sconto_txt, 935, 130, f_badge, COL_RED, COL_WHITE, pad_x=26, pad_y=12)

    # Nome modello (max 2 righe centrate)
    righe = spezza_righe(draw, item["titolo_breve"], f_title, max_w=920, max_righe=2)
    ty = 710 if len(righe) == 2 else 735
    for r in righe:
        h_r = disegna_testo_centrato(draw, r, cx, ty, f_title, COL_WHITE)
        ty += h_r + 12

    # Box prezzo sopra la safe zone di TikTok
    pbox = (70, 842, 1010, 1028)
    draw.rounded_rectangle(pbox, radius=28, fill=COL_NAVY_CARD, outline=COL_GOLD, width=2)

    old_str = formatta_euro(item["prezzo_vecchio"])
    new_str = formatta_euro(item["prezzo_nuovo"])
    save_str = f"RISPARMI {formatta_euro(item['risparmio'])}"

    old_x, old_y = 118, 874
    draw.text((old_x, old_y), old_str, font=f_old, fill=COL_MUTED)
    ob = draw.textbbox((old_x, old_y), old_str, font=f_old)
    mid_y = (ob[1] + ob[3]) // 2
    draw.line([(ob[0] - 6, mid_y), (ob[2] + 6, mid_y)], fill=COL_RED, width=4)

    draw.text((118, 922), new_str, font=f_new, fill=COL_GOLD)

    sw, sh = misura_testo(draw, save_str, f_save)
    sx1 = 965
    sx0 = sx1 - sw - 42
    sy0 = 906
    sy1 = sy0 + sh + 28
    draw.rounded_rectangle([sx0, sy0, sx1, sy1], radius=24, fill=COL_GREEN_BG)
    draw.text((sx0 + 21, sy0 + 12), save_str, font=f_save, fill=COL_GREEN_TXT)

    disegna_testo_centrato(draw, f"Rivenditore autorizzato: {item['negozio']}", cx, 1054, f_store, COL_MUTED)
    footer_txt = "Radar Orologi & Offerte  •  Scorri >>>" if numero < totale else "Radar Orologi & Offerte  •  Link nell'ultima slide >>>"
    disegna_testo_centrato(draw, footer_txt, cx, 1102, f_foot, COL_GOLD_SOFT)

    return jpg_bytes(img)


def disegna_barra_ricerca_telegram(draw, handle_canale, y_top=758):
    bx0, by0, bx1, by1 = 124, y_top, 956, y_top + 104
    draw.rounded_rectangle([bx0, by0, bx1, by1], radius=52, fill=COL_WHITE)

    lcx, lcy = bx0 + 56, by0 + 48
    draw.ellipse([lcx - 16, lcy - 16, lcx + 16, lcy + 16], outline=COL_NAVY, width=5)
    draw.line([(lcx + 11, lcy + 11), (lcx + 24, lcy + 24)], fill=COL_NAVY, width=6)

    tcx, tcy, tr = bx1 - 54, (by0 + by1) // 2, 34
    draw.ellipse([tcx - tr, tcy - tr, tcx + tr, tcy + tr], fill=COL_TG_BLUE)
    plane = [
        (tcx + 16, tcy - 14),
        (tcx - 19, tcy - 1),
        (tcx - 5, tcy + 4),
        (tcx + 8, tcy + 15),
    ]
    draw.polygon(plane, fill=COL_WHITE)
    draw.line([(tcx + 14, tcy - 12), (tcx - 5, tcy + 4)], fill=COL_TG_BLUE, width=2)

    f_search = ottieni_font_adattato(draw, handle_canale, max_w=600, size_iniziale=38, size_min=24, bold=True)
    _, th = misura_testo(draw, handle_canale, f_search)
    draw.text((bx0 + 104, (by0 + by1 - th) // 2 - 4), handle_canale, font=f_search, fill=COL_NAVY)


def genera_slide_cta(handle_canale):
    img, draw = crea_sfondo_radar()
    cx = 540

    f_pill = ottieni_font(25, bold=True)
    f_h1 = ottieni_font(58, bold=True)
    f_item = ottieni_font(30, bold=False)
    f_label = ottieni_font(24, bold=True)
    f_bio = ottieni_font(26, bold=True)
    f_note = ottieni_font(26, bold=False)

    disegna_pill(
        draw, "RADAR AUTOMATICO 24/7", cx, 84, f_pill,
        COL_NAVY_CARD, COL_GOLD, pad_x=38, pad_y=13, outline=COL_GOLD_SOFT,
    )

    disegna_testo_centrato(draw, "VUOI I LINK DIRETTI", cx, 182, f_h1, COL_WHITE)
    disegna_testo_centrato(draw, "DI QUESTI OROLOGI?", cx, 260, f_h1, COL_GOLD)

    punti = [
        "Sconti reali su Hamilton, Tissot, Seiko, Longines",
        "Avvisi di restock, nuovi drop ed edizioni limitate",
        "Solo Amazon e rivenditori autorizzati in Euro",
        "Canale gratuito e senza spam",
    ]
    py = 376
    for testo in punti:
        draw.ellipse([105, py + 11, 121, py + 27], fill=COL_GOLD)
        draw.text((146, py), testo, font=f_item, fill=COL_WHITE)
        py += 66

    draw.rounded_rectangle([84, 678, 996, 956], radius=34, fill=COL_NAVY_CARD, outline=COL_GOLD, width=3)
    disegna_testo_centrato(draw, "CERCA IL CANALE SU TELEGRAM", cx, 710, f_label, COL_GOLD)
    disegna_barra_ricerca_telegram(draw, handle_canale, y_top=758)
    disegna_testo_centrato(draw, "Oppure clicca il link diretto in bio", cx, 892, f_bio, COL_WHITE)

    disegna_testo_centrato(draw, "Quale dei 3 metteresti al polso? Scrivilo nei commenti", cx, 1006, f_note, COL_WHITE)
    disegna_testo_centrato(draw, "Salva il post per ritrovare questi modelli", cx, 1058, f_note, COL_MUTED)

    return jpg_bytes(img)


# ==========================================
# INVIO TELEGRAM (ALBUM + DIDASCALIA PRONTA)
# ==========================================
def invia_album_telegram(token, chat_id, slides_bytes, caption_album):
    boundary = f"----TelegramAlbum{uuid.uuid4().hex}"
    media = []
    for i in range(len(slides_bytes)):
        voce = {"type": "photo", "media": f"attach://slide{i}"}
        if i == 0:
            voce["caption"] = caption_album
            voce["parse_mode"] = "HTML"
        media.append(voce)

    body = bytearray()
    for key, val in [("chat_id", chat_id), ("media", json.dumps(media))]:
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
        body.extend(str(val).encode("utf-8"))
        body.extend(b"\r\n")

    for i, raw in enumerate(slides_bytes):
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="slide{i}"; filename="slide_{i + 1}.jpg"\r\n'.encode("utf-8"))
        body.extend(b"Content-Type: image/jpeg\r\n\r\n")
        body.extend(raw)
        body.extend(b"\r\n")

    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMediaGroup",
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=35) as resp:
            resp.read()
        return True
    except urllib.error.HTTPError as e:
        print(f"Errore sendMediaGroup HTTP {e.code}: {e.read().decode('utf-8', errors='ignore')}")
        return False
    except Exception as e:
        print(f"Errore sendMediaGroup: {e}")
        return False


def invia_messaggio_telegram(token, chat_id, testo_html):
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": testo_html,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()
        return True
    except urllib.error.HTTPError as e:
        print(f"Errore sendMessage HTTP {e.code}: {e.read().decode('utf-8', errors='ignore')}")
        return False
    except Exception as e:
        print(f"Errore sendMessage: {e}")
        return False


def costruisci_didascalia_social(orologi, handle_canale):
    righe_modelli = []
    hashtag_marche = []
    for i, item in enumerate(orologi, start=1):
        righe_modelli.append(
            f"{i}. {item['marca']} {item['titolo_breve']} -> "
            f"{formatta_euro(item['prezzo_nuovo'])} anziché {formatta_euro(item['prezzo_vecchio'])} (-{item['sconto_pct']:.0f}%)"
        )
        tag_m = re.sub(r"[^a-z0-9]", "", item["marca"].lower())
        if tag_m:
            hashtag_marche.append(f"#{tag_m}")

    modelli_txt = "\n".join(righe_modelli)
    tags_extra = " ".join(dict.fromkeys(hashtag_marche))

    caption_pronta = (
        f"3 orologi selezionati in offerta oggi (prezzi verificati in Euro) ⌚🔥\n\n"
        f"{modelli_txt}\n\n"
        f"Quale metteresti al polso tra questi 3? Scrivilo nei commenti 👇\n"
        f"📲 Link diretti e avvisi 24/7 sul canale Telegram in bio ({handle_canale})\n\n"
        f"#orologi #orologeria #orologiuomo #offerte #sconti {tags_extra} #watchcommunity"
    )

    righe_link = "\n".join(
        f"• <b>{html.escape(it['marca'])}</b>: <a href=\"{html.escape(it['url'], quote=True)}\">{html.escape(it['negozio'])}</a>"
        for it in orologi
    )

    return (
        f"📋 <b>DIDASCALIA PRONTA (tocca per copiare):</b>\n\n"
        f"<pre>{html.escape(caption_pronta)}</pre>\n\n"
        f"🔗 <b>Link di controllo per te:</b>\n{righe_link}"
    )


def main():
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    admin_id = os.environ.get("TELEGRAM_ADMIN_ID", "").strip()
    channel_env = os.environ.get("TELEGRAM_CHANNEL", "").strip()

    if not token or not admin_id:
        print("Mancano TELEGRAM_TOKEN o TELEGRAM_ADMIN_ID nei Secrets di GitHub.")
        return

    if channel_env and not channel_env.lstrip("-").isdigit():
        handle_canale = channel_env if channel_env.startswith("@") else f"@{channel_env}"
    else:
        handle_canale = NOME_CANALE

    stato = carica_stato()
    usati_set = set(stato.get("usati", []))

    print("1) Ricerca migliori offerte in Euro della giornata...")
    candidati, sessioni = raccogli_candidati(usati_set)
    scelti = seleziona_orologi_carosello(candidati, sessioni, quantita=NUM_OROLOGI)

    if len(scelti) < NUM_OROLOGI:
        print(f"Trovati solo {len(scelti)} orologi validi: annullo generazione carosello.")
        return

    print("2) Generazione delle 5 slide grafiche (1080x1350)...")
    slides = [genera_slide_copertina(scelti)]
    for idx, item in enumerate(scelti, start=1):
        slides.append(genera_slide_orologio(item, idx, totale=NUM_OROLOGI))
    slides.append(genera_slide_cta(handle_canale))

    print("3) Invio bozza carosello in privato su Telegram...")
    titolo_album = f"🎨 <b>CAROSELLO SOCIAL PRONTO ({data_italia()})</b> — 5 slide (TikTok + Instagram)"
    ok_album = invia_album_telegram(token, admin_id, slides, titolo_album)

    if ok_album:
        testo_copia = costruisci_didascalia_social(scelti, handle_canale)
        invia_messaggio_telegram(token, admin_id, testo_copia)
        for item in scelti:
            if item["id"] not in stato["usati"]:
                stato["usati"].append(item["id"])
        salva_stato(stato)
        print("Carosello inviato con successo!")
    else:
        print("Invio album fallito: controlla di aver premuto /start in privato col bot e che TELEGRAM_ADMIN_ID sia corretto.")


if __name__ == "__main__":
    main()
