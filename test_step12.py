import json
from pipeline import (
    load_gwas_sumstats,
    extract_significant_snps,
    map_snp_to_genes,
    get_eqtl_from_gtex,
)

print("=" * 50)
print("[Step 1] 유의 SNP 추출")
print("=" * 50)

df = load_gwas_sumstats("sleep_gwas.tsv")
print(f"전체 SNP: {len(df)}개")
print(f"컬럼: {list(df.columns)}")

sig = extract_significant_snps(df, top_n=10)
print("\n상위 10개 lead SNP:")
print(sig[['SNP', 'CHR', 'BP', 'P']].to_string(index=False))

print("\n" + "=" * 50)
print("[Step 2] 유전자 매핑 (상위 3개 SNP)")
print("=" * 50)

results = []
for _, row in sig.head(3).iterrows():
    snp_id = row['SNP']
    chrom = str(row['CHR'])
    pos = int(row['BP'])

    print(f"\n▶ {snp_id} (chr{chrom}:{pos})")

    genes_info = map_snp_to_genes(chrom, pos)
    gene_names = [g['gene_name'] for g in genes_info if g['gene_name']][:5]
    print(f"  Ensembl 유전자 ({len(genes_info)}개 hit): {', '.join(gene_names[:5]) or '없음'}")

    eqtl_info = get_eqtl_from_gtex(snp_id)
    eqtl_tissues = [e.get('tissueSiteDetailId', '') for e in eqtl_info]
    print(f"  GTEx eQTL ({len(eqtl_info)}개): {', '.join(eqtl_tissues) or '없음'}")

    results.append({
        'snp_id': snp_id,
        'chr': chrom,
        'pos': pos,
        'p_value': float(row['P']),
        'genes': gene_names,
        'eqtl_tissues': eqtl_tissues,
    })

with open('step12_results.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print("\n✓ step12_results.json 저장 완료")
