import re
import time
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from typing import List, Optional
from urllib.parse import urljoin

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup, NavigableString, Tag

st.set_page_config(
    page_title="Radio verjaardagen dashboard",
    page_icon="🎙️",
    layout="wide",
)

BASE_URL = "https://www.jarigvandaag.nl"
MONTHS_NL = {
    1: "januari",
    2: "februari",
    3: "maart",
    4: "april",
    5: "mei",
    6: "juni",
    7: "juli",
    8: "augustus",
    9: "september",
    10: "oktober",
    11: "november",
    12: "december",
}
WEEKDAYS_NL = {
    0: "maandag",
    1: "dinsdag",
    2: "woensdag",
    3: "donderdag",
    4: "vrijdag",
    5: "zaterdag",
    6: "zondag",
}

MUSIC_KEYWORDS = [
    "zanger", "zangeres", "dj", "producer", "muzikant", "drummer",
    "gitarist", "rapper", "band", "songwriter", "componist",
    "musicus", "muziekproducent", "muzikaal", "bassist", "pianist",
]
DUTCH_KEYWORDS = [
    "nederlands", "nederlandse", "koning der nederlanden",
    "prins van oranje", "hollandse", "hollands",
]
RADIO_KEYWORDS = [
    "presentator", "presentatrice", "radio", "televisie", "acteur", "actrice",
    "cabaretier", "entertainer", "persoonlijkheid", "comedian",
]

USER_AGENT = (
    "Mozilla/5.0 (compatible; RadioVoicetrackDashboard/1.0; +https://github.com/)"
)


@dataclass
class BirthdayPerson:
    query_date: str
    query_date_iso: str
    name: str
    bio: str
    birth_date: Optional[str]
    current_age: Optional[int]
    turning_age: Optional[int]
    deceased: bool
    death_date: Optional[str]
    image_url: Optional[str]
    source_url: str

    @property
    def is_music(self) -> bool:
        bio = self.bio.lower()
        return any(word in bio for word in MUSIC_KEYWORDS)

    @property
    def is_dutch(self) -> bool:
        bio = self.bio.lower()
        return any(word in bio for word in DUTCH_KEYWORDS)

    @property
    def is_radio_friendly(self) -> bool:
        bio = self.bio.lower()
        return self.is_music or any(word in bio for word in RADIO_KEYWORDS)

    def voicetrack_text(self) -> str:
        day_txt = self.query_date.lower()
        if self.deceased:
            age_txt = (
                f"Op {day_txt} zou {self.name} {self.turning_age} jaar zijn geworden. "
                if self.turning_age
                else f"Op {day_txt} herdenken we de geboortedag van {self.name}. "
            )
            return f"{age_txt}{self.name} stond bekend als {self.bio}."
        age_txt = (
            f"Op {day_txt} is {self.name} jarig en wordt {self.turning_age} jaar. "
            if self.turning_age
            else f"Op {day_txt} is {self.name} jarig. "
        )
        return f"{age_txt}{self.name} is bekend als {self.bio}."


def slug_for_date(d: date) -> str:
    return f"{d.day}-{MONTHS_NL[d.month]}"


def url_for_date(d: date) -> str:
    return f"{BASE_URL}/datum/{slug_for_date(d)}"


def safe_text(node) -> str:
    if isinstance(node, NavigableString):
        return str(node).strip()
    if isinstance(node, Tag):
        return node.get_text(" ", strip=True)
    return ""


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_person_from_block(
    *,
    page_date: date,
    name: str,
    bio: str,
    facts: List[str],
    image_url: Optional[str],
    source_url: str,
) -> BirthdayPerson:
    deceased = "†" in name
    death_date = None
    death_match = re.search(r"\[\s*†\s*([^\]]+)\]", name)
    if death_match:
        death_date = death_match.group(1).strip()
        name = re.sub(r"\s*\[\s*†[^\]]+\]", "", name).strip()

    birth_date = None
    current_age = None
    turning_age = None

    joined_facts = " ".join(facts)

    birth_match = re.search(r"(\d{2}-\d{2}-\d{4})", joined_facts)
    if birth_match:
        birth_date = birth_match.group(1)

    current_age_match = re.search(r"is nu (\d+) jaar oud", joined_facts, re.I)
    if current_age_match:
        current_age = int(current_age_match.group(1))

    turning_match = re.search(r"(?:wordt|zou) .*? (\d+) jaar", joined_facts, re.I)
    if turning_match:
        turning_age = int(turning_match.group(1))

    if "zou" in joined_facts.lower():
        deceased = True

    day_label = f"{page_date.day} {MONTHS_NL[page_date.month]}"

    return BirthdayPerson(
        query_date=day_label,
        query_date_iso=page_date.isoformat(),
        name=normalize_spaces(name),
        bio=normalize_spaces(bio),
        birth_date=birth_date,
        current_age=current_age,
        turning_age=turning_age,
        deceased=deceased,
        death_date=death_date,
        image_url=image_url,
        source_url=source_url,
    )


