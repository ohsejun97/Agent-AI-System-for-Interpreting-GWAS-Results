"""
Jansen et al. Insomnia GWAS — Step 3: 근거 수집
입력: insomnia/results/gene_mapping_results.csv
출력: insomnia/results/evidence_results.csv
컬럼: SNP_ID, gene, gwas_catalog_traits, open_targets_diseases, open_targets_scores
"""
from pathlib import Path
import pandas as pd
import requests
import time

BASE = Path(__file__).parent
RESULTS = BASE / 'results'

PHENOTYPE = "insomnia"


def query_gwas_catalog(snp_id: str) -> list:
    url = f"https://www.ebi.ac.uk/gwas/rest/api/singleNucleotidePolymorphisms/{snp_id}/studies"
    try:
        r = requests.get(url, timeout=10)
        time.sleep(0.3)
        if r.status_code == 200:
            studies = r.json().get('_embedded', {}).get('studies', [])
            results = []
            for s in studies[:3]:
                trait = s.get('diseaseTrait', {}).get('trait', '')
                accession = s.get('accessionId', '')
                if trait:
                    results.append({'trait': trait, 'accession': accession})
            return results
    except Exception as e:
        print(f"    GC 오류 ({snp_id}): {e}")
    return []


OT_QUERY = """
query SearchTarget($q: String!) {
  search(queryString: $q, entityNames: ["target"], page: {index: 0, size: 1}) {
    hits {
      object {
        ... on Target {
          approvedSymbol
          associatedDiseases(page: {index: 0, size: 3}) {
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


def query_open_targets(gene_name: str) -> list:
    try:
        r = requests.post(
            'https://api.platform.opentargets.org/api/v4/graphql',
            json={'query': OT_QUERY, 'variables': {'q': gene_name}},
            timeout=15
        )
        time.sleep(0.3)
        if r.status_code == 200:
            hits = r.json().get('data', {}).get('search', {}).get('hits', [])
            for hit in hits[:1]:
                obj = hit.get('object', {})
                if obj.get('approvedSymbol', '').upper() == gene_name.upper():
                    return [
                        {'disease': row['disease']['name'], 'score': round(row['score'], 3)}
                        for row in obj.get('associatedDiseases', {}).get('rows', [])
                    ]
    except Exception as e:
        print(f"    OT 오류 ({gene_name}): {e}")
    return []


# ──────────────────────────────────────────────────────────────
# 메인 실행
# ──────────────────────────────────────────────────────────────

gene_df = pd.read_csv(RESULTS / 'gene_mapping_results.csv')
gene_df = gene_df[gene_df['genes'].notna() & (gene_df['genes'] != '')].reset_index(drop=True)
print(f"[Step 3] 근거 수집: {len(gene_df)}개 SNP  (표현형: {PHENOTYPE})")
print("=" * 60)

rows = []
for i, (_, row) in enumerate(gene_df.iterrows(), 1):
    snp_id = row['SNP_ID']
    genes  = [g for g in str(row['genes']).split(';') if g][:3]

    print(f"[{i:2d}/{len(gene_df)}] {snp_id}  →  {', '.join(genes)}")

    gc_results = query_gwas_catalog(snp_id)
    gc_traits  = ' | '.join(r['trait'] for r in gc_results) or ''
    print(f"    GC : {gc_traits[:70] or '없음'}")

    for gene in genes:
        ot_results  = query_open_targets(gene)
        ot_diseases = ' | '.join(r['disease'] for r in ot_results) or ''
        ot_scores   = ' | '.join(str(r['score']) for r in ot_results) or ''
        print(f"    OT [{gene}]: {ot_diseases[:60] or '없음'}")

        rows.append({
            'SNP_ID':                snp_id,
            'gene':                  gene,
            'gwas_catalog_traits':   gc_traits,
            'open_targets_diseases': ot_diseases,
            'open_targets_scores':   ot_scores,
        })

result_df = pd.DataFrame(rows)
result_df.to_csv(RESULTS / 'evidence_results.csv', index=False)

print(f"\n{'='*60}")
gc_hit = (result_df['gwas_catalog_traits'] != '').sum()
ot_hit = (result_df['open_targets_diseases'] != '').sum()
total  = len(result_df)
print(f"완료: {len(gene_df)}개 SNP × 유전자 최대 3개 = {total}행")
print(f"GWAS Catalog 근거: {gc_hit}/{total}행")
print(f"Open Targets 근거: {ot_hit}/{total}행")
print(f"\n✓ results/evidence_results.csv 저장 완료")
