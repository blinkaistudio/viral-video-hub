# -*- coding: utf-8 -*-
"""API 키 없이 5개 플랫폼에서 바이럴 영상 수집.

- YouTube  : 검색 결과 페이지 스크래핑 (조회수순 + 최근 업로드 필터, ytInitialData)
- TikTok   : tikwm.com 공개 트렌딩 피드 (무인증)
- Instagram: DuckDuckGo 비디오 검색 (instagram.com/reel 필터)
- Vimeo    : Staff Picks 공식 RSS
- Reddit   : 서브레딧 top RSS (일간) — 크로스플랫폼 바이럴 클립 프록시
"""
import re, json, time, html
import xml.etree.ElementTree as ET
from common import session, video, parse_views, parse_ago_hours, parse_duration

# ---------------------------------------------------------------- YouTube
# sp 파라미터: CAM = 조회수순 정렬, EgQIAxAB = 이번 주 + 동영상, EgQIAhAB = 오늘 + 동영상
YT_SP_WEEK = "CAMSBAgDEAE%3D"
YT_SP_DAY = "CAMSBAgCEAE%3D"

YT_QUERIES_KR = ["쇼츠", "챌린지", "예능", "먹방", "브이로그", "하이라이트", "광고", "AI",
                 "아이돌", "드라마", "개그", "리뷰"]
YT_QUERIES_GLOBAL = ["shorts", "challenge", "viral", "trailer", "AI", "satisfying"]

# run_all.py가 fetch_kr_trends() 결과를 여기 주입 → 트렌드 키워드 기반 수집에 사용
KR_TRENDS = []


def fetch_kr_trends():
    """한국 실시간 트렌드 키워드 (구글 트렌드 KR RSS + signal.bz 실검). 영상이 아닌 키워드 소스."""
    s = session()
    out, seen = [], set()
    try:
        r = s.get("https://trends.google.com/trending/rss?geo=KR", timeout=15)
        root = ET.fromstring(r.content)
        for item in root.iter("item"):
            kw = (item.findtext("title") or "").strip()
            traffic = (item.findtext("{https://trends.google.com/trending/rss}approx_traffic") or "").strip()
            if kw and kw.lower() not in seen:
                seen.add(kw.lower())
                out.append({"keyword": kw, "traffic": traffic, "source": "구글 트렌드"})
    except Exception as e:
        print(f"  구글트렌드 실패: {e}")
    try:
        r = s.get("https://api.signal.bz/news/realtime", timeout=10)
        for row in r.json().get("top10", []):
            kw = (row.get("keyword") or "").strip()
            if kw and kw.lower() not in seen:
                seen.add(kw.lower())
                out.append({"keyword": kw, "traffic": "", "source": "실시간 검색어"})
    except Exception as e:
        print(f"  signal.bz 실패: {e}")
    return out[:20]


def _yt_search(s, query, sp, gl, hl, region_label):
    from urllib.parse import quote_plus
    url = (f"https://www.youtube.com/results?search_query={quote_plus(query)}"
           f"&sp={sp}&gl={gl}&hl={hl}")
    r = s.get(url, timeout=20)
    r.raise_for_status()
    m = re.search(r"ytInitialData\s*=\s*({.+?});</script>", r.text)
    if not m:
        return []
    out = []

    def walk(o):
        if isinstance(o, dict):
            if "videoRenderer" in o:
                vr = o["videoRenderer"]
                try:
                    vid = vr["videoId"]
                    title = "".join(t.get("text", "") for t in vr.get("title", {}).get("runs", []))
                    ch = "".join(t.get("text", "") for t in vr.get("ownerText", {}).get("runs", []))
                    vt = vr.get("viewCountText", {})
                    views_text = vt.get("simpleText") or "".join(t.get("text", "") for t in vt.get("runs", []))
                    ago = vr.get("publishedTimeText", {}).get("simpleText", "")
                    dur = vr.get("lengthText", {}).get("simpleText", "")
                    thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
                    out.append(video(
                        "youtube", vid, title,
                        f"https://www.youtube.com/watch?v={vid}",
                        thumb, ch,
                        views=parse_views(views_text), views_text=views_text,
                        ago_hours=parse_ago_hours(ago), ago_text=ago,
                        duration=parse_duration(dur), region=region_label,
                    ))
                except Exception:
                    pass
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(json.loads(m.group(1)))
    return out


