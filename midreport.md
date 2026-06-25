# 중간보고서
## 유전체 연관분석 결과 해석을 위한 검증형 Agent AI 시스템 개발

---

## 1. 연구 배경 및 목적

GWAS(Genome-Wide Association Study)는 수십만~수백만 개의 SNP와 표현형 간의 통계적 연관성을 산출하는 핵심 유전체 분석 기법이다. 그러나 유의미한 SNP 목록을 생물학적으로 해석하는 과정은 전적으로 수작업에 의존한다. 연구자는 GWAS Catalog, GTEx, Open Targets, PubMed 등 다수의 이종 데이터베이스를 개별적으로 탐색해야 하며, 이 과정은 반복적이고 시간 소모적이어서 대규모 GWAS 분석의 구조적 병목을 형성한다.

LLM 기반 접근법이 시도되고 있으나, 기존 연구(GeneAgent, Wang et al. 2025)는 두 가지 결함을 지닌다.

- **입력 한계**: 이미 정제된 유전자 목록을 입력으로 받는 downstream 구조 — raw GWAS 파일을 직접 처리할 수 없음
- **신뢰성 문제**: 생성된 해석의 근거 출처가 불투명하여 할루시네이션 검증이 불가능

본 연구는 raw GWAS summary statistics를 직접 입력받아 DB 근거 기반 SNP 해석과 자기검증 결과를 출력하는 end-to-end 검증형 Agent AI 시스템을 개발하고자 한다.

### 선행 연구(GeneAgent) 대비 차별점

| 항목 | GeneAgent (Wang et al., 2025) | 본 연구 |
|------|-------------------------------|---------|
| 입력 형식 | 정제된 유전자 목록 | Raw GWAS summary statistics |
| 처리 범위 | Downstream only | End-to-End |
| 활용 DB | GO, MSigDB (일반 기능 주석) | GWAS Catalog, GTEx, Open Targets (GWAS 특화) |
| 출력 형식 | 생물학적 프로세스 이름 | SNP별 근거 리포트 + 정량적 신뢰도 점수 |
| 할루시네이션 제어 | 미포함 | Self-verification 루프 내장 |
| 선행 연구 근거 지지율 | 92% (보고) | 측정 예정 |

---

## 2. 시스템 설계

### 파이프라인 구조 (5단계)

```
Raw GWAS summary statistics
         ↓
[Step 1] 유의 SNP 추출       ← p < 5×10⁻⁸ 필터링, 500kb 그리디 LD clumping
         ↓
[Step 2] 유전자 매핑         ← Ensembl REST API (GRCh37) ±500kb
         ↓
[Step 3] 근거 수집           ← GWAS Catalog / Open Targets GraphQL / PubMed
         ↓
[Step 4] LLM 해석 생성       ← 근거 기반 프롬프팅 (Gemini API 예정)
         ↓
[Step 5] 자기검증            ← 클레임 DB 재조회 → SUPPORTED/PARTIALLY/UNSUPPORTED
         ↓
      신뢰도 점수 + Evidence Report
```

### 데이터셋

- **수면 시간 GWAS**: Jansen et al. (Nature Genetics, 2019)
- **출처**: UK Biobank 단독 (N=384,317)
- **SNP 수**: 10,862,567개
- **비고**: 논문의 78 loci는 23andMe 메타분석 결과이며, 공개 파일은 UK Biobank 단독으로 23andMe 미포함

---

## 3. 현재 진행 상황

### Step 1 — 유의 SNP 추출 ✅ 완료

| 항목 | 수치 |
|------|------|
| 전체 SNP | 10,862,567개 |
| p < 5×10⁻⁸ 유의 SNP | 3,886개 |
| LD clumping 후 lead SNP | **52개** |
| 분포 염색체 수 | 16개 |
| 최강 신호 | rs62158206 (chr2:114,084,596, p=3.0×10⁻⁴³) |
| LD clumping 정합성 | 500kb 내 중복 쌍 0개 ✓ |

**구현 방식**: PLINK 없이 500kb 창 기반 그리디 방식 채택 (p-value 오름차순 정렬 후 이미 선택된 SNP과 500kb 내에 있으면 제외). 정밀 재현을 위해서는 PLINK 기반 r² clumping이 필요하며, 이는 추후 개선 과제로 남긴다.

**논문(78 loci) 대비 52 loci 이유**:
1. 공개 파일이 UK Biobank 단독 결과 (23andMe 미포함)
2. 거리 기반 그리디 clumping의 한계 — 500kb 내 독립 신호 2개를 하나로 처리 가능

### Step 2 — 유전자 매핑 ✅ 완료

| 항목 | 수치 |
|------|------|
| 매핑 성공 SNP | 49/52 (94.2%) |
| 총 후보 유전자 (고유) | 196개 |
| SNP당 평균 유전자 수 | 8.3개 |
| 사용 API | Ensembl REST (grch37.rest.ensembl.org) |
| 윈도우 크기 | ±500kb |

**주요 매핑 유전자**: PAX8, FTO, SLC6A3, FOXP2, MAPT, NOS1, RBFOX1, TCF4, GRM5 등

