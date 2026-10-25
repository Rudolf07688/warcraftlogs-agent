"""Stage 1: the per-run generation briefing and its live sources (version, hotfixes).

A guide run starts from facts about "now", never from the model's memory (FR-002):
the UTC time, the exact live build (Blizzard's version endpoint, research R1), the newest
hotfix article (research R2), the raid tier and Mythic+ season (Warcraft Logs zones), and
the class's live specs. Both Blizzard sources are best-effort; only an unknown live patch
stops a run (FR-006), and a Mythic+ run also needs the season.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime, time, timedelta
from html.parser import HTMLParser

import httpx

from wcl_agent.cache.cache import CacheFamily, get_or_load, keys
from wcl_agent.cache.cache_models import HotfixEntry, HotfixFeed, LiveVersion
from wcl_agent.game.constants import normalize_class_name, role_for_spec
from wcl_agent.game.patch import current_mplus_season, current_patch, current_raid_tier
from wcl_agent.game.roster import roster_snapshot
from wcl_agent.client.wcl_client import background_lane

from ...config import settings
from .models import ContentType, GenerationBriefing
from .research import ENV_MARKERS

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT_S = 10.0
_HEADERS = {"User-Agent": "wcl-agent guide briefing (+https://www.warcraftlogs.com)"}
_REGION = "us"


class PatchUnknown(Exception):
    """Neither Blizzard nor Warcraft Logs says which patch is live: postpone (FR-006)."""


class SeasonUnknown(Exception):
    """A Mythic+ guide needs the current season, and none is known."""


# --- live build (research R1) -----------------------------------------------------------


def parse_versions(text: str, region: str = _REGION) -> LiveVersion | None:
    """Parse Blizzard's pipe-separated ``versions`` file for one region's row.

    The header row names the columns (``Region!STRING:0|...|BuildId!DEC:4|VersionsName!String:0``),
    a ``## seqn = N`` line carries the sequence number, then one row per region.
    """
    header: list[str] | None = None
    seqn: int | None = None
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("##"):
            match = re.search(r"seqn\s*=\s*(\d+)", line)
            if match:
                seqn = int(match.group(1))
            continue
        cells = line.split("|")
        if header is None:
            header = [c.split("!", 1)[0].strip().lower() for c in cells]
            continue
        row = dict(zip(header, cells))
        if row.get("region", "").strip().lower() != region:
            continue
        version = (row.get("versionsname") or "").strip()
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:\.\d+)?", version):
            return None
        build = (row.get("buildid") or "").strip()
        return LiveVersion(
            region=region,
            version=version,
            build_id=int(build) if build.isdigit() else None,
            seqn=seqn,
            fetched_at=datetime.now(UTC),
        )
    return None


async def fetch_live_version() -> LiveVersion | None:
    """The live retail build (product ``wow`` only, so a PTR build can never leak in)."""

    async def load() -> LiveVersion | None:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_S, headers=_HEADERS) as client:
            response = await client.get(settings.wow_version_url)
            response.raise_for_status()
        return parse_versions(response.text)

    try:
        return await get_or_load(
            CacheFamily.LIVE_VERSION, keys.live_version(_REGION), LiveVersion, load
        )
    except Exception as exc:  # noqa: BLE001 - best-effort; WCL's major.minor is the floor
        logger.warning("live version lookup failed: %s", exc)
        return None


# --- hotfixes (research R2) -------------------------------------------------------------

_LISTING_RE = re.compile(r'"title":"(Hotfixes:[^"]*)","id":\d+,"slug":"[^"]+","url":"(/news/\d+/[^"]+)"')
_LISTING_HREF_RE = re.compile(r'href="((?:/en-us)?/news/\d+/hotfixes-[^"]+)"')
_JSON_LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
_DATE_RE = re.compile(
    r"^(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},\s+\d{4}$"
)
_ALL_CLASSES = {"all classes", "general", "classes"}
_MAX_HEADING = 60  # a date/section heading is a short bold line


def newest_hotfix_url(listing_html: str, news_url: str) -> str | None:
    """The newest "Hotfixes:" article on the news listing page (absolute URL)."""
    match = _LISTING_RE.search(listing_html or "")
    path = match.group(2) if match else None
    if path is None:
        href = _LISTING_HREF_RE.search(listing_html or "")
        path = href.group(1) if href else None
    if path is None:
        return None
    path = path.removeprefix("/en-us")
    return news_url.rstrip("/").removesuffix("/news") + path


def _spec_value(class_name: str, spec_text: str) -> str | None:
    key = spec_text.replace(" ", "").replace("'", "").casefold()
    for spec in _class_specs(class_name):
        if spec.casefold() == key:
            return spec
    return None


class _HotfixBodyParser(HTMLParser):
    """Walks the article body: date paragraphs → section paragraphs → the Classes list.

    Inside "Classes", a top-level ``<li><strong>Class</strong>`` opens a class; a nested
    ``<li><strong>Spec</strong>`` names a spec; a nested item without a spec heading means
    the whole class changed. Anything after a Classic-flavoured heading is ignored.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: dict[tuple[str | None, str], set[str] | None] = {}
        self.touches_all = False
        self._date: str | None = None
        self._section: str | None = None
        self._retail = True
        self._tags: list[str] = []
        self._li_depth = 0
        self._text = ""
        self._in_strong = False
        self._strong_text = ""
        self._strong_at_li_start = False
        self._li_has_text = False
        self._class: str | None = None
        self._class_depth = 0

    # Block-level bookkeeping -------------------------------------------------------------

    def handle_starttag(self, tag, attrs):
        self._tags.append(tag)
        if tag == "li":
            self._li_depth += 1
            self._li_has_text = False
            self._strong_at_li_start = True
        elif tag == "strong":
            self._in_strong = True
            self._strong_text = ""
        elif tag in ("p", "h2", "h3", "h4"):
            self._text = ""

    def handle_endtag(self, tag):
        if self._tags and self._tags[-1] == tag:
            self._tags.pop()
        if tag == "strong":
            self._in_strong = False
            self._on_strong(self._strong_text.strip())
        elif tag == "li":
            if self._class is not None and self._li_depth == self._class_depth:
                self._class = None
            self._li_depth -= 1
        elif tag in ("p", "h2", "h3", "h4") and self._li_depth == 0:
            self._on_heading(self._text.strip())

    def handle_data(self, data):
        if self._in_strong:
            self._strong_text += data
        self._text += data
        if self._li_depth and data.strip() and not self._in_strong:
            # A nested class item with plain text = a change for the whole class.
            if (
                self._retail
                and self._section == "classes"
                and self._class is not None
                and self._li_depth == self._class_depth + 1
                and not self._li_has_text
            ):
                self.entries[(self._date, self._class)] = None
            self._li_has_text = True

    # Semantics -----------------------------------------------------------------------------

    def _on_heading(self, text: str) -> None:
        if not text or len(text) > _MAX_HEADING:
            return  # prose (e.g. the intro naming every game flavour), not a heading
        if ENV_MARKERS["classic"].search(text):
            self._retail = False
            return
        if _DATE_RE.match(text):
            self._date = text
            self._section = None
            return
        if self._li_depth == 0:
            self._section = text.casefold()

    def _on_strong(self, text: str) -> None:
        if not (self._retail and self._section == "classes" and text and self._li_depth):
            return
        if self._li_has_text:
            return  # bold text mid-sentence, not a heading
        if self._class is None:
            if text.casefold() in _ALL_CLASSES:
                self.touches_all = True
                return
            cls = normalize_class_name(text)
            if cls is not None:
                self._class = cls
                self._class_depth = self._li_depth
                self.entries.setdefault((self._date, cls), set())
            return
        if self._li_depth == self._class_depth + 1:
            # An unknown spec heading keeps its own name: it is a spec, not the whole class.
            spec = _spec_value(self._class, text) or text.replace(" ", "")
            specs = self.entries.get((self._date, self._class))
            if specs is not None:
                specs.add(spec)
            self._li_has_text = True  # the spec heading is this item's start


