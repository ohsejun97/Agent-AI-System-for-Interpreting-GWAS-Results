"""
Jansen et al. Sleep duration GWAS — Step 1~2 실행
입력: dataset/Sleepdur_sumstats_Jansenetal.txt.gz
출력: snp_results.csv, gene_mapping_results.csv
"""
import pandas as pd
import requests
import time
import json

# ──────────────────────────────────────────────────────────────
# Step 1: 유의 SNP 추출 + LD clumping
# ──────────────────────────────────────────────────────────────

print("=" * 55)
print("[Step 1] 유의 SNP 추출 (p < 5×10⁻⁸)")
print("=" * 55)

df = pd.read_csv(
    'dataset/Sleepdur_sumstats_Jansenetal.txt.gz',
    sep='\t', compression='gzip',
    usecols=['SNP', 'CHR', 'BP', 'P']
)
print(f"전체 SNP 수: {len(df):,}개")

# p-value 필터
sig = df[df['P'] < 5e-8].copy().sort_values('P').reset_index(drop=True)
print(f"p < 5×10⁻⁸ 유의 SNP: {len(sig)}개")

# 500kb 그리디 LD clumping
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

snp_df = pd.DataFrame(keep)[['SNP', 'CHR', 'BP', 'P']]
snp_df.to_csv('results/snp_results.csv', index=False)
print(f"LD clumping 후 lead SNP: {len(snp_df)}개 → results/snp_results.csv 저장 완료")

print(snp_df.to_string(index=False))

# ──────────────────────────────────────────────────────────────
# Step 2: Ensembl REST API 유전자 매핑
# ──────────────────────────────────────────────────────────────

print("\n" + "=" * 55)
print("[Step 2] Ensembl REST API 유전자 매핑 (±500kb)")
print("=" * 55)

def map_snp_to_genes(chrom, pos, window_kb=500):
    start = max(1, pos - window_kb * 1000)
    end = pos + window_kb * 1000
    # Jansen 데이터가 GRCh37(hg19) 좌표이므로 grch37 전용 엔드포인트 사용
    url = (
        f"https://grch37.rest.ensembl.org/overlap/region/human/"
        f"{chrom}:{start}-{end}"
        f"?feature=gene&biotype=protein_coding&content-type=application/json"
    )
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=15)
            time.sleep(0.3)
            if r.status_code == 200:
                genes = r.json()
                # SNP와의 거리 기준 정렬
                genes_with_dist = [
                    (abs(pos - (g['start'] + g['end']) // 2), g.get('external_name', ''))
                    for g in genes if g.get('external_name')
                ]
                genes_with_dist.sort()
                return [name for _, name in genes_with_dist]
            elif r.status_code == 429:
                print(f"  rate limit, {1*(attempt+1)}초 대기...")
                time.sleep(1.0 * (attempt + 1))
        except Exception as e:
            print(f"  Ensembl 오류 ({chrom}:{pos}): {e}")
            time.sleep(1.0)
    return []

results = []
for i, (_, row) in enumerate(snp_df.iterrows(), 1):
    snp_id = row['SNP']
    chrom  = str(int(row['CHR']))
    pos    = int(row['BP'])

    genes = map_snp_to_genes(chrom, pos)
    top_genes = genes[:5]

    print(f"  [{i:2d}/{len(snp_df)}] {snp_id:15s} chr{chrom}:{pos:>10,}  "
          f"p={row['P']:.2e}  유전자: {', '.join(top_genes) if top_genes else '없음'}")

    results.append({
        'SNP_ID':   snp_id,
        'CHR':      chrom,
        'BP':       pos,
        'P':        row['P'],
        'genes':    ';'.join(top_genes),
        'n_genes':  len(genes),
    })

result_df = pd.DataFrame(results)
result_df.to_csv('results/gene_mapping_results_full.csv', index=False)

print("\n" + "=" * 55)
print("최종 결과 테이블")
print("=" * 55)
print(result_df[['SNP_ID', 'CHR', 'BP', 'P', 'genes']].to_string(index=False))
print(f"\n✓ results/gene_mapping_results_full.csv 저장 완료 ({len(result_df)}개 SNP)")