**수정 사항**: 초기 구현에서 GRCh38 기반 Ensembl API(`rest.ensembl.org`) 사용으로 일부 SNP의 유전자 매핑 오류 발생 (예: rs62158206 → ACTR3). Jansen 데이터가 GRCh37(hg19) 좌표 기반임을 확인하고 GRCh37 전용 엔드포인트(`grch37.rest.ensembl.org`)로 수정 후 재실행하여 PAX8 등 논문 일치 결과 확인.

### Step 3 — 근거 수집 ✅ 완료

49개 SNP의 상위 3개 유전자(총 137 유전자-SNP 쌍)에 대해 2개 DB 조회 완료.

| DB | 조회 방식 | 응답률 | 수면 직접 연관 |
|----|----------|--------|---------------|
| GWAS Catalog | SNP → studies → diseaseTrait | 137/137 (100%) | **123/137 (89.8%)** |
| Open Targets | GraphQL, 유전자-질병 연관 점수 | 125/137 (91.2%) | 3/137 (2.2%) |

**GWAS Catalog 수면 직접 연관 SNP (44개)**:

| SNP | 주요 유전자 | 연관 형질 |
|-----|-----------|----------|
| rs62158206 | PAX8 | Long sleep duration, Insomnia, Sleep duration |
| rs11621908 | ADCK1 | Sleep duration, Short sleep duration (<5 hours) |
| rs12215241 | HIST1H2BJ | Non-REM sleep duration, Sleep duration |
| rs4767550 | NOS1 | Insomnia, Sleep duration |
| rs1668331 | FOXP2 | Sleep duration, Insomnia |
| rs3823624 | MAD1L1 | Depression, Sleep duration |
| rs62061734 | MAPT | Sleep duration |
| ... | ... | ... |

**Open Targets 수면 직접 연관 (3건)**: SDC3 → insomnia, DAB1 → restless legs syndrome, SEMA6D → restless legs syndrome

**구현 이슈 및 해결**:
- GWAS Catalog의 `/genes/{gene_name}/associations` 엔드포인트가 404를 반환하여, `SNP → studies → diseaseTrait` 경로로 우회
- Open Targets GraphQL의 `page` 파라미터 형식이 `{index: 0, size: N}`으로 변경되어 수정

### Step 4, 5 — 미구현

LLM 기반 해석 생성(Step 4) 및 자기검증 루프(Step 5)는 미구현 상태이다. Gemini API를 활용하여 구현 예정.

---

## 4. 예비 결과 및 중간 결론

1. **파이프라인 작동 확인**: Raw GWAS summary statistics → DB 근거 수집까지 Step 1~3 end-to-end 파이프라인이 정상 작동함을 확인. "정제된 유전자 목록이 아닌 raw 파일의 직접 처리"라는 핵심 차별점 구현.

2. **H2 가설 방향 지지**: GWAS Catalog 수면 직접 근거 지지율 89.8%는 GWAS 특화 DB가 수면 표현형에 대해 높은 직접 근거를 제공한다는 H2 가설의 방향을 지지한다. 반면 Open Targets의 수면 직접 연관 비율은 2.2%로 낮아, 희귀 단일유전자 질환 중심 DB로서 수면 연구에서의 활용도가 제한적임을 확인.

3. **locus 재현율**: 52 loci / 논문 78 loci = 66.7%. 23andMe 미포함 데이터 한계 및 거리 기반 clumping의 보수성에 기인.

4. **어셈블리 불일치 버그 발견 및 수정**: GRCh37/GRCh38 좌표 불일치 문제를 검증 과정에서 발견하고 수정. 검증 절차의 중요성 확인.

---

## 5. 연구계획 변경사항

| 항목 | 기존 계획 | 변경 내용 | 변경 이유 |
|------|-----------|-----------|-----------|
| LLM 모델 | Claude (Anthropic API) | **Gemini API** | 연구 환경 변경 |
| LD clumping | PLINK 기반 r² < 0.1 | 거리 기반 그리디 (500kb) | 외부 도구 의존성 제거, PLINK 교체는 추후 과제 |
| Step 3 DB 구성 | GWAS Catalog + GTEx + Open Targets + PubMed | **GWAS Catalog + Open Targets** 우선 | GTEx: SNP ID 형식 변환 필요 / PubMed: 차순위 구현 예정 |
| 입력 데이터 | UK Biobank + 23andMe 메타분석 | UK Biobank 단독 | 23andMe 데이터 공유 제한 |

---

## 6. 향후 계획

- **Step 4**: Gemini API 기반 근거 프롬프팅 해석 생성 구현
- **Step 5**: 클레임 추출 → DB 재조회 → SUPPORTED/PARTIALLY/UNSUPPORTED 판정 및 신뢰도 점수 계산
- **평가**: H1(자기검증 적용 시 지지율 향상) 및 H2(GWAS 특화 DB 유효성) 정량 검증
- **확장**: 불면증(Insomnia_sumstats_Jansenetal.txt.gz) 데이터셋 추가 실험
- **개선**: PLINK 기반 LD clumping, GTEx eQTL 연동 (SNP ID 형식 변환 포함)

---

## 참고문헌

- Jansen, P.R. et al. (2019). Genome-wide analysis of insomnia in 1,331,010 individuals identifies new risk loci and functional pathways. *Nature Genetics*, 51, 394–403.
- Wang, Z. et al. (2025). GeneAgent: Self-verification language agent for gene set knowledge discovery using heterogeneous databases. *bioRxiv*.
