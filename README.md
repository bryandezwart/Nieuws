# JarigVandaag Streamlit app

Een Streamlit-pagina voor je radiovoicetracks met verjaardagen van JarigVandaag.

## Wat deze app doet

- haalt verjaardagen op voor de komende 1 t/m 14 dagen
- filtert op:
  - alleen muziek
  - alleen NL
  - alleen radio-proof
  - overleden personen wel/niet tonen
- toont per dag een overzicht
- maakt per persoon een korte voorleestekst
- laat je de selectie als CSV downloaden

## Bestanden

- `app.py` — de Streamlit app
- `requirements.txt` — benodigde packages

## Lokaal starten

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy via GitHub + Streamlit Community Cloud

1. Zet `app.py` en `requirements.txt` in een GitHub repository.
2. Ga in Streamlit Community Cloud naar **New app**.
3. Kies je repository en selecteer `app.py`.
4. Deploy.

## Let op

Deze app leest publiek beschikbare pagina's van `jarigvandaag.nl`. Als de HTML-structuur van de site verandert, kan de parser aangepast moeten worden.
