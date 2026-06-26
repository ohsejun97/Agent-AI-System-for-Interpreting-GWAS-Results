# 파이프라인 현황 요약

> 마지막 업데이트: 2026-06-26

## 전체 진행률

| 단계 | sleepdur | insomnia |
|------|----------|----------|
| Step 1 — 유의 SNP 추출 | ✅ 완료 | ✅ 완료 |
| Step 2 — 유전자 매핑 | ✅ 완료 | ✅ 완료 |
| Step 3 — 근거 수집 | ✅ 완료 | ✅ 완료 |
| Step 4 — LLM 해석 생성 | 🔄 진행 중 | ✅ 완료 |
| Step 5 — 자기검증 | 🔄 진행 중 | ✅ 완료 |

---

## Step 1~3 결과 요약

### sleepdur

| 항목 | 수치 |
|------|------|
| lead SNP | 52개 |
| 유전자 매핑 | 49/52 (94.2%) |
| 고유 후보 유전자 | 196개 |
| evidence rows | 137행 |
| GWAS Catalog 근거 | 137/137 (100%) |
| GWAS Catalog 수면 직접 연관 | 123/137 (89.8%) |
| Open Targets 근거 | 125/137 (91.2%) |
| Open Targets 수면 직접 연관 | 3/137 (2.2%) |

**주요 유전자**: PAX8, FTO, SLC6A3, FOXP2, MAPT, NOS1, RBFOX1, TCF4, GRM5

### insomnia

| 항목 | 수치 |
|------|------|
| lead SNP | 14개 |
| 유전자 매핑 | 11/14 (78.6%) |
| 고유 후보 유전자 | 37개 |
| evidence rows | 25행 |
| GWAS Catalog 근거 | 21/25 (84.0%) |
| GWAS Catalog 불면증/수면 직접 연관 | 7/25 (28.0%) |
| Open Targets 근거 | 24/25 (96.0%) |
| Open Targets 불면증/수면 직접 연관 | 7/25 (28.0%) |

**주요 유전자**: MEIS1, OLFM4, DIAPH3, TCF4, LIN28B, CNIH2, LSAMP

---

## Step 4~5 현황

- LLM: **Ollama qwen2.5:3b** (로컬, GTX 1650 Super)
- 클레임 추출 버그 수정 완료 (다양한 마커 형식 정규식 처리)
### insomnia Step 4~5 결과 (1차, qwen2.5:3b)

| 항목 | 수치 |
|------|------|
| 처리 SNP | 11개 |
| 클레임 추출 | 11/11 (100%) |
| 전체 검증 클레임 | 26개 |
| SUPPORTED | 1 (3.8%) |
| PARTIALLY_SUPPORTED | 10 (38.5%) |
| UNSUPPORTED | 15 (57.7%) |
| DB 지지율 (S+P) | **42.3%** |
| 평균 신뢰도 점수 | 0.212 |

- sleepdur Step 4~5 실행 예정

### 알려진 이슈

- qwen2.5:3b가 간혹 메타 발언을 클레임으로 포함 → 프롬프트 개선 여지 있음
- 자기검증 UNSUPPORTED 비율 높음 → 추가 분석 필요

---

## 검증 가설

- **H1**: 자기검증 적용 시 클레임 DB 근거 지지율 > 미적용 baseline (GeneAgent 92% 대비)
- **H2**: GWAS 특화 DB(GWAS Catalog + Open Targets)가 일반 DB 대비 수면 직접 근거 높음
  - 현재 sleepdur GWAS Catalog 직접 근거 89.8% → H2 방향 지지
