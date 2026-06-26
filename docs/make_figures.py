"""
midreport 첨부 그림 생성 스크립트
출력: docs/figures/*.png
"""
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import koreanize_matplotlib  # noqa: F401  — Korean font support
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch
import json

FIGURES = Path(__file__).parent / 'figures'
ROOT    = Path(__file__).parent.parent

plt.rcParams.update({
    'axes.spines.top': False,
    'axes.spines.right': False,
    'figure.dpi': 150,
})


# ──────────────────────────────────────────────────────────────
# Figure 1: 파이프라인 플로우차트
# ──────────────────────────────────────────────────────────────
def fig_pipeline():
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 7)
    ax.axis('off')

    steps = [
        (5, 6.2, "Raw GWAS\nSummary Statistics", "#6C8EBF", "white"),
        (5, 5.0, "Step 1 — 유의 SNP 추출\n(p < 5×10⁻⁸, LD clumping)", "#7BC67E", "white"),
        (5, 3.8, "Step 2 — 유전자 매핑\n(Ensembl REST ±500kb)", "#7BC67E", "white"),
        (5, 2.6, "Step 3 — DB 근거 수집\n(GWAS Catalog + Open Targets)", "#7BC67E", "white"),
        (5, 1.4, "Step 4 — LLM 해석 생성\n(Ollama qwen2.5:3b)", "#FFB347", "white"),
        (5, 0.2, "Step 5 — 자기검증\n(클레임 → SUPPORTED/PARTIALLY/UNSUPPORTED)", "#FF7F7F", "white"),
    ]

    for x, y, label, color, fc in steps:
        bbox = dict(boxstyle='round,pad=0.4', facecolor=color, edgecolor='white', linewidth=1.5)
        ax.text(x, y, label, ha='center', va='center', fontsize=9.5,
                color=fc, bbox=bbox, fontweight='bold')

    for i in range(len(steps) - 1):
        y1 = steps[i][1] - 0.28
        y2 = steps[i+1][1] + 0.28
        ax.annotate('', xy=(5, y2), xytext=(5, y1),
                    arrowprops=dict(arrowstyle='->', color='#555', lw=1.8))

    # 오른쪽 레이블
    notes = [
        (7.8, 5.0,  "sleepdur: 52개\ninsomnia: 14개"),
        (7.8, 3.8,  "sleepdur: 49/52\ninsomnia: 11/14"),
        (7.8, 2.6,  "GC + OT\n137 / 25 행"),
        (7.8, 1.4,  "클레임 추출"),
        (7.8, 0.2,  "신뢰도 점수 산출"),
    ]
    for x, y, note in notes:
        ax.text(x, y, note, ha='center', va='center', fontsize=7.5,
                color='#444', style='italic')

    ax.set_title("GWAS 해석 Agent AI — 파이프라인 구조", fontsize=13, fontweight='bold', pad=10)
    fig.tight_layout()
    fig.savefig(FIGURES / 'fig1_pipeline.png', bbox_inches='tight')
    plt.close()
    print("✓ fig1_pipeline.png")


# ──────────────────────────────────────────────────────────────
# Figure 2: Step 3 근거 수집 비교 막대그래프
# ──────────────────────────────────────────────────────────────
def fig_evidence():
    categories = ['GC 전체\n응답률', 'GC 수면\n직접 연관', 'OT 전체\n응답률', 'OT 수면\n직접 연관']
    sleepdur = [100.0, 89.8, 91.2, 2.2]
    insomnia = [84.0,  28.0, 96.0, 28.0]

    x = np.arange(len(categories))
    w = 0.35

    fig, ax = plt.subplots(figsize=(9, 5))
    b1 = ax.bar(x - w/2, sleepdur, w, label='sleepdur', color='#5B9BD5', alpha=0.85)
    b2 = ax.bar(x + w/2, insomnia, w, label='insomnia', color='#ED7D31', alpha=0.85)

    for bar in b1:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1.5,
                f'{bar.get_height():.1f}%', ha='center', va='bottom', fontsize=8.5)
    for bar in b2:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1.5,
                f'{bar.get_height():.1f}%', ha='center', va='bottom', fontsize=8.5)

    ax.set_ylabel('비율 (%)', fontsize=11)
    ax.set_title('Step 3 — DB 근거 수집 비교 (sleepdur vs insomnia)', fontsize=12, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=10)
    ax.set_ylim(0, 115)
    ax.axhline(92, color='gray', linestyle='--', linewidth=1, alpha=0.6)
    ax.text(3.6, 93.5, 'GeneAgent 92%', fontsize=8, color='gray')
    ax.legend(fontsize=10)
    ax.yaxis.grid(True, alpha=0.3)
    ax.set_axisbelow(True)

    fig.tight_layout()
    fig.savefig(FIGURES / 'fig2_evidence_comparison.png', bbox_inches='tight')
    plt.close()
    print("✓ fig2_evidence_comparison.png")


