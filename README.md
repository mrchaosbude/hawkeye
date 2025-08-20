# Hawkeye Telegram Bot

Hawkeye ist ein einfacher Telegram-Bot, der Kryptowährungspreise überwacht und dich per Nachricht informiert, wenn dein Stop-Loss oder Take-Profit erreicht wird. Jeder Benutzer kann mehrere Symbole gleichzeitig beobachten. Der Preis wird in regelmäßigen Abständen über die Binance Futures API abgefragt. Bei Benachrichtigungen sendet der Bot außerdem ein Balkendiagramm mit den aktuellen Käufer- und Verkäufervolumina.

## Voraussetzungen

- Python 3.9 oder neuer
- Ein Telegram-Bot-Token
- Abhängigkeiten: `requests`, `telebot`, `schedule`, `matplotlib`, `mplfinance`

Installiere die Abhängigkeiten am besten in einem virtuellen Umfeld:

```bash
python -m venv venv
source venv/bin/activate
pip install requests telebot schedule matplotlib mplfinance
```

## Konfiguration

1. Kopiere die Datei `config.json` und trage deinen Bot-Token ein. Optional kannst du
   einen CoinGecko-API-Key (`coingecko_api_key`) hinzufügen, damit der `/top10`
   Befehl zuverlässig Daten liefert.
2. Starte den Bot anschließend mit:

```bash
python hawkeye.py
```

## Benutzung

Im Chat mit deinem Bot stehen folgende Befehle zur Verfügung:

- `/set SYMBOL STOP_LOSS TAKE_PROFIT` – Symbol hinzufügen oder aktualisieren, z. B. `/set BTCUSDT 42000 46000`
- `/remove SYMBOL` – Symbol entfernen
- `/percent SYMBOL PROZENT` – Benachrichtigung bei ±PROZENT Preisänderung
- `/stop` – Benachrichtigungen deaktivieren
- `/start` – Benachrichtigungen aktivieren
- `/menu` oder `/help` – Hilfe und aktuelle Einstellungen anzeigen
- `/interval MINUTEN` – Zeitabstand zwischen den Prüfungen festlegen
- `/now` – Aktuelle Preise der beobachteten Symbole anzeigen
- `/top10` – Top 10 Kryptowährungen mit Preis, 24h-Änderung und Candlestick-Chart

## Hinweise

- Die Preise werden standardmäßig alle 5 Minuten geprüft. Über `/interval` lässt sich dieser Wert anpassen.
- Der Bot aktualisiert sich selbst, wenn neue Commits im Git-Repository vorhanden sind.

## Lizenz

Dieses Projekt steht unter der MIT-Lizenz.