def fetch_youtube():
    s = session()
    seen, items = set(), []
    # 실시간 트렌드 키워드는 '오늘 업로드' 필터로 — 지금 한국에서 터지는 영상 포착
    trend_jobs = [(t["keyword"], "KR", "ko", "KR", YT_SP_DAY) for t in KR_TRENDS[:6]]
    jobs = (trend_jobs +
            [(q, "KR", "ko", "KR", YT_SP_WEEK) for q in YT_QUERIES_KR] +
            [(q, "US", "en", "Global", YT_SP_WEEK) for q in YT_QUERIES_GLOBAL])
    for q, gl, hl, label, sp in jobs:
        try:
            for it in _yt_search(s, q, sp, gl, hl, label):
                if it["id"] not in seen and it["views"]:
                    seen.add(it["id"])
                    items.append(it)
        except Exception as e:
            print(f"  yt query '{q}' 실패: {e}")
        time.sleep(0.5)
    # 시간당 조회수(바이럴 속도) 우선 정렬 — 국내/글로벌 각각 상위 보장
    items.sort(key=lambda x: (x["velocity"] or 0, x["views"] or 0), reverse=True)
    kr = [v for v in items if v["region"] == "KR"][:45]
    gl_ = [v for v in items if v["region"] != "KR"][:40]
    return kr + gl_


# ---------------------------------------------------------------- TikTok (tikwm)
def _tikwm_items(d):
    data = d.get("data")
    if isinstance(data, dict):
        return data.get("videos") or []
    return data or []


def fetch_tiktok():
    s = session()
    seen, items = set(), []
    # 한국 키워드 검색 (트렌드 상위 + 고정 키워드) + 지역 트렌딩 피드
    kr_keywords = [t["keyword"] for t in KR_TRENDS[:3]] + ["챌린지", "한국"]
    jobs = ([("search", kw) for kw in kr_keywords] +
            [("feed", r) for r in ["KR", "US", "JP"]])
    for kind, arg in jobs:
        try:
            if kind == "search":
                r = s.post("https://www.tikwm.com/api/feed/search",
                           data={"keywords": arg, "count": 12, "region": "KR"}, timeout=25)
            else:
                r = s.get(f"https://www.tikwm.com/api/feed/list?region={arg}&count=20", timeout=25)
            d = r.json()
            for it in _tikwm_items(d):
                vid = str(it.get("video_id") or it.get("id") or "")
                author = it.get("author") or {}
                uid = author.get("unique_id", "")
                if not vid or not uid or vid in seen:
                    continue
                seen.add(vid)
                created = it.get("create_time")
                ago_h = None
                if created:
                    ago_h = max((time.time() - created) / 3600, 0.5)
                items.append(video(
                    "tiktok", vid, it.get("title") or "(제목 없음)",
                    f"https://www.tiktok.com/@{uid}/video/{vid}",
                    it.get("cover") or "",
                    author.get("nickname") or uid,
                    views=it.get("play_count"),
                    ago_hours=ago_h,
                    ago_text=_ago_kr(ago_h),
                    duration=it.get("duration"),
                    region="KR" if it.get("region") == "KR" else "Global",
                    extra=f"❤️ {_num(it.get('digg_count'))}",
                ))
        except Exception as e:
            print(f"  tiktok {kind}:{arg} 실패: {e}")
        time.sleep(1.5)
    items.sort(key=lambda x: (x["velocity"] or 0, x["views"] or 0), reverse=True)
    kr = [v for v in items if v["region"] == "KR"][:30]
    gl_ = [v for v in items if v["region"] != "KR"][:30]
    return kr + gl_


def _num(n):
    from common import fmt_views
    return fmt_views(n) if n else "0"


def _ago_kr(h):
    if not h:
        return ""
    if h < 24:
        return f"{int(h)}시간 전"
    if h < 24 * 30:
        return f"{int(h/24)}일 전"
    return f"{int(h/720)}개월 전"


# ---------------------------------------------------------------- Instagram (DuckDuckGo videos)
def _ddg_videos(s, query, df="w"):
    r = s.get("https://duckduckgo.com/", params={"q": query, "iax": "videos", "ia": "videos"}, timeout=20)
    m = re.search(r'vqd=["\']?([\d-]+)', r.text)
    if not m:
        return []
    r2 = s.get("https://duckduckgo.com/v.js",
               params={"l": "wt-wt", "o": "json", "q": query, "vqd": m.group(1), "f": f",,,,,videoDuration:short", "df": df, "p": "1"},
               timeout=20)
    return r2.json().get("results", [])


