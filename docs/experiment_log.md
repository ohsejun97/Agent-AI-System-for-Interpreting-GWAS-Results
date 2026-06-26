# 실험 진행 로그

## 프로젝트 개요

**GWAS 해석 Agent AI** — Raw GWAS summary statistics를 입력받아 DB 근거 기반 SNP 해석 및 자기검증 결과를 출력하는 5단계 파이프라인.

- 데이터셋: Jansen et al. (Nature Genetics, 2019) — 수면 시간(sleepdur) / 불면증(insomnia)
- 분석 환경: Python 3.13, WSL2 (Ubuntu), GTX 1650 Super

---

## 커밋 히스토리 요약

| 커밋 | 내용 |
|------|------|
| `127a367` | Step 1~2 초기 구현 (Jansen 수면 시간 데이터) |
| `d90ba0e` | Step 1 top_n 제한 해제 → 52개 lead SNP 추출 |
| `5e9e517` | Step 2 전체 52개 SNP Ensembl 유전자 매핑 완료 |
| `53e65aa` | gene_mapping_results_full → gene_mapping_results 통합 |
| `2d21084` | **버그 수정**: Ensembl API GRCh38 → GRCh37 수정, Step 2 재실행 |
| `8564742` | Step 3 근거 수집 구현 및 실행 완료 |
| `ad448b3` | 중간보고서 작성 (Step 1~3 결과) |
| `18079e7` | 중간보고서 섹션 재구성 |
| `78b5516` | sleepdur/insomnia 디렉토리 분리 및 파이프라인 구성 |
| `878b24a` | insomnia Step 1~3 실행 결과 추가 |
| `b66f289` | 중간보고서 양 표현형 비교로 업데이트 |
| `b56233c` | Step 4~5 LLM 해석 + 자기검증 코드 구현 |

---

## Step별 진행 현황

### Step 1 — 유의 SNP 추출 ✅

- 기준: p < 5×10⁻⁸, 500kb 그리디 LD clumping
- sleepdur: 전체 10,862,567개 → 유의 3,886개 → lead SNP **52개**
- insomnia: 전체 10,862,567개 → 유의 463개 → lead SNP **14개**

### Step 2 — Ensembl 유전자 매핑 ✅

- GRCh37 전용 엔드포인트 사용 (hg19 좌표 기반 데이터)
- sleepdur: 49/52 매핑 (94.2%), 고유 유전자 196개
- insomnia: 11/14 매핑 (78.6%), 고유 유전자 37개

**발생 버그**: 초기 GRCh38 API 사용으로 유전자 오매핑 발생 (rs62158206: PAX8 → ACTR3). GRCh37 수정 후 재실행.

### Step 3 — 근거 수집 ✅

GWAS Catalog (SNP 단위) + Open Targets GraphQL (유전자 단위) 조회.

| 표현형 | evidence rows | GC 응답률 | GC 직접 연관 | OT 응답률 | OT 직접 연관 |
|--------|-------------|-----------|-------------|-----------|-------------|
| sleepdur | 137행 | 137/137 (100%) | 123/137 (89.8%) | 125/137 (91.2%) | 3/137 (2.2%) |
| insomnia | 25행 | 21/25 (84.0%) | 7/25 (28.0%) | 24/25 (96.0%) | 7/25 (28.0%) |

### Step 4~5 — LLM 해석 + 자기검증 🔄 진행 중

#### LLM 선택 과정

| 시도 | 결과 | 원인 |
|------|------|------|
| Gemini 2.0 Flash (google.generativeai) | 404 NOT_FOUND | 구버전 패키지 |
| Gemini 2.0 Flash (google.genai) | 429 limit:0 | 무료 티어 미지원 모델 |
| Gemini 2.0 Flash Lite | 429 | 동일 |
| Gemini 1.5 Flash | 404 | 계정에 미등록 모델 |
| Gemini 2.5 Flash Lite | 429 limit:10 RPM | 무료 티어 분당 10회 한도 초과 |
| **Ollama qwen2.5:3b** | ✅ 동작 | 로컬 실행, rate limit 없음 |

**전환 이유**: Gemini Pro 구독과 Gemini API는 별개 과금 체계. 무료 API 티어 한도 소진으로 로컬 Ollama로 전환.

#### 현재 발견된 이슈

1. **클레임 추출 버그** (수정 완료): 모델이 `### 클레임 목록`, `[클레임 목록]`, `클레임 목록:` 등 다양한 형식 사용 → 정규식으로 통합 처리
2. **모델 품질**: qwen2.5:3b가 간혹 지시를 벗어난 클레임 생성 (예: "귀하의 요청대로 근거 없는 추측은 하지 않았습니다" 같은 메타 발언을 클레임으로 포함)
3. **자기검증 판정**: 대부분 UNSUPPORTED 판정 → 프롬프트 개선 필요 가능성 있음

---

## 파이프라인 구조

```
dataset/
  Sleepdur_sumstats_Jansenetal.txt.gz
  Insomnia_sumstats_Jansenetal.txt.gz

sleepdur/
  run_step12.py     → results/snp_results.csv, gene_mapping_results.csv
  run_step3.py      → results/evidence_results.csv
  run_step45.py     → results/interpretation_results.json
  results/

insomnia/
  run_step12.py     → results/snp_results.csv, gene_mapping_results.csv
  run_step3.py      → results/evidence_results.csv
  run_step45.py     → results/interpretation_results.json
  results/
```

### 실행 순서

```bash
# 환경 활성화
source gwas/bin/activate

# sleepdur
python sleepdur/run_step12.py
python sleepdur/run_step3.py
python sleepdur/run_step45.py   # Ollama 필요: ollama pull qwen2.5:3b

# insomnia
python insomnia/run_step12.py
python insomnia/run_step3.py
python insomnia/run_step45.py
```

---

## 외부 API 사용 현황

| API | 용도 | Rate limit 대응 |
|-----|------|----------------|
| Ensembl REST (GRCh37) | 유전자 매핑 | sleep 0.3s, 429 시 재시도 3회 |
| GWAS Catalog REST | SNP-형질 근거 | sleep 0.3s |
| Open Targets GraphQL | 유전자-질병 연관 | sleep 0.3s |
| Ollama (qwen2.5:3b) | LLM 해석/검증 | 로컬, 제한 없음 |

---

## 향후 계획

- [ ] Step 4~5 insomnia/sleepdur 전체 실행 완료
- [ ] 자기검증 프롬프트 개선 (UNSUPPORTED 과다 판정 원인 분석)
- [ ] 전체 파이프라인 단일 스크립트로 통합 (`run_pipeline.py`)
- [ ] H1 가설 검증: 자기검증 적용 시 DB 근거 지지율 > 미적용 baseline
- [ ] H2 가설 검증: GWAS 특화 DB vs 일반 DB 직접 근거 비율 비교
