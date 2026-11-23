import html
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
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw

# ==========================================
# BOT OROLOGI 3-IN-1: AMAZON + PEPPER + RADAR
# ==========================================
FILE_STATO = "pubblicati.json"
NOME_CANALE = "Radar Orologi & Offerte"
MAX_POST_PER_GIRO = 2             # Massimo 2 post ogni 30 min
MAX_STORICO_ASIN = 500
MAX_STORICO_RADAR = 500

# Soglie offerte Amazon
SCONTO_MINIMO_AMAZON_PCT = 6.0
RISPARMIO_MINIMO_AMAZON_EUR = 10.0

# Soglie Radar rivenditori ufficiali / brand
SCONTO_MINIMO_RADAR_PCT = 10.0
PREZZO_MINIMO_RADAR = 35.0
MAX_LIMITED_CATALOGO_PER_FONTE = 2

# 1) Feed CamelCamelCamel (solo 3 con pausa -> zero errori 429)
CCC_FEED_URLS = [
    "https://it.camelcamelcamel.com/top_drops/feed?t=recent&s=relative&i=7&bn=orologi&d=1",
    "https://it.camelcamelcamel.com/top_drops/feed?t=recent&s=relative&i=1&bn=moda&d=1",
    "https://it.camelcamelcamel.com/top_drops/feed?t=recent&s=relative&i=1&bn=elettronica&d=1",
]

# 2) Feed Pepper.it (offerte Amazon.it segnalate dagli utenti)
PEPPER_FEED_URLS = [
    "https://www.pepper.it/rss/search?q=seiko",
    "https://www.pepper.it/rss/search?q=casio",
    "https://www.pepper.it/rss/search?q=citizen",
    "https://www.pepper.it/rss/search?q=tissot",
    "https://www.pepper.it/rss/search?q=hamilton",
    "https://www.pepper.it/rss/search?q=orologio",
]

# 3) Radar: D1 Milano + Baltic + Rivenditori autorizzati italiani (Hamilton, Tissot, Seiko, Citizen, Casio)
RADAR_FONTI = [
    {
        "negozio": "D1 Milano",
        "base_url": "https://d1milano.com",
        "collezioni": [""],
        "filtra_marche": False,
        "valuta": "€",
    },
    {
        "negozio": "Baltic",
        "base_url": "https://baltic-watches.com",
        "collezioni": [""],
        "filtra_marche": False,
        "valuta": "€",
    },
    {
        "negozio": "Orafo La Morgia",
        "base_url": "https://www.orafolamorgia.it",
        "collezioni": ["hamilton", "tissot", "seiko"],
        "filtra_marche": True,
        "valuta": "€",
    },
    {
        "negozio": "Ferrari Luca Gioielli",
        "base_url": "https://ferrarilucagioielli.it",
        "collezioni": ["hamilton", "tissot", "seiko", "citizen", "orologi-casio"],
        "filtra_marche": True,
        "valuta": "€",
    },
    {
        "negozio": "2B Gioielli",
        "base_url": "https://2bgioielli.it",
        "collezioni": ["orologi-eleganti", "citizen", "orologi"],
        "filtra_marche": True,
        "valuta": "€",
    },
]

# Marchi ammessi dal Radar sui rivenditori multimarca
MARCHE_TOP_RADAR = [
    "hamilton", "tissot", "seiko", "casio", "g-shock", "gshock", "edifice",
    "citizen", "orient", "bulova", "longines", "mido", "certina", "oris",
    "frederique constant", "eberhard", "tag heuer", "tudor", "omega",
    "d1 milano", "baltic", "swatch", "timex", "garmin", "suunto",
]

# Marchi/parole valide per Amazon e Pepper
PAROLE_OROLOGI_AMAZON = [
    "seiko", "casio", "g-shock", "gshock", "edifice", "citizen", "orient",
    "tissot", "hamilton", "timex", "bulova", "swatch", "longines", "mido",
    "certina", "oris", "frederique constant", "d1 milano", "baltic",
    "suunto", "garmin", "polar", "mondaine", "junghans", "glycine",
    "festina", "sector", "breil", "locman", "philip watch", "bering",
    "orologio", "orologi", "cronografo", "chronograph", "smartwatch",
]