def fetch_instagram():
    s = session()
    seen, items = set(), []
    queries = ["instagram reels viral site:instagram.com", "인스타 릴스 인기 site:instagram.com", "instagram.com/reel"]
    queries += [f"{t['keyword']} site:instagram.com" for t in KR_TRENDS[:2]]
    for q in queries:
        try:
            for x in _ddg_videos(s, q):
                content = x.get("content") or ""
                if "instagram.com" not in content or content in seen:
                    continue
                seen.add(content)
                stats = x.get("statistics") or {}
                views = stats.get("viewCount")
                pub = x.get("published") or ""
                ago_h = None
                if pub:
                    try:
                        import datetime
                        dt = datetime.datetime.fromisoformat(pub.replace("Z", "+00:00"))
                        ago_h = max((datetime.datetime.now(datetime.timezone.utc) - dt).total_seconds() / 3600, 0.5)
                    except Exception:
                        pass
                images = x.get("images") or {}
                items.append(video(
                    "instagram", content.rstrip("/").split("/")[-1] or content,
                    html.unescape(x.get("title") or ""),
                    content,
                    images.get("medium") or images.get("small") or "",
                    x.get("uploader") or x.get("publisher") or "",
                    views=views,
                    ago_hours=ago_h, ago_text=_ago_kr(ago_h),
                    duration=parse_duration(x.get("duration")),
                    region="Global",
                ))
        except Exception as e:
            print(f"  instagram ddg '{q[:20]}' 실패: {e}")
        time.sleep(1)
    items.sort(key=lambda x: (x["views"] or 0), reverse=True)
    return items[:30]


# ---------------------------------------------------------------- Vimeo (RSS)
def fetch_vimeo():
    s = session()
    items = []
    for name, url in [("Staff Picks", "https://vimeo.com/channels/staffpicks/videos/rss")]:
        try:
            r = s.get(url, timeout=20)
            root = ET.fromstring(r.content)
            for item in root.iter("item"):
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                mc = item.find(f"{MRSS}content")
                thumb, creator, dur = "", "", None
                if mc is not None:
                    te = mc.find(f"{MRSS}thumbnail")
                    thumb = te.get("url") if te is not None else ""
                    ce = mc.find(f"{MRSS}credit")
                    creator = ce.text if ce is not None else ""
                    dur = int(mc.get("duration")) if mc.get("duration") else None
                pub = item.findtext("pubDate") or ""
                ago_h = None
                if pub:
                    try:
                        import email.utils, datetime
                        dt = email.utils.parsedate_to_datetime(pub)
                        ago_h = max((datetime.datetime.now(datetime.timezone.utc) - dt).total_seconds() / 3600, 0.5)
                    except Exception:
                        pass
                vid = link.rstrip("/").split("/")[-1]
                items.append(video(
                    "vimeo", vid, title, link, thumb,
                    creator, region="Global",
                    ago_hours=ago_h, ago_text=_ago_kr(ago_h),
                    duration=dur, extra=name,
                ))
        except Exception as e:
            print(f"  vimeo 실패: {e}")
    return items[:20]


# ---------------------------------------------------------------- Reddit (RSS)
REDDIT_SUBS = ["videos", "TikTokCringe", "nextfuckinglevel", "Damnthatsinteresting"]
ATOM = "{http://www.w3.org/2005/Atom}"
MRSS = "{http://search.yahoo.com/mrss/}"


def fetch_reddit():
    """멀티레딧으로 한 번에 수집 → 레이트리밋 회피."""
    s = session()
    items = []
    multi = "+".join(REDDIT_SUBS)
    root = None
    for attempt in range(4):
        r = s.get(f"https://www.reddit.com/r/{multi}/top.rss?t=day&limit=32", timeout=20)
        if r.ok and r.content.strip().startswith(b"<?xml"):
            root = ET.fromstring(r.content)
            break
        time.sleep(5 + attempt * 5)
    if root is None:
        raise RuntimeError(f"reddit HTTP {r.status_code}")
    rank = 0
    for e in root.iter(f"{ATOM}entry"):
        rank += 1
        title = e.findtext(f"{ATOM}title") or ""
        link_el = e.find(f"{ATOM}link")
        link = link_el.get("href") if link_el is not None else ""
        thumb_el = e.find(f"{MRSS}thumbnail")
        thumb = thumb_el.get("url") if thumb_el is not None else ""
        content = e.findtext(f"{ATOM}content") or ""
        # 본문의 [link] = 실제 영상 원본 링크
        ml = re.search(r'href="([^"]+)">\[link\]', content)
        out_url = html.unescape(ml.group(1)) if ml else link
        author = e.findtext(f"{ATOM}author/{ATOM}name") or ""
        cat = e.find(f"{ATOM}category")
        sub_label = cat.get("label") if cat is not None else "reddit"
        items.append(video(
            "reddit", link.rstrip("/").split("/")[-2] if "/comments/" in link else link,
            html.unescape(title), out_url, thumb, author,
            region="Global",
            extra=f"{sub_label} 일간 상위",
        ))
    return items[:32]


ALL_SOURCES = {
    "youtube": fetch_youtube,
    "tiktok": fetch_tiktok,
    "instagram": fetch_instagram,
    "vimeo": fetch_vimeo,
    "reddit": fetch_reddit,
}
