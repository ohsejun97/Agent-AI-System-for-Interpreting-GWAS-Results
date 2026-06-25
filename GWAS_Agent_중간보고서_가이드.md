# GWAS 해석 Agent AI — 중간보고서 완전 가이드
> 작성 기준: 1일(~8시간) 안에 작동 가능한 프로토타입 + 보고서 작성 완료

---

## PART 1. 연구 개요 (보고서 서론 내용)

### 1-1. 핵심 문제

GWAS(Genome-Wide Association Study)는 수십만~수백만 개의 SNP와 표현형 간의 통계적 연관성을 산출하는 핵심 유전체 분석 기법이다. 그러나 **유의미한 SNP 목록을 생물학적으로 해석하는 과정은 전적으로 수작업에 의존**한다. 연구자는 GWAS Catalog, GTEx, Open Targets, PubMed 등 다수의 이종 데이터베이스를 개별적으로 탐색해야 하며, 이 과정은 반복적이고 시간 소모적이어서 대규모 GWAS 분석의 구조적 병목을 형성한다.

LLM 기반 접근법이 시도되고 있으나, 기존 연구(GeneAgent, Wang et al. 2025)는 두 가지 결함을 지닌다:

- **입력 한계**: 이미 정제된 유전자 목록을 입력으로 받는 downstream 구조 — raw GWAS 파일을 직접 처리할 수 없음
- **신뢰성 문제**: 생성된 해석의 근거 출처가 불투명하여 할루시네이션 검증이 불가능

### 1-2. 핵심 가설

> **자기검증(self-verification) 루프를 포함한 end-to-end Agent AI 시스템은,
> raw GWAS summary statistics를 직접 처리하면서 동시에 생성 해석의 DB 근거 지지율을
> 자기검증 미적용 LLM 대비 유의미하게 향상시킬 수 있다.**

구체적으로 검증할 가설:
- **H1**: Self-verification 적용 시 클레임의 DB 근거 지지율 > 미적용 시 (baseline 비교)
- **H2**: GWAS 특화 DB 구성(GWAS Catalog + GTEx + Open Targets)이 일반 기능 주석 DB 대비 더 직접적인 근거를 제공한다

### 1-3. 선행 연구 대비 차별점

| 항목 | GeneAgent (Wang et al., 2025) | 본 연구 |
|------|-------------------------------|---------|
| 입력 형식 | 정제된 유전자 목록 | Raw GWAS summary statistics |
| 처리 범위 | Downstream only | Upstream 포함 End-to-End |
| 활용 DB | GO, MSigDB (일반 기능 주석) | GWAS Catalog, GTEx, Open Targets (GWAS 특화) |
| 출력 형식 | 생물학적 프로세스 이름 | SNP별 근거 리포트 + 정량적 신뢰도 점수 |
| 할루시네이션 제어 | 미포함 | Self-verification 루프 내장 |
| 선행 연구 근거 지지율 | 92% (GeneAgent 보고) | 측정 예정 (비교 대상) |

---

## PART 2. 파이프라인 설계

### 2-1. 전체 흐름

```
Raw GWAS summary statistics
         ↓
[Step 1] 유의 SNP 추출         ← p < 5×10⁻⁸ 필터링, LD clumping
         ↓
[Step 2] 유전자 매핑           ← 위치 기반 ±500 kb + GTEx eQTL
         ↓
[Step 3] 근거 수집             ← GWAS Catalog / GTEx / Open Targets / PubMed
         ↓
[Step 4] 해석 생성 (LLM)       ← 근거 기반 SNP-질환 연결 설명
         ↓
[Step 5] 자기검증              ← 클레임 DB 재조회 → 검증 → 신뢰도 점수
         ↓ (재조회 루프)        ↑ Unsupported 클레임 → 재생성
         ↓
Evidence Report + 신뢰도 점수
```

### 2-2. 각 단계 상세

**Step 1 — 유의 SNP 추출**
- 기준: p-value < 5×10⁻⁸ (전장유전체 유의성 기준)
- LD clumping: r² < 0.1, 250 kb 창 (독립 신호만 유지)
- 출력: `[SNP_ID, CHR, POS, P_VALUE, EFFECT_ALLELE, BETA, SE]`

**Step 2 — 유전자 매핑**
- 위치 기반: SNP 주변 ±500 kb 내 단백질 코딩 유전자 조회 (Ensembl REST API)
- eQTL 연계: GTEx v8 API로 해당 SNP가 어느 조직에서 유전자 발현 조절하는지 확인
- 출력: `SNP → [gene1, gene2, ...]` 매핑 테이블