PAROLE_VIETATE_AMAZON = [
    "compatibile con", "cinturino per", "cinturini per",
    "cinturino di ricambio", "cinturino compatibile", "cinturini compatibili",
    "vetro temperato", "pellicola", "protezione schermo", "screen protector",
    "cover", "custodia", "ricambio", "caricatore", "caricabatterie", "charger",
    "cavo di ricarica", "supporto di ricarica", "scatola porta orologi",
    "porta orologi", "kit riparazione", "parete", "muro", "sveglia", "tavolo",
    "comodino", "calcolatrice", "tastiera", "pianoforte", "stampante",
    "etichettatrice", "toner", "cartuccia", "figurine", "pupazzo", "giocattolo",
    "giocattoli", "jouets", "lego", "libro", "portafoglio", "borsa", "zaino",
    "occhiali", "profumo", "collana", "anello", "orecchini", "cintura",
    "scarpe", "stivali", "maglietta", "t-shirt", "felpa", "giacca",
    "pantaloni", "sneakers", "jeans", "camicia", "mutande", "boxer", "calzini",
    "iphone", "ipad", "airpods", "attrezzi", "ps4", "ps5", "xbox", "nintendo",
    "dvd", "blu-ray", "cuffie", "auricolari",
]

# Blocca gioielli e accessori sui siti delle gioiellerie
PAROLE_VIETATE_RADAR = [
    "strap", "straps", "cinturino", "cinturini", "buckle", "clasp", "fibbia",
    "pouch", "watch roll", "roll", "travel case", "scatola", "astuccio",
    "tool", "spring bar", "bezel insert", "link", "links", "maglia",
    "collana", "collane", "anello", "anelli", "fedina", "solitario", "trilogy",
    "orecchini", "orecchino", "bracciale", "bracciali", "ciondolo", "charm",
    "pendente", "gemelli", "spilla", "pandora", "dodo", "miluna", "stroili",
    "cap", "hat", "t-shirt", "shirt", "hoodie", "jacket", "gift card",
    "voucher", "buono regalo", "book", "magazine", "poster", "print",
    "accessory", "accessories", "accessori", "servicing", "warranty",
    "polishing", "cloth", "wallet", "portafoglio", "keyring", "portachiavi",
    "stand", "sveglia", "parete", "muro",
]

PAROLE_LIMITED = [
    "limited", "edition", "edizione limitata", "special edition",
    "numbered", "collab", "collaboration", "exclusive", "esclusiva",
    "anniversary", "collector", "capsule", "murph", "alpinist",
]

HEADERS_WEB = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
}


def ora_italia():
    try:
        return datetime.now(ZoneInfo("Europe/Rome")).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return datetime.now().strftime("%d/%m/%Y %H:%M")


def carica_stato():
    base = {
        "asin": [],
        "radar_postati": [],
        "radar_stock": {},
        "radar_inizializzati": [],
    }
    if not os.path.exists(FILE_STATO):
        return base
    try:
        with open(FILE_STATO, "r", encoding="utf-8") as f:
            dati = json.load(f)
        if isinstance(dati, list):
            base["asin"] = dati
            return base
        if isinstance(dati, dict):
            base["asin"] = dati.get("asin", [])
            base["radar_postati"] = dati.get("radar_postati", [])
            base["radar_stock"] = dati.get("radar_stock", {})
            base["radar_inizializzati"] = dati.get("radar_inizializzati", [])
            return base
    except Exception as e:
        print(f"Errore lettura {FILE_STATO}: {e}")
    return base


def salva_stato(stato):
    stato["asin"] = stato["asin"][-MAX_STORICO_ASIN:]
    stato["radar_postati"] = stato["radar_postati"][-MAX_STORICO_RADAR:]
    with open(FILE_STATO, "w", encoding="utf-8") as f:
        json.dump(stato, f, indent=2, ensure_ascii=False)


def contiene_parola(testo, lista_parole):
    for parola in lista_parole:
        if re.search(r"\b" + re.escape(parola.strip()) + r"\b", testo, flags=re.IGNORECASE):
            return parola
    return None


def e_un_orologio_amazon(titolo):
    vietata = contiene_parola(titolo, PAROLE_VIETATE_AMAZON)
    if vietata:
        return False, f"scartato per '{vietata}'"
    trovata = contiene_parola(titolo, PAROLE_OROLOGI_AMAZON)
    if trovata:
        return True, f"ok ('{trovata}')"
    return False, "non è un orologio"


def e_accessorio_o_gioiello(titolo, product_type=""):
    testo = f"{titolo} {product_type}".strip()
    return contiene_parola(testo, PAROLE_VIETATE_RADAR) is not None


def trova_marca_top(titolo, vendor=""):
    testo = f"{vendor} {titolo}".strip()
    trovata = contiene_parola(testo, MARCHE_TOP_RADAR)
    if not trovata:
        return None
    if trovata.lower() in ("g-shock", "gshock"):
        return "Casio G-Shock"
    if trovata.lower() == "d1 milano":
        return "D1 Milano"
    return trovata.title()


