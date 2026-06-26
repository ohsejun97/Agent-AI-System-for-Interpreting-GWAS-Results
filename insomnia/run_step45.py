"""
Jansen et al. Insomnia GWAS — Step 4~5
입력: insomnia/results/evidence_results.csv
출력: insomnia/results/interpretation_results.json

실행 전 Ollama 서버가 실행 중이어야 함:
  ollama serve  (이미 실행 중이면 생략)
"""
from pathlib import Path
import pandas as pd
import json
import time
import ollama

BASE = Path(__file__).parent
RESULTS = BASE / 'results'

PHENOTYPE = "insomnia"
MODEL = "qwen2.5:3b"

# ──────────────────────────────────────────────────────────────
# Step 4: LLM 해석 생성
# ──────────────────────────────────────────────────────────────

INTERPRETATION_PROMPT = """당신은 유전체 연구자입니다. 아래 제공된 DB 근거만을 기반으로
SNP와 표현형의 연관성을 해석하세요.

규칙:
1. 제공된 근거에 명시된 내용만 언급하세요 (추측 금지)
2. 각 주장에 근거 출처를 명시하세요 (예: [GWAS Catalog], [Open Targets])
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


def call_llm(prompt: str, label: str = '') -> str:
    try:
        response = ollama.chat(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}]
        )
        return response['message']['content']
    except Exception as e:
        print(f"  Ollama 오류 ({label}): {e}")
        return ''


def generate_interpretation(snp_id: str, evidence_rows: list, phenotype: str) -> dict:
    evidence_json = json.dumps(evidence_rows, ensure_ascii=False, indent=2)
    prompt = INTERPRETATION_PROMPT.format(
        snp_id=snp_id,
        phenotype=phenotype,
        evidence_json=evidence_json
    )
    response_text = call_llm(prompt, '해석')
    if not response_text:
        return {'snp_id': snp_id, 'interpretation': '', 'claims': []}

    import re
    claims = []
    # ### 클레임 목록, [클레임 목록], 클레임 목록: 등 다양한 형식 대응
    marker = re.search(r'(?:#{1,3}\s*|[\[\*]*)클레임\s*목록[\]\*]*\s*:?\n', response_text)
    if marker:
        claim_section = response_text[marker.end():]
        for line in claim_section.strip().split('\n'):
            line = line.strip()
            # 숫자로 시작하는 줄만 클레임으로 인식
            if re.match(r'^\d+[\.\)]\s+', line):
                claims.append(line)
            # 빈 줄 두 번 이상이면 클레임 섹션 종료
            elif not line and claims:
                pass  # 빈 줄은 무시하고 계속

    return {'snp_id': snp_id, 'interpretation': response_text, 'claims': claims}


# ──────────────────────────────────────────────────────────────
# Step 5: 자기검증
# ──────────────────────────────────────────────────────────────

VERIFICATION_PROMPT = """아래 클레임이 제공된 DB 근거에 의해 지지되는지 판정하세요.

클레임: {claim}

DB 근거:
{evidence_json}

판정 형식 (아래 중 하나만 출력):
SUPPORTED - 근거에 명확히 지지됨
PARTIALLY_SUPPORTED - 근거가 일부만 존재
UNSUPPORTED - 근거 없음 또는 근거와 모순

