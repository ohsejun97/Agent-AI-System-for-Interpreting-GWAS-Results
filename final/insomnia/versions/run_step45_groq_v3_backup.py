"""
Jansen et al. Insomnia GWAS — Step 4~5
Step 4: Evidence-grounded initial interpretation
Step 5: Claim-level self-verification + corrected final interpretation

입력:
    insomnia/results/evidence_results.csv

출력:
    insomnia/results/interpretation_results_verified.json
"""

from pathlib import Path
import json
import os
import random
import re
import time

import pandas as pd
from groq import Groq


BASE = Path(__file__).parent
RESULTS = BASE / "results"

PHENOTYPE = "insomnia"
GENERATION_MODEL = "openai/gpt-oss-20b"
VERIFICATION_MODEL = "llama-3.1-8b-instant"

if not os.getenv("GROQ_API_KEY"):
    raise RuntimeError(
        "GROQ_API_KEY 환경변수가 없습니다. "
        "먼저 API 키를 export한 뒤 다시 실행하세요."
    )

client = Groq(
    api_key=os.environ["GROQ_API_KEY"],
    timeout=90.0,
    max_retries=0,
)

API_STATS = {
    "requests": 0,
    "successful_requests": 0,
    "failed_requests": 0,
    "rate_limit_retries": 0,
    "empty_response_retries": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "reasoning_tokens": 0,
    "total_tokens": 0,
}


# ============================================================
# 공통 LLM 호출
# ============================================================

def call_llm(
    prompt: str,
    label: str = "",
    max_tokens: int = 512,
    model: str = GENERATION_MODEL,
    use_reasoning: bool = True,
    stop_sequences: list[str] | None = None,
) -> str:
    """
    Groq API 호출.

    무료 토큰 절약 설정:
    - reasoning_effort="low"
    - 작업별 max_completion_tokens 차등 적용
    - temperature=0
    - 429 및 빈 응답만 제한적으로 재시도
    """

    max_attempts = 3

    for attempt in range(1, max_attempts + 1):
        API_STATS["requests"] += 1

        try:
            request_kwargs = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                "temperature": 0.0,
                "max_completion_tokens": max_tokens,
            }
            if use_reasoning:
                request_kwargs["reasoning_effort"] = "low"
            if stop_sequences:
                request_kwargs["stop"] = stop_sequences

            response = client.chat.completions.create(**request_kwargs)

            usage = getattr(response, "usage", None)

            if usage is not None:
                prompt_tokens = int(
                    getattr(usage, "prompt_tokens", 0) or 0
                )
                completion_tokens = int(
                    getattr(usage, "completion_tokens", 0) or 0
                )
                total_tokens = int(
                    getattr(usage, "total_tokens", 0) or 0
                )

                details = getattr(
                    usage,
                    "completion_tokens_details",
                    None,
                )
                reasoning_tokens = (
                    int(
                        getattr(
                            details,
                            "reasoning_tokens",
                            0,
                        )
                        or 0
                    )
                    if details is not None
                    else 0
                )

                API_STATS["prompt_tokens"] += prompt_tokens
                API_STATS["completion_tokens"] += completion_tokens
                API_STATS["reasoning_tokens"] += reasoning_tokens
                API_STATS["total_tokens"] += total_tokens

                print(
                    f"    [Groq] {label} | "
                    f"in={prompt_tokens:,}, "
                    f"out={completion_tokens:,}, "
                    f"reasoning={reasoning_tokens:,}, "
                    f"total={total_tokens:,}"
                )

            content = (
                response.choices[0].message.content
                or ""
            ).strip()

            if not content:
                API_STATS["empty_response_retries"] += 1

                if attempt < max_attempts:
                    wait_seconds = min(
                        20.0,
                        2.0 * attempt,
                    )
                    print(
                        f"    [Groq 빈 응답] {label} | "
                        f"{wait_seconds:.1f}초 후 재시도 "
                        f"({attempt}/{max_attempts})"
                    )
                    time.sleep(wait_seconds)
                    continue

                API_STATS["failed_requests"] += 1
                return ""

            API_STATS["successful_requests"] += 1

            # 모델별 무료 TPM 한도에 여유를 둔 동적 간격.
            pacing_tokens = (
                int(getattr(usage, "total_tokens", 0) or 0)
                if usage is not None
                else 1000
            )
            safe_tpm = (
                5500.0
                if model == VERIFICATION_MODEL
                else 7500.0
            )
            wait_seconds = max(
                1.0,
                pacing_tokens / safe_tpm * 60.0,
            )
            print(
                f"    [Groq pacing] {wait_seconds:.1f}초 대기"
            )
            time.sleep(wait_seconds)

            return content

        except Exception as exc:
            status_code = getattr(
                exc,
                "status_code",
                None,
            )
            response_obj = getattr(
                exc,
                "response",
                None,
            )

            if (
                status_code is None
                and response_obj is not None
            ):
                status_code = getattr(
                    response_obj,
                    "status_code",
                    None,
                )

            if status_code == 429:
                API_STATS["rate_limit_retries"] += 1

                headers = (
                    getattr(
                        response_obj,
                        "headers",
                        {},
                    )
                    if response_obj is not None
                    else {}
                )

                retry_after = headers.get("retry-after")

                try:
                    wait_seconds = float(retry_after)
                except (TypeError, ValueError):
                    wait_seconds = min(
                        60.0,
                        (2 ** attempt)
                        + random.uniform(0.5, 2.0),
                    )

                wait_seconds = max(
                    10.0,
                    wait_seconds,
                )

                print(
                    f"    [Groq 429] {label} | "
                    f"{wait_seconds:.1f}초 대기 "
                    f"({attempt}/{max_attempts})"
                )

                time.sleep(wait_seconds)
                continue

            API_STATS["failed_requests"] += 1
            print(
                f"    Groq API 오류 ({label}) "
                f"[status={status_code}]: {exc}"
            )
            return ""

    API_STATS["failed_requests"] += 1
    print(f"    Groq API 재시도 한도 초과 ({label})")
    return ""