def e_edizione_limitata(titolo, tags=""):
    testo = f"{titolo} {tags}".lower()
    for p in PAROLE_LIMITED:
        if p in testo:
            return True
    return False


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


def formatta_prezzo(valore, valuta="€"):
    num = f"{valore:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if valuta == "$":
        return f"${num}"
    return f"{num}€"


def estrai_asin(testo):
    if not testo:
        return None
    m = re.search(r"/(?:product|dp|gp/product)/([A-Z0-9]{10})", testo)
    if m:
        return m.group(1)
    m = re.search(r"\b(B0[A-Z0-9]{8})\b", testo)
    return m.group(1) if m else None


def costruisci_link_amazon(asin, tag):
    base = f"https://www.amazon.it/dp/{asin}"
    if tag:
        return f"{base}?tag={urllib.parse.quote(tag)}"
    return base


def estrai_codice_modello(testo):
    """Cerca la referenza dell'orologio (es. H64655941, T137.407.11.041.00, SRPD55K1, GA-2100-1A1ER)."""
    if not testo:
        return None
    tokens = re.findall(r"\b[A-Za-z0-9][A-Za-z0-9.\-]{4,22}\b", testo)
    for tok in reversed(tokens):
        pulito = tok.strip(".-")
        if len(pulito) < 5:
            continue
        # Scarta misure (42mm, 100m, 10atm, 20bar) e parole lunghe tipo "Edition-2026"
        if re.fullmatch(r"\d+(?:[.,]\d+)?(?:mm|cm|m|atm|bar|hz|g|gr|h|l|v)", pulito, flags=re.IGNORECASE):
            continue
        if re.search(r"[A-Za-z]{5,}", pulito):
            continue
        ha_lettere = bool(re.search(r"[A-Za-z]", pulito))
        num_cifre = len(re.findall(r"\d", pulito))
        if ha_lettere and num_cifre >= 2:
            return pulito
    return None


def costruisci_link_ricerca_amazon(titolo, marca, sku, tag):
    """Genera il link di ricerca su Amazon.it con codice modello (o nome pulito) + tag affiliato."""
    codice = estrai_codice_modello(titolo) or estrai_codice_modello(sku)
    if codice:
        if marca and marca.lower() not in codice.lower():
            query = f"{marca} {codice}"
        else:
            query = codice
    else:
        pulito = re.sub(r"[|•/]+", " ", titolo or "")
        pulito = re.sub(r"\s+", " ", pulito).strip()
        parole = [
            p for p in pulito.split()
            if p.lower() not in ("orologio", "orologi", "uomo", "donna", "unisex", "-")
        ]
        query = " ".join(parole[:6]).strip()
        if marca and marca.lower() not in query.lower():
            query = f"{marca} {query}".strip()

    base = f"https://www.amazon.it/s?k={urllib.parse.quote_plus(query)}"
    if tag:
        return f"{base}&tag={urllib.parse.quote(tag)}"
    return base


def versioni_hd_amazon(url):
    candidati = []
    hd = re.sub(r"\._[^/]+_\.(jpg|jpeg|png|webp)", r"._AC_SL1000_.\1", url, flags=re.IGNORECASE)
    if hd != url:
        candidati.append(hd)
    candidati.append(url)
    return candidati


def scarica_immagine_valida(url):
    if not url:
        return None
    req = urllib.request.Request(url, headers=HEADERS_WEB)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        if len(data) < 1500:
            return None
        img = Image.open(io.BytesIO(data))
        if img.width < 80 or img.height < 80:
            return None
        return data
    except Exception:
        return None