def parse_hotfix_article(html: str, url: str | None = None) -> HotfixFeed:
    """Reduce one "Hotfixes:" article to its time and the classes/specs it touches."""
    latest_at = None
    for block in _JSON_LD_RE.findall(html or ""):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        stamp = data.get("dateModified") or data.get("datePublished")
        if stamp:
            latest_at = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            break
    start = (html or "").find('class="detail"')
    parser = _HotfixBodyParser()
    parser.feed(html[start:] if start >= 0 else html or "")
    entries = [
        HotfixEntry(date=d, class_name=cls, specs=sorted(specs) if specs else [])
        for (d, cls), specs in parser.entries.items()
    ]
    return HotfixFeed(
        article_url=url, latest_at=latest_at, entries=entries, touches_all_classes=parser.touches_all
    )


async def fetch_hotfix_feed() -> HotfixFeed | None:
    """The newest Blizzard hotfix article, parsed (cached 30 min). None when unavailable."""

    async def load() -> HotfixFeed | None:
        async with httpx.AsyncClient(
            timeout=_HTTP_TIMEOUT_S, headers=_HEADERS, follow_redirects=True
        ) as client:
            listing = await client.get(settings.wow_news_url)
            listing.raise_for_status()
            url = newest_hotfix_url(listing.text, settings.wow_news_url)
            if url is None:
                return None
            article = await client.get(url)
            article.raise_for_status()
        return parse_hotfix_article(article.text, url)

    try:
        return await get_or_load(CacheFamily.HOTFIX_FEED, keys.hotfix_feed(), HotfixFeed, load)
    except Exception as exc:  # noqa: BLE001 - best-effort: no hotfix signal
        logger.warning("hotfix feed lookup failed: %s", exc)
        return None


