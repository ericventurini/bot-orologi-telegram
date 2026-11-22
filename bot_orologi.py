import html
import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw

# ==========================================
# BOT OFFERTE OROLOGI AMAZON -> TELEGRAM
# ==========================================
FILE_PUBBLICATI = "pubblicati.json"
NOME_CANALE = "Radar Orologi & Offerte"
MAX_POST_PER_GIRO = 2             # Massimo 2 post ogni 30 min
MAX_STORICO = 500
SCONTO_MINIMO = 8.0               # Sconto minimo in %
SOLO_CON_FOTO = True              # Se True, salta i prodotti senza foto

FEED_URLS = [
    "https://it.camelcamelcamel.com/top_drops/feed?t=recent&s=relative&i=7&bn=orologi&d=1",
    "https://it.camelcamelcamel.com/popular.xml?deal=1&bn=orologi",
    "https://it.camelcamelcamel.com/top_drops/feed?t=recent&s=relative&i=7&bn=moda&d=1",
    "https://it.camelcamelcamel.com/top_drops/feed?t=relative&s=relative&i=7&bn=moda&d=1",
    "https://it.camelcamelcamel.com/top_drops/feed?t=absolute&s=relative&i=7&bn=moda&d=1",
    "https://it.camelcamelcamel.com/top_drops/feed?t=recent&s=relative&i=7&bn=elettronica&d=1",
]

PAROLE_OROLOGI = [
    "orologio", "orologi", "cronografo", "chronograph", "smartwatch",
    "wristwatch", "montre", "uhren", "watch",
    "seiko", "casio", "g-shock", "gshock", "edifice", "baby-g", "citizen",
    "orient", "tissot", "hamilton", "timex", "bulova", "festina", "sector",
    "swatch", "breil", "locman", "philip watch", "invicta", "longines",
    "mido", "certina", "spinnaker", "pagani design", "steeldive",
    "san martin", "cadisen", "mondaine", "suunto", "amazfit", "coros",
    "polar", "garmin", "fossil", "diesel", "maserati", "emporio armani",
    "armani exchange", "tommy hilfiger", "hugo boss", "guess", "morellato",
    "lorus", "skagen", "bering", "nixon", "police", "lotus", "viceroy",
    "daniel wellington", "cluse", "ice-watch", "lacoste", "calvin klein",
    "michael kors", "chronostar", "d1 milano", "zeppelin", "vostok",
]

