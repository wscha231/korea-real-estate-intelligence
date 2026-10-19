# Korea Real Estate Intelligence

전국 아파트 실거래가·전월세·법정동코드를 바탕으로 한 **Phase 1 데이터 수집 및 검증** 저장소입니다.

**Current status:** `OFFLINE_QA_PASS / LIVE_AUTH_PENDING / NATIONAL_BACKFILL_BLOCKED`.

이 저장소는 **Public**입니다. API 키, 실제 원본 거래자료, 개인 식별정보 및 상용 제휴 데이터를 커밋하지 마세요. 자동 전국 수집·가격예측·매수 추천은 아직 지원하지 않습니다.

## Offline QA (Python 3.11+)

    python -m unittest discover -s tests -v
    python -O -m unittest discover -s tests -v
    python scripts/collect_lawd.py --dry-run
    python scripts/collect_rtms.py --service trade_detail --lawd 11110 --ymd 202609 --dry-run

외부 요청은 명시적인 `--live` 없이는 수행하지 않습니다. 서비스별 공식 API 활용승인과 라이선스를 확인한 뒤, 인증키는 GitHub Secret `DATA_GO_KR_SERVICE_KEY`로만 등록하세요. **미확인·실패·부분응답을 0건으로 해석하지 않습니다.**

- [공식 API 신청 및 인증 절차](docs/API_APPROVAL.md)
- [현재 진행 및 차단 게이트](docs/PHASE1_STATUS.md)
- [데이터 조달 레지스트리](registry/api_registry.csv)
- [품질 검증 규칙](registry/quality_gates.csv)
- [에이전트 작업 규칙](AGENTS.md)

`COMPLETE`는 **단일 API × 5자리 시군구 × 계약월**의 페이징 검증만 의미하며, 전국 완전성·과거 정정이력·데이터 상업 이용 승인과 무관합니다.
