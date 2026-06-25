# GWAS 해석 Agent AI System

Raw GWAS summary statistics를 입력받아 DB 근거 기반 SNP 해석과 자기검증 결과를 출력하는 end-to-end 파이프라인.

## 선행 연구(GeneAgent) 대비 차별점

| 항목 | GeneAgent (Wang et al., 2025) | 본 연구 |
|------|-------------------------------|---------|
| 입력 형식 | 정제된 유전자 목록 | Raw GWAS summary statistics |
| 처리 범위 | Downstream only | End-to-End |
| 활용 DB | GO, MSigDB | GWAS Catalog, GTEx, Open Targets |
| 할루시네이션 제어 | 미포함 | Self-verification 루프 내장 |

## 파이프라인 구조

```
Raw GWAS → [Step 1] 유의 SNP 추출  (p < 5×10⁻⁸, LD clumping)
         → [Step 2] 유전자 매핑    (Ensembl REST ±500kb)
         → [Step 3] 근거 수집      (GWAS Catalog / GTEx / Open Targets / PubMed)
         → [Step 4] LLM 해석 생성  (근거 기반 프롬프팅)
         → [Step 5] 자기검증       (클레임 DB 재조회 → 신뢰도 점수)
```

## 데이터셋

- **수면 시간 GWAS**: Jansen et al. (Nature Genetics, 2019), UK Biobank N=384,317
- 파일: `Sleepdur_sumstats_Jansenetal.txt.gz` (별도 다운로드 필요, `dataset/` 폴더에 위치)
- **주의**: 이 파일은 UK Biobank 단독 결과이며, 논문의 78 loci는 23andMe와의 메타분석 결과임. 23andMe 데이터는 공유 제한으로 미포함.

## 실행 방법

```bash
# 환경 설정
python -m venv gwas && source gwas/bin/activate
pip install -r requirements.txt

# Step 1-2 실행 (Jansen et al. 데이터)
python run_step12_jansen.py

# 테스트용 합성 데이터 생성 후 Step 1-2 테스트
python make_test_data.py
python test_step12.py
```

## 결과 파일

| 파일 | 설명 |
|------|------|
| `results/snp_results.csv` | Step 1 출력 — lead SNP 52개 (SNP ID, CHR, BP, p-value) |
| `results/gene_mapping_results.csv` | Step 2 출력 — SNP별 매핑 유전자 목록 (상위 30개 기준) |

## 현재 구현 결과 (Step 1-2)

- 전체 10,862,567개 SNP → p < 5×10⁻⁸ 유의 SNP **3,886개** → LD clumping 후 **52개 lead SNP**
- 최강 신호: rs62158206 (chr2:114,084,596, p=3.0×10⁻⁴³)
- 주요 매핑 유전자: FTO, SLC6A3, FOXP2, NRXN3, DCC 등

### 논문(78 loci) 대비 52 loci의 이유

1. **데이터 불완전**: 공유 파일이 UK Biobank 단독이며 23andMe 미포함 → 일부 약한 신호 누락
2. **간소화 LD clumping**: 실제 r² 정보 없이 500kb 거리만으로 처리 → 500kb 내 독립 신호 2개를 하나로 합산할 수 있음

> 정밀한 LD clumping을 위해서는 PLINK (`--clump`, r² < 0.1, 500kb) 사용 필요. 현재 구현은 외부 도구 의존성 제거를 위해 거리 기반 그리디 방식을 채택.

## 향후 계획

- Step 3-5 구현 (근거 수집 → LLM 해석 → 자기검증)
- PLINK 기반 LD clumping으로 교체
- 불면증(Insomnia) 데이터셋 추가 실험
