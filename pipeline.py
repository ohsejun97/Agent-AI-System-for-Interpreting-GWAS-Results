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

    url = (f"https://rest.ensembl.org/overlap/region/human/"
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