def recupera_foto_amazon(asin, desc_html="", extra_img=None):
    candidati = []
    titolo_completo = None

    if extra_img:
        candidati.append(extra_img)

    desc_pulita = html.unescape(desc_html or "")
    for m in re.finditer(r"https://(?:m\.media-amazon\.com|images-[a-z]+\.ssl-images-amazon\.com)/images/I/[^\"'\s<>]+", desc_pulita):
        candidati.extend(versioni_hd_amazon(m.group(0)))

    url_ccc = f"https://it.camelcamelcamel.com/product/{asin}"
    req = urllib.request.Request(url_ccc, headers=HEADERS_WEB)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            pagina = resp.read().decode("utf-8", errors="ignore")

        m_title = re.search(r"<title>([^<]+)</title>", pagina, flags=re.IGNORECASE)
        if m_title:
            t = html.unescape(m_title.group(1)).split("|")[0].strip()
            if len(t) > 12 and "camelcamelcamel" not in t.lower():
                titolo_completo = t

        m_og = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', pagina, flags=re.IGNORECASE)
        if m_og and "amazon" in m_og.group(1):
            candidati.extend(versioni_hd_amazon(m_og.group(1)))

        for m in re.finditer(r"https://(?:m\.media-amazon\.com|images-[a-z]+\.ssl-images-amazon\.com)/images/I/[^\"'\s<>]+", pagina):
            u = m.group(0)
            if "sprite" not in u.lower():
                candidati.extend(versioni_hd_amazon(u))
    except Exception:
        pass

    candidati.extend([
        f"https://images-eu.ssl-images-amazon.com/images/P/{asin}.01._SCLZZZZZZZ_.jpg",
        f"https://images-na.ssl-images-amazon.com/images/P/{asin}.01._SCLZZZZZZZ_.jpg",
        f"https://images-eu.ssl-images-amazon.com/images/P/{asin}.01.LZZZZZZZ.jpg",
    ])

    visti = set()
    for url in candidati:
        if not url or url in visti:
            continue
        visti.add(url)
        raw = scarica_immagine_valida(url)
        if raw:
            return raw, titolo_completo

    return None, titolo_completo


def crea_scheda_grafica(raw_bytes):
    """Monta la foto prodotto pulita su una scheda bianca 16:9 senza logo."""
    canvas_w, canvas_h = 1200, 675
    sfondo = Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 255))

    foto = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
    max_w, max_h = 1060, 570
    foto.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)

    pos_x = (canvas_w - foto.width) // 2
    pos_y = (canvas_h - foto.height) // 2
    sfondo.paste(foto, (pos_x, pos_y), foto)

    draw = ImageDraw.Draw(sfondo)
    draw.rectangle([0, 0, canvas_w - 1, canvas_h - 1], outline=(226, 232, 240, 255), width=6)

    output = io.BytesIO()
    sfondo.convert("RGB").save(output, format="JPEG", quality=92)
    return output.getvalue()


