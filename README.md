# Radio dashboard voor voicetracks

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

## Bestanden

- `app.py`
- `requirements.txt`

## Lokaal starten

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy via GitHub + Streamlit Community Cloud

1. Zet `app.py` en `requirements.txt` in je GitHub-repository.
2. Maak in Streamlit Community Cloud een nieuwe app.
3. Kies je repository en selecteer `app.py`.
4. Deploy.

## Opmerking

De nieuwsfilter voor "radio-proof" werkt met eenvoudige trefwoorden. Daardoor kan een item soms te streng of te los worden gefilterd. Je kunt die woorden later makkelijk aanpassen in `NEWS_EXCLUDE_TERMS` en `NEWS_PREFER_TERMS`.
