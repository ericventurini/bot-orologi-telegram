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
MAX_POST_PER_GIRO = 2      # Massimo 2 post ogni 30 min (niente spam)
MAX_STORICO = 500          # Ricorda gli ultimi 500 orologi già postati

# Feed pubblici cali di prezzo Amazon Italia (categoria orologi)
FEED_URLS = [
    "https://it.camelcamelcamel.com/top_drops/feed?t=relative&i=7&s=amazon&d=15&c=watches",
    "https://it.camelcamelcamel.com/top_drops/feed?t=relative&i=7&s=new&d=15&c=watches",
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
            print(f"Errore HTTP {e.code} sul feed: {e.reason}")
            continue
        except Exception as e:
            print(f"Errore connessione feed: {e}")
            continue

        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError as e:
            print(f"Errore lettura XML: {e}")
            continue

        items = root.findall(".//item")
        print(f"Trovati {len(items)} elementi nel feed.")

        for item in items:
            titolo = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            guid = (item.findtext("guid") or "").strip()
            desc = (item.findtext("description") or "").strip()

            asin = estrai_asin(f"{link} {guid} {desc}")
            if not asin or asin in visti:
                continue

            visti.add(asin)
            offerte.append({
                "asin": asin,
                "titolo": titolo,
                "immagine": estrai_immagine(desc),
            })

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

    # Prova prima con la foto del prodotto, se disponibile
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

    # Fallback: messaggio testuale pulito con bottone
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
        print(f"[{ora_italia()}] Nessuna offerta trovata in questo giro.")
        return

    nuovi_post = 0
    for off in offerte:
        if nuovi_post >= MAX_POST_PER_GIRO:
            break
        if off["asin"] in pubblicati:
            continue

        url_amazon = costruisci_link_amazon(off["asin"], amazon_tag)
        titolo_sicuro = html.escape(off["titolo"])

        messaggio = (
            f"📉 <b>CALO DI PREZZO OROLOGIO</b>\n\n"
            f"⌚ <b>{titolo_sicuro}</b>\n\n"
            f"<i>Prezzo rilevato al momento del post — verifica la disponibilità su Amazon.</i>"
        )

        if invia_su_telegram(token, channel, messaggio, url_amazon, off["immagine"]):
            print(f"Pubblicato sul canale: {off['asin']} | {off['titolo'][:60]}")
            pubblicati.append(off["asin"])
            nuovi_post += 1

    if nuovi_post > 0:
        salva_pubblicati(pubblicati)
        print(f"[{ora_italia()}] Completato: {nuovi_post} nuove offerte pubblicate.")
    else:
        print(f"[{ora_italia()}] Tutte le offerte trovate erano già state pubblicate.")


if __name__ == "__main__":
    main()
