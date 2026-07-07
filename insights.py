# -*- coding: utf-8 -*-
"""수집 데이터에서 룰 기반 인사이트 추출 (AI API 불필요)."""
import re, json, collections
from pathlib import Path
from common import ARCHIVE, fmt_views

STOPWORDS = set("""
the a an of to in on for and or with from this that is are was be at by it its as
you your yours when what how why who where which most best top like love my me we
all one day out up can get got just more so do dont not now new has have had will
im his her him she he they them their our us it if but about after before over
video videos official new full episode ep part watch live stream vs de la el
영상 공식 풀버전 하이라이트 지금 오늘 진짜 완전 그리고 하는 있는 없는 어떤 이거 저거 그거 합니다 했다 하기
shorts 쇼츠 short reel reels tiktok youtube instagram vimeo viral 바이럴
인스타 인스타그램 릴스 좋아요 팔로우 맞팔 소통 일상 추천
fyp foryou foryoupage fypシ trending viralvideo viralvideos capcut duet stitch
""".split())

TOKEN_RE = re.compile(r"#?[A-Za-z가-힣0-9]{2,}")


def tokenize(title):
    toks = []
    for t in TOKEN_RE.findall(title or ""):
        low = t.lower().lstrip("#")
        if low in STOPWORDS or low.isdigit():
            continue
        toks.append((t if t.startswith("#") else low))
    return toks


def load_yesterday_keywords():
    """오늘 이전의 가장 최근 아카이브에서 키워드 카운트 로드 (같은 날 재실행 대비)."""
    try:
        import datetime
        today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%Y-%m-%d")
        files = [f for f in sorted(ARCHIVE.glob("*.json")) if f.stem != today]
        if not files:
            return {}
        d = json.loads(files[-1].read_text(encoding="utf-8"))
        return d.get("insights", {}).get("keyword_counts", {})
    except Exception:
        return {}


def build_insights(videos):
    kw_count = collections.Counter()
    kw_platforms = collections.defaultdict(set)
    hashtags = collections.Counter()
    channel_count = collections.Counter()

    for v in videos:
        for t in tokenize(v["title"]):
            if t.startswith("#"):
                hashtags[t.lower()] += 1
                key = t.lower().lstrip("#")
            else:
                key = t
            kw_count[key] += 1
            kw_platforms[key].add(v["platform"])
        if v.get("channel"):
            channel_count[f'{v["channel"]}|{v["platform"]}'] += 1

    # 플랫폼 통계
    plat = collections.defaultdict(lambda: {"count": 0, "views": 0})
    durations = []
    shorts_n, long_n = 0, 0
    for v in videos:
        p = plat[v["platform"]]
        p["count"] += 1
        p["views"] += v.get("views") or 0
        d = v.get("duration")
        if d:
            durations.append(d)
            if d <= 90:
                shorts_n += 1
            else:
                long_n += 1

    # 바이럴 속도 TOP (시간당 조회수)
    with_vel = [v for v in videos if v.get("velocity")]
    with_vel.sort(key=lambda x: x["velocity"], reverse=True)
    top_velocity = [
        {"id": v["id"], "title": v["title"][:60], "platform": v["platform"],
         "velocity": v["velocity"], "views": v["views"], "url": v["url"]}
        for v in with_vel[:6]
    ]

    # 크로스 플랫폼 키워드 (2개 이상 플랫폼 동시 등장)
    cross = sorted(
        [{"keyword": k, "platforms": sorted(kw_platforms[k]), "count": kw_count[k]}
         for k in kw_platforms if len(kw_platforms[k]) >= 2 and kw_count[k] >= 3],
        key=lambda x: (len(x["platforms"]), x["count"]), reverse=True)[:10]

    # 어제 대비 급상승 키워드
    y = load_yesterday_keywords()
    rising = []
    if y:
        for k, c in kw_count.most_common(200):
            prev = y.get(k, 0)
            if c >= 3 and c >= prev * 2:
                rising.append({"keyword": k, "today": c, "yesterday": prev})
    rising = rising[:10]

    top_keywords = [{"keyword": k, "count": c} for k, c in kw_count.most_common(24) if c >= 2]
    top_hashtags = [{"tag": t, "count": c} for t, c in hashtags.most_common(15) if c >= 2]
    top_channels = []
    for key, c in channel_count.most_common(30):
        ch, p = key.rsplit("|", 1)
        if c >= 2:
            top_channels.append({"channel": ch, "platform": p, "count": c})
    top_channels = top_channels[:8]

    total_views = sum(v.get("views") or 0 for v in videos)
    med_dur = sorted(durations)[len(durations) // 2] if durations else None

    # 룰 기반 코멘트 (제작자 관점)
    comments = []
    if top_velocity:
        t = top_velocity[0]
        comments.append(f"지금 가장 빠르게 터지는 영상은 {_pname(t['platform'])}의 \"{t['title'][:36]}…\" — 시간당 {fmt_views(t['velocity'])}회 페이스입니다.")
    if cross:
        c = cross[0]
        comments.append(f"'{c['keyword']}' 소재가 {len(c['platforms'])}개 플랫폼({', '.join(_pname(p) for p in c['platforms'])})에서 동시에 돌고 있습니다 — 크로스 플랫폼으로 번지는 토픽은 수명이 깁니다.")
    if rising:
        r = rising[0]
        comments.append(f"어제 대비 급상승 키워드: '{r['keyword']}' (어제 {r['yesterday']}회 → 오늘 {r['today']}회 언급). 지금 올라타면 빠른 소재입니다.")
    if shorts_n + long_n > 0:
        ratio = shorts_n / (shorts_n + long_n) * 100
        comments.append(f"오늘 바이럴 풀에서 숏폼(90초 이하) 비중 {ratio:.0f}%" + (" — 여전히 숏폼이 지배적입니다." if ratio > 60 else " — 롱폼도 상당수 터지고 있습니다."))
    if top_hashtags:
        comments.append("해시태그 상위: " + " ".join(h["tag"] for h in top_hashtags[:5]))
    if top_channels:
        ch = top_channels[0]
        comments.append(f"오늘 가장 많이 노출된 크리에이터: {ch['channel']} ({_pname(ch['platform'])}, {ch['count']}편) — 반복 등장하는 채널의 포맷은 뜯어볼 가치가 있습니다.")

    return {
        "total_videos": len(videos),
        "total_views": total_views,
        "total_views_text": fmt_views(total_views),
        "platforms": dict(plat),
        "median_duration": med_dur,
        "shorts_ratio": round(shorts_n / (shorts_n + long_n) * 100) if (shorts_n + long_n) else None,
        "top_keywords": top_keywords,
        "top_hashtags": top_hashtags,
        "top_channels": top_channels,
        "top_velocity": top_velocity,
        "cross_platform": cross,
        "rising": rising,
        "comments": comments,
        "keyword_counts": dict(kw_count.most_common(300)),
    }


def _pname(p):
    return {"youtube": "유튜브", "tiktok": "틱톡", "instagram": "인스타그램",
            "vimeo": "비메오", "reddit": "레딧"}.get(p, p)
