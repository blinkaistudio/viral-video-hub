# -*- coding: utf-8 -*-
"""전체 파이프라인: 수집 → 인사이트 → docs/data.json + 아카이브.

소스 하나가 죽어도 나머지는 진행하고, 실패한 소스는 직전 데이터를 유지(stale 표시).
틱톡 커버 등 서명 만료되는 썸네일은 docs/thumbs/에 로컬 저장.
"""
import sys, json, time, datetime
from pathlib import Path
from common import DOCS, ARCHIVE, THUMBS, session, thumb_key
import sources
from sources import ALL_SOURCES, fetch_kr_trends
from insights import build_insights

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

KST = datetime.timezone(datetime.timedelta(hours=9))

# 썸네일 URL이 만료/핫링크 차단되는 플랫폼 → 로컬로 내려받아 서빙
LOCALIZE_THUMBS = {"tiktok", "instagram"}


def load_previous():
    f = DOCS / "data.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"videos": [], "sources": {}}


def localize_thumbs(videos):
    THUMBS.mkdir(parents=True, exist_ok=True)
    s = session()
    used = set()
    for v in videos:
        if v["platform"] not in LOCALIZE_THUMBS or not v["thumb"] or v["thumb"].startswith("thumbs/"):
            if v["thumb"].startswith("thumbs/"):
                used.add(v["thumb"].split("/", 1)[1])
            continue
        name = thumb_key(v["thumb"])
        path = THUMBS / name
        if not path.exists():
            try:
                r = s.get(v["thumb"], timeout=15)
                if r.ok and len(r.content) > 1000:
                    path.write_bytes(r.content)
                else:
                    continue
            except Exception:
                continue
        v["thumb"] = f"thumbs/{name}"
        used.add(name)
    # 안 쓰는 썸네일 정리
    for f in THUMBS.glob("*.jpg"):
        if f.name not in used:
            try:
                f.unlink()
            except OSError:
                pass


def main():
    now = datetime.datetime.now(KST)
    prev = load_previous()
    prev_by_platform = {}
    for v in prev.get("videos", []):
        prev_by_platform.setdefault(v["platform"], []).append(v)

    # 🇰🇷 한국 실시간 트렌드 키워드 먼저 수집 → 각 소스의 키워드 기반 검색에 주입
    print("[한국 트렌드] 수집 중...")
    kr_trends = []
    try:
        kr_trends = fetch_kr_trends()
        sources.KR_TRENDS = kr_trends
        print(f"  ✓ 키워드 {len(kr_trends)}개: " + ", ".join(t["keyword"] for t in kr_trends[:6]))
    except Exception as e:
        print(f"  ✗ 트렌드 실패 (키워드 없이 진행): {e}")

    videos, source_status = [], {}
    for name, fn in ALL_SOURCES.items():
        print(f"[{name}] 수집 중...")
        t0 = time.time()
        try:
            items = fn()
            if not items:
                raise RuntimeError("0건 수집")
            videos.extend(items)
            source_status[name] = {"ok": True, "count": len(items),
                                   "fetched_at": now.isoformat(), "stale": False}
            print(f"  ✓ {len(items)}건 ({time.time()-t0:.1f}s)")
        except Exception as e:
            old = prev_by_platform.get(name, [])
            old_status = prev.get("sources", {}).get(name, {})
            videos.extend(old)
            source_status[name] = {"ok": False, "count": len(old),
                                   "fetched_at": old_status.get("fetched_at", ""),
                                   "stale": True, "error": str(e)[:200]}
            print(f"  ✗ 실패 → 직전 데이터 {len(old)}건 유지: {e}")

    print("[썸네일] 로컬 저장...")
    localize_thumbs(videos)

    print("[인사이트] 계산...")
    ins = build_insights(videos)
    ins["kr_trends"] = kr_trends
    kr_n = sum(1 for v in videos if v.get("region") == "KR")
    if kr_n:
        ins["comments"].insert(0, f"🇰🇷 국내 콘텐츠 {kr_n}건 수집 — 실시간 트렌드 키워드"
                               + (f"('{kr_trends[0]['keyword']}' 외 {len(kr_trends)-1}개)" if kr_trends else "")
                               + " 기반 검색이 포함되어 있습니다. 국내 필터로 모아 보세요.")

    data = {
        "generated_at": now.isoformat(),
        "generated_at_kst": now.strftime("%Y-%m-%d %H:%M"),
        "date": now.strftime("%Y-%m-%d"),
        "sources": source_status,
        "videos": videos,
        "insights": ins,
    }

    DOCS.mkdir(parents=True, exist_ok=True)
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    (DOCS / "data.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    # 아카이브: 영상 메타 없이 인사이트+요약만 (용량 관리), 하루 1파일 덮어쓰기
    arch = {
        "date": data["date"],
        "generated_at": data["generated_at"],
        "insights": {k: ins[k] for k in
                     ["total_videos", "total_views", "top_keywords", "top_hashtags",
                      "rising", "cross_platform", "shorts_ratio", "keyword_counts"]},
    }
    (ARCHIVE / f"{data['date']}.json").write_text(json.dumps(arch, ensure_ascii=False), encoding="utf-8")
    # 최근 30일만 유지
    files = sorted(ARCHIVE.glob("*.json"))
    for f in files[:-30]:
        f.unlink()

    ok = sum(1 for s in source_status.values() if s["ok"])
    print(f"\n완료: 영상 {len(videos)}건, 소스 {ok}/{len(source_status)} 성공 → docs/data.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