PAROLE_VIETATE = [
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
    "dvd", "blu-ray",
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


def carica_pubblicati():
    if os.path.exists(FILE_PUBBLICATI):
        with open(FILE_PUBBLICATI, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def salva_pubblicati(lista):
    with open(FILE_PUBBLICATI, "w", encoding="utf-8") as f:
        json.dump(lista[-MAX_STORICO:], f, indent=2)


def contiene_parola(testo, lista_parole):
    for parola in lista_parole:
        if re.search(r"\b" + re.escape(parola) + r"\b", testo, flags=re.IGNORECASE):
            return parola
    return None


def e_un_orologio(titolo):
    vietata = contiene_parola(titolo, PAROLE_VIETATE)
    if vietata:
        return False, f"scartato per '{vietata}'"
    trovata = contiene_parola(titolo, PAROLE_OROLOGI)
    if trovata:
        return True, f"ok ('{trovata}')"
    return False, "non è un orologio"


def parse_euro(testo):
    s = testo.strip().replace("€", "").strip()
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def formatta_euro(valore):
    return f"{valore:,.2f}€".replace(",", "X").replace(".", ",").replace("X", ".")


def analizza_titolo_e_prezzi(titolo_grezzo, desc_html=""):
    testo_completo = f"{titolo_grezzo} {html.unescape(desc_html or '')}"

    sconto_pct = None
    m_pct = re.search(r"\bdown\s+([\d.,]+)%", testo_completo, flags=re.IGNORECASE)
    if m_pct:
        sconto_pct = parse_euro(m_pct.group(1))

    risparmio = None
    m_risp = re.search(r"\(([\d.,]+)\s*€\)", testo_completo)
    if m_risp:
        risparmio = parse_euro(m_risp.group(1))

    prezzo_nuovo = None
    m_nuovo = re.search(r"\bto\s+([\d.,]+)\s*€", testo_completo, flags=re.IGNORECASE)
    if m_nuovo:
        prezzo_nuovo = parse_euro(m_nuovo.group(1))

    prezzo_vecchio = None
    m_vecchio = re.search(r"\bfrom\s+([\d.,]+)\s*€", testo_completo, flags=re.IGNORECASE)
    if m_vecchio:
        prezzo_vecchio = parse_euro(m_vecchio.group(1))

    if prezzo_nuovo is not None and prezzo_vecchio is None and risparmio is not None:
        prezzo_vecchio = round(prezzo_nuovo + risparmio, 2)

    titolo_pulito = re.split(r"\s*-\s*down\s+", titolo_grezzo, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    return titolo_pulito, sconto_pct, prezzo_nuovo, prezzo_vecchio


def estrai_asin(testo):
    m = re.search(r"/(?:product|dp|gp/product)/([A-Z0-9]{10})", testo)
    if m:
        return m.group(1)
    m = re.search(r"\b(B0[A-Z0-9]{8})\b", testo)
    return m.group(1) if m else None


def versioni_hd_amazon(url):
    candidati = []
    hd = re.sub(r"\._[^/]+_\.(jpg|jpeg|png|webp)", r"._AC_SL1000_.\1", url, flags=re.IGNORECASE)
    if hd != url:
        candidati.append(hd)
    candidati.append(url)
    return candidati


def scarica_immagine_valida(url):
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


def recupera_foto_e_titolo_completo(asin, desc_html):
    candidati = []
    titolo_completo = None

    desc_pulita = html.unescape(desc_html or "")
    for m in re.finditer(r"https://(?:m\.media-amazon\.com|images-[a-z]+\.ssl-images-amazon\.com)/images/I/[^\"'\s<>]+", desc_pulita):
        candidati.extend(versioni_hd_amazon(m.group(0)))

    url_ccc = f"https://it.camelcamelcamel.com/product/{asin}"
    req = urllib.request.Request(url_ccc, headers=HEADERS_WEB)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            pagina = resp.read().decode("utf-8", errors="ignore")

        m_h1 = re.search(r"<h2[^>]*>\s*<a[^>]*>([^<]+)</a>", pagina)
        if m_h1:
            t = html.unescape(m_h1.group(1)).strip()
            if len(t) > 10:
                titolo_completo = t

        for m in re.finditer(r"https://(?:m\.media-amazon\.com|images-[a-z]+\.ssl-images-amazon\.com)/images/I/[^\"'\s<>]+", pagina):
            u = m.group(0)
            if "sprite" not in u.lower():
                candidati.extend(versioni_hd_amazon(u))
    except Exception as e:
        print(f"  Info pagina CCC non disponibile per {asin}: {e}")

    candidati.append(f"https://images-eu.ssl-images-amazon.com/images/P/{asin}.01._SCLZZZZZZZ_.jpg")

    visti = set()
    for url in candidati:
        if url in visti:
            continue
        visti.add(url)
        raw = scarica_immagine_valida(url)
        if raw:
            print(f"  Foto trovata per {asin}: {url[:80]}")
            return raw, titolo_completo

    print(f"  Nessuna foto prodotto trovata per {asin}")
    return None, titolo_completo


def crea_scheda_grafica(raw_bytes):
    """Monta la foto prodotto pulita su una scheda bianca 16:9."""
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


def scarica_offerte():
    offerte = []
    visti = set()

    for url in FEED_URLS:
        print(f"Controllo feed: {url}")
        req = urllib.request.Request(url, headers=HEADERS_WEB)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                xml_data = resp.read()
        except Exception as e:
            print(f"  Errore feed: {e}")
            continue

        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError as e:
            print(f"  Errore XML: {e}")
            continue

        items = root.findall(".//item")
        print(f"  Elementi trovati: {len(items)}")

        for item in items:
            titolo_grezzo = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            guid = (item.findtext("guid") or "").strip()
            desc = (item.findtext("description") or "").strip()

            titolo_pulito, sconto_pct, prezzo_nuovo, prezzo_vecchio = analizza_titolo_e_prezzi(titolo_grezzo, desc)
            valido, motivo = e_un_orologio(titolo_pulito)

            if sconto_pct is not None and sconto_pct < SCONTO_MINIMO:
                continue
            if not valido:
                continue

            asin = estrai_asin(f"{link} {guid} {desc}")
            if not asin or asin in visti:
                continue

            visti.add(asin)
            offerte.append({
                "asin": asin,
                "titolo": titolo_pulito,
                "sconto_pct": sconto_pct,
                "prezzo_nuovo": prezzo_nuovo,
                "prezzo_vecchio": prezzo_vecchio,
                "desc": desc,
                "motivo": motivo,
            })

    print(f"Orologi validi dopo il filtro: {len(offerte)}")
    return offerte


def costruisci_link_amazon(asin, tag):
    base = f"https://www.amazon.it/dp/{asin}"
    if tag:
        return f"{base}?tag={urllib.parse.quote(tag)}"
    return base


def invia_foto_su_telegram(token, channel, caption_html, url_amazon, image_bytes):
    boundary = f"----TelegramBotBoundary{uuid.uuid4().hex}"
    tastiera = json.dumps({
        "inline_keyboard": [[
            {"text": "⌚ Apri su Amazon", "url": url_amazon}
        ]]
    })

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


def main():
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    channel = os.environ.get("TELEGRAM_CHANNEL", "").strip()
    amazon_tag = os.environ.get("AMAZON_TAG", "").strip()
    test_grafica = os.environ.get("TEST_GRAFICA", "false").lower() == "true"

    if not token or not channel:
        print("Mancano TELEGRAM_TOKEN o TELEGRAM_CHANNEL nei Secrets di GitHub.")
        return

    if not channel.startswith("@") and not channel.lstrip("-").isdigit():
        channel = "@" + channel

    pubblicati = carica_pubblicati()
    offerte = scarica_offerte()

    if not offerte:
        print(f"[{ora_italia()}] Nessun orologio valido trovato in questo giro.")
        return

    limite = 1 if test_grafica else MAX_POST_PER_GIRO
    nuovi_post = 0

    for off in offerte:
        if nuovi_post >= limite:
            break
        if not test_grafica and off["asin"] in pubblicati:
            continue

        raw_img, titolo_pieno = recupera_foto_e_titolo_completo(off["asin"], off["desc"])
        if not raw_img and SOLO_CON_FOTO:
            continue

        scheda_jpg = crea_scheda_grafica(raw_img)
        url_amazon = costruisci_link_amazon(off["asin"], amazon_tag)
        titolo_finale = html.escape(titolo_pieno or off["titolo"])
        url_sicuro = html.escape(url_amazon, quote=True)

        if off["prezzo_nuovo"] is not None and off["prezzo_vecchio"] is not None and off["prezzo_vecchio"] > off["prezzo_nuovo"]:
            extra_pct = f" (-{off['sconto_pct']:.0f}%)" if off["sconto_pct"] else ""
            riga_prezzo = f"💰 <b>{formatta_euro(off['prezzo_nuovo'])} anziché {formatta_euro(off['prezzo_vecchio'])}!</b>{extra_pct}"
        elif off["prezzo_nuovo"] is not None:
            riga_prezzo = f"💰 <b>In offerta a {formatta_euro(off['prezzo_nuovo'])}!</b>"
        elif off["sconto_pct"] is not None:
            riga_prezzo = f"📉 <b>Calo di prezzo del -{off['sconto_pct']:.0f}%!</b>"
        else:
            riga_prezzo = "📉 <b>Offerta attiva su Amazon!</b>"

        messaggio = (
            f"⌚ <i>{titolo_finale}</i>\n\n"
            f"{riga_prezzo}\n"
            f"👉 <a href=\"{url_sicuro}\">Apri su Amazon</a>\n\n"
            f"⌚ Segnalata su {html.escape(NOME_CANALE)} - #Ad"
        )

        if invia_foto_su_telegram(token, channel, messaggio, url_amazon, scheda_jpg):
            print(f"Pubblicato con foto: {off['asin']} | {titolo_finale[:60]}")
            if off["asin"] not in pubblicati:
                pubblicati.append(off["asin"])
            nuovi_post += 1

    if nuovi_post > 0:
        salva_pubblicati(pubblicati)
        print(f"[{ora_italia()}] Completato: {nuovi_post} post con foto pubblicati.")
    else:
        print(f"[{ora_italia()}] Nessun nuovo post pubblicato (già postati o senza foto).")


if __name__ == "__main__":
    main()
