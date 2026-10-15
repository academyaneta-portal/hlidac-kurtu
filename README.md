# Hlídač kurtů – Sprint & Paradise (Brno)

Mezi 7:00 a 21:00 každých ~5 minut zkontroluje volné hodiny **po–pá 8:00–9:00 a 15:00–18:00** na:

- hala Sprint – https://memberzone.cz/sprint_tenis/ (systém ukazuje 7 dní dopředu)
- Tenis Paradise – https://jdemenato.cz/reservation/tenis-paradise/reservationcalendaroverview (hlídá 14 dní) – **zatím vypnuto**: Cloudflare blokuje servery GitHubu (403). Lokálně funguje (`HALLS=Sprint,Paradise`).

Když se objeví **nově uvolněná** hodina, přijde push do aplikace **ntfy** (kanál je v GitHub secretu `NTFY_TOPIC`).
V noci se nekontroluje; první kontrola v 7:00 pošle ranní souhrn, co se uvolnilo přes noc (nebo že nic).
Běží přes GitHub Actions (`.github/workflows/hlidac.yml`), stav posledního běhu je v `state.json`.

## Změna nastavení
Do `env:` ve workflow lze přidat:
- `WINDOWS` – hlídaná okna (výchozí `8:00-9:00,15:00-18:00`)
- `WEEKDAYS` – dny (0 = po … 6 = ne), výchozí `0,1,2,3,4`
- `ACTIVE_HOURS` – kdy hlídat (výchozí `7:00-21:00`)
- `HALLS` – které haly hlídat (`Sprint`, `Paradise`)
- `DAYS_AHEAD` – kolik dní dopředu hlídat u Paradise (výchozí 14)

Volitelně e-mail (`EMAIL_TO`, `SMTP_USER`, `SMTP_PASSWORD`) a SMS přes Twilio (`TWILIO_SID`, `TWILIO_TOKEN`, `TWILIO_FROM`, `SMS_TO`) – skript je umí, jen nejsou zapnuté.

## Ruční test
    python3 hlidac.py --dry-run

Vypnutí: GitHub → repozitář → Actions → Hlídač kurtů → ⋯ → Disable workflow.