# ============================================================
# Step 4: 초기 해석 생성
# ============================================================

INTERPRETATION_PROMPT = """
당신은 GWAS 결과를 해석하는 유전체 연구자입니다.

아래 SNP에 대해 제공된 데이터베이스 근거만 사용하여
간결하고 과학적으로 보수적인 초기 해석을 작성하세요.

중요한 근거 해석 규칙:

1. GWAS Catalog의 trait 정보는 해당 SNP와 보고된 phenotype 간의
   직접적인 GWAS association evidence로 취급할 수 있습니다.

2. 여기서 제공되는 gene은 해당 SNP 주변 ±500 kb에서 매핑된
   candidate gene입니다.
   이 정보만으로 해당 gene이 causal gene이라고 단정할 수 없습니다.

3. Open Targets의 disease 정보는 해당 gene과 disease 간의
   target-disease association입니다.

4. Open Targets의 gene-disease association을
   SNP-disease 직접 연관으로 표현하면 안 됩니다.

5. Open Targets score는 gene-disease association score이며,
   SNP effect size, GWAS P-value 또는 SNP-phenotype association strength가 아닙니다.

6. 제공되지 않은 biological mechanism이나 causal relationship을
   추측하지 마세요.

SNP:
{snp_id}

분석 대상 표현형:
{phenotype}

DB 근거:
{evidence_json}

먼저 전체 해석을 작성하세요.

그 다음 반드시 아래 형식으로,
DB 근거와 직접 대조할 수 있는 개별 클레임만 작성하세요.

[클레임 목록]
1. 구체적인 단일 주장
2. 구체적인 단일 주장
3. 구체적인 단일 주장

각 클레임에는 한 가지 핵심 주장만 포함하세요.
클레임은 정확히 3개 작성하고, 각 문장은 마침표로 끝나는 완결문이어야 합니다.
전체 해석은 5문장 이내로 간결하게 작성하세요.
"""