판정:"""


def verify_claims(interpretation_result: dict, evidence_rows: list) -> dict:
    claims = interpretation_result.get('claims', [])
    evidence_json = json.dumps(evidence_rows, ensure_ascii=False, indent=2)
    verified_claims = []

    for claim in claims:
        prompt = VERIFICATION_PROMPT.format(
            claim=claim,
            evidence_json=evidence_json
        )
        verdict_text = call_llm(prompt, '검증')

        if 'SUPPORTED' in verdict_text and 'PARTIALLY' not in verdict_text and 'UN' not in verdict_text:
            verdict = 'SUPPORTED'
        elif 'PARTIALLY' in verdict_text:
            verdict = 'PARTIALLY_SUPPORTED'
        else:
            verdict = 'UNSUPPORTED'

        verified_claims.append({'claim': claim, 'verdict': verdict})

    if verified_claims:
        score = sum(
            1.0 if c['verdict'] == 'SUPPORTED' else
            0.5 if c['verdict'] == 'PARTIALLY_SUPPORTED' else
            0.0
            for c in verified_claims
        ) / len(verified_claims)
    else:
        score = 0.0

    support_rate = (
        sum(1 for c in verified_claims if c['verdict'] == 'SUPPORTED') / len(verified_claims)
        if verified_claims else 0.0
    )

    return {
        'snp_id': interpretation_result['snp_id'],
        'verified_claims': verified_claims,
        'confidence_score': round(score, 3),
        'support_rate': round(support_rate, 3),
    }


# ──────────────────────────────────────────────────────────────
# 메인 실행
# ──────────────────────────────────────────────────────────────

ev = pd.read_csv(RESULTS / 'evidence_results.csv').fillna('')

snp_groups = {}
for _, row in ev.iterrows():
    sid = row['SNP_ID']
    if sid not in snp_groups:
        snp_groups[sid] = []
    snp_groups[sid].append({
        'gene':                  row['gene'],
        'gwas_catalog_traits':   row['gwas_catalog_traits'],
        'open_targets_diseases': row['open_targets_diseases'],
        'open_targets_scores':   row['open_targets_scores'],
    })

snp_list = list(snp_groups.keys())
print(f"[Step 4~5] {len(snp_list)}개 SNP 처리 시작  (표현형: {PHENOTYPE})")
print("=" * 60)

results = []
for i, snp_id in enumerate(snp_list, 1):
    evidence_rows = snp_groups[snp_id]
    genes = list({r['gene'] for r in evidence_rows})
    print(f"\n[{i:2d}/{len(snp_list)}] {snp_id}  유전자: {', '.join(genes)}")

    # Step 4
    print("  [Step 4] 해석 생성...")
    interp = generate_interpretation(snp_id, evidence_rows, PHENOTYPE)
    print(f"  → 클레임 {len(interp['claims'])}개 추출")

    # Step 5
    print("  [Step 5] 자기검증...")
    verif = verify_claims(interp, evidence_rows)

    if verif['confidence_score'] < 0.5 and interp['claims']:
        print("  → 낮은 신뢰도, 재생성 시도...")
        interp = generate_interpretation(snp_id, evidence_rows, PHENOTYPE)
        verif = verify_claims(interp, evidence_rows)

    verdicts = [c['verdict'] for c in verif['verified_claims']]
    s = verdicts.count('SUPPORTED')
    p = verdicts.count('PARTIALLY_SUPPORTED')
    u = verdicts.count('UNSUPPORTED')
    print(f"  ✓ 신뢰도: {verif['confidence_score']:.2f} | "
          f"S:{s} P:{p} U:{u}")

    results.append({
        'snp_id':           snp_id,
        'genes':            genes,
        'interpretation':   interp['interpretation'],
        'claims':           interp['claims'],
        'verified_claims':  verif['verified_claims'],
        'confidence_score': verif['confidence_score'],
        'support_rate':     verif['support_rate'],
    })

out_path = RESULTS / 'interpretation_results.json'
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print("\n" + "=" * 60)
all_verdicts = [c['verdict'] for r in results for c in r['verified_claims']]
total_claims = len(all_verdicts)
s_n = all_verdicts.count('SUPPORTED')
p_n = all_verdicts.count('PARTIALLY_SUPPORTED')
u_n = all_verdicts.count('UNSUPPORTED')
avg_conf = sum(r['confidence_score'] for r in results) / len(results)

print(f"완료: {len(results)}개 SNP")
print(f"전체 클레임: {total_claims}개")
if total_claims > 0:
    print(f"  SUPPORTED:           {s_n} ({s_n/total_claims*100:.1f}%)")
    print(f"  PARTIALLY_SUPPORTED: {p_n} ({p_n/total_claims*100:.1f}%)")
    print(f"  UNSUPPORTED:         {u_n} ({u_n/total_claims*100:.1f}%)")
    print(f"DB 근거 지지율 (S+P): {(s_n+p_n)/total_claims*100:.1f}%")
else:
    print("  클레임 없음 — 프롬프트 또는 API 오류 확인 필요")
print(f"평균 신뢰도 점수:     {avg_conf:.3f}")
print(f"\n✓ {out_path} 저장 완료")