def parse_with_anchor_blocks(soup: BeautifulSoup, page_date: date, source_url: str) -> List[BirthdayPerson]:
    people: List[BirthdayPerson] = []

    anchor_candidates = []
    for a in soup.find_all("a"):
        if not a.find("img"):
            continue
        text = normalize_spaces(a.get_text(" ", strip=True))
        if not text:
            img = a.find("img")
            text = normalize_spaces(img.get("alt", "")) if img else ""
        if not text:
            continue
        if text.lower() in {"jarig vandaag", "datum"}:
            continue
        anchor_candidates.append(a)

    seen_names = set()

    for a in anchor_candidates:
        img = a.find("img")
        name = normalize_spaces(a.get_text(" ", strip=True))
        if not name and img:
            name = normalize_spaces(img.get("alt", ""))
        if not name or name in seen_names:
            continue

        seen_names.add(name)
        image_url = None
        if img and img.get("src"):
            image_url = urljoin(source_url, img.get("src"))

        sibling_lines: List[str] = []
        for sibling in a.next_siblings:
            if isinstance(sibling, Tag) and sibling.name == "a" and sibling.find("img"):
                break
            txt = safe_text(sibling)
            if not txt:
                continue
            sibling_lines.extend(
                [normalize_spaces(part) for part in txt.split("\n") if normalize_spaces(part)]
            )

        if len(sibling_lines) < 2 and a.parent:
            parent_text = a.parent.get_text("\n", strip=True)
            parent_lines = [normalize_spaces(x) for x in parent_text.split("\n") if normalize_spaces(x)]
            if parent_lines and parent_lines[0] == name:
                sibling_lines = parent_lines[1:]

        if not sibling_lines:
            continue

        bio = sibling_lines[0]
        fact_lines = sibling_lines[1:]
        person = parse_person_from_block(
            page_date=page_date,
            name=name,
            bio=bio,
            facts=fact_lines,
            image_url=image_url,
            source_url=source_url,
        )
        people.append(person)

    return people


def parse_with_text_fallback(soup: BeautifulSoup, page_date: date, source_url: str) -> List[BirthdayPerson]:
    text = soup.get_text("\n", strip=True)
    lines = [normalize_spaces(x) for x in text.split("\n") if normalize_spaces(x)]

    start_idx = 0
    for i, line in enumerate(lines):
        if line.startswith("Bekijk de lijst hieronder") or line.startswith("Iedere dag een nieuw overzicht") or line.startswith("Lijst met bekende personen"):
            start_idx = i + 1
            break

    end_markers = {"Volg ons ook op Twitter", "Onvolledigheden of onjuistheden", "Adverteren op JarigVandaag.nl"}
    end_idx = len(lines)
    for i, line in enumerate(lines[start_idx:], start=start_idx):
        if line in end_markers or line.startswith("←") or line.endswith("→"):
            end_idx = i
            break

    content = lines[start_idx:end_idx]
    people: List[BirthdayPerson] = []
    i = 0
    while i < len(content) - 2:
        name = content[i]
        bio = content[i + 1]
        facts = [content[i + 2]]
        if i + 3 < len(content) and ("wordt" in content[i + 3].lower() or "zou" in content[i + 3].lower()):
            facts.append(content[i + 3])
            i += 4
        else:
            i += 3

        if any(skip in name.lower() for skip in ["twitter", "privacy", "cookie"]):
            continue
        people.append(
            parse_person_from_block(
                page_date=page_date,
                name=name,
                bio=bio,
                facts=facts,
                image_url=None,
                source_url=source_url,
            )
        )

    return people


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_birthdays_for_date(page_date: date) -> List[BirthdayPerson]:
    url = url_for_date(page_date)
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    people = parse_with_anchor_blocks(soup, page_date, url)
    if not people:
        people = parse_with_text_fallback(soup, page_date, url)

    time.sleep(0.15)
    return people


def day_range(start_day: date, num_days: int) -> List[date]:
    return [start_day + timedelta(days=i) for i in range(num_days)]


def render_person_card(person: BirthdayPerson):
    col1, col2 = st.columns([1, 4], vertical_alignment="top")
    with col1:
        if person.image_url:
            st.image(person.image_url, use_container_width=True)
        else:
            st.markdown("🎂")
    with col2:
        badge_parts = []
        if person.is_music:
            badge_parts.append("🎵 muziek")
        if person.is_dutch:
            badge_parts.append("🇳🇱 NL")
        if person.is_radio_friendly:
            badge_parts.append("🎙️ radio-proof")
        if person.deceased:
            badge_parts.append("🕯️ overleden")

        badge_line = " | ".join(badge_parts) if badge_parts else "algemeen"

        st.markdown(f"### {person.name}")
        st.caption(badge_line)
        st.write(person.bio)

        meta = []
        if person.birth_date:
            meta.append(f"Geboortedatum: {person.birth_date}")
        if person.current_age is not None:
            meta.append(f"Nu: {person.current_age}")
        if person.turning_age is not None:
            meta.append(f"Wordt: {person.turning_age}")
        if person.deceased and person.death_date:
            meta.append(f"Overleden: {person.death_date}")

        if meta:
            st.write(" • ".join(meta))

        with st.expander("Voorleestekst voor voicetrack", expanded=False):
            st.text_area(
                "Tekst",
                value=person.voicetrack_text(),
                key=f"vt_{person.query_date_iso}_{person.name}",
                height=90,
                label_visibility="collapsed",
            )
            st.markdown(f"[Open bron]({person.source_url})")