**Step 3 — 근거 수집 (4개 DB)**
- GWAS Catalog: 동일 SNP/유전자의 선행 연구 연관성 조회
- GTEx v8: eQTL 효과 크기(NES), 조직별 유의성(p-value)
- Open Targets: 유전자-질병 연관 점수 (Overall Association Score, 0~1)
- PubMed: 유전자명 + 표현형 키워드 기반 논문 검색 (제목 + 초록)
- 출력: SNP별 구조화된 근거 딕셔너리

**Step 4 — LLM 기반 해석 생성**
- 프롬프트 전략: 수집된 근거를 컨텍스트로 제공, "제공된 근거에 명시된 내용만 언급, 출처 명시" 제약
- 출력: SNP별 자연어 해석 + 검증 가능한 클레임 리스트

**Step 5 — 자기검증**
- 클레임 추출 → DB 재조회 → Supported / Partially Supported / Unsupported 판정
- 신뢰도 점수 = Supported 클레임 수 / 전체 클레임 수
- Unsupported 비율 높으면 → 해당 SNP 해석 재생성 (1회 재시도)

---

## PART 3. 1일 구현 로드맵

> **목표**: SNP 30개짜리 수면 데이터로 5단계 파이프라인 end-to-end 작동 확인

### ⏱️ 시간표

| 시간 | 작업 |
|------|------|
| 00:00 ~ 00:30 | 환경 세팅 + 데이터 다운로드 |
| 00:30 ~ 02:00 | Step 1: SNP 추출 구현 및 테스트 |
| 02:00 ~ 03:30 | Step 2: 유전자 매핑 구현 |
| 03:30 ~ 05:30 | Step 3: DB API 연동 4개 |
| 05:30 ~ 07:00 | Step 4~5: LLM + 자기검증 |
| 07:00 ~ 08:00 | 통합 테스트 + 결과 캡처 + 보고서 작성 |

### 환경 세팅 (30분)

```bash
pip install pandas requests anthropic tqdm
```

**데이터 소스 — UK Biobank 대신 이걸 써라:**

```bash
# OpenGWAS API로 수면 시간 GWAS 다운로드 (즉시 가능)
# trait: ieu-b-108 (sleep duration, UK Biobank)
curl "https://gwas.mrcieu.ac.uk/files/ieu-b-108/ieu-b-108.vcf.gz" -o sleep_gwas.vcf.gz
# 또는 GWAS Catalog에서 공개 summary stats 다운로드
# https://www.ebi.ac.uk/gwas/studies/GCST006585 (Jones et al. 2019, sleep duration)
```

**API 키 설정 (환경변수로):**

```bash
export ANTHROPIC_API_KEY="sk-ant-..."  # claude API
```

---

## PART 4. 실제 구현 코드

### Step 1: 유의 SNP 추출

```python
import pandas as pd

def load_gwas_sumstats(filepath: str) -> pd.DataFrame:
    """
    GWAS summary statistics 로드
    필수 컬럼: SNP, CHR, BP, P, A1, BETA, SE
    """
    df = pd.read_csv(filepath, sep='\t', compression='infer')
    
    # 컬럼명 표준화 (데이터마다 다를 수 있음)
    col_map = {
        'variant_id': 'SNP', 'rsid': 'SNP',
        'chromosome': 'CHR', 'chrom': 'CHR', '#CHROM': 'CHR',
        'base_pair_location': 'BP', 'pos': 'BP', 'POS': 'BP',
        'p_value': 'P', 'pval': 'P', 'P-value': 'P',
        'effect_allele': 'A1', 'beta': 'BETA', 'standard_error': 'SE'
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
    return df

def extract_significant_snps(df: pd.DataFrame, 
                               p_threshold: float = 5e-8,
                               top_n: int = 50) -> pd.DataFrame:
    """
    유의 SNP 추출 + 간소화 LD 처리 (p-value 기반 top SNP 선별)
    실제 LD clumping은 PLINK 필요하므로 중간보고서 단계에서는 top_n 방식 사용
    """
    sig = df[df['P'] < p_threshold].copy()
    sig = sig.sort_values('P')
    
    # 간소화 LD: 500kb 창 안에서 가장 유의한 SNP만 유지 (그리디)
    sig = sig.reset_index(drop=True)
    keep = []
    kept_positions = []
    
    for _, row in sig.iterrows():
        too_close = any(
            row['CHR'] == pos[0] and abs(row['BP'] - pos[1]) < 500_000
            for pos in kept_positions
        )
        if not too_close:
            keep.append(row)
            kept_positions.append((row['CHR'], row['BP']))
        if len(keep) >= top_n:
            break
    
    result = pd.DataFrame(keep)
    print(f"유의 SNP: {len(df[df['P'] < p_threshold])}개 → LD 처리 후: {len(result)}개")
    return result
```

