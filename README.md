# Hawkeye Telegram Bot

Hawkeye ist ein einfacher Telegram-Bot, der Kryptowährungspreise überwacht und dich per Nachricht informiert, wenn dein Stop-Loss oder Take-Profit erreicht wird. Der Preis wird in regelmäßigen Abständen über die Binance Futures API abgefragt.

## Voraussetzungen

- Python 3.9 oder neuer
- Ein Telegram-Bot-Token
- Abhängigkeiten: `requests`, `telebot`, `schedule`

Installiere die Abhängigkeiten am besten in einem virtuellen Umfeld:

```bash
python -m venv venv
source venv/bin/activate
pip install requests telebot schedule
```

## Konfiguration

1. Kopiere die Datei `config.json` und trage deinen Bot-Token ein.
2. Starte den Bot anschließend mit:

```bash
python hawkeye.py
```

## Benutzung

Im Chat mit deinem Bot stehen folgende Befehle zur Verfügung:

- `/set SYMBOL STOP_LOSS TAKE_PROFIT` – Konfiguration setzen, z. B. `/set BTCUSDT 42000 46000`
- `/stop` – Benachrichtigungen deaktivieren
- `/start` – Benachrichtigungen aktivieren
- `/menu` oder `/help` – Hilfe und aktuelle Einstellungen anzeigen

## Hinweise

- Die Preise werden alle 5 Minuten geprüft.
- Der Bot aktualisiert sich selbst, wenn neue Commits im Git-Repository vorhanden sind.

## Lizenz

Dieses Projekt steht unter der MIT-Lizenz.

