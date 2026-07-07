# -*- coding: utf-8 -*-
"""공통 유틸: HTTP 세션, 숫자/시간 파싱, 데이터 모델."""
import sys, re, time, json, hashlib
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
ARCHIVE = DOCS / "archive"
THUMBS = DOCS / "thumbs"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

import requests

def session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    })
    # 유튜브 EU 동의 페이지 우회 (GitHub Actions 등 해외 IP 대비)
    s.cookies.set("CONSENT", "YES+cb.20240101-00-p0.en+FX+000", domain=".youtube.com")
    return s


def parse_views(text):
    """'조회수 1.2만회', '1.5M views', '123,456' → int (모르면 None)"""
    if not text:
        return None
    t = str(text).replace(",", "").replace("조회수", "").replace("views", "").replace("view", "").strip()
    m = re.search(r"([\d.]+)\s*([만억KMBkmb]?)", t)
    if not m:
        return None
    try:
        n = float(m.group(1))
    except ValueError:
        return None
    unit = m.group(2)
    mult = {"만": 1e4, "억": 1e8, "K": 1e3, "k": 1e3, "M": 1e6, "m": 1e6, "B": 1e9, "b": 1e9}.get(unit, 1)
    return int(n * mult)


def parse_ago_hours(text):
    """'3시간 전', '2 days ago' → 경과 시간(시간 단위 float, 모르면 None)"""
    if not text:
        return None
    t = str(text)
    m = re.search(r"([\d.]+)\s*(분|시간|일|주|개월|년|minute|hour|day|week|month|year)", t)
    if not m:
        return None
    n = float(m.group(1))
    u = m.group(2)
    per = {"분": 1 / 60, "minute": 1 / 60, "시간": 1, "hour": 1, "일": 24, "day": 24,
           "주": 168, "week": 168, "개월": 720, "month": 720, "년": 8760, "year": 8760}[u]
    return n * per


def parse_duration(text):
    """'12:34' 또는 '1:02:03' → 초"""
    if not text:
        return None
    parts = str(text).strip().split(":")
    if not all(p.strip().isdigit() for p in parts):
        return None
    sec = 0
    for p in parts:
        sec = sec * 60 + int(p)
    return sec


def fmt_views(n):
    if n is None:
        return ""
    if n >= 1e8:
        return f"{n/1e8:.1f}억"
    if n >= 1e4:
        v = n / 1e4
        return f"{v:.1f}만" if v < 100 else f"{v:.0f}만"
    return f"{n:,}"


def video(platform, vid, title, url, thumb, channel="", views=None, views_text="",
          ago_hours=None, ago_text="", duration=None, region="", extra=""):
    v = {
        "id": f"{platform}:{vid}",
        "platform": platform,
        "title": (title or "").strip()[:180],
        "url": url,
        "thumb": thumb or "",
        "channel": (channel or "").strip()[:60],
        "views": views,
        "views_text": views_text or (fmt_views(views) if views else ""),
        "ago_hours": round(ago_hours, 2) if ago_hours else None,
        "ago_text": ago_text or "",
        "duration": duration,
        "region": region,
        "extra": extra,
    }
    # 바이럴 속도 = 시간당 조회수
    if views and ago_hours and ago_hours > 0:
        v["velocity"] = int(views / ago_hours)
    else:
        v["velocity"] = None
    return v


def thumb_key(url):
    return hashlib.md5(url.encode()).hexdigest()[:16] + ".jpg"