### Step 2: 유전자 매핑

```python
import requests
import time

def map_snp_to_genes(chrom: str, pos: int, window_kb: int = 500) -> list[dict]:
    """
    Ensembl REST API로 SNP 주변 유전자 조회
    """
    start = max(1, pos - window_kb * 1000)
    end = pos + window_kb * 1000
    
    url = (f"https://rest.ensembl.org/overlap/region/human/"
           f"{chrom}:{start}-{end}"
           f"?feature=gene&biotype=protein_coding&content-type=application/json")
    
    try:
        response = requests.get(url, timeout=10)
        time.sleep(0.1)  # rate limit
        if response.status_code == 200:
            genes = response.json()
            return [
                {
                    'gene_id': g.get('id', ''),
                    'gene_name': g.get('external_name', ''),
                    'distance_to_snp': abs(pos - (g['start'] + g['end']) // 2)
                }
                for g in genes
            ]
    except Exception as e:
        print(f"Ensembl API 오류 ({chrom}:{pos}): {e}")
    return []

def get_eqtl_from_gtex(snp_id: str, top_n: int = 5) -> list[dict]:
    """
    GTEx v8 API로 eQTL 정보 조회
    """
    url = "https://gtexportal.org/api/v2/association/singleTissueEqtl"
    params = {'variantId': snp_id, 'datasetId': 'gtex_v8'}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        time.sleep(0.3)
        if response.status_code == 200:
            data = response.json().get('data', [])
            # p-value 순으로 정렬
            data.sort(key=lambda x: x.get('pValue', 1))
            return data[:top_n]
    except Exception as e:
        print(f"GTEx API 오류 ({snp_id}): {e}")
    return []
```

### Step 3: 근거 수집 (DB별)

