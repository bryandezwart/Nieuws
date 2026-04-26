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
    page_title="Radio Dashboard",
    page_icon="🎙️",
    layout="wide",
)

BASE_URL = "https://www.jarigvandaag.nl"
NU_RSS_URL = "https://www.nu.nl/rss/Opmerkelijk"

MONTHS_NL = {
    1: "januari", 2: "februari", 3: "maart", 4: "april",
    5: "mei", 6: "juni", 7: "juli", 8: "augustus",
    9: "september", 10: "oktober", 11: "november", 12: "december",
}
WEEKDAYS_NL = {
    0: "maandag", 1: "dinsdag", 2: "woensdag", 3: "donderdag",
    4: "vrijdag", 5: "zaterdag", 6: "zondag",
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
    "presentator", "presentatrice", "radio", "televisie", "acteur",
    "actrice", "cabaretier", "entertainer", "comedian", "persoonlijkheid",
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

USER_AGENT = "Mozilla/5.0 (compatible; RadioVoicetrackDashboard/4.0)"


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
        return any(word in self.bio.lower() for word in MUSIC_KEYWORDS)

    @property
    def is_dutch(self) -> bool:
        return any(word in self.bio.lower() for word in DUTCH_KEYWORDS)

    @property
    def is_radio_friendly(self) -> bool:
        bio = self.bio.lower()
        return self.is_music or any(word in bio for word in RADIO_KEYWORDS)


@dataclass
class NewsItem:
    title: str
    link: str
    description: str
    pub_date: str
    category: str
    image_url: Optional[str]

    @property
    def is_radio_safe(self) -> bool:
        blob = f"{self.title} {self.description} {self.category}".lower()
        return not any(term in blob for term in NEWS_EXCLUDE_TERMS)

    @property
    def is_preferred(self) -> bool:
        blob = f"{self.title} {self.description} {self.category}".lower()
        return any(term in blob for term in NEWS_PREFER_TERMS) or self.category.lower() == "opmerkelijk"

    def short_date(self) -> str:
        try:
            dt = parsedate_to_datetime(self.pub_date)
            return f"{WEEKDAYS_NL[dt.weekday()].capitalize()} {dt.day} {MONTHS_NL[dt.month]}"
        except Exception:
            return self.pub_date


def inject_custom_css():
    st.markdown(
        """
        <style>
        :root {
            --rm-orange: #F28C18;
            --rm-orange-2: #FFB347;
            --rm-orange-dark: #DA7405;
            --rm-bg-1: #050B14;
            --rm-bg-2: #0A1321;
            --rm-panel: rgba(15, 27, 45, 0.92);
            --rm-panel-2: rgba(19, 35, 56, 0.95);
            --rm-border: rgba(255, 176, 71, 0.18);
            --rm-border-strong: rgba(242, 140, 24, 0.42);
            --rm-text: #F7F9FC;
            --rm-muted: #A9B7C8;
            --rm-shadow: 0 20px 44px rgba(0, 0, 0, 0.32);
        }

        .stApp {
            background:
                radial-gradient(circle at top right, rgba(242, 140, 24, 0.14), transparent 24%),
                radial-gradient(circle at bottom left, rgba(255, 179, 71, 0.08), transparent 22%),
                linear-gradient(180deg, var(--rm-bg-1) 0%, var(--rm-bg-2) 48%, #0D1728 100%);
            color: var(--rm-text);
        }

        [data-testid="stHeader"] {background: transparent;}
        #MainMenu, footer {visibility: hidden;}
        .block-container {max-width: 1280px; padding-top: 1rem; padding-bottom: 2rem;}
        h1, h2, h3, h4, h5, h6, p, label, div, span {color: var(--rm-text);}

        .rm-hero {
            position: relative;
            overflow: hidden;
            padding: 1.5rem 1.6rem 1.2rem 1.6rem;
            border-radius: 26px;
            background: linear-gradient(135deg, rgba(16, 28, 46, 0.97) 0%, rgba(10, 21, 35, 0.98) 100%);
            border: 1px solid var(--rm-border);
            box-shadow: var(--rm-shadow);
            margin-bottom: 1.2rem;
        }
        .rm-hero::before {
            content: "";
            position: absolute;
            inset: 0;
            background:
                radial-gradient(circle at 85% 10%, rgba(242,140,24,0.18), transparent 24%),
                radial-gradient(circle at 8% 90%, rgba(255,179,71,0.08), transparent 20%);
            pointer-events: none;
        }
        .rm-title {font-size: 2.25rem; font-weight: 800; letter-spacing: -0.03em; margin: 0.1rem 0 0 0;}
        .rm-subtitle {color: var(--rm-orange); font-size: 1.08rem; font-weight: 700; margin-top: 0.38rem;}
        .rm-badges {display: flex; flex-wrap: wrap; gap: 0.6rem; margin-top: 0.95rem;}
        .rm-badge {
            display: inline-flex; align-items: center; gap: 0.4rem;
            background: rgba(255,255,255,0.04);
            border: 1px solid var(--rm-border);
            border-radius: 999px;
            padding: 0.42rem 0.78rem;
            font-size: 0.83rem;
            color: var(--rm-text);
            backdrop-filter: blur(6px);
        }
        .rm-subheader {display: inline-flex; align-items: center; gap: 0.55rem; font-size: 1.18rem; font-weight: 800; margin-bottom: 0.18rem;}
        .rm-section-intro {color: var(--rm-muted); margin-bottom: 1rem;}

        div[data-testid="stMetric"] {
            background: linear-gradient(180deg, rgba(19, 34, 56, 0.95) 0%, rgba(12, 24, 41, 0.96) 100%);
            border: 1px solid var(--rm-border);
            border-radius: 20px;
            padding: 0.9rem 1rem;
            box-shadow: 0 10px 22px rgba(0, 0, 0, 0.18);
        }

        div[data-baseweb="tab-list"] {gap: 0.65rem; margin-bottom: 0.65rem;}
        button[role="tab"] {
            border-radius: 14px !important;
            border: 1px solid var(--rm-border) !important;
            background: rgba(19, 34, 56, 0.88) !important;
            color: var(--rm-text) !important;
            padding: 0.7rem 1rem !important;
            box-shadow: none !important;
        }
        button[role="tab"][aria-selected="true"] {
            background: linear-gradient(180deg, var(--rm-orange) 0%, var(--rm-orange-dark) 100%) !important;
            color: #141414 !important;
            border-color: var(--rm-orange) !important;
            box-shadow: 0 10px 24px rgba(242,140,24,0.28) !important;
            font-weight: 800 !important;
        }

        .stButton > button, .stDownloadButton > button {
            background: linear-gradient(180deg, var(--rm-orange) 0%, var(--rm-orange-dark) 100%) !important;
            color: #101010 !important;
            border: none !important;
            border-radius: 14px !important;
            font-weight: 800 !important;
            box-shadow: 0 12px 28px rgba(242,140,24,0.24) !important;
        }
        .stButton > button:hover, .stDownloadButton > button:hover {
            transform: translateY(-1px);
            filter: brightness(1.02);
        }

        .stSlider [data-baseweb="slider"] div[role="slider"] {
            background: var(--rm-orange) !important;
            border-color: var(--rm-orange) !important;
            box-shadow: 0 0 0 2px rgba(242,140,24,0.2) !important;
        }
        .stSlider [data-baseweb="slider"] > div > div > div {background: var(--rm-orange) !important;}
        div[data-baseweb="checkbox"] div[aria-checked="true"] {
            background-color: var(--rm-orange) !important;
            border-color: var(--rm-orange) !important;
        }
        input, textarea {
            caret-color: var(--rm-orange) !important;
        }
        div[data-baseweb="input"] > div, .stDateInput > div > div {
            background: rgba(14,26,42,0.96) !important;
            border: 1px solid var(--rm-border) !important;
            border-radius: 14px !important;
        }
        .stTextArea textarea {
            background: rgba(8, 16, 29, 0.98) !important;
            color: var(--rm-text) !important;
            border: 1px solid var(--rm-border) !important;
            border-radius: 14px !important;
        }

        div[data-testid="stDataFrame"], div[data-testid="stExpander"] {
            border: 1px solid var(--rm-border);
            border-radius: 18px;
            overflow: hidden;
            box-shadow: 0 10px 24px rgba(0,0,0,0.18);
        }
        div[data-testid="stExpander"] {
            background: linear-gradient(180deg, rgba(15,27,45,0.92) 0%, rgba(10,20,35,0.94) 100%);
        }
        div[data-testid="stExpander"] summary {
            background: rgba(21, 38, 61, 0.58);
            border-radius: 18px;
            font-weight: 700;
        }
        a {color: var(--rm-orange) !important; font-weight: 700;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero_header():
    st.markdown(
        """
        <div class="rm-hero">
            <div class="rm-title">Radio Dashboard</div>
            <div class="rm-subtitle">Verjaardagen en Opmerkelijk Nieuws</div>
            <div class="rm-badges">
                <div class="rm-badge">🎂 JarigVandaag</div>
                <div class="rm-badge">📰 NU.nl Opmerkelijk</div>
                <div class="rm-badge">🎙️ Premium voicetrack-overzicht</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def looks_like_date_text(text: str) -> bool:
    text = normalize_spaces(text).lower().strip(".")
    if re.fullmatch(r"\d{2}-\d{2}-\d{4}", text):
        return True
    if re.fullmatch(r"\d{1,2}\s+(januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december)", text):
        return True
    return False


def contains_letters(text: str) -> bool:
    return bool(re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", text or ""))


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


def parse_person_from_block(page_date: date, name: str, bio: str, facts: List[str], image_url: Optional[str], source_url: str) -> BirthdayPerson:
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

    return BirthdayPerson(
        query_date=f"{page_date.day} {MONTHS_NL[page_date.month]}",
        query_date_iso=page_date.isoformat(),
        name=normalize_spaces(name),
        bio=normalize_spaces(bio) or "Bekende persoon",
        birth_date=birth_date,
        current_age=current_age,
        turning_age=turning_age,
        deceased=deceased,
        death_date=death_date,
        image_url=image_url,
        source_url=source_url,
    )


def parse_with_anchor_blocks(soup: BeautifulSoup, page_date: date, source_url: str) -> List[BirthdayPerson]:
    people = []
    seen_names = set()
    for a in soup.find_all("a"):
        if not a.find("img"):
            continue
        text = normalize_spaces(a.get_text(" ", strip=True))
        if not text:
            img = a.find("img")
            text = normalize_spaces(img.get("alt", "")) if img else ""
        if not text or text.lower() in {"jarig vandaag", "datum"} or text in seen_names:
            continue
        seen_names.add(text)
        img = a.find("img")
        image_url = urljoin(source_url, img.get("src")) if img and img.get("src") else None
        sibling_lines = []
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
        people.append(parse_person_from_block(page_date, text, sibling_lines[0], sibling_lines[1:], image_url, source_url))
    return people


def parse_with_text_fallback(soup: BeautifulSoup, page_date: date, source_url: str) -> List[BirthdayPerson]:
    text = soup.get_text("\n", strip=True)
    lines = [normalize_spaces(x) for x in text.split("\n") if normalize_spaces(x)]
    start_idx = 0
    for i, line in enumerate(lines):
        if line.startswith("Bekijk de lijst hieronder") or line.startswith("Iedere dag een nieuw overzicht") or line.startswith("Lijst met bekende personen"):
            start_idx = i + 1
            break
    end_idx = len(lines)
    end_markers = {"Volg ons ook op Twitter", "Onvolledigheden of onjuistheden", "Adverteren op JarigVandaag.nl"}
    for i, line in enumerate(lines[start_idx:], start=start_idx):
        if line in end_markers or line.startswith("←") or line.endswith("→"):
            end_idx = i
            break
    content = lines[start_idx:end_idx]
    people = []
    i = 0
    while i < len(content):
        name = content[i]
        bio = content[i + 1] if i + 1 < len(content) else "Bekende persoon"
        facts = []
        if i + 2 < len(content):
            facts.append(content[i + 2])
        if i + 3 < len(content) and ("wordt" in content[i + 3].lower() or "zou" in content[i + 3].lower() or "is nu" in content[i + 3].lower()):
            facts.append(content[i + 3])
            i += 4
        else:
            i += 3
        people.append(parse_person_from_block(page_date, name, bio, facts, None, source_url))
    return people


def is_valid_birthday_person(person: BirthdayPerson) -> bool:
    name = normalize_spaces(person.name)
    bio = normalize_spaces(person.bio)
    name_lower = name.lower().strip(".")
    bio_lower = bio.lower().strip(".")

    invalid_name_exact = {"", ".", "algemeen", "none", "bekende persoon", "jarig", person.query_date.lower()}
    invalid_name_phrases = ["is geboren op", "vandaag is", "jaar oud geworden", "zijn op ", "worden op ", "op deze dag"]
    invalid_bio_phrases = ["is geboren op", "vandaag is", "jaar oud geworden"]

    if name_lower in invalid_name_exact or looks_like_date_text(name) or not contains_letters(name):
        return False
    if any(phrase in name_lower for phrase in invalid_name_phrases):
        return False
    if bio_lower in {"", ".", "none"}:
        return False
    if any(phrase in bio_lower for phrase in invalid_bio_phrases) and not any(k in bio_lower for k in MUSIC_KEYWORDS + RADIO_KEYWORDS + DUTCH_KEYWORDS):
        return False
    return True


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
        if not is_valid_birthday_person(person):
            continue
        key = (person.name, person.query_date_iso)
        if key not in unique:
            unique[key] = person
    time.sleep(0.1)
    return list(unique.values())


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_nu_rss(feed_url: str) -> List[NewsItem]:
    response = requests.get(feed_url, headers={"User-Agent": USER_AGENT}, timeout=20)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    items = []
    for item in root.findall("./channel/item"):
        title = normalize_spaces(item.findtext("title", default=""))
        link = normalize_spaces(item.findtext("link", default=""))
        description_raw = item.findtext("description", default="") or ""
        description = BeautifulSoup(html.unescape(description_raw), "html.parser").get_text(" ", strip=True)
        pub_date = normalize_spaces(item.findtext("pubDate", default=""))
        category = normalize_spaces(item.findtext("category", default="")) or "opmerkelijk"
        enclosure = item.find("enclosure")
        image_url = enclosure.attrib.get("url") if enclosure is not None else None
        if title and link:
            items.append(NewsItem(title, link, normalize_spaces(description), pub_date, category, image_url))
    return items


def day_range(start_day: date, num_days: int) -> List[date]:
    return [start_day + timedelta(days=i) for i in range(num_days)]


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
            p.name.lower(),
        ),
    )


def select_news_for_voicetrack(news_items: List[NewsItem], target_date: date, max_items: int = 1):
    exact = [item for item in news_items if item.is_radio_safe and parsed_pub_date_to_date(item.pub_date) == target_date]
    if exact:
        exact = sorted(exact, key=lambda i: (0 if i.is_preferred else 1, i.title.lower()))
        return exact[:max_items], "exact"
    recent_safe = [item for item in news_items if item.is_radio_safe]
    if recent_safe:
        recent_safe = sorted(recent_safe, key=lambda i: (0 if i.is_preferred else 1, i.title.lower()))
        return recent_safe[:max_items], "recent"
    return [], "none"


def birthday_line_for_script(person: BirthdayPerson, tone: str = "luchtig") -> str:
    if tone == "enthousiast":
        if person.deceased:
            if person.turning_age:
                return f"En hoe leuk is deze naam: {person.name} zou vandaag {person.turning_age} jaar zijn geworden. Een naam die je kent als {person.bio}."
            return f"En ook deze naam mag je best even noemen: {person.name}, bekend als {person.bio}."
        if person.turning_age:
            return f"Ook leuk voor vandaag: {person.name} is jarig en wordt {person.turning_age} jaar. Je kent {person.name} natuurlijk als {person.bio}."
        return f"Ook leuk voor vandaag: {person.name} is jarig. Je kent {person.name} natuurlijk als {person.bio}."
    if tone == "zakelijk":
        if person.deceased:
            if person.turning_age:
                return f"Op de kalender staat {person.name}; die zou vandaag {person.turning_age} jaar zijn geworden. Bekend als {person.bio}."
            return f"Op de kalender staat {person.name}, bekend als {person.bio}."
        if person.turning_age:
            return f"{person.name} is vandaag jarig en wordt {person.turning_age} jaar. Bekend als {person.bio}."
        return f"{person.name} is vandaag jarig. Bekend als {person.bio}."
    if person.deceased:
        if person.turning_age:
            return f"Op de kalender staat ook {person.name}: die zou {person.turning_age} jaar zijn geworden. Je kent {person.name} als {person.bio}."
        return f"Op de kalender staat ook {person.name}. {person.name} stond bekend als {person.bio}."
    if person.turning_age:
        return f"{person.name} is jarig en wordt {person.turning_age} jaar. Je kent {person.name} als {person.bio}."
    return f"{person.name} is jarig. Je kent {person.name} als {person.bio}."


def build_complete_voicetrack(day_obj: date, day_people: List[BirthdayPerson], news_items: List[NewsItem], news_mode: str, script_length: str = "normaal", script_tone: str = "luchtig") -> str:
    weekday = WEEKDAYS_NL[day_obj.weekday()]
    month = MONTHS_NL[day_obj.month]
    ranked_people = rank_people_for_voicetrack(day_people)
    chosen_people = ranked_people[:1] if script_length == "kort" else ranked_people[:4] if script_length == "uitgebreid" else ranked_people[:3]

    if script_tone == "enthousiast":
        opener = f"Yes, het is {weekday} {day_obj.day} {month} en tijd voor een lekkere snelle update op Radio Muziekstad."
        exact_intro = "En dan nog iets opmerkelijks van vandaag, ook zo'n verhaal waarvan je denkt: dat verzin je niet."
        recent_intro = "En ook nog een opvallend nieuwtje dat de afgelopen dagen voorbij kwam."
        no_news = "Voor het opmerkelijke nieuws kun je hier later nog een extra opvallend item aan toevoegen."
        outro = "Zo heb je meteen een complete, energieke break te pakken. En natuurlijk gaan we verder met muziek die je pakt."
    elif script_tone == "zakelijk":
        opener = f"Het is {weekday} {day_obj.day} {month} en dit is de update van Radio Muziekstad."
        exact_intro = "Daarnaast is er ook een opmerkelijk nieuwsitem van vandaag."
        recent_intro = "Daarnaast is er ook een opvallend nieuwsitem van de afgelopen dagen."
        no_news = "Voor het opmerkelijke nieuws kan hier later nog een aanvullend item worden toegevoegd."
        outro = "Zo staat er een complete, rustige break klaar. We gaan verder met muziek op Radio Muziekstad."
    else:
        opener = f"Het is {weekday} {day_obj.day} {month} en dit is jouw korte update op Radio Muziekstad."
        exact_intro = "En ook nog iets opmerkelijks van vandaag."
        recent_intro = "En nog iets opvallends dat de afgelopen dagen in het nieuws opdook."
        no_news = "Voor het opmerkelijke nieuws kun je hier later nog een extra luchtig item aan toevoegen."
        outro = "Zo heb je in één keer een complete en vloeiende break met zowel verjaardagen als een opvallend nieuwsmoment. Dat was 'm voor nu, en natuurlijk gaan we weer verder met muziek die je pakt."

    lines = [opener]
    if chosen_people:
        intro = f"Op de verjaardagskalender staan vandaag {len(chosen_people)} namen die je mooi kunt meenemen in je break."
        lines.append(intro)
        for idx, person in enumerate(chosen_people):
            if script_length == "kort" and idx > 0:
                break
            lines.append(birthday_line_for_script(person, tone=script_tone))
    if news_items:
        lines.append(exact_intro if news_mode == "exact" else recent_intro)
        lines.append(f"{news_items[0].title}.")
        if script_length == "uitgebreid" and news_items[0].description:
            lines.append(news_items[0].description)
    else:
        lines.append(no_news)
    lines.append(outro)
    return "\n\n".join(lines)


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
    return df[["query_date", "name", "bio", "turning_age", "current_age", "deceased", "is_music", "is_dutch", "is_radio_friendly", "source_url"]]


def news_dataframe(items: List[NewsItem]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "datum": item.short_date(),
            "titel": item.title,
            "omschrijving": item.description,
            "categorie": item.category,
            "radio_proof": item.is_radio_safe,
            "bruikbaar": item.is_preferred,
            "link": item.link,
        }
        for item in items
    ])


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
            st.text_area("Tekst", value=birthday_line_for_script(person, tone="luchtig"), height=90, label_visibility="collapsed", key=f"vt_{person.query_date_iso}_{person.name}")
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
            st.text_area("Tekst", value=f"Nog iets opvallends uit het nieuws: {item.title}. Dat is zo'n bericht dat je bijna niet verzint.", height=90, label_visibility="collapsed", key=f"news_{item.link}")
            st.markdown(f"[Open bron]({item.link})")


