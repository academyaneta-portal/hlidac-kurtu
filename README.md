# Hlídač kurtů – Sprint & Paradise (Brno)

Každých ~5 minut (v noci 15) zkontroluje volné hodiny **po–pá 8:00–9:00 a 15:00–18:00** na:

- hala Sprint – https://memberzone.cz/sprint_tenis/ (systém ukazuje 7 dní dopředu)
- Tenis Paradise – https://jdemenato.cz/reservation/tenis-paradise/reservationcalendaroverview (hlídá 14 dní)

Když se objeví **nově uvolněná** hodina, přijde push do aplikace **ntfy** (kanál je v GitHub secretu `NTFY_TOPIC`).
Běží přes GitHub Actions (`.github/workflows/hlidac.yml`), stav posledního běhu je v `state.json`.

## Změna nastavení
Do `env:` ve workflow lze přidat:
- `WINDOWS` – hlídaná okna (výchozí `8:00-9:00,15:00-18:00`)
- `WEEKDAYS` – dny (0 = po … 6 = ne), výchozí `0,1,2,3,4`
- `DAYS_AHEAD` – kolik dní dopředu hlídat u Paradise (výchozí 14)

Volitelně e-mail (`EMAIL_TO`, `SMTP_USER`, `SMTP_PASSWORD`) a SMS přes Twilio (`TWILIO_SID`, `TWILIO_TOKEN`, `TWILIO_FROM`, `SMS_TO`) – skript je umí, jen nejsou zapnuté.

## Ruční test
    python3 hlidac.py --dry-run

Vypnutí: GitHub → repozitář → Actions → Hlídač kurtů → ⋯ → Disable workflow.