```python
import json

# ── GWAS Catalog ──────────────────────────────────────────
def query_gwas_catalog(gene_name: str) -> list[dict]:
    """
    GWAS Catalog에서 유전자 관련 선행 연구 연관성 조회
    """
    url = f"https://www.ebi.ac.uk/gwas/rest/api/genes/{gene_name}/associations"
    try:
        r = requests.get(url, timeout=10)
        time.sleep(0.2)
        if r.status_code == 200:
            assocs = r.json().get('_embedded', {}).get('associations', [])
            results = []
            for a in assocs[:5]:  # 상위 5개만
                trait = a.get('efoTraits', [{}])[0].get('trait', 'Unknown') if a.get('efoTraits') else 'Unknown'
                results.append({
                    'trait': trait,
                    'p_value': a.get('pvalue', None),
                    'study': a.get('study', {}).get('accessionId', '')
                })
            return results
    except Exception as e:
        print(f"GWAS Catalog 오류 ({gene_name}): {e}")
    return []

# ── Open Targets ──────────────────────────────────────────
def query_open_targets(gene_name: str) -> list[dict]:
    """
    Open Targets GraphQL API로 유전자-질병 연관 점수 조회
    """
    url = "https://api.platform.opentargets.org/api/v4/graphql"
    query = """
    query GeneAssociations($geneName: String!) {
      search(queryString: $geneName, entityNames: ["target"]) {
        hits {
          object {
            ... on Target {
              id
              approvedSymbol
              associatedDiseases(page: {size: 5}) {
                rows {
                  disease {
                    name
                  }
                  score
                }
              }
            }
          }
        }
      }
    }
    """
    try:
        r = requests.post(url, json={'query': query, 'variables': {'geneName': gene_name}}, timeout=15)
        time.sleep(0.3)
        if r.status_code == 200:
            data = r.json()
            hits = data.get('data', {}).get('search', {}).get('hits', [])
            results = []
            for hit in hits[:1]:  # 첫 번째 타겟만
                target = hit.get('object', {})
                if target.get('approvedSymbol', '').upper() == gene_name.upper():
                    diseases = target.get('associatedDiseases', {}).get('rows', [])
                    for d in diseases:
                        results.append({
                            'disease': d['disease']['name'],
                            'association_score': round(d['score'], 3)
                        })
            return results
    except Exception as e:
        print(f"Open Targets 오류 ({gene_name}): {e}")
    return []

# ── PubMed ────────────────────────────────────────────────
def query_pubmed(gene_name: str, phenotype: str = "sleep", max_results: int = 3) -> list[dict]:
    """
    PubMed E-utilities API로 관련 논문 검색
    """
    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    
    search_params = {
        'db': 'pubmed', 'term': f"{gene_name}[Gene] AND {phenotype}[Title/Abstract]",
        'retmax': max_results, 'retmode': 'json', 'sort': 'relevance'
    }
    try:
        r = requests.get(search_url, params=search_params, timeout=10)
        time.sleep(0.3)
        ids = r.json().get('esearchresult', {}).get('idlist', [])
        if not ids:
            return []
        
        fetch_params = {
            'db': 'pubmed', 'id': ','.join(ids),
            'rettype': 'abstract', 'retmode': 'text'
        }
        r2 = requests.get(fetch_url, params=fetch_params, timeout=10)
        return [{'pmids': ids, 'abstracts': r2.text[:500]}]  # 요약만
    except Exception as e:
        print(f"PubMed 오류 ({gene_name}): {e}")
    return []

# ── 통합 근거 수집 ────────────────────────────────────────
def collect_evidence(snp_id: str, genes: list[str], phenotype: str = "sleep") -> dict:
    """
    SNP 하나에 대해 모든 DB에서 근거 수집
    """
    evidence = {
        'snp_id': snp_id,
        'genes': genes,
        'gwas_catalog': {},
        'open_targets': {},
        'pubmed': {}
    }
    
    for gene in genes[:3]:  # 상위 3개 유전자만
        evidence['gwas_catalog'][gene] = query_gwas_catalog(gene)
        evidence['open_targets'][gene] = query_open_targets(gene)
        evidence['pubmed'][gene] = query_pubmed(gene, phenotype)
    
    return evidence
```

### Step 4: LLM 기반 해석 생성

```python
import anthropic

client = anthropic.Anthropic()  # ANTHROPIC_API_KEY 환경변수 자동 사용

INTERPRETATION_PROMPT = """당신은 유전체 연구자입니다. 아래 제공된 DB 근거만을 기반으로 
SNP와 표현형의 연관성을 해석하세요.

규칙:
1. 제공된 근거에 명시된 내용만 언급하세요 (추측 금지)
2. 각 주장에 근거 출처를 명시하세요 (예: [GWAS Catalog], [Open Targets], [GTEx])
3. 근거가 없는 주장은 하지 마세요
4. 해석 마지막에 검증 가능한 클레임을 번호 목록으로 정리하세요

SNP: {snp_id}
표현형: {phenotype}

수집된 근거:
{evidence_json}

해석을 작성하고, 마지막에 다음 형식으로 클레임 목록을 작성하세요:
[클레임 목록]
1. (근거 출처) 구체적 주장
2. ...
"""

def generate_interpretation(snp_id: str, evidence: dict, phenotype: str = "sleep duration") -> dict:
    """
    LLM으로 SNP 해석 생성
    """
    prompt = INTERPRETATION_PROMPT.format(
        snp_id=snp_id,
        phenotype=phenotype,
        evidence_json=json.dumps(evidence, ensure_ascii=False, indent=2)
    )
    
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    
    response_text = message.content[0].text
    
    # 클레임 추출
    claims = []
    if '[클레임 목록]' in response_text:
        claim_section = response_text.split('[클레임 목록]')[1]
        for line in claim_section.strip().split('\n'):
            line = line.strip()
            if line and line[0].isdigit():
                claims.append(line)
    
    return {
        'snp_id': snp_id,
        'interpretation': response_text,
        'claims': claims
    }
```

### Step 5: 자기검증

