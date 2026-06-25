# 중간보고서
## 유전체 연관분석 결과 해석을 위한 검증형 Agent AI 시스템 개발

---

## 연구진행상황요약

### 데이터셋
- **수면 시간 GWAS**: Jansen et al. (Nature Genetics, 2019), UK Biobank 단독 (N=384,317, SNP 10,862,567개)
- 논문의 78 loci는 23andMe 메타분석 결과이며, 공개 파일은 UK Biobank 단독으로 23andMe 미포함

### Step 1 — 유의 SNP 추출 ✅ 완료

전장유전체 유의성 기준(p < 5×10⁻⁸)을 적용하여 3,886개의 유의 SNP를 추출하고, 500kb 창 기반 그리디 LD clumping을 통해 **52개 독립 lead SNP**를 선별하였다.

| 항목 | 수치 |
|------|------|
| 전체 SNP | 10,862,567개 |
| p < 5×10⁻⁸ 유의 SNP | 3,886개 |
| LD clumping 후 lead SNP | **52개** |
| 분포 염색체 수 | 16개 |
| 최강 신호 | rs62158206 (chr2, p=3.0×10⁻⁴³) |
| LD clumping 정합성 검증 | 500kb 내 중복 쌍 0개 ✓ |

### Step 2 — 유전자 매핑 ✅ 완료

Ensembl REST API(GRCh37 전용 엔드포인트)를 이용하여 각 lead SNP 주변 ±500kb 내 단백질 코딩 유전자를 조회하였다.

| 항목 | 수치 |
|------|------|
| 매핑 성공 SNP | 49/52 (94.2%) |
| 총 후보 유전자 (고유) | 196개 |
| SNP당 평균 유전자 수 | 8.3개 |

주요 매핑 유전자: PAX8, FTO, SLC6A3, FOXP2, MAPT, NOS1, RBFOX1, TCF4, GRM5 등

### Step 3 — 근거 수집 ✅ 완료

49개 SNP의 상위 3개 유전자(총 137 유전자-SNP 쌍)에 대해 GWAS Catalog 및 Open Targets GraphQL API를 조회하였다.

| DB | 응답률 | 수면 직접 연관 |
|----|--------|---------------|
| GWAS Catalog | 137/137 (100%) | **123/137 (89.8%)** |
| Open Targets | 125/137 (91.2%) | 3/137 (2.2%) |

GWAS Catalog에서 "Sleep duration", "Insomnia", "Non-REM sleep duration" 등 수면 관련 형질이 직접 명시된 SNP 44개 확인.

### Step 4, 5 — 미구현

LLM 기반 해석 생성(Step 4) 및 자기검증 루프(Step 5)는 미구현 상태이며, Gemini API를 활용하여 구현 예정이다.

---

## 연구진행중간결론

### 1. 파이프라인 작동 확인
Raw GWAS summary statistics 입력부터 DB 근거 수집까지 Step 1~3 end-to-end 파이프라인이 정상 작동함을 확인하였다. 이는 본 연구의 핵심 차별점인 "정제된 유전자 목록이 아닌 raw 파일의 직접 처리"가 구현됨을 의미한다.

### 2. H2 가설 방향 지지
GWAS Catalog 수면 직접 근거 지지율 89.8%는, GWAS 특화 DB가 수면 표현형에 대해 높은 직접 근거를 제공한다는 H2 가설의 방향을 지지한다. 반면 Open Targets의 수면 직접 연관 비율은 2.2%로 낮아, 희귀 단일유전자 질환 중심 DB로서 수면 연구에서의 활용도가 제한적임을 확인하였다.

### 3. Locus 재현율
본 파이프라인의 52개 lead SNP는 논문 보고 78개 대비 66.7% 수준이다. 이는 공개 파일이 UK Biobank 단독 결과이며 23andMe 메타분석 데이터가 미포함된 데이터 한계에 기인한다.

### 4. 어셈블리 불일치 버그 발견 및 수정
초기 구현에서 GRCh38 기반 Ensembl API를 사용하여 일부 SNP의 유전자 매핑에 오류가 발생하였다 (예: rs62158206에서 PAX8 대신 ACTR3 매핑). Jansen 데이터가 GRCh37(hg19) 좌표 기반임을 확인하고 GRCh37 전용 엔드포인트로 수정 후 재실행하여 논문 보고 locus와 일치하는 결과를 확인하였다. 이는 파이프라인 검증 절차의 필요성을 방증한다.

---

## 연구계획변경사항

| 항목 | 기존 계획 | 변경 내용 | 변경 이유 |
|------|-----------|-----------|-----------|
| LLM 모델 | Claude (Anthropic API) | **Gemini API** | 연구 환경 변경 |
| LD clumping | PLINK 기반 r² < 0.1 | 거리 기반 그리디 (500kb) | 외부 도구 의존성 제거, PLINK 교체는 추후 과제 |
| Step 3 DB 구성 | GWAS Catalog + GTEx + Open Targets + PubMed | GWAS Catalog + Open Targets 우선 구현 | GTEx는 SNP ID 형식 변환 필요, PubMed는 차순위 구현 예정 |
| 입력 데이터 | UK Biobank + 23andMe 메타분석 | UK Biobank 단독 | 23andMe 데이터 공유 제한 |
