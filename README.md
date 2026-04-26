# Radio Dashboard voor voicetracks

Streamlit-app met 2 onderdelen:

- **JarigVandaag** voor verjaardagen
- **NU.nl Opmerkelijk** via RSS voor luchtig nieuws

## Functies

### Verjaardagen
- komende 1 t/m 14 dagen ophalen
- filters voor:
  - alleen muziek
  - alleen NL
  - alleen radio-proof
  - overleden personen tonen of verbergen
- per persoon een voorleestekst
- CSV-download

### Opmerkelijk nieuws
- laadt standaard de feed `https://www.nu.nl/rss/Opmerkelijk`
- filter op:
  - alleen radio-proof
  - alleen bruikbare items
- per item een voorleestekst
- CSV-download

## Huisstijl
- donkere / diep donkerblauwe achtergrond
- oranje accentkleur in de stijl van Radio Muziekstad
- logo in de header
- Streamlit theme-config via `.streamlit/config.toml`

## Bestanden
- `app.py`
- `requirements.txt`
- `radio_muziekstad_logo.png`
- `.streamlit/config.toml`

## Lokaal starten

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy via GitHub + Streamlit Community Cloud

1. Zet alle bestanden in je GitHub-repository.
2. Zorg dat ook de map `.streamlit` wordt meegecommit.
3. Maak in Streamlit Community Cloud een nieuwe app.
4. Kies je repository en selecteer `app.py`.
5. Deploy.

## Opmerking
De nieuwsfilter voor "radio-proof" werkt met eenvoudige trefwoorden. Daardoor kan een item soms te streng of te los worden gefilterd. Je kunt die woorden later aanpassen in `NEWS_EXCLUDE_TERMS` en `NEWS_PREFER_TERMS`.

## UI update

Deze versie heeft een extra strakke premium UI met een donkere hero-header, glasachtige panelen, strakkere tabs, metrics en kaarten in Radio Muziekstad-stijl.

## Nieuwe functie

- knop **Maak complete voicetrack voor deze dag** per dagblok
- combineert verjaardagen met een bruikbaar opmerkelijk nieuwsitem als dat beschikbaar is
- download van de gegenereerde spreektekst als `.txt`

## Extra keuze voor voicetrack

Bij de knop **Maak complete voicetrack voor deze dag** kun je nu kiezen uit:

- **kort**
- **normaal**
- **uitgebreid**

## Extra keuze voor stijl

Bij de complete dag-voicetrack kun je nu kiezen uit:

- **luchtig**
- **enthousiast**
- **zakelijk**