```python
VERIFICATION_PROMPT = """아래 클레임이 제공된 DB 근거에 의해 지지되는지 판정하세요.

클레임: {claim}

DB 근거:
{evidence_json}

판정 형식 (아래 중 하나만):
SUPPORTED - 근거에 명확히 지지됨
PARTIALLY_SUPPORTED - 근거가 일부만 존재
UNSUPPORTED - 근거 없음 또는 근거와 모순

판정: """

def verify_claims(interpretation_result: dict, evidence: dict) -> dict:
    """
    생성된 클레임을 DB 근거와 대조하여 검증
    """
    claims = interpretation_result.get('claims', [])
    verified_claims = []
    
    for claim in claims:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=100,
            messages=[{
                "role": "user",
                "content": VERIFICATION_PROMPT.format(
                    claim=claim,
                    evidence_json=json.dumps(evidence, ensure_ascii=False, indent=2)
                )
            }]
        )
        
        verdict_text = message.content[0].text.strip()
        if 'SUPPORTED' in verdict_text and 'PARTIALLY' not in verdict_text and 'UN' not in verdict_text:
            verdict = 'SUPPORTED'
        elif 'PARTIALLY' in verdict_text:
            verdict = 'PARTIALLY_SUPPORTED'
        else:
            verdict = 'UNSUPPORTED'
        
        verified_claims.append({'claim': claim, 'verdict': verdict})
        time.sleep(0.2)
    
    # 신뢰도 점수 계산
    if verified_claims:
        score = sum(
            1.0 if c['verdict'] == 'SUPPORTED' else
            0.5 if c['verdict'] == 'PARTIALLY_SUPPORTED' else
            0.0
            for c in verified_claims
        ) / len(verified_claims)
    else:
        score = 0.0
    
    return {
        'snp_id': interpretation_result['snp_id'],
        'verified_claims': verified_claims,
        'confidence_score': round(score, 3),
        'support_rate': round(
            sum(1 for c in verified_claims if c['verdict'] == 'SUPPORTED') / len(verified_claims)
            if verified_claims else 0, 3
        )
    }
```

### 전체 파이프라인 실행