# ──────────────────────────────────────────────────────────────
# Figure 3: Step 5 자기검증 판정 분포 (insomnia)
# ──────────────────────────────────────────────────────────────
def fig_verdict():
    interp_path = ROOT / 'insomnia' / 'results' / 'interpretation_results.json'
    if not interp_path.exists():
        print("✗ fig3: interpretation_results.json 없음")
        return

    with open(interp_path) as f:
        res = json.load(f)

    all_v = [c['verdict'] for r in res for c in r['verified_claims']]
    s = all_v.count('SUPPORTED')
    p = all_v.count('PARTIALLY_SUPPORTED')
    u = all_v.count('UNSUPPORTED')
    total = len(all_v)

    fig, axes = plt.subplots(1, 2, figsize=(11, 5))

    # 파이차트
    sizes  = [s, p, u]
    labels = [f'SUPPORTED\n({s}, {s/total*100:.1f}%)',
              f'PARTIALLY\n({p}, {p/total*100:.1f}%)',
              f'UNSUPPORTED\n({u}, {u/total*100:.1f}%)']
    colors = ['#70AD47', '#FFC000', '#FF4444']
    explode = (0.05, 0.05, 0.05)
    axes[0].pie(sizes, labels=labels, colors=colors, explode=explode,
                autopct='', startangle=140, textprops={'fontsize': 9.5})
    axes[0].set_title('insomnia 클레임 판정 분포', fontsize=11, fontweight='bold')

    # SNP별 신뢰도 점수 막대
    snp_ids = [r['snp_id'] for r in res if r['verified_claims']]
    scores  = [r['confidence_score'] for r in res if r['verified_claims']]
    colors_bar = ['#70AD47' if s >= 0.5 else '#FFC000' if s >= 0.2 else '#FF4444' for s in scores]

    axes[1].barh(range(len(snp_ids)), scores, color=colors_bar, alpha=0.85)
    axes[1].set_yticks(range(len(snp_ids)))
    axes[1].set_yticklabels(snp_ids, fontsize=8.5)
    axes[1].set_xlabel('신뢰도 점수', fontsize=10)
    axes[1].set_title('SNP별 신뢰도 점수 (insomnia)', fontsize=11, fontweight='bold')
    axes[1].axvline(0.5, color='gray', linestyle='--', linewidth=1, alpha=0.7)
    axes[1].set_xlim(0, 1)
    axes[1].xaxis.grid(True, alpha=0.3)
    axes[1].set_axisbelow(True)

    fig.suptitle('Step 5 — 자기검증 결과', fontsize=13, fontweight='bold')
    fig.tight_layout()
    fig.savefig(FIGURES / 'fig3_verdict_insomnia.png', bbox_inches='tight')
    plt.close()
    print("✓ fig3_verdict_insomnia.png")


# ──────────────────────────────────────────────────────────────
# Figure 4: Manhattan plot (sleepdur + insomnia)
# ──────────────────────────────────────────────────────────────
def fig_manhattan():
    fig, axes = plt.subplots(2, 1, figsize=(14, 8))

    datasets = [
        ('sleepdur', ROOT / 'dataset' / 'Sleepdur_sumstats_Jansenetal.txt.gz', axes[0]),
        ('insomnia', ROOT / 'dataset' / 'Insomnia_sumstats_Jansenetal.txt.gz', axes[1]),
    ]

    chrom_colors = ['#4472C4', '#70AD47']

    for name, path, ax in datasets:
        print(f"  Manhattan {name} 로딩...")
        df = pd.read_csv(path, sep='\t', compression='gzip',
                         usecols=['CHR', 'BP', 'P'], low_memory=False)
        df = df.dropna(subset=['CHR', 'BP', 'P'])
        df['CHR'] = pd.to_numeric(df['CHR'], errors='coerce')
        df['P']   = pd.to_numeric(df['P'],   errors='coerce')
        df = df.dropna()
        df = df[df['P'] > 0]

        # 비유의 SNP 샘플링 (속도)
        sig   = df[df['P'] < 5e-8]
        nonsig = df[df['P'] >= 5e-8].sample(frac=0.03, random_state=42)
        df = pd.concat([sig, nonsig]).sort_values(['CHR', 'BP'])
        df['-logP'] = -np.log10(df['P'])

        # 염색체별 누적 좌표
        chrom_offsets = {}
        offset = 0
        for chrom in sorted(df['CHR'].unique()):
            chrom_offsets[chrom] = offset
            offset += df[df['CHR'] == chrom]['BP'].max() + 5_000_000
        df['abs_pos'] = df.apply(lambda r: r['BP'] + chrom_offsets[r['CHR']], axis=1)

        for i, chrom in enumerate(sorted(df['CHR'].unique())):
            sub = df[df['CHR'] == chrom]
            color = chrom_colors[i % 2]
            ax.scatter(sub['abs_pos'], sub['-logP'], s=1.5, color=color, alpha=0.6, rasterized=True)

        # 유의성 선
        ax.axhline(-np.log10(5e-8), color='red', linestyle='--', linewidth=0.8, alpha=0.8)
        ax.axhline(-np.log10(1e-5), color='blue', linestyle=':', linewidth=0.6, alpha=0.5)

        # x축 염색체 레이블
        tick_pos = [chrom_offsets[c] + df[df['CHR']==c]['BP'].median()
                    for c in sorted(df['CHR'].unique())]
        ax.set_xticks(tick_pos)
        ax.set_xticklabels([str(int(c)) for c in sorted(df['CHR'].unique())], fontsize=7)
        ax.set_ylabel('-log₁₀(p)', fontsize=10)
        ax.set_title(f'Manhattan Plot — {name}', fontsize=11, fontweight='bold')
        ax.set_xlim(0, offset)

    fig.tight_layout()
    fig.savefig(FIGURES / 'fig4_manhattan.png', bbox_inches='tight', dpi=150)
    plt.close()
    print("✓ fig4_manhattan.png")


if __name__ == '__main__':
    print("그림 생성 중...")
    fig_pipeline()
    fig_evidence()
    fig_verdict()
    fig_manhattan()
    print("\n완료. docs/figures/ 저장됨.")