def birthdays_tab():
    st.markdown('<div class="rm-subheader">🎂 Verjaardagen van JarigVandaag</div>', unsafe_allow_html=True)
    st.markdown('<div class="rm-section-intro">Haal verjaardagen op voor de komende dagen en filter op muziek, Nederland en radio-geschiktheid.</div>', unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 1])
    with c1:
        start_day = st.date_input("Startdatum", value=date.today())
    with c2:
        num_days = st.slider("Aantal dagen", 1, 14, 7)
    with c3:
        only_music = st.checkbox("Alleen muziek", value=True)
    with c4:
        only_dutch = st.checkbox("Alleen NL", value=False)
    with c5:
        include_deceased = st.checkbox("Overleden tonen", value=False)
    only_radio = st.checkbox("Alleen radio-proof", value=False)

    all_people = []
    errors = []
    with st.spinner("Verjaardagen ophalen..."):
        for d in day_range(start_day, num_days):
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

    try:
        news_items_for_scripts = fetch_nu_rss(NU_RSS_URL)
    except Exception:
        news_items_for_scripts = []

    grouped = {}
    for person in filtered:
        grouped.setdefault(person.query_date_iso, []).append(person)

    for day_iso in sorted(grouped):
        day_people = grouped[day_iso]
        day_obj = datetime.strptime(day_iso, "%Y-%m-%d").date()
        label = f"{WEEKDAYS_NL[day_obj.weekday()].capitalize()} {day_obj.day} {MONTHS_NL[day_obj.month]}"
        music_count = sum(1 for p in day_people if p.is_music)
        with st.expander(f"{label} — {len(day_people)} personen • {music_count} muziek", expanded=(day_iso == sorted(grouped)[0])):
            df = birthday_dataframe(day_people)
            if not df.empty:
                st.dataframe(df.rename(columns={
                    "query_date": "Datum", "name": "Naam", "bio": "Omschrijving", "turning_age": "Wordt",
                    "current_age": "Nu", "deceased": "Overleden", "is_music": "Muziek", "is_dutch": "NL",
                    "is_radio_friendly": "Radio-proof", "source_url": "Bron",
                }), use_container_width=True, hide_index=True)
            st.markdown("### Aanklikbare items")
            for idx, person in enumerate(day_people, start=1):
                with st.expander(f"{idx}. {person.name} — {person.bio}"):
                    render_person_card(person)
            st.markdown("### Complete dag-voicetrack")
            selected_news, news_mode = select_news_for_voicetrack(news_items_for_scripts, day_obj, max_items=2)
            if selected_news:
                st.caption(f"Gebruikt nieuwsitem: {selected_news[0].title}")
            else:
                st.caption("Geen opmerkelijk nieuws beschikbaar; de voicetrack bestaat dan uit verjaardagen.")
            len_col, tone_col = st.columns(2)
            with len_col:
                st.radio("Lengte", ["kort", "normaal", "uitgebreid"], horizontal=True, index=1, key=f"len_{day_iso}")
            with tone_col:
                st.radio("Stijl", ["luchtig", "enthousiast", "zakelijk"], horizontal=True, index=0, key=f"tone_{day_iso}")
            if st.button("🎙️ Maak complete voicetrack voor deze dag", key=f"btn_{day_iso}"):
                st.session_state[f"show_script_{day_iso}"] = True
            if st.session_state.get(f"show_script_{day_iso}"):
                script = build_complete_voicetrack(
                    day_obj,
                    day_people,
                    selected_news,
                    news_mode,
                    script_length=st.session_state.get(f"len_{day_iso}", "normaal"),
                    script_tone=st.session_state.get(f"tone_{day_iso}", "luchtig"),
                )
                st.text_area("Complete voicetrack", value=script, height=320, key=f"script_{day_iso}")
                st.download_button("⬇️ Download voicetrack als TXT", data=script.encode("utf-8"), file_name=f"voicetrack_{day_iso}.txt", mime="text/plain", key=f"dl_{day_iso}")

    csv_df = birthday_dataframe(filtered)
    if not csv_df.empty:
        st.download_button("⬇️ Download verjaardagen als CSV", data=csv_df.to_csv(index=False).encode("utf-8-sig"), file_name="jarigvandaag_selectie.csv", mime="text/csv")