```python
def run_pipeline(sumstats_path: str, 
                 phenotype: str = "sleep duration",
                 n_snps: int = 30,
                 use_cache: bool = True) -> list[dict]:
    """
    5단계 파이프라인 end-to-end 실행
    """
    import os
    CACHE_FILE = "pipeline_cache.json"
    
    # ── Step 1: SNP 추출 ──
    print("=" * 50)
    print("[Step 1] 유의 SNP 추출...")
    df = load_gwas_sumstats(sumstats_path)
    sig_snps = extract_significant_snps(df, top_n=n_snps)
    print(f"  → {len(sig_snps)}개 lead SNP 선별 완료")
    
    results = []
    
    for idx, snp_row in sig_snps.iterrows():
        snp_id = snp_row['SNP']
        chrom = str(snp_row['CHR'])
        pos = int(snp_row['BP'])
        
        print(f"\n[{idx+1}/{len(sig_snps)}] 처리 중: {snp_id}")
        
        # ── Step 2: 유전자 매핑 ──
        print("  [Step 2] 유전자 매핑...")
        genes_info = map_snp_to_genes(chrom, pos)
        gene_names = [g['gene_name'] for g in genes_info if g['gene_name']][:5]
        eqtl_info = get_eqtl_from_gtex(snp_id)
        
        if not gene_names:
            print(f"  → 매핑된 유전자 없음, 스킵")
            continue
        
        print(f"  → 후보 유전자: {', '.join(gene_names[:3])}")
        
        # ── Step 3: 근거 수집 ──
        print("  [Step 3] DB 근거 수집...")
        evidence = collect_evidence(snp_id, gene_names, phenotype)
        evidence['eqtl'] = eqtl_info
        
        # ── Step 4: LLM 해석 생성 ──
        print("  [Step 4] LLM 해석 생성...")
        interpretation = generate_interpretation(snp_id, evidence, phenotype)
        
        # ── Step 5: 자기검증 ──
        print("  [Step 5] 자기검증...")
        verification = verify_claims(interpretation, evidence)
        
        # 낮은 신뢰도 → 재생성 1회
        if verification['confidence_score'] < 0.5 and interpretation['claims']:
            print("  → 낮은 신뢰도, 재생성 시도...")
            interpretation = generate_interpretation(snp_id, evidence, phenotype)
            verification = verify_claims(interpretation, evidence)
        
        result = {
            'snp_id': snp_id,
            'chr': chrom,
            'pos': pos,
            'p_value': float(snp_row['P']),
            'genes': gene_names,
            'evidence_summary': {
                'gwas_catalog_hits': sum(len(v) for v in evidence['gwas_catalog'].values()),
                'open_targets_hits': sum(len(v) for v in evidence['open_targets'].values()),
                'eqtl_tissues': len(eqtl_info)
            },
            'interpretation': interpretation['interpretation'],
            'claims': interpretation['claims'],
            'verified_claims': verification['verified_claims'],
            'confidence_score': verification['confidence_score'],
            'support_rate': verification['support_rate']
        }
        results.append(result)
        print(f"  ✓ 완료 | 신뢰도: {verification['confidence_score']:.2f} | 지지율: {verification['support_rate']:.2f}")
    
    # 결과 저장
    with open('pipeline_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*50}")
    print(f"파이프라인 완료: {len(results)}개 SNP 처리")
    print(f"평균 신뢰도 점수: {sum(r['confidence_score'] for r in results)/len(results):.3f}")
    print(f"평균 DB 지지율: {sum(r['support_rate'] for r in results)/len(results):.3f}")
    
    return results


# ── 결과 요약 출력 ──────────────────────────────────────
def print_summary(results: list[dict]):
    """보고서용 요약 출력"""
    print("\n" + "="*60)
    print("EVIDENCE REPORT 요약")
    print("="*60)
    
    for r in results:
        print(f"\n▶ {r['snp_id']} (chr{r['chr']}:{r['pos']}, p={r['p_value']:.2e})")
        print(f"  유전자: {', '.join(r['genes'][:3])}")
        print(f"  근거: GWAS Catalog {r['evidence_summary']['gwas_catalog_hits']}건 | "
              f"eQTL {r['evidence_summary']['eqtl_tissues']}조직")
        print(f"  신뢰도 점수: {r['confidence_score']:.2f} | 지지율: {r['support_rate']:.2f}")
        print(f"  클레임 ({len(r['claims'])}개):")
        for vc in r['verified_claims']:
            icon = '✓' if vc['verdict'] == 'SUPPORTED' else '△' if 'PARTIAL' in vc['verdict'] else '✗'
            print(f"    {icon} {vc['claim'][:80]}...")
    
    print("\n[전체 통계]")
    all_verdicts = [vc['verdict'] for r in results for vc in r['verified_claims']]
    print(f"  전체 클레임: {len(all_verdicts)}개")
    print(f"  SUPPORTED: {all_verdicts.count('SUPPORTED')} ({all_verdicts.count('SUPPORTED')/len(all_verdicts)*100:.1f}%)")
    print(f"  PARTIALLY: {all_verdicts.count('PARTIALLY_SUPPORTED')} ({all_verdicts.count('PARTIALLY_SUPPORTED')/len(all_verdicts)*100:.1f}%)")
    print(f"  UNSUPPORTED: {all_verdicts.count('UNSUPPORTED')} ({all_verdicts.count('UNSUPPORTED')/len(all_verdicts)*100:.1f}%)")
    print(f"  DB 근거 지지율: {(all_verdicts.count('SUPPORTED')+all_verdicts.count('PARTIALLY_SUPPORTED'))/len(all_verdicts)*100:.1f}%")


if __name__ == "__main__":
    results = run_pipeline(
        sumstats_path="sleep_gwas.tsv",
        phenotype="sleep duration",
        n_snps=30
    )
    print_summary(results)
```

---

## PART 5. 중간보고서 작성 가이드

### 5-1. 권장 구성 (섹션별)

**① 연구 배경 및 목적** (~1페이지)
- GWAS 해석 병목 문제 → 기존 LLM 접근법의 한계 → 본 연구 필요성 순으로 기술
- GeneAgent와의 차별점 표 삽입 (위 Part 1 표 활용)

**② 연구 방법 — 시스템 설계** (~2페이지)
- 5단계 파이프라인 흐름도 삽입 (발표 자료의 다이어그램 활용)
- 각 단계별 구현 방법, 활용 DB, 출력 형식 기술
- 데이터셋 선택 근거: "수면 시간 표현형을 1차 검증 대상으로 선정한 이유는 연속형 표현형으로 처리 파이프라인이 단순하고, OpenGWAS (ieu-b-108)를 통해 즉시 접근 가능하기 때문"

**③ 현재 진행 상황** (~1페이지)
- Step 1~3: 구현 및 테스트 완료 (스크린샷 삽입)
- Step 4~5: 구현 완료, 소규모 pilot 결과 (표 삽입)
- 현재까지 처리된 SNP 수, 수집된 근거 건수 제시

