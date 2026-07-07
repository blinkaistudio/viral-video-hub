# 🔥 Viral Video Hub

유튜브·틱톡·인스타그램·비메오·레딧의 바이럴 영상을 **API 키 없이** 매일 수집해서
한 화면 대시보드로 보여주는 사이트.

**사이트**: https://blinkaistudio.github.io/viral-video-hub/ (모바일 OK)

## 수집 방식 (API 키 불필요)
| 플랫폼 | 방법 |
|---|---|
| YouTube | 검색 결과 페이지 스크래핑 (조회수순 + 최근 업로드, KR/Global 시드 쿼리) |
| TikTok | tikwm.com 공개 트렌딩 피드 (KR/US/JP) |
| Instagram | DuckDuckGo 비디오 검색 (instagram.com/reel 필터) |
| Vimeo | Staff Picks 공식 RSS |
| Reddit | 멀티레딧 top RSS (r/videos+TikTokCringe+nextfuckinglevel+Damnthatsinteresting) |

## 자동 갱신
- **GitHub Actions**: 매일 07:30 KST 크론 (PC 꺼져 있어도 갱신)
- **로컬 백업**: Windows 작업 스케줄러가 08:30에 `자동갱신.bat` 실행 (Actions가 IP 차단당해도 커버)
- 소스 하나가 죽어도 나머지는 진행, 실패 소스는 직전 데이터 유지 + 대시보드에 ⚠️ 표시

## 인사이트 (룰 기반, AI API 불필요)
- 시간당 조회수(바이럴 속도) TOP
- 크로스 플랫폼 동시 등장 토픽 / 어제 대비 급상승 키워드 (30일 아카이브 비교)
- 숏폼 비중, 해시태그·키워드·크리에이터 상위, 제작자 노트 자동 생성

## 수동 실행
`갱신.bat` 더블클릭 → 수집 → 푸시 → 브라우저 오픈