def build_dataframe(people: List[BirthdayPerson]) -> pd.DataFrame:
    rows = []
    for p in people:
        row = asdict(p)
        row["is_music"] = p.is_music
        row["is_dutch"] = p.is_dutch
        row["is_radio_friendly"] = p.is_radio_friendly
        rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    preferred_cols = [
        "query_date",
        "name",
        "bio",
        "turning_age",
        "current_age",
        "deceased",
        "is_music",
        "is_dutch",
        "is_radio_friendly",
        "source_url",
    ]
    return df[preferred_cols]


def app():
    st.title("🎙️ Radio-verjaardagen dashboard")
    st.write(
        "Haal verjaardagen op van JarigVandaag per dag of voor de komende week. "
        "Filter op muziek, Nederland en radio-proof personen en gebruik direct een korte voorleestekst."
    )

    with st.sidebar:
        st.header("Instellingen")
        start_day = st.date_input("Startdatum", value=date.today())
        num_days = st.slider("Aantal dagen", min_value=1, max_value=14, value=7)
        only_music = st.checkbox("Alleen muziek", value=True)
        only_dutch = st.checkbox("Alleen NL", value=False)
        only_radio = st.checkbox("Alleen radio-proof", value=False)
        include_deceased = st.checkbox("Overleden personen tonen", value=False)
        st.markdown("---")
        st.caption(
            "Let op: deze app leest publiek beschikbare pagina's van JarigVandaag. "
            "Als de sitestructuur verandert, moet de parser mogelijk worden aangepast."
        )

    dates = day_range(start_day, num_days)

    all_people: List[BirthdayPerson] = []
    errors = []

    with st.spinner("Verjaardagen ophalen..."):
        for d in dates:
            try:
                all_people.extend(fetch_birthdays_for_date(d))
            except Exception as exc:
                errors.append(f"{d.isoformat()}: {exc}")

    filtered = []
    for person in all_people:
        if only_music and not person.is_music:
            continue
        if only_dutch and not person.is_dutch:
            continue
        if only_radio and not person.is_radio_friendly:
            continue
        if not include_deceased and person.deceased:
            continue
        filtered.append(person)

    if errors:
        st.warning("Niet alle dagen konden worden opgehaald:\n\n- " + "\n- ".join(errors))

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Totaal gevonden", len(all_people))
    m2.metric("Na filters", len(filtered))
    m3.metric("Muziek", sum(1 for p in filtered if p.is_music))
    m4.metric("NL", sum(1 for p in filtered if p.is_dutch))

    if not filtered:
        st.info("Geen resultaten met deze filters.")
        return

    st.markdown("## Overzicht")
    grouped = {}
    for person in filtered:
        grouped.setdefault(person.query_date_iso, []).append(person)

    ordered_days = sorted(grouped)
    for day_iso in ordered_days:
        day_people = grouped[day_iso]
        day_obj = datetime.strptime(day_iso, "%Y-%m-%d").date()
        label = f"{WEEKDAYS_NL[day_obj.weekday()].capitalize()} {day_obj.day} {MONTHS_NL[day_obj.month]}"
        music_count = sum(1 for p in day_people if p.is_music)
        with st.expander(f"{label} — {len(day_people)} personen • {music_count} muziek", expanded=(day_iso == ordered_days[0])):
            top_df = build_dataframe(day_people)
            if not top_df.empty:
                preview_df = top_df[["name", "bio", "turning_age", "is_music", "is_dutch", "is_radio_friendly"]].rename(
                    columns={
                        "name": "Naam",
                        "bio": "Omschrijving",
                        "turning_age": "Wordt",
                        "is_music": "Muziek",
                        "is_dutch": "NL",
                        "is_radio_friendly": "Radio-proof",
                    }
                )
                st.dataframe(preview_df, use_container_width=True, hide_index=True)

            st.markdown("### Aanklikbare items")
            for idx, person in enumerate(day_people, start=1):
                title = f"{idx}. {person.name}"
                subtitle = f" — {person.bio}"
                with st.expander(title + subtitle):
                    render_person_card(person)

    csv_df = build_dataframe(filtered)
    if not csv_df.empty:
        csv_bytes = csv_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "⬇️ Download CSV van deze selectie",
            data=csv_bytes,
            file_name="jarigvandaag_selectie.csv",
            mime="text/csv",
        )

    st.markdown("## Start lokaal")
    st.code("streamlit run app.py", language="bash")


if __name__ == "__main__":
    app()
