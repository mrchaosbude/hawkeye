# Hawkeye Telegram Bot

Hawkeye ist ein einfacher Telegram-Bot, der Kryptowährungspreise überwacht und dich per Nachricht informiert, wenn dein Stop-Loss oder Take-Profit erreicht wird. Jeder Benutzer kann mehrere Symbole gleichzeitig beobachten (standardmäßig bis zu fünf, konfigurierbar über `max_symbols`). Der Preis wird in regelmäßigen Abständen über die Binance Futures API abgefragt. Bei Benachrichtigungen sendet der Bot außerdem ein Balkendiagramm mit den aktuellen Käufer- und Verkäufervolumina.

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

1. Kopiere die Datei `config.json` und trage deinen Bot-Token ein. In der
   Sektion `users` können Chat-IDs mit Rollen versehen werden, z. B.
   `"role": "admin"`, um globale Einstellungen ändern zu dürfen. Optional
   lässt sich mit `"max_symbols"` die maximale Anzahl an Symbolen pro Nutzer
   festlegen (Standard 5). Der `/top10`-Befehl nutzt Daten von Coingecko.
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
- `/interval MINUTEN` – Zeitabstand zwischen den Prüfungen festlegen (nur Admin)
- `/summarytime HH:MM` – Zeitpunkt der Tageszusammenfassung setzen (nur Admin)
- `/now` – Aktuelle Preise der beobachteten Symbole anzeigen
- `/summary` – Tageszusammenfassung jetzt senden (nur Admin)
- `/top10` – Top 10 Kryptowährungen mit Preis, 24h-Änderung und Candlestick-Chart
  (Candlestick-Daten werden täglich in `cache.db` gespeichert; aktuelle Preise werden live geladen)
- `/signal SYMBOL BENCHMARK` – Berechnet Score und Signal für `SYMBOL` relativ zur `BENCHMARK`

## Beispiel: Trading-Signale

Eine einfache Umsetzung eines regelbasierten Systems findet sich in `trading_strategy.py`. Das Skript berechnet technische Indikatoren, vergibt einen Score und erzeugt Kauf- bzw. Verkaufssignale auf Basis täglicher OHLCV-Daten.

## Hinweise

- Die Preise werden standardmäßig alle 5 Minuten geprüft. Über `/interval` (nur Admin) lässt sich dieser Wert anpassen.
- Der Bot aktualisiert sich selbst, wenn neue Commits im Git-Repository vorhanden sind.

## Lizenz

Dieses Projekt steht unter der MIT-Lizenz.