# ==========================================
# FONTE 1: CAMELCAMELCAMEL (AMAZON.IT)
# ==========================================
def analizza_titolo_ccc(titolo_grezzo, desc_html=""):
    testo = f"{titolo_grezzo} {html.unescape(desc_html or '')}"

    sconto_pct = None
    m_pct = re.search(r"(?:down\s+|\()([\d.,]+)%", testo, flags=re.IGNORECASE)
    if m_pct:
        sconto_pct = parse_numero(m_pct.group(1))

    risparmio = None
    m_risp = re.search(r"(?:down\s+|\()([\d.,]+)\s*€", testo, flags=re.IGNORECASE)
    if m_risp:
        risparmio = parse_numero(m_risp.group(1))

    prezzo_nuovo = None
    m_nuovo = re.search(r"\bto\s+([\d.,]+)\s*€", testo, flags=re.IGNORECASE)
    if m_nuovo:
        prezzo_nuovo = parse_numero(m_nuovo.group(1))

    prezzo_vecchio = None
    m_vecchio = re.search(r"\bfrom\s+([\d.,]+)\s*€", testo, flags=re.IGNORECASE)
    if m_vecchio:
        prezzo_vecchio = parse_numero(m_vecchio.group(1))

    if prezzo_nuovo is not None and prezzo_vecchio is None and risparmio is not None:
        prezzo_vecchio = round(prezzo_nuovo + risparmio, 2)

    if sconto_pct is None and prezzo_nuovo and prezzo_vecchio and prezzo_vecchio > prezzo_nuovo:
        sconto_pct = round(((prezzo_vecchio - prezzo_nuovo) / prezzo_vecchio) * 100.0, 2)

    titolo_pulito = re.split(r"\s*-\s*down\s+", titolo_grezzo, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    return titolo_pulito, sconto_pct, risparmio, prezzo_nuovo, prezzo_vecchio


def raccogli_da_ccc(asin_gia_postati, forza_test=False):
    candidati = []
    visti = set()
    print("--- [1/3] Controllo CamelCamelCamel Italia ---")

    for idx, url in enumerate(CCC_FEED_URLS):
        if idx > 0:
            time.sleep(3.0)
        req = urllib.request.Request(url, headers=HEADERS_WEB)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                xml_data = resp.read()
        except Exception as e:
            print(f"  CCC feed {idx + 1} errore: {e}")
            continue

        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError:
            continue

        items = root.findall(".//item")
        trovati = 0
        for item in items:
            titolo_grezzo = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            guid = (item.findtext("guid") or "").strip()
            desc = (item.findtext("description") or "").strip()

            titolo_pulito, sconto_pct, risparmio, p_nuovo, p_vecchio = analizza_titolo_ccc(titolo_grezzo, desc)
            valido, _ = e_un_orologio_amazon(titolo_pulito)
            if not valido:
                continue

            if sconto_pct is not None or risparmio is not None:
                ok_pct = sconto_pct is not None and sconto_pct >= SCONTO_MINIMO_AMAZON_PCT
                ok_eur = risparmio is not None and risparmio >= RISPARMIO_MINIMO_AMAZON_EUR
                if not (ok_pct or ok_eur):
                    continue

            asin = estrai_asin(f"{link} {guid} {desc}")
            if not asin or asin in visti:
                continue
            if not forza_test and asin in asin_gia_postati:
                continue

            visti.add(asin)
            trovati += 1
            candidati.append({
                "tipo": "AMAZON",
                "priorita": 1,
                "id_univoco": asin,
                "titolo": titolo_pulito,
                "marca": "Amazon",
                "sku": "",
                "prezzo_nuovo": p_nuovo,
                "prezzo_vecchio": p_vecchio,
                "sconto_pct": sconto_pct,
                "valuta": "€",
                "desc_html": desc,
                "img_url": None,
                "negozio": "Amazon",
            })

        print(f"  CCC feed {idx + 1}: {len(items)} elementi | {trovati} nuovi orologi")

    return candidati


# ==========================================
# FONTE 2: PEPPER.IT (OFFERTE AMAZON ITALIA)
# ==========================================
def estrai_immagine_rss(item, desc_html):
    for child in item:
        tag = child.tag.lower()
        if tag.endswith("content") or tag.endswith("enclosure") or tag.endswith("thumbnail"):
            u = child.attrib.get("url")
            if u and u.startswith("http"):
                return u
    m = re.search(r'<img[^>]+src=["\'](https?://[^"\']+)["\']', desc_html or "")
    return m.group(1) if m else None


def cerca_asin_su_pepper(link_pepper, desc_html):
    asin = estrai_asin(desc_html)
    if asin:
        return asin
    if not link_pepper:
        return None
    req = urllib.request.Request(link_pepper, headers=HEADERS_WEB)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            pagina = resp.read().decode("utf-8", errors="ignore")
        if "amazon.it" not in pagina.lower():
            return None
        return estrai_asin(pagina)
    except Exception:
        return None


def raccogli_da_pepper(asin_gia_postati, forza_test=False):
    candidati = []
    visti = set()
    print("--- [2/3] Controllo Pepper.it (offerte Amazon) ---")

    for idx, url in enumerate(PEPPER_FEED_URLS):
        if idx > 0:
            time.sleep(1.5)
        req = urllib.request.Request(url, headers=HEADERS_WEB)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                xml_data = resp.read()
        except urllib.error.HTTPError as e:
            print(f"  Pepper feed {idx + 1} bloccato (HTTP {e.code}) - salto Pepper.")
            if e.code in (403, 429):
                break
            continue
        except Exception as e:
            print(f"  Pepper feed {idx + 1} errore: {e}")
            continue

        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError:
            continue

        items = root.findall(".//item")[:10]
        trovati = 0
        for item in items:
            titolo = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = (item.findtext("description") or "").strip()

            valido, _ = e_un_orologio_amazon(titolo)
            if not valido:
                continue

            merchant_ok = "amazon" in f"{titolo} {desc}".lower()
            for child in item:
                if "merchant" in child.tag.lower() and "amazon" in (child.attrib.get("name", "") + (child.text or "")).lower():
                    merchant_ok = True
            if not merchant_ok:
                continue

            asin = cerca_asin_su_pepper(link, desc)
            if not asin or asin in visti:
                continue
            if not forza_test and asin in asin_gia_postati:
                continue

            p_nuovo = None
            for child in item:
                if "merchant" in child.tag.lower() and child.attrib.get("price"):
                    p_nuovo = parse_numero(child.attrib.get("price"))
            if p_nuovo is None:
                m_eur = re.search(r"(\d+(?:[.,]\d{1,2})?)\s*€", titolo)
                if m_eur:
                    p_nuovo = parse_numero(m_eur.group(1))

            visti.add(asin)
            trovati += 1
            candidati.append({
                "tipo": "AMAZON",
                "priorita": 1,
                "id_univoco": asin,
                "titolo": titolo,
                "marca": "Amazon",
                "sku": "",
                "prezzo_nuovo": p_nuovo,
                "prezzo_vecchio": None,
                "sconto_pct": None,
                "valuta": "€",
                "desc_html": desc,
                "img_url": estrai_immagine_rss(item, desc),
                "negozio": "Amazon",
            })

        print(f"  Pepper feed {idx + 1}: {len(items)} letti | {trovati} orologi Amazon nuovi")

    return candidati


# ==========================================
# FONTE 3: RADAR (D1 MILANO, BALTIC, HAMILTON, TISSOT, SEIKO, CITIZEN, CASIO)
# ==========================================
def raccogli_da_radar(stato, forza_test=False):
    candidati = []
    radar_stock = stato["radar_stock"]
    radar_postati = set(stato["radar_postati"])
    inizializzati = set(stato["radar_inizializzati"])
    stato_modificato = False

    print("--- [3/3] Controllo Radar (D1 Milano, Baltic, Hamilton, Tissot, Seiko, Citizen, Casio) ---")

    for fonte in RADAR_FONTI:
        nome_negozio = fonte["negozio"]
        base_url = fonte["base_url"].rstrip("/")
        valuta = fonte["valuta"]
        filtra_marche = fonte["filtra_marche"]

        prima_volta = nome_negozio not in inizializzati
        limited_aggiunti = 0
        trovati_negozio = 0
        totale_prodotti_negozio = 0
        visti_nel_negozio = set()
        almeno_una_risposta = False

        for col in fonte["collezioni"]:
            if col:
                url_json = f"{base_url}/collections/{col}/products.json?limit=60"
            else:
                url_json = f"{base_url}/products.json?limit=60"

            time.sleep(0.4)
            req = urllib.request.Request(url_json, headers=HEADERS_WEB)
            try:
                with urllib.request.urlopen(req, timeout=18) as resp:
                    dati = json.loads(resp.read().decode("utf-8", errors="ignore"))
                almeno_una_risposta = True
            except Exception as e:
                print(f"  Radar {nome_negozio} ({col or 'catalogo'}): errore ({e})")
                continue

            prodotti = dati.get("products", [])
            totale_prodotti_negozio += len(prodotti)

            for prod in prodotti:
                prod_id = prod.get("id")
                if not prod_id or prod_id in visti_nel_negozio:
                    continue
                visti_nel_negozio.add(prod_id)

                titolo = (prod.get("title") or "").strip()
                handle = (prod.get("handle") or "").strip()
                vendor = (prod.get("vendor") or "").strip()
                ptype = (prod.get("product_type") or "").strip()
                tags_raw = prod.get("tags", [])
                tags = " ".join(tags_raw) if isinstance(tags_raw, list) else str(tags_raw)

                if not titolo or not handle:
                    continue
                if e_accessorio_o_gioiello(titolo, ptype):
                    continue

                if filtra_marche:
                    marca = trova_marca_top(titolo, vendor)
                    if not marca:
                        continue
                else:
                    marca = nome_negozio

                variants = prod.get("variants") or []
                if not variants:
                    continue

                disponibili = [v for v in variants if v.get("available")]
                disponibile = len(disponibili) > 0
                v_ref = disponibili[0] if disponibili else variants[0]

                p_nuovo = parse_numero(v_ref.get("price"))
                p_vecchio = parse_numero(v_ref.get("compare_at_price"))
                if p_nuovo is None or p_nuovo < PREZZO_MINIMO_RADAR:
                    continue

                sconto_pct = None
                if p_vecchio and p_vecchio > p_nuovo:
                    sconto_pct = round(((p_vecchio - p_nuovo) / p_vecchio) * 100.0, 1)

                images = prod.get("images") or []
                img_url = images[0].get("src") if images else None
                if not img_url:
                    continue

                pid = f"{nome_negozio}:{prod_id}"
                era_noto = pid in radar_stock
                era_disponibile = radar_stock.get(pid, False)

                if not era_noto or era_disponibile != disponibile:
                    radar_stock[pid] = disponibile
                    stato_modificato = True

                if not disponibile:
                    continue

                url_prodotto = f"{base_url}/products/{handle}"
                is_limited = e_edizione_limitata(titolo, tags)
                is_sconto = sconto_pct is not None and sconto_pct >= SCONTO_MINIMO_RADAR_PCT

                tipo_evento = None
                priorita = 9

                if not prima_volta and era_noto and not era_disponibile:
                    tipo_evento = "RADAR_RESTOCK"
                    priorita = 2
                elif not prima_volta and not era_noto:
                    tipo_evento = "RADAR_DROP"
                    priorita = 3
                elif is_sconto and (forza_test or pid not in radar_postati):
                    tipo_evento = "RADAR_SCONTO"
                    priorita = 4
                elif is_limited and (forza_test or pid not in radar_postati):
                    if limited_aggiunti < MAX_LIMITED_CATALOGO_PER_FONTE:
                        tipo_evento = "RADAR_LIMITED"
                        priorita = 5
                        limited_aggiunti += 1

                if tipo_evento:
                    trovati_negozio += 1
                    candidati.append({
                        "tipo": tipo_evento,
                        "priorita": priorita,
                        "id_univoco": pid,
                        "titolo": titolo,
                        "marca": marca,
                        "sku": (v_ref.get("sku") or "").strip(),
                        "prezzo_nuovo": p_nuovo,
                        "prezzo_vecchio": p_vecchio if is_sconto else None,
                        "sconto_pct": sconto_pct if is_sconto else None,
                        "valuta": valuta,
                        "url": url_prodotto,
                        "img_url": img_url,
                        "negozio": nome_negozio,
                    })

        if prima_volta and almeno_una_risposta:
            inizializzati.add(nome_negozio)
            stato_modificato = True

        print(f"  Radar {nome_negozio}: {totale_prodotti_negozio} letti | {trovati_negozio} segnalazioni")

    stato["radar_inizializzati"] = sorted(list(inizializzati))
    return candidati, stato_modificato


# ==========================================
# ORDINAMENTO + MESCOLAMENTO PER MARCHIO
# ==========================================
def ordina_e_mescola_candidati(candidati):
    """Priorità: Amazon -> Restock -> Drop -> Sconti -> Limited, alternando marchi diversi."""
    candidati.sort(key=lambda x: x["priorita"])
    unici = []
    visti_id = set()
    for c in candidati:
        if c["id_univoco"] in visti_id:
            continue
        visti_id.add(c["id_univoco"])
        unici.append(c)

    per_priorita = {}
    for c in unici:
        p = c["priorita"]
        marca = (c.get("marca") or c.get("negozio") or "Altro").lower()
        per_priorita.setdefault(p, {}).setdefault(marca, []).append(c)

    risultato = []
    for p in sorted(per_priorita.keys()):
        gruppi_marca = per_priorita[p]
        marche = list(gruppi_marca.keys())
        random.shuffle(marche)
        for m in marche:
            random.shuffle(gruppi_marca[m])

        while any(gruppi_marca[m] for m in marche):
            for m in marche:
                if gruppi_marca[m]:
                    risultato.append(gruppi_marca[m].pop(0))

    return risultato


# ==========================================
# INVIO TELEGRAM
# ==========================================
def invia_foto_su_telegram(token, channel, caption_html, bottoni, image_bytes):
    boundary = f"----TelegramBotBoundary{uuid.uuid4().hex}"
    tastiera = json.dumps({"inline_keyboard": bottoni})

    fields = {
        "chat_id": channel,
        "caption": caption_html,
        "parse_mode": "HTML",
        "reply_markup": tastiera,
    }

    body = bytearray()
    for key, val in fields.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
        body.extend(str(val).encode("utf-8"))
        body.extend(b"\r\n")

    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(b'Content-Disposition: form-data; name="photo"; filename="orologio.jpg"\r\n')
    body.extend(b"Content-Type: image/jpeg\r\n\r\n")
    body.extend(image_bytes)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    url_api = f"https://api.telegram.org/bot{token}/sendPhoto"
    req = urllib.request.Request(
        url_api,
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            resp.read()
        return True
    except urllib.error.HTTPError as e:
        print(f"Errore Telegram HTTP {e.code}: {e.read().decode('utf-8', errors='ignore')}")
        return False
    except Exception as e:
        print(f"Errore Telegram: {e}")
        return False


def formatta_messaggio(item, url_finale, titolo_finale, amazon_tag=""):
    titolo_esc = html.escape(titolo_finale)
    url_esc = html.escape(url_finale, quote=True)
    negozio_esc = html.escape(item["negozio"])
    marca_esc = html.escape(item.get("marca") or item["negozio"])
    canale_esc = html.escape(NOME_CANALE)
    valuta = item["valuta"]

    p_nuovo = item.get("prezzo_nuovo")
    p_vecchio = item.get("prezzo_vecchio")
    pct = item.get("sconto_pct")

    if p_nuovo is not None and p_vecchio is not None and p_vecchio > p_nuovo:
        extra = f" (-{pct:.0f}%)" if pct else ""
        riga_prezzo = f"💰 <b>{formatta_prezzo(p_nuovo, valuta)} anziché {formatta_prezzo(p_vecchio, valuta)}!</b>{extra}"
    elif p_nuovo is not None:
        riga_prezzo = f"💰 <b>{formatta_prezzo(p_nuovo, valuta)}</b>"
    elif pct is not None:
        riga_prezzo = f"📉 <b>Calo di prezzo del -{pct:.0f}%!</b>"
    else:
        riga_prezzo = "📉 <b>Offerta attiva!</b>"

    if item["tipo"] == "AMAZON":
        caption = (
            f"⌚ <i>{titolo_esc}</i>\n\n"
            f"{riga_prezzo}\n"
            f"👉 <a href=\"{url_esc}\">Apri su Amazon</a>\n\n"
            f"⌚ Segnalata su {canale_esc} - #Ad"
        )
        bottoni = [[{"text": "⌚ Apri su Amazon", "url": url_finale}]]
        return caption, bottoni

    badge_map = {
        "RADAR_RESTOCK": f"🔥 <b>RESTOCK DISPONIBILE — {marca_esc}</b>",
        "RADAR_DROP": f"🚨 <b>NUOVO DROP — {marca_esc}</b>",
        "RADAR_SCONTO": f"📉 <b>OFFERTA — {marca_esc}</b>",
        "RADAR_LIMITED": f"✨ <b>EDIZIONE LIMITATA — {marca_esc}</b>",
    }
    badge = badge_map.get(item["tipo"], f"⌚ <b>{marca_esc}</b>")

    url_amazon_cerca = costruisci_link_ricerca_amazon(
        titolo_finale,
        item.get("marca") or "",
        item.get("sku") or "",
        amazon_tag,
    )
    suffisso_ad = " - #Ad" if amazon_tag else ""

    caption = (
        f"{badge}\n\n"
        f"⌚ <i>{titolo_esc}</i>\n\n"
        f"{riga_prezzo}\n"
        f"👉 <a href=\"{url_esc}\">Vedi su {negozio_esc}</a>\n\n"
        f"⌚ Segnalata su {canale_esc}{suffisso_ad}"
    )
    bottoni = [
        [{"text": f"⌚ Vedi su {item['negozio']}", "url": url_finale}],
        [{"text": "🛒 Cerca su Amazon", "url": url_amazon_cerca}],
    ]
    return caption, bottoni


def main():
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    channel = os.environ.get("TELEGRAM_CHANNEL", "").strip()
    amazon_tag = os.environ.get("AMAZON_TAG", "").strip()
    forza_test = os.environ.get("TEST_GRAFICA", "false").lower() == "true"

    if not token or not channel:
        print("Mancano TELEGRAM_TOKEN o TELEGRAM_CHANNEL nei Secrets di GitHub.")
        return

    if not channel.startswith("@") and not channel.lstrip("-").isdigit():
        channel = "@" + channel

    stato = carica_stato()
    asin_set = set(stato["asin"])

    candidati = []
    candidati.extend(raccogli_da_ccc(asin_set, forza_test))
    candidati.extend(raccogli_da_pepper(asin_set, forza_test))
    candidati_radar, stato_modificato = raccogli_da_radar(stato, forza_test)
    candidati.extend(candidati_radar)

    unici = ordina_e_mescola_candidati(candidati)
    print(f"Candidati totali pronti (priorità Amazon + mescolati): {len(unici)}")

    limite = 1 if forza_test else MAX_POST_PER_GIRO
    pubblicati_ora = 0
    saltati_senza_foto = 0

    for item in unici:
        if pubblicati_ora >= limite:
            break

        if item["tipo"] == "AMAZON":
            raw_img, titolo_pieno = recupera_foto_amazon(item["id_univoco"], item["desc_html"], item["img_url"])
            url_finale = costruisci_link_amazon(item["id_univoco"], amazon_tag)
            titolo_finale = titolo_pieno or item["titolo"]
        else:
            raw_img = scarica_immagine_valida(item["img_url"])
            url_finale = item["url"]
            titolo_finale = item["titolo"]

        if not raw_img:
            saltati_senza_foto += 1
            continue

        scheda_jpg = crea_scheda_grafica(raw_img)
        caption, bottoni = formatta_messaggio(item, url_finale, titolo_finale, amazon_tag)

        if invia_foto_su_telegram(token, channel, caption, bottoni, scheda_jpg):
            print(f"Pubblicato [{item['tipo']} - {item.get('marca')}]: {titolo_finale[:60]}")
            if item["tipo"] == "AMAZON":
                if item["id_univoco"] not in stato["asin"]:
                    stato["asin"].append(item["id_univoco"])
            else:
                if item["id_univoco"] not in stato["radar_postati"]:
                    stato["radar_postati"].append(item["id_univoco"])
            stato_modificato = True
            pubblicati_ora += 1

    print(
        f"[{ora_italia()}] Fine giro -> Pubblicati: {pubblicati_ora} | "
        f"Senza foto: {saltati_senza_foto}"
    )

    if stato_modificato:
        salva_stato(stato)


if __name__ == "__main__":
    main()
