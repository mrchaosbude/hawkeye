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
   festlegen (Standard 5). Über den Schlüssel `strategy` wählst du die zu
   verwendende Handelsstrategie (`momentum`, `trend_following` oder
   `arbitrage`). Strategieabhängige Optionen kannst du in
   `strategy_params` angeben.
2. Beispielkonfiguration:

   ```json
   {
     "telegram_token": "DEIN_TELEGRAM_TOKEN",
     "users": {"123456789": {"role": "admin"}},
     "check_interval": 5,
     "summary_time": "09:00",
     "strategy": "arbitrage",
     "strategy_params": {
       "symbol": "BTCUSDT",
       "threshold": 0.01
     }
   }
   ```
3. Starte den Bot anschließend mit:

```bash
python hawkeye.py
```

## Benutzung

Im Chat mit deinem Bot stehen folgende Befehle zur Verfügung:

- `/set SYMBOL STOP_LOSS TAKE_PROFIT` – Symbol hinzufügen oder aktualisieren, z. B. `/set BTCUSDT 42000 46000`
- `/watch SYMBOL` – Symbol für automatische Signaländerungen beobachten
- `/autotrade SYMBOL BETRAG|PROZENT%` – Automatischer Handel für SYMBOL mit fixem Betrag oder Prozent des Guthabens
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

Die Logik für Handelssignale liegt im Paket `strategies`. Neben der
Standard-Implementierung `MomentumStrategy` steht mit
`TrendFollowingStrategy` eine weitere Strategie bereit. Beide lassen sich
auch außerhalb des Bots verwenden:

```python
from strategies import get_strategy
import pandas as pd

asset = pd.read_csv("asset.csv", parse_dates=["Date"], index_col="Date")
bench = pd.read_csv("benchmark.csv", parse_dates=["Date"], index_col="Date")

strategy = get_strategy("momentum")
signals = strategy.generate_signals(asset, bench, stress_threshold=0.08)
print(signals[["Signal"]].tail())
```

Fehlen Fundamentaldaten, setzt die Momentum-Strategie einen neutralen Wert
von `0.5` an. Diese Annahme entspricht dem Hawkeye-Blueprint.

### Arbitrage-Strategie

Für eine einfache Arbitrage zwischen Binance und Coinbase kannst du die
Strategie wie folgt konfigurieren:

```json
{
  "strategy": "arbitrage",
  "strategy_params": {"symbol": "BTCUSDT", "threshold": 0.01}
}
```

Die Preise beider Börsen werden verglichen. Überschreitet der Spread den
Schwellenwert, wird ein Kauf-/Verkaufs-Signal ausgegeben.

## Hinweise

- Die Preise werden standardmäßig alle 5 Minuten geprüft. Über `/interval` (nur Admin) lässt sich dieser Wert anpassen.
- Der Bot aktualisiert sich selbst, wenn neue Commits im Git-Repository vorhanden sind.
- Für echte Trades auf den Börsen sind API-Schlüssel erforderlich. Die
  Beispiel-Implementierung nutzt nur öffentliche Preisdaten.
- Arbitrage birgt Risiken durch Gebühren, Latenzen und Slippage; ein
  positiver Spread garantiert keinen Gewinn.

## Lizenz

Dieses Projekt steht unter der MIT-Lizenz.

