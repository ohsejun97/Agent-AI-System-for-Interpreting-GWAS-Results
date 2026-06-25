import pandas as pd
import requests
import time
import json


# ──────────────────────────────────────────────────────────────
# Step 1: 유의 SNP 추출
# ──────────────────────────────────────────────────────────────

def load_gwas_sumstats(filepath: str) -> pd.DataFrame:
    df = pd.read_csv(filepath, sep='\t', compression='infer')

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
    sig = df[df['P'] < p_threshold].copy()
    sig = sig.sort_values('P').reset_index(drop=True)

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


# ──────────────────────────────────────────────────────────────
# Step 2: 유전자 매핑
# ──────────────────────────────────────────────────────────────

def map_snp_to_genes(chrom: str, pos: int, window_kb: int = 500) -> list:
    start = max(1, pos - window_kb * 1000)
    end = pos + window_kb * 1000

    # GRCh37(hg19) 좌표 기반 데이터에 맞는 전용 엔드포인트 사용
    url = (f"https://grch37.rest.ensembl.org/overlap/region/human/"
           f"{chrom}:{start}-{end}"
           f"?feature=gene&biotype=protein_coding&content-type=application/json")

    try:
        response = requests.get(url, timeout=10)
        time.sleep(0.1)
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
        elif response.status_code == 429:
            print(f"  Ensembl rate limit, 1초 대기...")
            time.sleep(1.0)
    except Exception as e:
        print(f"Ensembl API 오류 ({chrom}:{pos}): {e}")
    return []


def get_eqtl_from_gtex(snp_id: str, top_n: int = 5) -> list:
    url = "https://gtexportal.org/api/v2/association/singleTissueEqtl"
    params = {'variantId': snp_id, 'datasetId': 'gtex_v8'}

    try:
        response = requests.get(url, params=params, timeout=10)
        time.sleep(0.3)
        if response.status_code == 200:
            data = response.json().get('data', [])
            data.sort(key=lambda x: x.get('pValue', 1))
            return data[:top_n]
    except Exception as e:
        print(f"GTEx API 오류 ({snp_id}): {e}")
    return []


# ──────────────────────────────────────────────────────────────
# Step 3: 근거 수집
# ──────────────────────────────────────────────────────────────

def query_gwas_catalog(gene_name: str) -> list:
    url = f"https://www.ebi.ac.uk/gwas/rest/api/genes/{gene_name}/associations"
    try:
        r = requests.get(url, timeout=10)
        time.sleep(0.2)
        if r.status_code == 200:
            assocs = r.json().get('_embedded', {}).get('associations', [])
            results = []
            for a in assocs[:5]:
                trait = a.get('efoTraits', [{}])[0].get('trait', 'Unknown') if a.get('efoTraits') else 'Unknown'
                results.append({
                    'trait': trait,
                    'p_value': a.get('pvalue', None),
                    'study': a.get('study', {}).get('accessionId', '')
                })
            return results
    except Exception as e:
        print(f"  GWAS Catalog 오류 ({gene_name}): {e}")
    return []


def query_open_targets(gene_name: str) -> list:
    url = "https://api.platform.opentargets.org/api/v4/graphql"
    query = """
    query($geneName: String!) {
      search(queryString: $geneName, entityNames: ["target"]) {
        hits {
          object {
            ... on Target {
              approvedSymbol
              associatedDiseases(page: {size: 5}) {
                rows {
                  disease { name }
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
            hits = r.json().get('data', {}).get('search', {}).get('hits', [])
            for hit in hits[:1]:
                target = hit.get('object', {})
                if target.get('approvedSymbol', '').upper() == gene_name.upper():
                    return [
                        {'disease': d['disease']['name'], 'score': round(d['score'], 3)}
                        for d in target.get('associatedDiseases', {}).get('rows', [])
                    ]
    except Exception as e:
        print(f"  Open Targets 오류 ({gene_name}): {e}")
    return []


def query_pubmed(gene_name: str, phenotype: str = "sleep", max_results: int = 3) -> list:
    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    fetch_url  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    try:
        r = requests.get(search_url, params={
            'db': 'pubmed', 'retmode': 'json', 'retmax': max_results, 'sort': 'relevance',
            'term': f"{gene_name}[Gene] AND {phenotype}[Title/Abstract]"
        }, timeout=10)
        time.sleep(0.3)
        ids = r.json().get('esearchresult', {}).get('idlist', [])
        if not ids:
            return []
        r2 = requests.get(fetch_url, params={
            'db': 'pubmed', 'id': ','.join(ids), 'rettype': 'abstract', 'retmode': 'text'
        }, timeout=10)
        time.sleep(0.3)
        return [{'pmids': ids, 'abstract': r2.text[:600]}]
    except Exception as e:
        print(f"  PubMed 오류 ({gene_name}): {e}")
    return []


def collect_evidence(snp_id: str, genes: list, phenotype: str = "sleep") -> dict:
    evidence = {
        'snp_id': snp_id,
        'genes': genes,
        'gwas_catalog': {},
        'open_targets': {},
        'pubmed': {},
    }
    for gene in genes[:3]:
        evidence['gwas_catalog'][gene] = query_gwas_catalog(gene)
        evidence['open_targets'][gene] = query_open_targets(gene)
        evidence['pubmed'][gene]        = query_pubmed(gene, phenotype)
    return evidence