**④ 예비 결과** (~1페이지)
- Pilot 결과 표: SNP별 신뢰도 점수, DB 지지율
- 전체 클레임 판정 분포 (SUPPORTED/PARTIALLY/UNSUPPORTED 비율)
- 선행 연구(GeneAgent 92%) 대비 현재 수치 제시

**⑤ 향후 계획** (~0.5페이지)
- 전체 데이터셋 확대 (30개 SNP → 전체)
- 추가 데이터셋 (불면증, 우울증) 실험 예정
- 평가 지표 3가지 측정 완료 목표

### 5-2. 보고서에 넣을 결과 캡처 목록

구현 후 반드시 캡처해야 할 것들:

```
□ Step 1 출력: 유의 SNP 목록 상위 10개 테이블 (터미널 or 노트북)
□ Step 2 출력: SNP → 유전자 매핑 결과 예시 1~2개
□ Step 3 출력: 특정 SNP의 DB 근거 JSON 구조 (pretty print)
□ Step 4 출력: LLM이 생성한 해석 텍스트 예시 1개
□ Step 5 출력: 클레임 검증 결과 표 (SNP별 신뢰도 점수)
□ 최종 통계: 전체 클레임 판정 분포 (숫자 or 바 차트)
```

### 5-3. 결과 표 템플릿

보고서에 삽입할 핵심 표:

| SNP ID | 유전자 | GWAS hits | eQTL 조직수 | 클레임 수 | 신뢰도 점수 | 지지율 |
|--------|--------|-----------|------------|---------|-----------|--------|
| rs12345 | GENE1 | 3 | 5 | 4 | 0.88 | 0.75 |
| rs67890 | GENE2 | 1 | 2 | 3 | 0.67 | 0.67 |
| ... | ... | ... | ... | ... | ... | ... |

---

## PART 6. 체크리스트

### 구현 완료 확인

```
□ 환경 설치 (pandas, requests, anthropic)
□ GWAS summary stats 다운로드 완료
□ Step 1: p-value 필터링 작동 확인
□ Step 1: 간소화 LD 처리 작동 확인
□ Step 2: Ensembl REST API 응답 확인
□ Step 2: GTEx API 응답 확인
□ Step 3: GWAS Catalog API 응답 확인
□ Step 3: Open Targets GraphQL API 응답 확인
□ Step 3: PubMed E-utilities 응답 확인
□ Step 4: LLM 해석 생성 + 클레임 추출 확인
□ Step 5: 클레임 판정 (S/P/U) 확인
□ Step 5: 신뢰도 점수 계산 확인
□ End-to-end: 30개 SNP 전체 처리 완료
□ pipeline_results.json 저장 확인
□ 결과 요약 출력 확인
```

### 보고서 작성 완료 확인

```
□ 연구 배경 및 목적 작성
□ GeneAgent 대비 차별점 표 삽입
□ 5단계 파이프라인 흐름도 삽입
□ 데이터셋 선택 근거 기술
□ Step별 구현 방법 기술
□ 진행 현황 기술 (완료/예정 구분)
□ 예비 결과 표 삽입 (신뢰도 점수 등)
□ 전체 클레임 판정 분포 삽입
□ GeneAgent 92% 대비 현재 수치 언급
□ 향후 계획 기술 (평가 3가지)
□ 참고문헌 (GeneAgent 논문 등)
```

---

## PART 7. 자주 발생하는 오류 대처

| 오류 | 원인 | 해결 |
|------|------|------|
| Ensembl 429 Too Many Requests | Rate limit | `time.sleep(0.5)` 늘리기 |
| GTEx API 빈 응답 | SNP ID 형식 불일치 | `chr1_12345_A_G_b38` 형식으로 변환 |
| Open Targets GraphQL 오류 | 유전자명 대소문자 | 대문자 통일 (`GENE.upper()`) |
| PubMed API 느림 | 네트워크 | 결과 캐싱 (JSON 저장 후 재사용) |
| LLM 클레임 추출 실패 | 응답 형식 불일치 | `[클레임 목록]` 없으면 빈 리스트 반환 |
| GWAS 파일 컬럼명 불일치 | 데이터마다 다름 | `col_map` 딕셔너리에 추가 |

---

> **핵심 팁**: API 호출이 많아서 rate limit에 자주 걸린다.
> SNP 10개로 먼저 테스트 완료 후 30개로 확장하는 것을 권장.
> 중간 결과는 `json.dump`로 캐싱해서 API 재호출 낭비를 막아라.