def news_tab():
    st.markdown('<div class="rm-subheader">📰 Opmerkelijk nieuws van NU.nl</div>', unsafe_allow_html=True)
    st.markdown('<div class="rm-section-intro">Laad de Opmerkelijk RSS-feed en filter op radio-vriendelijke items voor je voicetracks.</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([3, 1, 1])
    with c1:
        rss_url = st.text_input("RSS-url", value=NU_RSS_URL)
    with c2:
        only_safe = st.checkbox("Alleen radio-proof", value=True)
    with c3:
        only_preferred = st.checkbox("Alleen bruikbaar", value=False)
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
    st.dataframe(news_dataframe(filtered), use_container_width=True, hide_index=True)
    st.markdown("### Aanklikbare items")
    for idx, item in enumerate(filtered, start=1):
        with st.expander(f"{idx}. {item.title} — {item.short_date()}"):
            render_news_card(item)
    st.download_button("⬇️ Download nieuwsitems als CSV", data=news_dataframe(filtered).to_csv(index=False).encode("utf-8-sig"), file_name="nu_opmerkelijk_selectie.csv", mime="text/csv")


def app():
    inject_custom_css()
    st.image("radio_muziekstad_logo.png", use_container_width=True)
    render_hero_header()
    tab1, tab2 = st.tabs(["🎂 Verjaardagen", "📰 Opmerkelijk nieuws"])
    with tab1:
        birthdays_tab()
    with tab2:
        news_tab()


if __name__ == "__main__":
    app()
