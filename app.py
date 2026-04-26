import re
import time
import html
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import List, Optional
from urllib.parse import urljoin

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup, NavigableString, Tag

st.set_page_config(
    page_title="Radio dashboard",
    page_icon="🎙️",
    layout="wide",
)

BASE_URL = "https://www.jarigvandaag.nl"
NU_RSS_URL = "https://www.nu.nl/rss/Opmerkelijk"

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
    "cabaretier", "entertainer", "comedian", "persoonlijkheid",
]

NEWS_EXCLUDE_TERMS = [
    "cel", "gevangenis", "gevangenisstraf", "schiet", "schoten", "misbruik",
    "seks", "zwanger", "rattengif", "gewond", "dood", "dode", "beet",
    "aanval", "aangevallen", "oorlog", "straf", "dwangarbeid", "smokkel",
    "gestolen", "steelt", "minderjarige", "wolf die vrouw", "opgelicht",
    "verdachte", "neppe doktersbriefjes", "potvis", "hond", "vogelspinnen",
]
NEWS_PREFER_TERMS = [
    "robot", "super mario", "schildpad", "goud", "munten", "chimpansees",
    "cruiseschip", "haai", "dieren", "opmerkelijk", "bizar", "grappig",
    "billboard", "bierbonnetje", "orang-oetan", "touwbrug", "rijdt ermee",
]

