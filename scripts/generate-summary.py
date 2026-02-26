#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import ssl
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin
from urllib.request import Request, urlopen

JST = dt.timezone(dt.timedelta(hours=9))
WEEKDAYS_JA = "月火水木金土日"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0 Safari/537.36"


@dataclass
class LinkItem:
    label: str
    url: str


@dataclass
class EventItem:
    site: str
    title: str
    date_iso: str
    date_text: str
    venue: str
    open_time: str = "記載なし"
    start_time: str = "記載なし"
    end_time: str = "記載なし"
    end_estimated: bool = False
    url: str = ""
    flyer_image: str = ""
    flyer_alt: str = ""
    flyer_missing: str = ""
    links: List[LinkItem] = field(default_factory=list)


@dataclass
class SiteResult:
    key: str
    label: str
    date_obj: dt.date
    events: List[EventItem] = field(default_factory=list)
    note: str = ""


def fetch_text(url: str, timeout: int = 20) -> str:
    req = Request(url, headers={"User-Agent": UA})
    try:
        with urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")
    except Exception as e:
        msg = str(e)
        if "CERTIFICATE_VERIFY_FAILED" in msg:
            pass
        elif "timed out" in msg.lower():
            with urlopen(req, timeout=max(timeout * 2, 30)) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                return resp.read().decode(charset, errors="replace")
        else:
            raise
    with urlopen(req, timeout=timeout, context=ssl._create_unverified_context()) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def fetch_bytes(url: str, timeout: int = 20) -> bytes:
    req = Request(url, headers={"User-Agent": UA})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception as e:
        msg = str(e)
        if "CERTIFICATE_VERIFY_FAILED" in msg:
            pass
        elif "timed out" in msg.lower():
            with urlopen(req, timeout=max(timeout * 2, 30)) as resp:
                return resp.read()
        else:
            raise
    with urlopen(req, timeout=timeout, context=ssl._create_unverified_context()) as resp:
        return resp.read()


def decode_bytes(data: bytes, encodings: Iterable[str]) -> str:
    for enc in encodings:
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def collapse_ws(s: str) -> str:
    return re.sub(r"[\t\r\n ]+", " ", s).strip()


def strip_tags(s: str) -> str:
    if s is None:
        return ""
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p>\s*<p[^>]*>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    # normalize Japanese full-width spaces only lightly; keep line breaks first
    s = s.replace("\xa0", " ")
    lines = [collapse_ws(line) for line in s.split("\n")]
    return "\n".join([line for line in lines if line])


def first_line(text: str) -> str:
    return text.split("\n", 1)[0].strip() if text else ""


def jp_date_compact(date_obj: dt.date) -> str:
    return f"{date_obj.year}年{date_obj.month}月{date_obj.day}日"


def jp_date_display(date_obj: dt.date) -> str:
    return f"{date_obj.year}年{date_obj.month}月{date_obj.day}日（{WEEKDAYS_JA[date_obj.weekday()]}）"


def hhmm_or_empty(value: Optional[str]) -> str:
    return value or ""


