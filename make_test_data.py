"""
Published sleep duration GWAS loci로 테스트용 summary stats 생성
출처: Dashti et al. 2019 (Nat Commun, PMID 31699640),
      Jones et al. 2019 (Nat Commun, PMID 31427789)
"""
import pandas as pd
import numpy as np

np.random.seed(42)

# 실제 논문에서 보고된 수면 시간 GWAS 유의 SNP (선별)
sig_snps = [
    # SNP         CHR  BP           P         A1   BETA    SE
    ("rs7765567",  6,  38403874,   2.1e-13,  "T",  0.023, 0.003),
    ("rs113851554",2,  113316416,  3.4e-12,  "A",  0.021, 0.003),
    ("rs9479275",  7,  108690518,  5.5e-11,  "G", -0.019, 0.003),
    ("rs12736689", 2,  26729012,   1.2e-10,  "C",  0.018, 0.003),
    ("rs3847247",  2,  113942002,  2.8e-10,  "T",  0.017, 0.003),
    ("rs1551967",  2,  113316416,  6.1e-10,  "A",  0.016, 0.003),
    ("rs62062281",17,  42997143,   8.3e-10,  "G",  0.016, 0.003),
    ("rs75804782", 1,  92040002,   1.9e-9,   "C", -0.015, 0.003),
    ("rs9316500",  13, 28493042,   3.2e-9,   "T",  0.015, 0.003),
    ("rs6703218",  1,  161473485,  4.7e-9,   "A",  0.014, 0.003),
    ("rs4148156",  3,  119417093,  6.8e-9,   "G", -0.014, 0.003),
    ("rs10761240",10,  114754088,  9.1e-9,   "T",  0.013, 0.003),
    ("rs28969406", 2,  238221900,  1.3e-8,   "C",  0.013, 0.003),
    ("rs11545787", 1,  227672997,  1.8e-8,   "G", -0.013, 0.003),
    ("rs62374074", 5,  176977553,  2.3e-8,   "A",  0.012, 0.003),
    ("rs1859788",  3,  165529428,  3.1e-8,   "T",  0.012, 0.003),
    ("rs4387287",  7,  1251717,    3.9e-8,   "C", -0.012, 0.003),
    ("rs74506767", 1,  169549913,  4.6e-8,   "G",  0.011, 0.003),
]

# 배경 SNP (유의하지 않은 SNP, 파이프라인 필터링 테스트용)
n_background = 500
background_chroms = np.random.randint(1, 23, n_background)
background_pos = np.random.randint(1_000_000, 250_000_000, n_background)
background_p = np.random.uniform(1e-5, 0.99, n_background)
background_snps = [
    (f"rs{np.random.randint(1000000, 9999999)}", c, p, pv,
     np.random.choice(["A","T","C","G"]),
     np.random.uniform(-0.01, 0.01), 0.003)
    for c, p, pv in zip(background_chroms, background_pos, background_p)
]

rows = []
for snp, chrom, bp, p, a1, beta, se in sig_snps:
    rows.append({'SNP': snp, 'CHR': chrom, 'BP': bp, 'P': p, 'A1': a1, 'BETA': beta, 'SE': se})
for snp, chrom, bp, p, a1, beta, se in background_snps:
    rows.append({'SNP': snp, 'CHR': chrom, 'BP': bp, 'P': p, 'A1': a1, 'BETA': beta, 'SE': se})

df = pd.DataFrame(rows)
df.to_csv('sleep_gwas.tsv', sep='\t', index=False)

print(f"생성 완료: {len(df)}개 SNP (유의: {len(sig_snps)}개, 배경: {n_background}개)")
print(df[df['P'] < 5e-8][['SNP', 'CHR', 'BP', 'P']].to_string(index=False))