USER_AGENT = (
    "Mozilla/5.0 (compatible; RadioVoicetrackDashboard/2.0; +https://github.com/)"
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
            if self.name:
                if self.turning_age:
                    return f"Op {day_txt} zou {self.name} {self.turning_age} jaar zijn geworden. {self.name} stond bekend als {self.bio}."
                return f"Op {day_txt} herdenken we de geboortedag van {self.name}. {self.name} stond bekend als {self.bio}."
            return f"Op {day_txt} herdenken we een bekende naam uit de entertainmentwereld."
        if self.turning_age:
            return f"Op {day_txt} is {self.name} jarig en wordt {self.turning_age} jaar. {self.name} is bekend als {self.bio}."
        return f"Op {day_txt} is {self.name} jarig. {self.name} is bekend als {self.bio}."


@dataclass
class NewsItem:
    title: str
    link: str
    description: str
    pub_date: str
    category: str
    image_url: Optional[str]
    source: str = "NU.nl Opmerkelijk"

    @property
    def is_radio_safe(self) -> bool:
        blob = f"{self.title} {self.description} {self.category}".lower()
        return not any(term in blob for term in NEWS_EXCLUDE_TERMS)

    @property
    def is_preferred(self) -> bool:
        blob = f"{self.title} {self.description} {self.category}".lower()
        return any(term in blob for term in NEWS_PREFER_TERMS) or self.category.lower() == "opmerkelijk"

    def voicetrack_text(self) -> str:
        clean_title = self.title.strip().rstrip(".")
        return f"Nog iets opvallends uit het nieuws: {clean_title}. Dat is zo'n bericht dat je bijna niet verzint."

    def short_date(self) -> str:
        try:
            dt = parsedate_to_datetime(self.pub_date)
            return f"{WEEKDAYS_NL[dt.weekday()].capitalize()} {dt.day} {MONTHS_NL[dt.month]}"
        except Exception:
            return self.pub_date


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


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

    turning_match = re.search(r"(?:wordt|zou)[^0-9]*(\d+) jaar", joined_facts, re.I)
    if turning_match:
        turning_age = int(turning_match.group(1))

    if "zou" in joined_facts.lower():
        deceased = True

    day_label = f"{page_date.day} {MONTHS_NL[page_date.month]}"
    clean_name = normalize_spaces(name)
    clean_bio = normalize_spaces(bio)

    if not clean_name and clean_bio:
        clean_name = clean_bio
        clean_bio = "Bekende persoon"

    return BirthdayPerson(
        query_date=day_label,
        query_date_iso=page_date.isoformat(),
        name=clean_name,
        bio=clean_bio,
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
    seen_names = set()

    for a in soup.find_all("a"):
        if not a.find("img"):
            continue

        text = normalize_spaces(a.get_text(" ", strip=True))
        if not text:
            img = a.find("img")
            text = normalize_spaces(img.get("alt", "")) if img else ""

        if not text or text.lower() in {"jarig vandaag", "datum"}:
            continue
        if text in seen_names:
            continue

        seen_names.add(text)

        img = a.find("img")
        image_url = urljoin(source_url, img.get("src")) if img and img.get("src") else None

        sibling_lines: List[str] = []
        for sibling in a.next_siblings:
            if isinstance(sibling, Tag) and sibling.name == "a" and sibling.find("img"):
                break
            txt = safe_text(sibling)
            if txt:
                sibling_lines.extend([normalize_spaces(part) for part in txt.split("\n") if normalize_spaces(part)])

        if len(sibling_lines) < 2 and a.parent:
            parent_text = a.parent.get_text("\n", strip=True)
            parent_lines = [normalize_spaces(x) for x in parent_text.split("\n") if normalize_spaces(x)]
            if parent_lines and parent_lines[0] == text:
                sibling_lines = parent_lines[1:]

        if not sibling_lines:
            continue

        bio = sibling_lines[0]
        fact_lines = sibling_lines[1:]
        people.append(
            parse_person_from_block(
                page_date=page_date,
                name=text,
                bio=bio,
                facts=fact_lines,
                image_url=image_url,
                source_url=source_url,
            )
        )
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

    while i < len(content):
        name = content[i]
        if any(skip in name.lower() for skip in ["twitter", "privacy", "cookie", "adverteren", "vorige dag", "volgende dag"]):
            i += 1
            continue

        bio = content[i + 1] if i + 1 < len(content) else "Bekende persoon"
        facts: List[str] = []
        if i + 2 < len(content):
            facts.append(content[i + 2])
        if i + 3 < len(content) and ("wordt" in content[i + 3].lower() or "zou" in content[i + 3].lower() or "is nu" in content[i + 3].lower()):
            facts.append(content[i + 3])
            i += 4
        else:
            i += 3

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

    unique = {}
    for person in people:
        key = (person.name, person.query_date_iso)
        if person.name and key not in unique:
            unique[key] = person
    return list(unique.values())


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_birthdays_for_date(page_date: date) -> List[BirthdayPerson]:
    url = url_for_date(page_date)
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    people = parse_with_anchor_blocks(soup, page_date, url)
    fallback_people = parse_with_text_fallback(soup, page_date, url)

    unique = {}
    for person in people + fallback_people:
        key = (person.name, person.query_date_iso)
        if person.name and key not in unique:
            unique[key] = person

    time.sleep(0.15)
    return list(unique.values())


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_nu_rss(feed_url: str) -> List[NewsItem]:
    response = requests.get(feed_url, headers={"User-Agent": USER_AGENT}, timeout=20)
    response.raise_for_status()

    root = ET.fromstring(response.content)
    items: List[NewsItem] = []

    for item in root.findall("./channel/item"):
        title = normalize_spaces(item.findtext("title", default=""))
        link = normalize_spaces(item.findtext("link", default=""))
        description_raw = item.findtext("description", default="") or ""
        description = BeautifulSoup(html.unescape(description_raw), "html.parser").get_text(" ", strip=True)
        description = normalize_spaces(description)
        pub_date = normalize_spaces(item.findtext("pubDate", default=""))
        category = normalize_spaces(item.findtext("category", default=""))
        enclosure = item.find("enclosure")
        image_url = enclosure.attrib.get("url") if enclosure is not None else None

        if title and link:
            items.append(
                NewsItem(
                    title=title,
                    link=link,
                    description=description,
                    pub_date=pub_date,
                    category=category or "opmerkelijk",
                    image_url=image_url,
                )
            )
    return items


def day_range(start_day: date, num_days: int) -> List[date]:
    return [start_day + timedelta(days=i) for i in range(num_days)]


def inject_custom_css():
    st.markdown(
        """
        <style>
        :root {
            --rm-orange: #F28C18;
            --rm-orange-2: #FFAA3B;
            --rm-orange-dark: #D97400;
            --rm-bg: #050C16;
            --rm-bg-soft: #091425;
            --rm-panel: rgba(14, 26, 43, 0.88);
            --rm-panel-2: rgba(19, 34, 56, 0.92);
            --rm-border: rgba(85, 110, 145, 0.28);
            --rm-border-strong: rgba(242, 140, 24, 0.30);
            --rm-text: #F7F9FC;
            --rm-muted: #A7B6CB;
            --rm-muted-2: #7F93AF;
            --rm-success: #7AD7A7;
            --rm-shadow: 0 18px 40px rgba(0, 0, 0, 0.26);
        }

        .stApp {
            background:
                radial-gradient(circle at top right, rgba(242, 140, 24, 0.12), transparent 24%),
                radial-gradient(circle at top left, rgba(54, 101, 172, 0.14), transparent 26%),
                linear-gradient(180deg, #040A13 0%, #08111F 42%, #091425 100%);
            color: var(--rm-text);
        }

        [data-testid="stHeader"] {
            background: transparent;
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, rgba(7, 15, 28, 0.98) 0%, rgba(10, 20, 37, 0.98) 100%);
            border-right: 1px solid var(--rm-border);
        }

        .block-container {
            max-width: 1260px;
            padding-top: 1.2rem;
            padding-bottom: 2rem;
        }

        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header[data-testid="stHeader"] {height: 0.5rem;}

        h1, h2, h3, h4, h5, h6,
        p, label, div, span, li {
            color: var(--rm-text);
        }

        .rm-hero {
            position: relative;
            overflow: hidden;
            padding: 1.4rem 1.5rem 1.2rem 1.5rem;
            border-radius: 24px;
            border: 1px solid var(--rm-border);
            background:
                linear-gradient(135deg, rgba(17, 31, 50, 0.94) 0%, rgba(10, 20, 36, 0.95) 100%);
            box-shadow: var(--rm-shadow);
            margin-bottom: 1.1rem;
        }

        .rm-hero::before {
            content: "";
            position: absolute;
            inset: 0;
            background:
                radial-gradient(circle at right top, rgba(242, 140, 24, 0.15), transparent 27%),
                radial-gradient(circle at left bottom, rgba(242, 140, 24, 0.08), transparent 20%);
            pointer-events: none;
        }

        .rm-badge-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin-top: 0.75rem;
        }

        .rm-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.38rem 0.7rem;
            font-size: 0.82rem;
            color: var(--rm-text);
            background: rgba(255,255,255,0.04);
            border: 1px solid var(--rm-border);
            border-radius: 999px;
            backdrop-filter: blur(6px);
        }

        .rm-title {
            font-size: 2.15rem;
            font-weight: 800;
            letter-spacing: -0.03em;
            margin: 0.3rem 0 0 0;
        }

        .rm-subtitle {
            color: var(--rm-orange);
            font-size: 1.08rem;
            font-weight: 700;
            letter-spacing: 0.02em;
            margin-top: 0.35rem;
            margin-bottom: 0;
        }

        .rm-section-intro {
            color: var(--rm-muted);
            margin: 0.1rem 0 1rem 0;
            font-size: 0.96rem;
        }

        .rm-subheader {
            display: inline-flex;
            align-items: center;
            gap: 0.55rem;
            font-size: 1.15rem;
            font-weight: 800;
            margin-bottom: 0.2rem;
        }

        .rm-soft-card {
            padding: 1rem 1.1rem;
            border-radius: 18px;
            border: 1px solid var(--rm-border);
            background: linear-gradient(180deg, rgba(14, 26, 43, 0.86) 0%, rgba(10, 21, 36, 0.92) 100%);
            box-shadow: 0 10px 30px rgba(0,0,0,0.18);
        }

        div[data-testid="stMetric"] {
            background: linear-gradient(180deg, rgba(18, 31, 49, 0.95) 0%, rgba(11, 22, 38, 0.95) 100%);
            border: 1px solid var(--rm-border);
            border-radius: 20px;
            padding: 0.9rem 1rem;
            box-shadow: 0 10px 24px rgba(0, 0, 0, 0.18);
        }

        div[data-testid="stMetricLabel"] > div {
            color: var(--rm-muted);
            font-weight: 600;
        }

        div[data-testid="stMetricValue"] {
            color: var(--rm-text);
            font-weight: 800;
        }

        div[data-baseweb="tab-list"] {
            gap: 0.65rem;
            margin-bottom: 0.6rem;
        }

        button[role="tab"] {
            background: rgba(18, 31, 49, 0.9);
            border: 1px solid var(--rm-border);
            border-radius: 14px;
            color: var(--rm-text);
            padding: 0.65rem 1rem;
            transition: all 0.2s ease;
        }

        button[role="tab"]:hover {
            border-color: var(--rm-border-strong);
            transform: translateY(-1px);
        }

        button[role="tab"][aria-selected="true"] {
            background: linear-gradient(180deg, var(--rm-orange) 0%, #E88011 100%);
            color: #111111;
            border-color: var(--rm-orange);
            font-weight: 800;
            box-shadow: 0 8px 22px rgba(242, 140, 24, 0.28);
        }

        .stButton > button,
        .stDownloadButton > button {
            background: linear-gradient(180deg, var(--rm-orange) 0%, #E88011 100%);
            color: #111111;
            border: none;
            border-radius: 14px;
            font-weight: 800;
            padding: 0.6rem 1rem;
            box-shadow: 0 10px 24px rgba(242, 140, 24, 0.20);
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover {
            background: linear-gradient(180deg, var(--rm-orange-2) 0%, var(--rm-orange) 100%);
            color: #111111;
        }

        div[data-baseweb="input"] > div,
        .stDateInput > div > div,
        .stTextInput > div > div {
            background: rgba(17, 30, 48, 0.92);
            color: var(--rm-text);
            border: 1px solid var(--rm-border);
            border-radius: 14px;
        }

        .stCheckbox label, .stRadio label, .stSelectbox label,
        .stDateInput label, .stTextInput label, .stSlider label {
            color: var(--rm-muted);
            font-weight: 600;
        }

        textarea, input {
            color: var(--rm-text) !important;
        }

        .stTextArea textarea {
            background: rgba(6, 14, 26, 0.96) !important;
            color: var(--rm-text) !important;
            border: 1px solid var(--rm-border) !important;
            border-radius: 14px !important;
        }

        div[data-testid="stDataFrame"] {
            border: 1px solid var(--rm-border);
            border-radius: 18px;
            overflow: hidden;
            box-shadow: 0 10px 24px rgba(0,0,0,0.18);
        }

        div[data-testid="stExpander"] {
            border: 1px solid var(--rm-border);
            border-radius: 18px;
            background: linear-gradient(180deg, rgba(14, 26, 43, 0.86) 0%, rgba(10, 21, 36, 0.90) 100%);
            overflow: hidden;
            box-shadow: 0 10px 24px rgba(0,0,0,0.15);
        }

        div[data-testid="stExpander"] summary {
            background: rgba(18, 31, 49, 0.60);
            border-radius: 18px;
            font-weight: 700;
        }

        div[data-testid="stExpander"] summary:hover {
            background: rgba(23, 39, 62, 0.85);
        }

        .stAlert {
            border-radius: 16px;
            border: 1px solid var(--rm-border);
        }

        a {
            color: var(--rm-orange) !important;
            font-weight: 600;
        }

        .stCodeBlock, pre {
            border-radius: 16px !important;
        }

        .rm-footer-note {
            margin-top: 1.2rem;
            padding: 0.95rem 1rem;
            border-radius: 16px;
            border: 1px solid var(--rm-border);
            background: rgba(15, 27, 43, 0.78);
            color: var(--rm-muted);
            font-size: 0.92rem;
        }

        hr {
            border-color: var(--rm-border);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

def render_hero_header():
    st.markdown(
        '''
        <div class="rm-hero">
            <div class="rm-title">Radio Dashboard</div>
            <div class="rm-subtitle">Verjaardagen en Opmerkelijk Nieuws</div>
            <div class="rm-badge-row">
                <div class="rm-badge">🎂 JarigVandaag</div>
                <div class="rm-badge">📰 NU.nl Opmerkelijk</div>
                <div class="rm-badge">🎙️ Klaar voor voicetracking</div>
            </div>
        </div>
        ''',
        unsafe_allow_html=True,
    )

def render_person_card(person: BirthdayPerson):
    col1, col2 = st.columns([1, 4], vertical_alignment="top")
    with col1:
        if person.image_url:
            st.image(person.image_url, use_container_width=True)
        else:
            st.markdown("🎂")
    with col2:
        badges = []
        if person.is_music:
            badges.append("🎵 muziek")
        if person.is_dutch:
            badges.append("🇳🇱 NL")
        if person.is_radio_friendly:
            badges.append("🎙️ radio-proof")
        if person.deceased:
            badges.append("🕯️ overleden")
        st.caption(" | ".join(badges) if badges else "algemeen")
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


def render_news_card(item: NewsItem):
    col1, col2 = st.columns([1, 4], vertical_alignment="top")
    with col1:
        if item.image_url:
            st.image(item.image_url, use_container_width=True)
        else:
            st.markdown("📰")
    with col2:
        badges = [f"categorie: {item.category}"]
        if item.is_radio_safe:
            badges.append("🎙️ radio-proof")
        if item.is_preferred:
            badges.append("⭐ bruikbaar")
        st.caption(" | ".join(badges))
        st.write(item.description)

        with st.expander("Voorleestekst voor voicetrack", expanded=False):
            st.text_area(
                "Tekst",
                value=item.voicetrack_text(),
                key=f"news_{item.link}",
                height=90,
                label_visibility="collapsed",
            )
            st.markdown(f"[Open bron]({item.link})")


def birthday_dataframe(people: List[BirthdayPerson]) -> pd.DataFrame:
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
    return df[
        [
            "query_date", "name", "bio", "turning_age", "current_age", "deceased",
            "is_music", "is_dutch", "is_radio_friendly", "source_url"
        ]
    ]


def news_dataframe(items: List[NewsItem]) -> pd.DataFrame:
    rows = []
    for item in items:
        rows.append(
            {
                "datum": item.short_date(),
                "titel": item.title,
                "omschrijving": item.description,
                "categorie": item.category,
                "radio_proof": item.is_radio_safe,
                "bruikbaar": item.is_preferred,
                "link": item.link,
            }
        )
    return pd.DataFrame(rows)


def parsed_pub_date_to_date(pub_date: str) -> Optional[date]:
    try:
        return parsedate_to_datetime(pub_date).date()
    except Exception:
        return None


def rank_people_for_voicetrack(people: List[BirthdayPerson]) -> List[BirthdayPerson]:
    return sorted(
        people,
        key=lambda p: (
            0 if p.is_music else 1,
            0 if p.is_radio_friendly else 1,
            0 if p.is_dutch else 1,
            1 if p.deceased else 0,
            p.name.lower() if p.name else "zzz",
        ),
    )


def select_news_for_voicetrack(news_items: List[NewsItem], target_date: date, max_items: int = 1):
    exact = [
        item for item in news_items
        if item.is_radio_safe and parsed_pub_date_to_date(item.pub_date) == target_date
    ]
    if exact:
        exact_sorted = sorted(exact, key=lambda i: (0 if i.is_preferred else 1, i.title.lower()))
        return exact_sorted[:max_items], "exact"

    recent_safe = [item for item in news_items if item.is_radio_safe]
    if recent_safe:
        recent_sorted = sorted(recent_safe, key=lambda i: (0 if i.is_preferred else 1, i.title.lower()))
        return recent_sorted[:max_items], "recent"

    return [], "none"


def birthday_line_for_script(person: BirthdayPerson) -> str:
    if person.deceased:
        if person.turning_age:
            return f"Op de kalender staat ook {person.name}: die zou {person.turning_age} jaar zijn geworden. Je kent {person.name} als {person.bio}."
        return f"Op de kalender staat ook {person.name}. {person.name} stond bekend als {person.bio}."

    if person.turning_age:
        return f"{person.name} is jarig en wordt {person.turning_age} jaar. Je kent {person.name} als {person.bio}."
    return f"{person.name} is jarig. Je kent {person.name} als {person.bio}."


def build_complete_voicetrack(
    day_obj: date,
    day_people: List[BirthdayPerson],
    news_items: List[NewsItem],
    news_mode: str,
    script_length: str = "normaal",
) -> str:
    weekday = WEEKDAYS_NL[day_obj.weekday()]
    month = MONTHS_NL[day_obj.month]
    ranked_people = rank_people_for_voicetrack(day_people)

    if script_length == "kort":
        chosen_people = ranked_people[:1]
    elif script_length == "uitgebreid":
        chosen_people = ranked_people[:4]
    else:
        chosen_people = ranked_people[:3]

    lines = [
        f"Het is {weekday} {day_obj.day} {month} en dit is jouw korte update op Radio Muziekstad.",
    ]

    if chosen_people:
        if script_length == "kort":
            lines.append("Even snel naar de verjaardagskalender van vandaag.")
        elif len(chosen_people) == 1:
            lines.append("Er staat vandaag één naam op de verjaardagskalender die je eruit kunt lichten.")
        else:
            lines.append(f"Op de verjaardagskalender staan vandaag {len(chosen_people)} namen die leuk zijn om even mee te pakken.")

        for idx, person in enumerate(chosen_people):
            if script_length == "kort" and idx > 0:
                break
            lines.append(birthday_line_for_script(person))

    if news_items:
        if news_mode == "exact":
            intro = "En ook nog iets opmerkelijks van vandaag."
        else:
            intro = "En nog iets opvallends dat de afgelopen dagen in het nieuws opdook."
        lines.append(intro)

        if script_length == "kort":
            lines.append(f"{news_items[0].title}.")
        elif script_length == "uitgebreid":
            for item in news_items[:2]:
                lines.append(f"{item.title}.")
                if item.description:
                    lines.append(item.description)
        else:
            item = news_items[0]
            lines.append(f"{item.title}.")
    else:
        if script_length == "kort":
            lines.append("Verder kun je hier nog een kort opvallend nieuwtje aan toevoegen.")
        else:
            lines.append("Voor het opmerkelijke nieuws kun je hier later nog een extra luchtig item aan toevoegen.")

    if script_length == "uitgebreid":
        lines.append("Zo heb je in één keer een complete en vloeiende break met zowel verjaardagen als een opvallend nieuwsmoment.")
        lines.append("Dat was 'm voor nu op Radio Muziekstad, en we gaan natuurlijk verder met muziek die je pakt.")
    elif script_length == "kort":
        lines.append("En we gaan snel weer verder met muziek die je pakt.")
    else:
        lines.append("Dat was 'm voor nu, en natuurlijk gaan we weer verder met muziek die je pakt.")

    return "\n\n".join(lines)


def birthdays_tab():
    st.markdown('<div class="rm-subheader">🎂 Verjaardagen van JarigVandaag</div>', unsafe_allow_html=True)
    st.markdown('<div class="rm-section-intro">Haal verjaardagen op voor de komende dagen en filter op muziek, Nederland en radio-geschiktheid.</div>', unsafe_allow_html=True)

    col_a, col_b, col_c, col_d, col_e = st.columns([1, 1, 1, 1, 1])
    with col_a:
        start_day = st.date_input("Startdatum", value=date.today(), key="b_start")
    with col_b:
        num_days = st.slider("Aantal dagen", min_value=1, max_value=14, value=7, key="b_days")
    with col_c:
        only_music = st.checkbox("Alleen muziek", value=True, key="b_music")
    with col_d:
        only_dutch = st.checkbox("Alleen NL", value=False, key="b_nl")
    with col_e:
        include_deceased = st.checkbox("Overleden tonen", value=False, key="b_deceased")

    only_radio = st.checkbox("Alleen radio-proof", value=False, key="b_radio")

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
            preview_df = birthday_dataframe(day_people)
            if not preview_df.empty:
                st.dataframe(
                    preview_df.rename(
                        columns={
                            "query_date": "Datum",
                            "name": "Naam",
                            "bio": "Omschrijving",
                            "turning_age": "Wordt",
                            "current_age": "Nu",
                            "deceased": "Overleden",
                            "is_music": "Muziek",
                            "is_dutch": "NL",
                            "is_radio_friendly": "Radio-proof",
                            "source_url": "Bron",
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

            st.markdown("### Aanklikbare items")
            for idx, person in enumerate(day_people, start=1):
                name = person.name if person.name else "Onbekende naam"
                with st.expander(f"{idx}. {name} — {person.bio}"):
                    render_person_card(person)

            st.markdown("### Complete dag-voicetrack")
            selected_news, news_mode = select_news_for_voicetrack(news_items_for_scripts, day_obj, max_items=2)

            if selected_news:
                if news_mode == "exact":
                    st.caption(f"Deze dag-voicetrack gebruikt een opmerkelijk item van dezelfde datum: {selected_news[0].title}")
                else:
                    st.caption(f"Deze dag-voicetrack gebruikt het meest bruikbare recente opmerkelijke item: {selected_news[0].title}")
            else:
                st.caption("Geen opmerkelijk nieuws beschikbaar: de voicetrack wordt dan opgebouwd uit verjaardagen en een open nieuwsbrug.")

            length_key = f"script_length_{day_iso}"
            tone_key = f"script_tone_{day_iso}"

            col_len, col_tone = st.columns(2)
            with col_len:
                st.radio(
                    "Lengte",
                    options=["kort", "normaal", "uitgebreid"],
                    index=1,
                    horizontal=True,
                    key=length_key,
                )
            with col_tone:
                st.radio(
                    "Stijl",
                    options=["luchtig", "enthousiast", "zakelijk"],
                    index=0,
                    horizontal=True,
                    key=tone_key,
                )

            script_key = f"complete_voicetrack_{day_iso}"
            if st.button("🎙️ Maak complete voicetrack voor deze dag", key=f"btn_{day_iso}"):
                st.session_state[script_key] = build_complete_voicetrack(
                    day_obj,
                    day_people,
                    selected_news,
                    news_mode,
                    script_length=st.session_state[length_key],
                    script_tone=st.session_state[tone_key],
                )

            if script_key in st.session_state:
                current_length = st.session_state.get(length_key, "normaal")
                current_tone = st.session_state.get(tone_key, "luchtig")
                current_script = build_complete_voicetrack(
                    day_obj,
                    day_people,
                    selected_news,
                    news_mode,
                    script_length=current_length,
                    script_tone=current_tone,
                )
                st.text_area(
                    "Complete voicetrack",
                    value=current_script,
                    key=f"ta_{day_iso}",
                    height=340 if current_length == "uitgebreid" else 250,
                )
                st.download_button(
                    "⬇️ Download voicetrack als TXT",
                    data=current_script.encode("utf-8"),
                    file_name=f"voicetrack_{day_iso}_{current_length}_{current_tone}.txt",
                    mime="text/plain",
                    key=f"dl_{day_iso}",
                )

    csv_df = birthday_dataframe(filtered)
    if not csv_df.empty:
        st.download_button(
            "⬇️ Download verjaardagen als CSV",
            data=csv_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="jarigvandaag_selectie.csv",
            mime="text/csv",
        )


def news_tab():
    st.markdown('<div class="rm-subheader">📰 Opmerkelijk nieuws van NU.nl</div>', unsafe_allow_html=True)
    st.markdown('<div class="rm-section-intro">Laad de Opmerkelijk RSS-feed in en filter op radio-vriendelijke items voor je voicetracks.</div>', unsafe_allow_html=True)

    col_a, col_b, col_c = st.columns([3, 1, 1])
    with col_a:
        rss_url = st.text_input("RSS-url", value=NU_RSS_URL, key="n_rss")
    with col_b:
        only_safe = st.checkbox("Alleen radio-proof", value=True, key="n_safe")
    with col_c:
        only_preferred = st.checkbox("Alleen bruikbaar", value=False, key="n_pref")

    try:
        items = fetch_nu_rss(rss_url)
    except Exception as exc:
        st.error(f"RSS kon niet worden geladen: {exc}")
        return

    filtered = []
    for item in items:
        if only_safe and not item.is_radio_safe:
            continue
        if only_preferred and not item.is_preferred:
            continue
        filtered.append(item)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Items in feed", len(items))
    m2.metric("Na filters", len(filtered))
    m3.metric("Radio-proof", sum(1 for i in items if i.is_radio_safe))
    m4.metric("Bruikbaar", sum(1 for i in items if i.is_preferred))

    if not filtered:
        st.info("Geen nieuwsitems met deze filters.")
        return

    df = news_dataframe(filtered)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("### Aanklikbare items")
    for idx, item in enumerate(filtered, start=1):
        with st.expander(f"{idx}. {item.title} — {item.short_date()}"):
            render_news_card(item)

    st.download_button(
        "⬇️ Download nieuwsitems als CSV",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name="nu_opmerkelijk_selectie.csv",
        mime="text/csv",
    )


def app():
    inject_custom_css()

    st.image("radio_muziekstad_logo.png", use_container_width=True)
    render_hero_header()

    tab1, tab2 = st.tabs(["🎂 Verjaardagen", "📰 Opmerkelijk nieuws"])
    with tab1:
        birthdays_tab()
    with tab2:
        news_tab()

    st.markdown(
        '<div class="rm-footer-note">Tip: upload alle bestanden inclusief <strong>radio_muziekstad_logo.png</strong> en de map <strong>.streamlit</strong> naar GitHub voor de volledige styling in Streamlit Community Cloud.</div>',
        unsafe_allow_html=True,
    )
    st.markdown("## Start lokaal")
    st.code("streamlit run app.py", language="bash")

if __name__ == "__main__":
    app()