def normalize_hhmm(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    m = re.search(r"(\d{1,2}):(\d{2})", value)
    if not m:
        return None
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def extract_time(text: str, label: str) -> Optional[str]:
    patterns = [
        rf"(\d{{1,2}}:\d{{2}})\s*{label}",
        rf"{label}[^\d]*(\d{{1,2}}:\d{{2}})",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return None


def extract_any_hhmm(text: str) -> Optional[str]:
    m = re.search(r"(\d{1,2}:\d{2})", text or "")
    return normalize_hhmm(m.group(1)) if m else None


def extract_times(text: str) -> Dict[str, Optional[str]]:
    t = strip_tags(text)
    return {
        "open": normalize_hhmm(extract_time(t, "開場")),
        "start": normalize_hhmm(extract_time(t, "開演")),
        "end": normalize_hhmm(extract_time(t, "終演")),
        "end_estimated": bool(re.search(r"終演.*予定|予定.*終演", t)),
    }


def parse_jp_date_from_text(text: str) -> Optional[dt.date]:
    if not text:
        return None
    m = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", text)
    if not m:
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def match_target_date_text(text: str, date_obj: dt.date) -> bool:
    return bool(
        re.search(
            rf"{date_obj.year}年\s*{date_obj.month}月\s*{date_obj.day}日",
            text or "",
        )
    )


def parse_dt_dd_by_id(page_html: str, dt_id: str) -> str:
    m = re.search(rf"<dt[^>]*id=[\"']{re.escape(dt_id)}[\"'][^>]*>.*?</dt>\s*<dd[^>]*>(.*?)</dd>", page_html, re.S | re.I)
    return m.group(1) if m else ""


def parse_dt_dd_by_label(page_html: str, label: str) -> str:
    m = re.search(rf"<dt[^>]*>\s*{re.escape(label)}\s*</dt>\s*<dd[^>]*>(.*?)</dd>", page_html, re.S | re.I)
    return m.group(1) if m else ""


def build_link(label: str, url: str) -> LinkItem:
    return LinkItem(label=collapse_ws(strip_tags(label)), url=url)


def ensure_abs(base: str, maybe_rel: str) -> str:
    return urljoin(base, maybe_rel)


def parse_kitara_detail(detail_url: str, fallback_title: str = "") -> EventItem:
    page = fetch_text(detail_url)
    title = strip_tags(re.search(r"<h2>(.*?)</h2>", page, re.S | re.I).group(1)) if re.search(r"<h2>(.*?)</h2>", page, re.S | re.I) else fallback_title

    d_time = parse_dt_dd_by_id(page, "d_time")
    d_flyer = parse_dt_dd_by_id(page, "d_flyer")

    venue_match = re.search(r"<b[^>]*class=[\"'][^\"']*place[^\"']*[\"'][^>]*>(.*?)</b>", d_time, re.S | re.I)
    venue = strip_tags(venue_match.group(1)) if venue_match else "記載なし"

    time_p_match = re.search(r"<p[^>]*>(.*?)</p>", d_time, re.S | re.I)
    time_text = strip_tags(time_p_match.group(1)) if time_p_match else strip_tags(d_time)
    date_text = first_line(time_text) or "記載なし"
    tt = extract_times(d_time)

    flyer_img = ""
    flyer_img_m = re.search(r"<img[^>]+src=[\"']([^\"']+)[\"']", d_flyer, re.S | re.I)
    if flyer_img_m:
        flyer_img = ensure_abs(detail_url, flyer_img_m.group(1))

    flyer_links: List[LinkItem] = []
    for lm in re.finditer(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", d_flyer, re.S | re.I):
        flyer_links.append(build_link(lm.group(2), ensure_abs(detail_url, lm.group(1))))

    return EventItem(
        site="Kitara",
        title=title,
        date_iso="",
        date_text=date_text,
        venue=venue,
        open_time=tt["open"] or "記載なし",
        start_time=tt["start"] or "記載なし",
        end_time=tt["end"] or "記載なし",
        end_estimated=bool(tt["end_estimated"] and tt["end"]),
        url=detail_url,
        flyer_image=flyer_img,
        flyer_alt=f"{title} フライヤー",
        flyer_missing="フライヤーなし（掲載なし）" if not flyer_img else "",
        links=flyer_links,
    )


def scrape_kitara(date_obj: dt.date, label: str) -> SiteResult:
    result = SiteResult(key="kitara", label=label, date_obj=date_obj)
    month = date_obj.strftime("%Y-%m")
    url = f"https://www.kitara-sapporo.or.jp/event/index.html?dsp=list&month={month}"
    page = fetch_text(url)

    if "該当する公演はありません" in page:
        result.note = "該当イベントなし"
        return result

    target_prefix = f"{date_obj.year}年{date_obj.month}月{date_obj.day}日"
    cards = re.findall(r"<article class=\"card\">(.*?)</article>", page, re.S | re.I)
    for card in cards:
        date_m = re.search(r"<span class=\"date\">(.*?)</span>", card, re.S | re.I)
        if not date_m:
            continue
        card_date = strip_tags(date_m.group(1))
        if not card_date.startswith(target_prefix):
            continue

        title_m = re.search(r"<h4 class=\"title\">(.*?)</h4>", card, re.S | re.I)
        href_m = re.search(r"href=\"([^\"]*event_detail\.php\?num=\d+)\"", card, re.I)
        thumb_m = re.search(r"<div class=\"thumb\">.*?<img[^>]+src=\"([^\"]+)\"", card, re.S | re.I)

        if not (title_m and href_m):
            continue

        detail_url = ensure_abs(url, href_m.group(1))
        event = parse_kitara_detail(detail_url, fallback_title=strip_tags(title_m.group(1)))
        event.date_iso = date_obj.isoformat()
        # Fallbacks from card if detail page lacks data
        if event.venue == "記載なし":
            place_m = re.search(r"<b class=\"place[^\"]*\">(.*?)</b>", card, re.S | re.I)
            event.venue = strip_tags(place_m.group(1)) if place_m else event.venue
        if not event.flyer_image and thumb_m:
            event.flyer_image = ensure_abs(url, thumb_m.group(1))
            event.flyer_alt = f"{event.title} 画像"
            event.flyer_missing = ""
        result.events.append(event)

    if not result.events:
        result.note = "該当イベントなし"
    return result


def parse_community_plaza_detail(detail_url: str, target_date: dt.date, label: str) -> EventItem:
    page = fetch_text(detail_url)
    title_m = re.search(r"<h3 class=\"title\">(.*?)</h3>", page, re.S | re.I)
    title = strip_tags(title_m.group(1)) if title_m else "公演名不明"

    datetime_dd = parse_dt_dd_by_label(page, "日時")
    venue_dd = parse_dt_dd_by_label(page, "会場")
    flyer_dl_dd = parse_dt_dd_by_label(page, "チラシダウンロード")

    dt_text = strip_tags(datetime_dd)
    date_text = first_line(dt_text) or jp_date_display(target_date)
    tt = extract_times(datetime_dd)
    venue = first_line(strip_tags(venue_dd)) or "記載なし"

    flyer_image = ""
    flyer_alt = ""
    image_candidates = []
    for m in re.finditer(r"<img[^>]+src=\"([^\"]+)\"[^>]*class=\"[^\"]*w top[^\"]*\"[^>]*>\s*<p>(.*?)</p>", page, re.S | re.I):
        image_candidates.append((ensure_abs(detail_url, m.group(1)), strip_tags(m.group(2))))
    if image_candidates:
        preferred = next((c for c in image_candidates if "チラシ表" in c[1]), image_candidates[0])
        flyer_image, caption = preferred
        flyer_alt = caption or f"{title} フライヤー"

    links: List[LinkItem] = []
    for m in re.finditer(r"<a[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>", flyer_dl_dd, re.S | re.I):
        links.append(build_link(m.group(2), ensure_abs(detail_url, m.group(1))))

    return EventItem(
        site=label,
        title=title,
        date_iso=target_date.isoformat(),
        date_text=date_text,
        venue=venue,
        open_time=tt["open"] or "記載なし",
        start_time=tt["start"] or "記載なし",
        end_time=tt["end"] or "記載なし",
        end_estimated=bool(tt["end_estimated"] and tt["end"]),
        url=detail_url,
        flyer_image=flyer_image,
        flyer_alt=flyer_alt or f"{title} フライヤー",
        flyer_missing="フライヤーなし（掲載なし）" if not flyer_image else "",
        links=links,
    )


def scrape_sapporo_community_plaza(date_obj: dt.date, label: str, kind: int = 2) -> SiteResult:
    result = SiteResult(key="sapporo_community_plaza", label=label, date_obj=date_obj)
    url = f"https://www.sapporo-community-plaza.jp/event.php?kind={kind}"
    page = fetch_text(url)

    target_str = jp_date_compact(date_obj)
    seen = set()
    for m in re.finditer(r"<p class=\"date\">(.*?)</p>.*?<h4 class=\"txt_b\"><a href=\"([^\"]+)\">(.*?)</a>", page, re.S | re.I):
        date_text = strip_tags(m.group(1))
        if target_str not in date_text:
            continue
        detail_url = ensure_abs(url, m.group(2))
        if detail_url in seen:
            continue
        seen.add(detail_url)
        try:
            event = parse_community_plaza_detail(detail_url, date_obj, label)
        except Exception as e:
            result.note = f"一部取得失敗: {e}"
            continue
        result.events.append(event)

    if not result.events and not result.note:
        result.note = "該当イベントなし"
    return result


def scrape_sapporo_shiminhall(date_obj: dt.date, label: str) -> SiteResult:
    result = SiteResult(key="sapporo_shiminhall", label=label, date_obj=date_obj)
    ymd = date_obj.strftime("%Y/%m/%d")
    url = f"https://www.sapporo-shiminhall.org/event/?ymd={ymd}"
    page = fetch_text(url)

    row_pat = re.compile(r"<tr id=\"(event[^\"]+)\">(.*?)</tr>", re.S | re.I)
    for row_id, row in row_pat.findall(page):
        day_m = re.search(r"<p class=\"day\">(\d+)</p>", row)
        if not day_m or int(day_m.group(1)) != date_obj.day:
            continue

        title_m = re.search(r"<td class=\"tbody01\">(.*?)</td>", row, re.S | re.I)
        if not title_m:
            continue
        title = strip_tags(title_m.group(1))

        open_m = re.search(r"data-label=\"開場\"[^>]*>\s*(.*?)</td>", row, re.S | re.I)
        start_m = re.search(r"data-label=\"開演\"[^>]*>\s*(.*?)</td>", row, re.S | re.I)
        open_t = extract_time(strip_tags(open_m.group(1)) if open_m else "", "")
        start_t = extract_time(strip_tags(start_m.group(1)) if start_m else "", "")
        if not open_t and open_m:
            m2 = re.search(r"(\d{1,2}:\d{2})", strip_tags(open_m.group(1)))
            open_t = m2.group(1) if m2 else None
        if not start_t and start_m:
            m2 = re.search(r"(\d{1,2}:\d{2})", strip_tags(start_m.group(1)))
            start_t = m2.group(1) if m2 else None

        flyer_link_m = re.search(r"<p class=\"flyer\"><a href=\"([^\"]+)\"[^>]*>(.*?)</a>", row, re.S | re.I)
        links: List[LinkItem] = []
        if flyer_link_m:
            links.append(build_link(flyer_link_m.group(2), ensure_abs(url, flyer_link_m.group(1))))

        event = EventItem(
            site=label,
            title=title,
            date_iso=date_obj.isoformat(),
            date_text=jp_date_display(date_obj),
            venue="カナモトホール（札幌市民ホール）",
            open_time=open_t or "記載なし",
            start_time=start_t or "記載なし",
            end_time="記載なし",
            end_estimated=False,
            url=f"{url}#{row_id}",
            flyer_image="",
            flyer_alt="",
            flyer_missing="フライヤーなし（掲載なし）",
            links=links,
        )
        result.events.append(event)

    if not result.events:
        result.note = "該当イベントなし"
    return result


def parse_musicfun_detail(detail_url: str, target_date: dt.date) -> Dict[str, str]:
    page = fetch_text(detail_url)
    out: Dict[str, str] = {"flyer_image": "", "open_time": "", "start_time": "", "end_time": ""}

    img_m = re.search(r'<div[^>]*class="main"[^>]*>.*?<img[^>]+src="([^"]+)"', page, re.S | re.I)
    if img_m:
        out["flyer_image"] = ensure_abs(detail_url, img_m.group(1))

    # Detail pages often list multiple dates in one page; pick the row containing the target date.
    y, m, d = target_date.year, target_date.month, target_date.day
    row_m = re.search(
        rf"{y}年\s*{m}月\s*{d}日[^<]*<br\s*/?>\s*([^<]*?)(?=<br\s*/?>|$)",
        page,
        re.I,
    )
    if row_m:
        line = strip_tags(row_m.group(1))
        out["open_time"] = normalize_hhmm(extract_time(line, "開場")) or ""
        out["start_time"] = normalize_hhmm(extract_time(line, "開演")) or ""

    if not out["start_time"]:
        plain = strip_tags(page)
        lines = [ln for ln in plain.split("\n") if ln]
        for idx, line in enumerate(lines):
            if match_target_date_text(line, target_date):
                window = " ".join(lines[idx : idx + 6])
                out["open_time"] = out["open_time"] or (normalize_hhmm(extract_time(window, "開場")) or "")
                out["start_time"] = out["start_time"] or (normalize_hhmm(extract_time(window, "開演")) or "")
                break
    return out


def scrape_musicfun(date_obj: dt.date, label: str) -> SiteResult:
    result = SiteResult(key="musicfun", label=label, date_obj=date_obj)
    url = "https://musicfun.co.jp/schedule"
    page = fetch_text(url)

    item_pat = re.compile(
        r"<li>\s*<a href=\"([^\"]+)\">\s*"
        r"<img[^>]+src=\"([^\"]+)\"[^>]*>\s*<div>\s*"
        r"<h5>(.*?)</h5>\s*"
        r"<p class=\"date\">(.*?)</p>\s*"
        r"<p class=\"lead\">(.*?)</p>",
        re.S | re.I,
    )
    detail_cache: Dict[str, Dict[str, str]] = {}
    for href, img, title_html, date_html, lead_html in item_pat.findall(page):
        card_date = parse_jp_date_from_text(strip_tags(date_html))
        if card_date != date_obj:
            continue
        detail_url = ensure_abs(url, href)
        if detail_url not in detail_cache:
            try:
                detail_cache[detail_url] = parse_musicfun_detail(detail_url, date_obj)
            except Exception:
                detail_cache[detail_url] = {"flyer_image": "", "open_time": "", "start_time": "", "end_time": ""}
        d = detail_cache[detail_url]
        flyer = d.get("flyer_image") or ensure_abs(url, img)
        result.events.append(
            EventItem(
                site=label,
                title=strip_tags(title_html) or "公演名不明",
                date_iso=date_obj.isoformat(),
                date_text=strip_tags(date_html) or jp_date_display(date_obj),
                venue=first_line(strip_tags(lead_html)) or "記載なし",
                open_time=d.get("open_time") or "記載なし",
                start_time=d.get("start_time") or "記載なし",
                end_time=d.get("end_time") or "記載なし",
                url=detail_url,
                flyer_image=flyer,
                flyer_alt=f"{strip_tags(title_html)} フライヤー",
                flyer_missing="フライヤーなし（掲載なし）" if not flyer else "",
            )
        )
    if not result.events:
        result.note = "該当イベントなし"
    return result


def parse_mountalive_detail(detail_url: str) -> Dict[str, str]:
    page = fetch_text(detail_url)
    out = {"open_time": "", "start_time": "", "date_text": "", "venue": "", "flyer_image": ""}

    date_m = re.search(r"<p id=\"op_st_date\">\s*(.*?)\s*</p>", page, re.S | re.I)
    if date_m:
        out["date_text"] = strip_tags(date_m.group(1))

    time_m = re.search(r"id='op_st_time'[^>]*>\s*OPEN\s*/\s*(\d{1,2}:\d{2}).*?START\s*/\s*(\d{1,2}:\d{2})", page, re.S | re.I)
    if time_m:
        out["open_time"] = normalize_hhmm(time_m.group(1)) or ""
        out["start_time"] = normalize_hhmm(time_m.group(2)) or ""

    hall_m = re.search(r"<p id='hall_name'[^>]*>(.*?)</p>", page, re.S | re.I)
    if hall_m:
        out["venue"] = strip_tags(hall_m.group(1))

    img_m = re.search(r"<div class=\"swiper-slide\"><img src=\"([^\"]+)\"", page, re.I)
    if img_m:
        out["flyer_image"] = ensure_abs(detail_url, img_m.group(1))
    return out


def scrape_mountalive(date_obj: dt.date, label: str) -> SiteResult:
    result = SiteResult(key="mountalive", label=label, date_obj=date_obj)
    xml_bytes = fetch_bytes("http://www.mountalive.com/schedule/schedule.xml")
    xml_text = decode_bytes(xml_bytes, ["euc_jp", "cp932", "utf-8"])
    detail_cache: Dict[str, Dict[str, str]] = {}

    for item_m in re.finditer(r"<item>(.*?)</item>", xml_text, re.S | re.I):
        item = item_m.group(1)
        title_raw = strip_tags(re.search(r"<title>(.*?)</title>", item, re.S | re.I).group(1)) if re.search(r"<title>(.*?)</title>", item, re.S | re.I) else ""
        link_m = re.search(r"<link>(.*?)</link>", item, re.S | re.I)
        desc_m = re.search(r"<description>(.*?)</description>", item, re.S | re.I)
        if not (link_m and desc_m):
            continue
        desc_html = html.unescape(desc_m.group(1))
        d_m = re.search(r"公演日：(\d{4})年(\d{1,2})月(\d{1,2})日", desc_html)
        if not d_m:
            continue
        item_date = dt.date(int(d_m.group(1)), int(d_m.group(2)), int(d_m.group(3)))
        if item_date != date_obj:
            continue
        detail_url = link_m.group(1).strip()
        if detail_url not in detail_cache:
            try:
                detail_cache[detail_url] = parse_mountalive_detail(ensure_abs("http://www.mountalive.com/schedule/", detail_url))
            except Exception:
                detail_cache[detail_url] = {"open_time": "", "start_time": "", "date_text": "", "venue": "", "flyer_image": ""}
        dd = detail_cache[detail_url]
        desc_text = strip_tags(desc_html)
        desc_lines = [ln for ln in desc_text.split("\n") if ln]
        desc_title = ""
        for ln in desc_lines:
            if not ln.startswith("公演日：") and not ln.startswith("会場：") and not ln.startswith("出演："):
                desc_title = ln
                break
        venue_m = re.search(r"会場：(.+)", desc_text)
        venue = dd.get("venue") or (venue_m.group(1).strip() if venue_m else "記載なし")
        flyer_m = re.search(r"<img src='([^']+)'", desc_html, re.I)
        flyer = dd.get("flyer_image") or (ensure_abs(detail_url, flyer_m.group(1)) if flyer_m else "")
        result.events.append(
            EventItem(
                site=label,
                title=desc_title or title_raw or "公演名不明",
                date_iso=date_obj.isoformat(),
                date_text=dd.get("date_text") or jp_date_display(date_obj),
                venue=venue,
                open_time=dd.get("open_time") or "記載なし",
                start_time=dd.get("start_time") or "記載なし",
                end_time="記載なし",
                url=ensure_abs("http://www.mountalive.com/schedule/", detail_url),
                flyer_image=flyer,
                flyer_alt=f"{(desc_title or title_raw or '公演')} フライヤー",
                flyer_missing="フライヤーなし（掲載なし）" if not flyer else "",
            )
        )

    if not result.events:
        result.note = "該当イベントなし"
    return result


def scrape_wess(date_obj: dt.date, label: str) -> SiteResult:
    result = SiteResult(key="wess", label=label, date_obj=date_obj)
    url = "https://wess.jp/wp-json/posts?filter[posts_per_page]=500"
    raw = fetch_text(url)
    posts = json.loads(raw)
    target = date_obj.strftime("%Y%m%d")
    for post in posts:
        meta = post.get("meta") or {}
        if str(meta.get("kouenbi", "")) != target:
            continue
        artist = collapse_ws(str(meta.get("artist", "") or ""))
        concert = collapse_ws(str(meta.get("concerttitle", "") or ""))
        title = concert or artist or collapse_ws(str(post.get("title") or "公演名不明"))
        if artist and concert and concert != artist:
            title = f"{artist} / {concert}"
        flyer = str(meta.get("thumbnail_url", "") or "")
        result.events.append(
            EventItem(
                site=label,
                title=title,
                date_iso=date_obj.isoformat(),
                date_text=jp_date_display(date_obj),
                venue=collapse_ws(str(meta.get("kaijo", "") or "")) or "記載なし",
                open_time=normalize_hhmm(str(meta.get("kaijojikan", "") or "")) or "記載なし",
                start_time=normalize_hhmm(str(meta.get("kaienjikan", "") or "")) or "記載なし",
                end_time="記載なし",
                url=str(post.get("link") or "https://wess.jp/"),
                flyer_image=flyer,
                flyer_alt=f"{title} フライヤー",
                flyer_missing="フライヤーなし（掲載なし）" if not flyer else "",
            )
        )
    if not result.events:
        result.note = "該当イベントなし"
    return result


def scrape_kyobun(date_obj: dt.date, label: str) -> SiteResult:
    result = SiteResult(key="kyobun", label=label, date_obj=date_obj)
    ym = date_obj.strftime("%Y%m")
    url = f"https://www.kyobun.org/event_schedule.html?k=lst&ym={ym}&h=a"
    page = fetch_text(url)

    for dt_html, dd_html in re.findall(r"<dt class=\"date\">(.*?)</dt>\s*<dd class=\"event_link\">(.*?)</dd>", page, re.S | re.I):
        dt_text = strip_tags(dt_html)
        if not match_target_date_text(dt_text, date_obj):
            continue
        title_link_m = re.search(r"<p class=\"title\">.*?<a href=\"([^\"]+)\">(.*?)</a>", dd_html, re.S | re.I)
        title_plain_m = re.search(r"<p class=\"title\">(.*?)</p>", dd_html, re.S | re.I)
        time_m = re.search(r"<p class=\"time\">(.*?)</p>", dd_html, re.S | re.I)
        img_m = re.search(r"<div class=\"event_photo\">.*?<img[^>]+src=\"([^\"]+)\"", dd_html, re.S | re.I)
        hall_m = re.search(r"<p class=\"icon ([^\"]+)\">(.*?)</p>", dd_html, re.S | re.I)

        tt = extract_times(time_m.group(1) if time_m else "")
        title = strip_tags(title_link_m.group(2)) if title_link_m else strip_tags(title_plain_m.group(1) if title_plain_m else "")
        event_url = ensure_abs(url, title_link_m.group(1)) if title_link_m else url
        venue = strip_tags(hall_m.group(2)) if hall_m else "記載なし"
        flyer = ensure_abs(url, img_m.group(1)) if img_m else ""
        result.events.append(
            EventItem(
                site=label,
                title=title or "公演名不明",
                date_iso=date_obj.isoformat(),
                date_text=jp_date_display(date_obj),
                venue=venue,
                open_time=tt["open"] or "記載なし",
                start_time=tt["start"] or "記載なし",
                end_time=tt["end"] or "記載なし",
                end_estimated=bool(tt["end_estimated"] and tt["end"]),
                url=event_url,
                flyer_image=flyer,
                flyer_alt=f"{title} フライヤー",
                flyer_missing="フライヤーなし（掲載なし）" if not flyer else "",
            )
        )
    if not result.events:
        result.note = "該当イベントなし"
    return result


def scrape_sapporo_dome(date_obj: dt.date, label: str) -> SiteResult:
    result = SiteResult(key="sapporo_dome", label=label, date_obj=date_obj)
    url = "https://www.sapporo-dome.co.jp/eventlist/"
    page = fetch_text(url)
    target = date_obj.strftime("%Y%m%d")
    block_pat = re.compile(
        r"<li class=\"un_eventlist_item[^\"]*\"[^>]*data-event-day=\"(\d{8})\"[^>]*>(.*?)</li>\s*(?=<li class=\"un_eventlist_item|</ul>)",
        re.S | re.I,
    )
    for day, block in block_pat.findall(page):
        if day != target:
            continue
        title_main = strip_tags(re.search(r"un_eventlist_detailTtl__main\">(.*?)</span>", block, re.S | re.I).group(1)) if re.search(r"un_eventlist_detailTtl__main\">(.*?)</span>", block, re.S | re.I) else ""
        title_sub = strip_tags(re.search(r"un_eventlist_detailTtl__sub\">(.*?)</span>", block, re.S | re.I).group(1)) if re.search(r"un_eventlist_detailTtl__sub\">(.*?)</span>", block, re.S | re.I) else ""
        title = f"{title_sub} {title_main}".strip() if title_sub else (title_main or "公演名不明")
        url_m = re.search(r"<a[^>]*class=\"js_eventItemLink\"[^>]*href=\"([^\"]+)\"", block, re.I) or re.search(r"<a[^>]*href=\"([^\"]+)\"[^>]*class=\"js_eventItemLink\"", block, re.I)
        img_m = re.search(r"<div class=\"un_eventlist_img.*?<img[^>]+data-src=\"([^\"]+)\"", block, re.S | re.I)
        if not img_m:
            img_m = re.search(r"<div class=\"un_eventlist_img.*?<img[^>]+src=\"([^\"]+)\"", block, re.S | re.I)

        open_time = start_time = end_time = ""
        for tm in re.finditer(r"<dt class=\"un_eventlist_opentimeTtl\">(.*?)</dt>\s*<dd class=\"un_eventlist_opentimeTxt\">(.*?)</dd>", block, re.S | re.I):
            k = strip_tags(tm.group(1))
            v = extract_any_hhmm(strip_tags(tm.group(2))) or ""
            if "開場" in k:
                open_time = v
            elif "開始" in k or "開演" in k:
                start_time = v
            elif "終了" in k:
                end_time = v

        result.events.append(
            EventItem(
                site=label,
                title=title,
                date_iso=date_obj.isoformat(),
                date_text=jp_date_display(date_obj),
                venue="大和ハウス プレミストドーム（札幌ドーム）",
                open_time=open_time or "記載なし",
                start_time=start_time or "記載なし",
                end_time=end_time or "記載なし",
                url=ensure_abs(url, url_m.group(1)) if url_m else url,
                flyer_image=ensure_abs(url, img_m.group(1)) if img_m else "",
                flyer_alt=f"{title} フライヤー",
                flyer_missing="フライヤーなし（掲載なし）" if not img_m else "",
            )
        )
    if not result.events:
        result.note = "該当イベントなし"
    return result


def scrape_sora_scc(date_obj: dt.date, label: str) -> SiteResult:
    result = SiteResult(key="sora_scc", label=label, date_obj=date_obj)
    url = "https://www.sora-scc.jp/event/"
    page = fetch_text(url)
    for block in re.findall(r"<li><time>.*?</li>", page, re.S | re.I):
        time_m = re.search(r"<time>(.*?)</time>", block, re.S | re.I)
        if not time_m:
            continue
        date_text = strip_tags(time_m.group(1))
        if not match_target_date_text(date_text, date_obj):
            continue
        title_m = re.search(r"<dt>催事名</dt><dd>(.*?)</dd>", block, re.S | re.I)
        org_m = re.search(r"<dt>主催者名</dt><dd>(.*?)</dd>", block, re.S | re.I)
        title = strip_tags(title_m.group(1)) if title_m else "公演名不明"
        org = strip_tags(org_m.group(1)) if org_m else ""
        links: List[LinkItem] = []
        if org:
            links.append(LinkItem(label=f"主催者: {org}", url=url))
        result.events.append(
            EventItem(
                site=label,
                title=title,
                date_iso=date_obj.isoformat(),
                date_text=date_text or jp_date_display(date_obj),
                venue="札幌コンベンションセンター",
                open_time="記載なし",
                start_time="記載なし",
                end_time="記載なし",
                url=url,
                flyer_image="",
                flyer_alt="",
                flyer_missing="フライヤーなし（掲載なし）",
                links=links,
            )
        )
    if not result.events:
        result.note = "該当イベントなし"
    return result


def scrape_axes(date_obj: dt.date, label: str) -> SiteResult:
    result = SiteResult(key="axes", label=label, date_obj=date_obj)
    url = "https://www.axes.or.jp/event_calendar/index.php"
    try:
        data = json.loads(fetch_text("https://www.axes.or.jp/event_calendar/event.json"))
    except Exception as e:
        result.note = f"取得失敗（event.json）: {e}"
        return result

    y = int(data.get("year", 0) or 0)
    m = int(data.get("month", 0) or 0)
    events = data.get("event") or []
    if y == date_obj.year and m == date_obj.month and isinstance(events, list):
        for ev in events:
            try:
                if int(ev.get("day")) != date_obj.day:
                    continue
            except Exception:
                continue
            title = collapse_ws(str(ev.get("title", "") or "催事名不明"))
            result.events.append(
                EventItem(
                    site=label,
                    title=title,
                    date_iso=date_obj.isoformat(),
                    date_text=jp_date_display(date_obj),
                    venue="アクセスサッポロ",
                    open_time="記載なし",
                    start_time="記載なし",
                    end_time="記載なし",
                    url=url,
                    flyer_image="",
                    flyer_alt="",
                    flyer_missing="フライヤーなし（掲載なし）",
                )
            )
    if not result.events:
        result.note = "月別イベントデータを自動取得できません（JS描画/提供JSON未更新の可能性）"
    return result


def scrape_makomanai_icearena(date_obj: dt.date, label: str) -> SiteResult:
    result = SiteResult(key="makomanai_icearena", label=label, date_obj=date_obj)
    url = "http://www.makomanai.com/icearena/event"
    page = fetch_text(url)
    pdf_m = re.search(rf"(https?://[^\"]*gyouji{date_obj.month}\.pdf|/[^\"']*gyouji{date_obj.month}\.pdf)", page, re.I)
    pdf_url = ensure_abs(url, pdf_m.group(1)) if pdf_m else url
    result.events.append(
        EventItem(
            site=label,
            title=f"{date_obj.month}月イベント表（PDF要確認）",
            date_iso=date_obj.isoformat(),
            date_text=jp_date_display(date_obj),
            venue="真駒内セキスイハイムアイスアリーナ",
            open_time="記載なし",
            start_time="記載なし",
            end_time="記載なし",
            url=pdf_url,
            flyer_image="",
            flyer_alt="",
            flyer_missing="月間PDFのみ掲載（自動日次抽出未対応）",
            links=[LinkItem(label="月間イベント表PDF", url=pdf_url)] if pdf_m else [],
        )
    )
    result.note = "月間PDFのみ掲載のため、日次の自動抽出は未対応（PDF確認リンクを表示）"
    return result


def parse_zepp_anchor_blocks(page: str) -> List[str]:
    blocks: List[str] = []
    pos = 0
    start_pat = re.compile(r"<a class=\"sch-content[^\"]*\" href=\"https://www\.zepp\.co\.jp/hall/sapporo/schedule/single/\?rid=\d+\">", re.I)
    while True:
        m = start_pat.search(page, pos)
        if not m:
            break
        start = m.start()
        next_m = start_pat.search(page, m.end())
        end = next_m.start() if next_m else len(page)
        blocks.append(page[start:end])
        pos = end
    return blocks


def scrape_zepp_sapporo(date_obj: dt.date, label: str) -> SiteResult:
    result = SiteResult(key="zepp_sapporo", label=label, date_obj=date_obj)
    url = f"https://www.zepp.co.jp/hall/sapporo/schedule/?_y={date_obj.year}&_m={date_obj.month}"
    page = fetch_text(url)

    for block in parse_zepp_anchor_blocks(page):
        year_m = re.search(r"sch-content-date__year\">(\d{4})</p>", block)
        md_m = re.search(r"sch-content-date__month\">(\d{1,2})\.(\d{1,2})</p>", block)
        if not (year_m and md_m):
            continue
        try:
            item_date = dt.date(int(year_m.group(1)), int(md_m.group(1)), int(md_m.group(2)))
        except ValueError:
            continue
        if item_date != date_obj:
            continue

        href_m = re.search(r"<a class=\"sch-content[^\"]*\" href=\"([^\"]+)\"", block)
        img_m = re.search(r"<div class=\"sch-content-img\">.*?<img src=\"([^\"]+)\"", block, re.S | re.I)
        perf_m = re.search(r"sch-content-text__performer\">(.*?)</h2>", block, re.S | re.I)
        ttl_m = re.search(r"sch-content-text__ttl\">(.*?)</h3>", block, re.S | re.I)
        performer = strip_tags(perf_m.group(1)) if perf_m else ""
        ttl = strip_tags(ttl_m.group(1)) if ttl_m else ""
        base_title = ttl or performer or "公演名不明"
        if performer and ttl and performer != ttl:
            base_title = f"{performer} / {ttl}"

        time_rows = list(
            re.finditer(
                r"sch-content-text-date\">.*?sch-content-text-date__open\">(\d{1,2}:\d{2})</span>.*?sch-content-text-date__start\">(\d{1,2}:\d{2})</span>",
                block,
                re.S | re.I,
            )
        )
        if not time_rows:
            result.events.append(
                EventItem(
                    site=label,
                    title=base_title,
                    date_iso=date_obj.isoformat(),
                    date_text=jp_date_display(date_obj),
                    venue="Zepp Sapporo",
                    open_time="記載なし",
                    start_time="記載なし",
                    end_time="記載なし",
                    url=ensure_abs(url, href_m.group(1)) if href_m else url,
                    flyer_image=ensure_abs(url, img_m.group(1)) if img_m else "",
                    flyer_alt=f"{base_title} フライヤー",
                    flyer_missing="フライヤーなし（掲載なし）" if not img_m else "",
                )
            )
            continue
        for idx, tm in enumerate(time_rows, start=1):
            title = base_title if len(time_rows) == 1 else f"{base_title}（{idx}部）"
            result.events.append(
                EventItem(
                    site=label,
                    title=title,
                    date_iso=date_obj.isoformat(),
                    date_text=jp_date_display(date_obj),
                    venue="Zepp Sapporo",
                    open_time=normalize_hhmm(tm.group(1)) or "記載なし",
                    start_time=normalize_hhmm(tm.group(2)) or "記載なし",
                    end_time="記載なし",
                    url=ensure_abs(url, href_m.group(1)) if href_m else url,
                    flyer_image=ensure_abs(url, img_m.group(1)) if img_m else "",
                    flyer_alt=f"{base_title} フライヤー",
                    flyer_missing="フライヤーなし（掲載なし）" if not img_m else "",
                )
            )
    if not result.events:
        result.note = "該当イベントなし"
    return result


def sort_events(events: List[EventItem]) -> List[EventItem]:
    def key(ev: EventItem):
        start = ev.start_time if re.fullmatch(r"\d{1,2}:\d{2}", ev.start_time or "") else "99:99"
        return (ev.date_iso, start, ev.title)
    return sorted(events, key=key)


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def render_flyer(event: EventItem) -> str:
    if event.flyer_image:
        return f'<div class="flyer"><img src="{esc(event.flyer_image)}" alt="{esc(event.flyer_alt or (event.title + " フライヤー"))}"></div>'
    return f'<div class="flyer none">{esc(event.flyer_missing or "フライヤーなし（掲載なし）")}</div>'


def render_gcal_button(event: EventItem) -> str:
    if not (re.fullmatch(r"\d{4}-\d{2}-\d{2}", event.date_iso or "") and re.fullmatch(r"\d{1,2}:\d{2}", event.start_time or "") and re.fullmatch(r"\d{1,2}:\d{2}", event.end_time or "")):
        return ""
    return (
        f'<a class="btn gcal gcal-btn" href="#" '
        f'data-title="{esc(event.title)}" '
        f'data-date="{esc(event.date_iso)}" '
        f'data-start="{esc(event.start_time)}" '
        f'data-end="{esc(event.end_time)}" '
        f'data-location="{esc(event.venue)}" '
        f'data-url="{esc(event.url)}">Googleカレンダーに追加</a>'
    )


def render_links(event: EventItem) -> str:
    items: List[str] = []
    gcal = render_gcal_button(event)
    if gcal:
        items.append(gcal)
    for link in event.links:
        items.append(f'<a class="btn" href="{esc(link.url)}" target="_blank" rel="noopener">{esc(link.label)}</a>')
    if not items:
        return ""
    return '<div class="links">' + "".join(items) + "</div>"


def render_event_card(event: EventItem) -> str:
    end_display = event.end_time
    if event.end_time != "記載なし" and event.end_estimated:
        end_display = f"{event.end_time}（予定）"
    body = [
        '<article class="card">',
        render_flyer(event),
        '<div class="body">',
        f'<h3 class="title">{esc(event.title)}</h3>',
        '<div class="chips">',
        f'<span class="chip">{esc(event.site)}</span>',
        f'<span class="chip">{esc(event.date_iso.replace("-", "/"))}</span>',
        '</div>',
        '<dl>',
        f'<dt>日時</dt><dd>{esc(event.date_text)}</dd>',
        f'<dt>会場</dt><dd>{esc(event.venue or "記載なし")}</dd>',
        f'<dt>開場</dt><dd>{esc(event.open_time or "記載なし")}</dd>',
        f'<dt>開演</dt><dd>{esc(event.start_time or "記載なし")}</dd>',
        f'<dt>終演</dt><dd>{esc(end_display or "記載なし")}</dd>',
        f'<dt>URL</dt><dd><a href="{esc(event.url)}" target="_blank" rel="noopener">詳細ページ</a></dd>',
        '</dl>',
    ]
    links_html = render_links(event)
    if links_html:
        body.append(links_html)
    body.extend(['</div>', '</article>'])
    return "".join(body)


def render_empty_card(label: str, note: str, date_obj: dt.date) -> str:
    return (
        '<article class="card">'
        '<div class="flyer none">該当イベントなし</div>'
        '<div class="body">'
        f'<h3 class="title">{esc(label)}（{esc(jp_date_display(date_obj))}）</h3>'
        '<div class="chips">'
        f'<span class="chip">{esc(label)}</span>'
        f'<span class="chip">{esc(date_obj.isoformat().replace("-", "/"))}</span>'
        '</div>'
        '<dl>'
        '<dt>状態</dt><dd>該当イベントなし</dd>'
        f'<dt>補足</dt><dd>{esc(note or "対象日の掲載イベントは見つかりませんでした")}</dd>'
        '</dl>'
        '</div>'
        '</article>'
    )


def render_site_block(site: SiteResult) -> str:
    title = f"{site.label}（{jp_date_display(site.date_obj)}）"
    cards_html = "".join(render_event_card(ev) for ev in sort_events(site.events)) if site.events else render_empty_card(site.label, site.note, site.date_obj)
    return (
        '<!-- SITE BLOCK START -->'
        f'<section class="site-block">'
        f'<h2>{esc(title)}</h2>'
        '<div class="grid">'
        f'{cards_html}'
        '</div>'
        '</section>'
        '<!-- SITE BLOCK END -->'
    )


def render_global_block(date_obj: dt.date, site_results: List[SiteResult]) -> str:
    events = []
    for site in site_results:
        events.extend(site.events)
    title = f"当日イベント一覧（開演順）{jp_date_display(date_obj)}"
    cards_html = "".join(render_event_card(ev) for ev in sort_events(events)) if events else render_empty_card("全サイト横断", "該当イベントなし", date_obj)
    return (
        '<!-- SITE BLOCK START -->'
        '<section class="site-block">'
        f"<h2>{esc(title)}</h2>"
        '<div class="grid">'
        f"{cards_html}"
        "</div>"
        "</section>"
        '<!-- SITE BLOCK END -->'
    )


def site_order_key(site: SiteResult) -> Tuple[str, str, str]:
    if not site.events:
        return ("99:99", "99:99", site.label)
    sorted_site_events = sort_events(site.events)
    first = sorted_site_events[0]
    start = first.start_time if re.fullmatch(r"\d{1,2}:\d{2}", first.start_time or "") else "99:99"
    return (first.date_iso or "9999-99-99", start, site.label)


def render_from_template(template_path: Path, out_path: Path, date_obj: dt.date, site_results: List[SiteResult]) -> None:
    template = template_path.read_text(encoding="utf-8")
    template = re.sub(r"作成日\s*:\s*YYYY-MM-DD", f"作成日 : {date_obj.isoformat()}", template, count=1)
    ordered_sites = sorted(site_results, key=site_order_key)
    # Event cards are shown only in the global opening-time list.
    # Placeholder "no event" cards are hidden to keep the page compact.
    blocks = render_global_block(date_obj, ordered_sites)
    template = re.sub(r"<!-- SITE BLOCK START -->.*?<!-- SITE BLOCK END -->", blocks, template, count=1, flags=re.S)
    out_path.write_text(template, encoding="utf-8")


def load_config(config_path: Path) -> List[dict]:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return [s for s in data.get("sources", []) if s.get("enabled", True)]


def run_scraper(source_conf: dict, date_obj: dt.date) -> SiteResult:
    stype = source_conf.get("type")
    label = source_conf.get("label") or stype or "source"
    if stype == "kitara":
        return scrape_kitara(date_obj, label)
    if stype == "sapporo_community_plaza":
        return scrape_sapporo_community_plaza(date_obj, label, int(source_conf.get("kind", 2)))
    if stype == "sapporo_shiminhall":
        return scrape_sapporo_shiminhall(date_obj, label)
    if stype == "musicfun":
        return scrape_musicfun(date_obj, label)
    if stype == "mountalive":
        return scrape_mountalive(date_obj, label)
    if stype == "wess":
        return scrape_wess(date_obj, label)
    if stype == "kyobun":
        return scrape_kyobun(date_obj, label)
    if stype == "sapporo_dome":
        return scrape_sapporo_dome(date_obj, label)
    if stype == "sora_scc":
        return scrape_sora_scc(date_obj, label)
    if stype == "axes":
        return scrape_axes(date_obj, label)
    if stype == "makomanai_icearena":
        return scrape_makomanai_icearena(date_obj, label)
    if stype == "zepp_sapporo":
        return scrape_zepp_sapporo(date_obj, label)
    return SiteResult(key=str(stype), label=label, date_obj=date_obj, note="未対応ソース")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate event-summary.html by scraping configured sources.")
    p.add_argument("--date", help="Target date in YYYY-MM-DD (default: today JST)")
    p.add_argument("--config", default="config/auto_sources.json")
    p.add_argument("--template", default="event-summary.template.html")
    p.add_argument("--output", default="event-summary.html")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parent.parent

    if args.date:
        try:
            date_obj = dt.date.fromisoformat(args.date)
        except ValueError:
            print("--date は YYYY-MM-DD 形式で指定してください", file=sys.stderr)
            return 2
    else:
        date_obj = dt.datetime.now(JST).date()

    config_path = (root / args.config).resolve()
    template_path = (root / args.template).resolve()
    output_path = (root / args.output).resolve()

    if not config_path.exists():
        print(f"config not found: {config_path}", file=sys.stderr)
        return 2
    if not template_path.exists():
        print(f"template not found: {template_path}", file=sys.stderr)
        return 2

    sources = load_config(config_path)
    results: List[SiteResult] = []
    for src in sources:
        label = src.get("label", src.get("type", "source"))
        try:
            print(f"[INFO] scraping {label} for {date_obj.isoformat()} ...")
            results.append(run_scraper(src, date_obj))
        except Exception as e:
            print(f"[WARN] {label}: scrape failed: {e}")
            results.append(SiteResult(key=str(src.get('type')), label=label, date_obj=date_obj, note=f"取得失敗: {e}"))

    render_from_template(template_path, output_path, date_obj, results)
    total_events = sum(len(r.events) for r in results)
    print(f"[INFO] generated {output_path} (sites={len(results)}, events={total_events})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