def extract_claims(response_text: str) -> list[str]:

    marker = re.search(
        r"(?:#{1,3}\s*|[\[\*]*)클레임\s*목록[\]\*]*\s*:?\s*\n",
        response_text,
        flags=re.IGNORECASE,
    )

    if not marker:
        return []

    claim_section = response_text[marker.end():]

    claims = []

    for line in claim_section.splitlines():

        line = line.strip()

        match = re.match(r"^\d+[\.\)]\s*(.+)", line)

        if match:
            claim = match.group(1).strip()

            if claim:
                claims.append(claim)

    return claims


def generate_interpretation(
    snp_id: str,
    evidence_rows: list,
    phenotype: str,
) -> dict:

    evidence_json = json.dumps(
        evidence_rows,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    prompt = INTERPRETATION_PROMPT.format(
        snp_id=snp_id,
        phenotype=phenotype,
        evidence_json=evidence_json,
    )

    response_text = call_llm(
        prompt,
        label=f"{snp_id} initial interpretation",
        max_tokens=768,
    )

    if not response_text:

        return {
            "snp_id": snp_id,
            "initial_interpretation": "",
            "initial_claims": [],
        }

    claims = extract_claims(response_text)

    return {
        "snp_id": snp_id,
        "initial_interpretation": response_text,
        "initial_claims": claims,
    }


# ============================================================
# Step 5-A: Claim-level verification
# ============================================================

VERIFICATION_PROMPT = """
당신은 GWAS 해석 claim을 제공된 DB 근거와 대조하는 분류기입니다.
설명하지 말고 반드시 첫 줄에 아래 셋 중 하나만 출력하세요.

SUPPORTED
PARTIALLY_SUPPORTED
UNSUPPORTED

판정 기준:

SUPPORTED
- claim의 핵심 주어, 관계, 객체가 DB 근거에 명시적으로 존재합니다.
- GWAS Catalog trait를 해당 SNP-trait의 보고된 GWAS association으로 표현한 경우입니다.
- gene을 ±500 kb 위치 기반 candidate gene으로 정확히 표현한 경우입니다.
- Open Targets disease를 해당 gene-disease association으로 정확히 표현한 경우입니다.
- 인과성이나 SNP-disease 직접 연관을 추가하지 않은 정확한 제한 문장도 포함합니다.

PARTIALLY_SUPPORTED
- 핵심 사실은 근거에 있지만 일부 표현이 더 강하거나 넓습니다.
- "제공된 근거에서 확인되지 않는다"가 아니라 전 세계적으로 증거가 없다고 단정합니다.
- candidate gene을 단순히 SNP의 gene이라고 표현하지만 causal gene이라고까지 단정하지는 않습니다.
- 하나의 claim에 여러 사실이 섞여 일부만 일치합니다.

UNSUPPORTED
- 핵심 관계가 DB 근거에 없습니다.
- gene-disease association을 SNP-disease 직접 association으로 바꿉니다.
- Open Targets score를 SNP effect size나 SNP-phenotype association strength로 해석합니다.
- causal mechanism, 기능 또는 인과성을 새로 추가합니다.
- 문장이 잘리거나 의미가 완결되지 않아 검증할 수 없습니다.

교정 예시 1:
근거: GWAS trait = Insomnia
claim: "rsX는 GWAS Catalog에서 insomnia와 연관된 SNP로 보고되었다."
정답: SUPPORTED

교정 예시 2:
근거: candidate gene = GENE1
claim: "rsX 주변 ±500 kb에 GENE1이 candidate gene으로 매핑된다."
정답: SUPPORTED

교정 예시 3:
근거: GENE1 Open Targets disease = insomnia
claim: "GENE1은 Open Targets에서 insomnia와 gene-disease association을 보인다."
정답: SUPPORTED

교정 예시 4:
근거: GENE1 Open Targets disease = insomnia
claim: "rsX는 Open Targets에서 insomnia와 직접 연관된다."
정답: UNSUPPORTED

교정 예시 5:
근거: 제공된 GWAS traits에 insomnia 없음
claim: "현재 제공된 DB 근거에서는 rsX-insomnia 직접 GWAS association이 확인되지 않는다."
정답: SUPPORTED

교정 예시 6:
근거: 제공된 GWAS traits에 insomnia 없음
claim: "rsX와 insomnia 사이에는 어떠한 GWAS 근거도 존재하지 않는다."
정답: PARTIALLY_SUPPORTED

SNP: {snp_id}
분석 대상 표현형: {phenotype}
검증 대상 claim: {claim}
DB 근거: {evidence_json}

첫 줄에 판정 단어 하나만 출력하세요.
"""


def parse_verdict(text: str) -> str:
    first_line = text.strip().splitlines()[0].strip().upper() if text.strip() else ""
    first_line = re.sub(r"[^A-Z_]", "", first_line)

    if first_line == "SUPPORTED":
        return "SUPPORTED"
    if first_line == "PARTIALLY_SUPPORTED":
        return "PARTIALLY_SUPPORTED"
    if first_line == "UNSUPPORTED":
        return "UNSUPPORTED"

    return "INVALID"


def verify_claims(
    snp_id: str,
    claims: list[str],
    evidence_rows: list,
    phenotype: str,
) -> list[dict]:

    evidence_json = json.dumps(
        evidence_rows,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    verified = []

    for claim in claims:

        prompt = VERIFICATION_PROMPT.format(
            snp_id=snp_id,
            phenotype=phenotype,
            claim=claim,
            evidence_json=evidence_json,
        )

        verdict_text = call_llm(
            prompt,
            label=f"{snp_id} verification",
            max_tokens=16,
            model=VERIFICATION_MODEL,
            use_reasoning=False,
            stop_sequences=["\n"],
        )

        verdict = parse_verdict(verdict_text)

        if verdict == "INVALID":
            print(
                f"    [검증 형식 오류] {snp_id} | "
                f"raw={verdict_text!r}; UNSUPPORTED로 기록"
            )
            verdict = "UNSUPPORTED"

        verified.append(
            {
                "claim": claim,
                "verdict": verdict,
                "raw_verdict": verdict_text,
            }
        )

    return verified


# ============================================================
# Step 5-B: 검증 결과 기반 최종 해석 재작성
# ============================================================

CORRECTION_PROMPT = """
당신은 GWAS 해석 결과를 최종 교정하는 유전체 연구자입니다.

아래 초기 해석과 claim 검증 결과를 이용하여
근거가 검증된 최종 해석을 작성하세요.

교정 규칙:

1. SUPPORTED claim은 유지할 수 있습니다.

2. PARTIALLY_SUPPORTED claim은
   DB 근거가 실제로 지지하는 범위까지만 표현을 완화하세요.

3. UNSUPPORTED claim은 최종 해석에서 제거하세요.

4. SNP 주변 candidate gene을 causal gene으로 단정하지 마세요.

5. Open Targets gene-disease association을
   SNP-disease 직접 association으로 표현하지 마세요.

6. Open Targets score를
   SNP association strength 또는 SNP effect size로 해석하지 마세요.

7. 근거가 부족한 경우에는
   "현재 수집된 근거만으로 직접적인 연관성을 확정하기 어렵다"
   와 같이 명확하게 제한점을 표현하세요.

8. 새로운 사실이나 새로운 biological mechanism을 추가하지 마세요.


SNP:
{snp_id}

분석 대상 표현형:
{phenotype}

초기 해석:
{initial_interpretation}

검증된 클레임:
{verified_claims_json}

DB 근거:
{evidence_json}


최종 결과는 아래 두 부분으로 작성하세요.

[최종 검증 해석]
검증을 통과한 근거만 사용한 최종 해석

[최종 클레임]
1. 최종적으로 유지된 주장
2. 최종적으로 유지된 주장
"""


def generate_corrected_interpretation(
    snp_id: str,
    initial_interpretation: str,
    verified_claims: list[dict],
    evidence_rows: list,
    phenotype: str,
) -> str:

    evidence_json = json.dumps(
        evidence_rows,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    verified_claims_json = json.dumps(
        verified_claims,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    prompt = CORRECTION_PROMPT.format(
        snp_id=snp_id,
        phenotype=phenotype,
        initial_interpretation=initial_interpretation,
        verified_claims_json=verified_claims_json,
        evidence_json=evidence_json,
    )

    return call_llm(
        prompt,
        label=f"{snp_id} correction",
        max_tokens=768,
    )


# ============================================================
# 메인 실행
# ============================================================

ev = pd.read_csv(
    RESULTS / "evidence_results.csv"
).fillna("")


# SNP별 evidence grouping
snp_groups = {}

for _, row in ev.iterrows():

    sid = row["SNP_ID"]

    if sid not in snp_groups:
        snp_groups[sid] = []

    snp_groups[sid].append(
        {
            "gene": row["gene"],
            "gwas_catalog_traits": row["gwas_catalog_traits"],
            "open_targets_diseases": row["open_targets_diseases"],
            "open_targets_scores": row["open_targets_scores"],
        }
    )


snp_list = list(snp_groups.keys())

print(
    f"[Step 4~5] {len(snp_list)}개 SNP 처리 시작 "
    f"(표현형: {PHENOTYPE})"
)

print("=" * 70)


results = []


for i, snp_id in enumerate(snp_list, 1):

    evidence_rows = snp_groups[snp_id]

    genes = list(
        dict.fromkeys(
            r["gene"]
            for r in evidence_rows
            if r["gene"]
        )
    )

    print(
        f"\n[{i:2d}/{len(snp_list)}] "
        f"{snp_id} | genes: {', '.join(genes)}"
    )


    # --------------------------------------------------------
    # Step 4
    # --------------------------------------------------------

    print("  [Step 4] 초기 해석 생성")

    interp = generate_interpretation(
        snp_id,
        evidence_rows,
        PHENOTYPE,
    )

    initial_claims = interp["initial_claims"]

    print(
        f"  → 초기 클레임: "
        f"{len(initial_claims)}개"
    )


    # --------------------------------------------------------
    # Step 5-A
    # --------------------------------------------------------

    print("  [Step 5-A] 클레임 검증")

    verified_claims = verify_claims(
        snp_id,
        initial_claims,
        evidence_rows,
        PHENOTYPE,
    )


    verdicts = [
        x["verdict"]
        for x in verified_claims
    ]

    s = verdicts.count("SUPPORTED")
    p = verdicts.count("PARTIALLY_SUPPORTED")
    u = verdicts.count("UNSUPPORTED")


    print(
        f"  → S:{s} "
        f"P:{p} "
        f"U:{u}"
    )


    # --------------------------------------------------------
    # Step 5-B
    # --------------------------------------------------------

    print(
        "  [Step 5-B] "
        "검증 결과 기반 최종 해석 생성"
    )

    corrected = generate_corrected_interpretation(
        snp_id,
        interp["initial_interpretation"],
        verified_claims,
        evidence_rows,
        PHENOTYPE,
    )


    # --------------------------------------------------------
    # 통계
    # --------------------------------------------------------

    total_claims = len(verified_claims)

    support_rate = (
        (s + p) / total_claims
        if total_claims
        else 0.0
    )

    strict_support_rate = (
        s / total_claims
        if total_claims
        else 0.0
    )

    unsupported_rate = (
        u / total_claims
        if total_claims
        else 0.0
    )

    confidence_score = (
        (
            s * 1.0
            + p * 0.5
        )
        / total_claims
        if total_claims
        else 0.0
    )


    results.append(
        {
            "snp_id": snp_id,

            "genes": genes,

            "evidence": evidence_rows,

            "initial_interpretation":
                interp["initial_interpretation"],

            "initial_claims":
                initial_claims,

            "verified_claims":
                verified_claims,

            "verified_interpretation":
                corrected,

            "statistics": {
                "n_claims":
                    total_claims,

                "supported":
                    s,

                "partially_supported":
                    p,

                "unsupported":
                    u,

                "strict_support_rate":
                    round(
                        strict_support_rate,
                        3,
                    ),

                "evidence_support_rate":
                    round(
                        support_rate,
                        3,
                    ),

                "unsupported_rate":
                    round(
                        unsupported_rate,
                        3,
                    ),

                "confidence_score":
                    round(
                        confidence_score,
                        3,
                    ),
            },
        }
    )


# ============================================================
# 저장
# ============================================================

out_path = (
    RESULTS
    / "interpretation_results_verified.json"
)

with open(
    out_path,
    "w",
    encoding="utf-8",
) as f:

    json.dump(
        results,
        f,
        ensure_ascii=False,
        indent=2,
    )


# ============================================================
# 전체 통계
# ============================================================

all_verdicts = [
    c["verdict"]
    for result in results
    for c in result["verified_claims"]
]


total = len(all_verdicts)

s_total = all_verdicts.count(
    "SUPPORTED"
)

p_total = all_verdicts.count(
    "PARTIALLY_SUPPORTED"
)

u_total = all_verdicts.count(
    "UNSUPPORTED"
)


print("\n" + "=" * 70)

print(
    f"완료 SNP: "
    f"{len(results)}"
)

print(
    f"전체 초기 클레임: "
    f"{total}"
)


if total:

    print(
        f"SUPPORTED: "
        f"{s_total} "
        f"({s_total / total * 100:.1f}%)"
    )

    print(
        f"PARTIALLY_SUPPORTED: "
        f"{p_total} "
        f"({p_total / total * 100:.1f}%)"
    )

    print(
        f"UNSUPPORTED: "
        f"{u_total} "
        f"({u_total / total * 100:.1f}%)"
    )

    print(
        "초기 claim DB 근거 지지율 "
        f"(S+P): "
        f"{(s_total + p_total) / total * 100:.1f}%"
    )

    print(
        "초기 claim unsupported rate: "
        f"{u_total / total * 100:.1f}%"
    )


print(
    f"\n저장 완료: "
    f"{out_path}"
)

# Groq 실행 메타데이터 저장
metadata_path = RESULTS / "groq_run_metadata.json"

run_metadata = {
    "provider": "Groq",
    "generation_model": GENERATION_MODEL,
    "verification_model": VERIFICATION_MODEL,
    "phenotype": PHENOTYPE,
    "temperature": 0.0,
    "pipeline_version": "groq_v3_calibrated",
    "generation_reasoning_effort": "low",
    "verification_reasoning_effort": None,
    "generation_max_completion_tokens": 768,
    "verification_max_completion_tokens": 16,
    "verification_stop": ["\n"],
    "api_statistics": API_STATS,
}

with open(
    metadata_path,
    "w",
    encoding="utf-8",
) as f:
    json.dump(
        run_metadata,
        f,
        ensure_ascii=False,
        indent=2,
    )

print("\n===== Groq API 사용량 =====")
print(f"전체 요청 시도: {API_STATS['requests']}")
print(f"성공 요청:      {API_STATS['successful_requests']}")
print(f"실패 요청:      {API_STATS['failed_requests']}")
print(f"429 재시도:     {API_STATS['rate_limit_retries']}")
print(f"빈 응답 재시도: {API_STATS['empty_response_retries']}")
print(f"입력 토큰:      {API_STATS['prompt_tokens']:,}")
print(f"출력 토큰:      {API_STATS['completion_tokens']:,}")
print(f"추론 토큰:      {API_STATS['reasoning_tokens']:,}")
print(f"전체 토큰:      {API_STATS['total_tokens']:,}")
print(f"메타데이터:     {metadata_path}")