def _entry_time(entry: HotfixEntry, feed: HotfixFeed) -> datetime | None:
    """When an entry's changes were live: the end of its dated day, capped at the article
    time (a date heading has no time of day)."""
    if entry.date:
        try:
            day = datetime.strptime(entry.date, "%B %d, %Y").date()
        except ValueError:
            day = None
        if day is not None:
            end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=UTC)
            return min(end, feed.latest_at) if feed.latest_at else end
    return feed.latest_at


def hotfix_touch_time(feed: HotfixFeed | None, class_name: str, spec: str) -> datetime | None:
    """The newest time the feed changed this spec (its class without a spec heading
    counts, and so does a change for all classes); None when it did not touch it."""
    if feed is None:
        return None
    times: list[datetime] = []
    if feed.touches_all_classes and feed.latest_at:
        times.append(feed.latest_at)
    for entry in feed.entries:
        if entry.class_name != class_name:
            continue
        if entry.specs and spec not in entry.specs:
            continue
        stamp = _entry_time(entry, feed)
        if stamp is not None:
            times.append(stamp)
    return max(times) if times else None


# --- roster -----------------------------------------------------------------------------


def _class_specs(class_name: str) -> list[str]:
    return roster_snapshot().specs_for(class_name)


def _class_display(class_name: str) -> str:
    return roster_snapshot().class_display(class_name)


# --- the briefing -----------------------------------------------------------------------


async def build_briefing(
    class_name: str, spec: str, content_type: ContentType
) -> GenerationBriefing:
    """Everything the run needs to know about "now". Raises ``PatchUnknown`` /
    ``SeasonUnknown`` when generation must be postponed."""
    version = await fetch_live_version()
    with background_lane():
        wcl_patch = await current_patch()
        raid_tier = await current_raid_tier()
        season = await current_mplus_season()
    live_patch = version.patch if version is not None else wcl_patch
    if not live_patch:
        raise PatchUnknown("live patch unknown (Blizzard version source and Warcraft Logs both failed)")
    if content_type == "mplus" and not season:
        raise SeasonUnknown("current Mythic+ season unknown")
    feed = await fetch_hotfix_feed()
    touched_at = hotfix_touch_time(feed, class_name, spec)
    return GenerationBriefing(
        now_utc=datetime.now(UTC),
        content_type=content_type,
        class_name=class_name,
        class_display=_class_display(class_name),
        spec=spec,
        role=role_for_spec(spec) or "dps",
        class_specs=_class_specs(class_name),
        live_patch=live_patch,
        live_build=version.version if version is not None else None,
        latest_hotfix_at=feed.latest_at if feed is not None else None,
        hotfix_touches_spec=touched_at is not None,
        raid_tier=raid_tier,
        mplus_season=season,
    )
