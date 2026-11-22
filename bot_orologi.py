import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo

# ==========================================
# BOT OFFERTE OROLOGI AMAZON -> TELEGRAM
# ==========================================
FILE_PUBBLICATI = "pubblicati.json"
MAX_POST_PER_GIRO = 2      # Massimo 2 post ogni 30 min
MAX_STORICO = 500          # Ricorda gli ultimi 500 ASIN già postati
SCONTO_MINIMO = 8.0        # Sconto minimo in % (alzabile poi a 15 o 20)

# Feed CamelCamelCamel Italia: Orologi + Moda (dove Amazon mette gran parte degli orologi) + Elettronica
FEED_URLS = [
    "https://it.camelcamelcamel.com/top_drops/feed?t=recent&s=relative&i=7&bn=orologi&d=1",
    "https://it.camelcamelcamel.com/popular.xml?deal=1&bn=orologi",
    "https://it.camelcamelcamel.com/top_drops/feed?t=recent&s=relative&i=7&bn=moda&d=1",
    "https://it.camelcamelcamel.com/top_drops/feed?t=relative&s=relative&i=7&bn=moda&d=1",
    "https://it.camelcamelcamel.com/top_drops/feed?t=absolute&s=relative&i=7&bn=moda&d=1",
    "https://it.camelcamelcamel.com/top_drops/feed?t=recent&s=relative&i=7&bn=elettronica&d=1",
]

# Deve contenere ALMENO una di queste parole/marche
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

# Blocca solo veri accessori / prodotti fuori tema (senza colpire "vetro zaffiro" o "cinturino in pelle")
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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
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


def analizza_titolo(titolo_grezzo):
    """Separa il nome pulito dell'orologio dalla percentuale di sconto."""
    sconto_pct = None
    m_pct = re.search(r"\bdown\s+([\d.,]+)%", titolo_grezzo, flags=re.IGNORECASE)
    if m_pct:
        try:
            sconto_pct = float(m_pct.group(1).replace(",", "."))
        except ValueError:
            sconto_pct = None

    titolo_pulito = re.split(r"\s*-\s*down\s+", titolo_grezzo, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    return titolo_pulito, sconto_pct


def estrai_asin(testo):
    m = re.search(r"/(?:product|dp|gp/product)/([A-Z0-9]{10})", testo)
    if m:
        return m.group(1)
    m = re.search(r"\b(B0[A-Z0-9]{8})\b", testo)
    return m.group(1) if m else None


def estrai_immagine(descrizione_html):
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', descrizione_html or "")
    return m.group(1) if m else None


def scarica_offerte():
    offerte = []
    visti = set()

    for url in FEED_URLS:
        print(f"Controllo feed: {url}")
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                xml_data = resp.read()
        except urllib.error.HTTPError as e:
            print(f"  Errore HTTP {e.code}: {e.reason}")
            continue
        except Exception as e:
            print(f"  Errore connessione: {e}")
            continue

        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError as e:
            print(f"  Errore lettura XML: {e}")
            continue

        items = root.findall(".//item")
        print(f"  Elementi trovati: {len(items)}")

        for idx, item in enumerate(items):
            titolo_grezzo = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            guid = (item.findtext("guid") or "").strip()
            desc = (item.findtext("description") or "").strip()

            titolo_pulito, sconto_pct = analizza_titolo(titolo_grezzo)
            valido, motivo = e_un_orologio(titolo_pulito)

            if idx < 2:
                print(f"    Esempio {idx + 1}: {titolo_grezzo[:80]} -> {motivo}")

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
                "immagine": estrai_immagine(desc),
                "motivo": motivo,
            })

    print(f"Orologi validi dopo il filtro: {len(offerte)}")
    return offerte


def costruisci_link_amazon(asin, tag):
    base = f"https://www.amazon.it/dp/{asin}"
    if tag:
        return f"{base}?tag={urllib.parse.quote(tag)}"
    return base


def invia_su_telegram(token, channel, testo_html, url_amazon, immagine=None):
    tastiera = json.dumps({
        "inline_keyboard": [[
            {"text": "⌚ Vedi offerta su Amazon.it", "url": url_amazon}
        ]]
    })

    if immagine:
        url_api = f"https://api.telegram.org/bot{token}/sendPhoto"
        payload = urllib.parse.urlencode({
            "chat_id": channel,
            "photo": immagine,
            "caption": testo_html,
            "parse_mode": "HTML",
            "reply_markup": tastiera,
        }).encode("utf-8")
        req = urllib.request.Request(url_api, data=payload, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                resp.read()
            return True
        except Exception as e:
            print(f"Invio con foto fallito ({e}), riprovo solo testo...")

    url_api = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": channel,
        "text": testo_html,
        "parse_mode": "HTML",
        "reply_markup": tastiera,
    }).encode("utf-8")
    req = urllib.request.Request(url_api, data=payload, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()
        return True
    except urllib.error.HTTPError as e:
        dettaglio = e.read().decode("utf-8", errors="ignore")
        print(f"Errore Telegram HTTP {e.code}: {dettaglio}")
        return False
    except Exception as e:
        print(f"Errore Telegram: {e}")
        return False


def main():
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    channel = os.environ.get("TELEGRAM_CHANNEL", "").strip()
    amazon_tag = os.environ.get("AMAZON_TAG", "").strip()

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

    nuovi_post = 0
    for off in offerte:
        if nuovi_post >= MAX_POST_PER_GIRO:
            break
        if off["asin"] in pubblicati:
            continue

        url_amazon = costruisci_link_amazon(off["asin"], amazon_tag)
        titolo_sicuro = html.escape(off["titolo"])

        if off["sconto_pct"] is not None:
            intestazione = f"📉 <b>CALO DI PREZZO (-{off['sconto_pct']:.0f}%)</b>"
        else:
            intestazione = "📉 <b>CALO DI PREZZO OROLOGIO</b>"

        messaggio = (
            f"{intestazione}\n\n"
            f"⌚ <b>{titolo_sicuro}</b>\n\n"
            f"<i>Verifica prezzo aggiornato e disponibilità su Amazon.</i>"
        )

        if invia_su_telegram(token, channel, messaggio, url_amazon, off["immagine"]):
            print(f"Pubblicato sul canale: {off['asin']} ({off['motivo']}) | {off['titolo'][:60]}")
            pubblicati.append(off["asin"])
            nuovi_post += 1

    if nuovi_post > 0:
        salva_pubblicati(pubblicati)
        print(f"[{ora_italia()}] Completato: {nuovi_post} nuove offerte pubblicate.")
    else:
        print(f"[{ora_italia()}] Tutti gli orologi trovati erano già stati pubblicati.")


if __name__ == "__main__":
    main()
