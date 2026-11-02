"""
Jansen et al. Insomnia GWAS — Step 4~5 (Groq v4)

Step 4: 구조화된 근거 기반 초기 해석 생성
Step 5-A: Python 규칙 기반 deterministic claim 검증
Step 5-B: 검증 결과에 따른 최종 해석 교정

입력:
    insomnia/results/evidence_results.csv

출력:
    insomnia/results/interpretation_results_verified.json
    insomnia/results/groq_run_metadata.json
"""

from __future__ import annotations

from pathlib import Path
import json
import os
import random
import re
import time
from typing import Any

import pandas as pd
from groq import Groq


BASE = Path(__file__).parent
RESULTS = BASE / "results"

PHENOTYPE = "insomnia"
GENERATION_MODEL = "openai/gpt-oss-20b"
PIPELINE_VERSION = "groq_v4_3_english_output"

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
# 공통 유틸리티
# ============================================================

def normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[\u2010-\u2015]", "-", text)
    text = re.sub(r"\s+", " ", text)
    return text


def split_pipe(value: Any) -> list[str]:
    return [x.strip() for x in str(value or "").split("|") if x.strip()]


def values_equal(a: Any, b: Any) -> bool:
    return normalize_text(a) == normalize_text(b)


def value_in_list(value: Any, candidates: list[Any]) -> bool:
    target = normalize_text(value)
    return any(normalize_text(x) == target for x in candidates)


def phenotype_matches_trait(phenotype: str, trait: str) -> bool:
    p = normalize_text(phenotype)
    t = normalize_text(trait)
    return bool(p and (p == t or p in t or t in p))


def parse_json_object(text: str) -> dict[str, Any] | None:
    """Markdown fence가 섞여도 첫 JSON object를 복구한다."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(cleaned[start : end + 1])
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None

    return None


def claim_statement_is_complete(statement: str) -> bool:
    s = str(statement or "").strip()
    if len(s) < 12:
        return False
    if s.endswith((".", "다.", "다", "요.", "임.")):
        return True
    return False


def split_pipe_values(value: Any) -> list[str]:
    if value is None:
        return []
    return [part.strip() for part in str(value).split("|") if part.strip()]


def unique_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = normalize_text(value)
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def canonical_claim_statement(claim: dict[str, Any], snp_id: str) -> str:
    ctype = claim.get("claim_type")
    trait = claim.get("trait")
    gene = str(claim.get("gene") or "").strip()
    disease = str(claim.get("disease") or "").strip()
    score = claim.get("score")
    limitation_type = claim.get("limitation_type")

    if ctype == "GWAS_TRAIT":
        traits = unique_values(split_pipe_values(trait))
        joined = " | ".join(traits) if traits else str(trait or "").strip()
        return f"GWAS Catalog reports an association between {snp_id} and {joined}."
    if ctype == "CANDIDATE_GENE":
        return f"{gene} is a candidate gene mapped within ±500 kb of {snp_id}."
    if ctype == "OT_GENE_DISEASE":
        diseases = unique_values(split_pipe_values(disease))
        joined = " | ".join(diseases) if diseases else disease
        return f"Open Targets reports gene–disease associations between {gene} and {joined}."
    if ctype == "OT_GENE_DISEASE_SCORE":
        diseases = split_pipe_values(disease)
        scores = split_pipe_values(score)
        if len(diseases) == len(scores) and diseases:
            pairs = "; ".join(f"{gene}–{d}={sc}" for d, sc in zip(diseases, scores))
            return f"The Open Targets gene–disease association scores are {pairs}."
        return f"The Open Targets gene–disease association score for {gene}–{disease} is {score}."
    if ctype == "LIMITATION":
        messages = {
            "NO_DIRECT_GWAS_FOR_PHENOTYPE": f"The provided GWAS Catalog evidence does not report a direct association between {snp_id} and the target phenotype.",
            "OT_IS_NOT_SNP_DISEASE_EVIDENCE": "Open Targets provides gene–disease association evidence, not direct SNP–disease evidence.",
            "NO_CAUSALITY_ESTABLISHED": "The provided evidence does not establish causality.",
        }
        return messages.get(limitation_type, str(claim.get("statement") or "").strip())
    return str(claim.get("statement") or "").strip()


# ============================================================
# Groq 호출
# ============================================================

def call_llm(
    prompt: str,
    label: str,
    max_tokens: int,
) -> str:
    max_attempts = 3

    for attempt in range(1, max_attempts + 1):
        API_STATS["requests"] += 1

        try:
            response = client.chat.completions.create(
                model=GENERATION_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                reasoning_effort="low",
                max_completion_tokens=max_tokens,
            )

            usage = getattr(response, "usage", None)
            if usage is not None:
                prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
                completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
                total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
                details = getattr(usage, "completion_tokens_details", None)
                reasoning_tokens = (
                    int(getattr(details, "reasoning_tokens", 0) or 0)
                    if details is not None
                    else 0
                )

                API_STATS["prompt_tokens"] += prompt_tokens
                API_STATS["completion_tokens"] += completion_tokens
                API_STATS["reasoning_tokens"] += reasoning_tokens
                API_STATS["total_tokens"] += total_tokens

                print(
                    f"    [Groq] {label} | "
                    f"in={prompt_tokens:,}, out={completion_tokens:,}, "
                    f"reasoning={reasoning_tokens:,}, total={total_tokens:,}"
                )

            content = (response.choices[0].message.content or "").strip()
            if not content:
                API_STATS["empty_response_retries"] += 1
                if attempt < max_attempts:
                    wait_seconds = 2.0 * attempt
                    print(
                        f"    [Groq 빈 응답] {label} | "
                        f"{wait_seconds:.1f}초 후 재시도 ({attempt}/{max_attempts})"
                    )
                    time.sleep(wait_seconds)
                    continue
                API_STATS["failed_requests"] += 1
                return ""

            API_STATS["successful_requests"] += 1

            pacing_tokens = int(getattr(usage, "total_tokens", 0) or 1000)
            wait_seconds = max(1.0, pacing_tokens / 7500.0 * 60.0)
            print(f"    [Groq pacing] {wait_seconds:.1f}초 대기")
            time.sleep(wait_seconds)
            return content

        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            response_obj = getattr(exc, "response", None)
            if status_code is None and response_obj is not None:
                status_code = getattr(response_obj, "status_code", None)

            if status_code == 429:
                API_STATS["rate_limit_retries"] += 1
                headers = getattr(response_obj, "headers", {}) if response_obj else {}
                retry_after = headers.get("retry-after")
                try:
                    wait_seconds = float(retry_after)
                except (TypeError, ValueError):
                    wait_seconds = min(60.0, (2**attempt) + random.uniform(0.5, 2.0))
                wait_seconds = max(10.0, wait_seconds)
                print(
                    f"    [Groq 429] {label} | "
                    f"{wait_seconds:.1f}초 대기 ({attempt}/{max_attempts})"
                )
                time.sleep(wait_seconds)
                continue

            API_STATS["failed_requests"] += 1
            print(f"    Groq API 오류 ({label}) [status={status_code}]: {exc}")
            return ""

    API_STATS["failed_requests"] += 1
    return ""


# ============================================================
# Evidence index
# ============================================================

def build_evidence_index(evidence_rows: list[dict[str, Any]]) -> dict[str, Any]:
    genes: list[str] = []
    all_traits: list[str] = []
    gene_diseases: dict[str, list[str]] = {}
    gene_scores: dict[str, dict[str, str]] = {}

    for row in evidence_rows:
        gene = str(row.get("gene", "")).strip()
        if gene and gene not in genes:
            genes.append(gene)

        traits = split_pipe(row.get("gwas_catalog_traits", ""))
        for trait in traits:
            if trait not in all_traits:
                all_traits.append(trait)

        diseases = split_pipe(row.get("open_targets_diseases", ""))
        scores = split_pipe(row.get("open_targets_scores", ""))

        if gene:
            gene_diseases.setdefault(gene, [])
            gene_scores.setdefault(gene, {})

            for disease in diseases:
                if disease not in gene_diseases[gene]:
                    gene_diseases[gene].append(disease)

            for disease, score in zip(diseases, scores):
                gene_scores[gene][normalize_text(disease)] = score

    return {
        "genes": genes,
        "traits": all_traits,
        "gene_diseases": gene_diseases,
        "gene_scores": gene_scores,
    }


# ============================================================
# Step 4: 구조화된 초기 해석 생성
# ============================================================

INTERPRETATION_PROMPT = r"""
You are a genomics researcher interpreting GWAS results.
Use only the supplied database evidence and return exactly one valid JSON object in English.
Do not output Markdown, code fences, or explanatory text outside the JSON object.

Evidence interpretation rules:
1. gwas_catalog_traits contains GWAS traits reported for the SNP.
2. gene is a positional candidate mapped within ±500 kb of the SNP; it is not established as causal.
3. open_targets_diseases and open_targets_scores are gene–disease associations for the gene in the same row.
4. Do not convert Open Targets gene–disease evidence into direct SNP–disease evidence.
5. Do not interpret an Open Targets score as a SNP effect size, GWAS P-value, or SNP–phenotype association strength.
6. No LD calculation was performed. Do not infer linkage disequilibrium, fine-mapping, mechanisms, pathways, or increased risk.
7. Do not use “nearest gene” or “statistically significant” unless explicitly provided in the evidence.
8. When a value is absent, state only that it is not reported in the provided evidence.
9. Preserve all SNP IDs, gene symbols, trait names, phenotype names, disease names, and numeric scores exactly as provided.
10. Keep the phenotype name “insomnia” exactly as written. Never translate, transliterate, or replace it.

Allowed claim_type values:
- GWAS_TRAIT: requires trait
- CANDIDATE_GENE: requires gene
- OT_GENE_DISEASE: requires gene and disease
- OT_GENE_DISEASE_SCORE: requires gene, disease, and score
- LIMITATION: requires limitation_type

Allowed limitation_type values:
- NO_DIRECT_GWAS_FOR_PHENOTYPE
- OT_IS_NOT_SNP_DISEASE_EVIDENCE
- NO_CAUSALITY_ESTABLISHED

Output schema:
{{
  "interpretation": "A conservative 3–5 sentence interpretation in English",
  "claims": [
    {{
      "claim_type": "one allowed type",
      "statement": "one complete factual sentence in English",
      "trait": null,
      "gene": null,
      "disease": null,
      "score": null,
      "limitation_type": null
    }}
  ]
}}

Requirements:
- Return exactly three claims.
- Each claim must contain one core fact only.
- Copy structured field values from the database evidence as literally as possible.
- Repeating a claim_type is allowed.

SNP: {snp_id}
Target phenotype: {phenotype}
Database evidence: {evidence_json}
"""


def sanitize_claim(raw: dict[str, Any], snp_id: str) -> dict[str, Any]:
    allowed_types = {
        "GWAS_TRAIT",
        "CANDIDATE_GENE",
        "OT_GENE_DISEASE",
        "OT_GENE_DISEASE_SCORE",
        "LIMITATION",
    }

    claim_type = str(raw.get("claim_type", "")).strip().upper()
    if claim_type not in allowed_types:
        claim_type = "INVALID"

    claim = {
        "claim_type": claim_type,
        "statement": str(raw.get("statement", "")).strip(),
        "trait": raw.get("trait"),
        "gene": raw.get("gene"),
        "disease": raw.get("disease"),
        "score": raw.get("score"),
        "limitation_type": (
            str(raw.get("limitation_type", "")).strip().upper()
            if raw.get("limitation_type") is not None
            else None
        ),
    }
    # LLM이 statement에 값만 넣더라도 구조화 필드로 완결문을 재구성합니다.
    claim["statement"] = canonical_claim_statement(claim, snp_id)
    return claim


def generate_interpretation(
    snp_id: str,
    evidence_rows: list[dict[str, Any]],
    phenotype: str,
) -> dict[str, Any]:
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
        label=f"{snp_id} structured interpretation",
        max_tokens=900,
    )
    parsed = parse_json_object(response_text)

    if not parsed:
        return {
            "snp_id": snp_id,
            "initial_interpretation": "",
            "structured_claims": [],
            "raw_generation": response_text,
            "generation_parse_ok": False,
        }

    raw_claims = parsed.get("claims", [])
    claims = [sanitize_claim(x, snp_id) for x in raw_claims if isinstance(x, dict)]
    claims = claims[:3]

    return {
        "snp_id": snp_id,
        "initial_interpretation": str(parsed.get("interpretation", "")).strip(),
        "structured_claims": claims,
        "raw_generation": response_text,
        "generation_parse_ok": len(claims) == 3,
    }


# ============================================================
# Step 5-A: deterministic verifier
# ============================================================

def verify_structured_claim(
    claim: dict[str, Any],
    evidence_index: dict[str, Any],
    phenotype: str,
) -> dict[str, Any]:
    ctype = claim.get("claim_type")
    statement = str(claim.get("statement", ""))

    genes = evidence_index["genes"]
    traits = evidence_index["traits"]
    gene_diseases = evidence_index["gene_diseases"]
    gene_scores = evidence_index["gene_scores"]

    verdict = "UNSUPPORTED"
    reason = "지원되지 않는 claim 유형 또는 근거 불일치입니다."

    if ctype == "GWAS_TRAIT":
        requested_traits = unique_values(split_pipe_values(claim.get("trait")))
        if not requested_traits:
            reason = "검증할 trait 값이 없습니다."
        else:
            exact = [value_in_list(x, traits) for x in requested_traits]
            partial = [
                any(
                    normalize_text(x) in normalize_text(t)
                    or normalize_text(t) in normalize_text(x)
                    for t in traits
                )
                for x in requested_traits
            ]
            if all(exact):
                verdict = "SUPPORTED"
                reason = "모든 trait가 제공된 GWAS Catalog 근거에 정확히 존재합니다."
            elif all(partial):
                verdict = "PARTIALLY_SUPPORTED"
                reason = "모든 trait가 제공 근거와 부분적으로 일치합니다."
            elif any(exact) or any(partial):
                verdict = "PARTIALLY_SUPPORTED"
                reason = "일부 trait만 제공된 GWAS Catalog 근거와 일치합니다."
            else:
                reason = "trait가 제공된 GWAS Catalog 근거에 없습니다."

    elif ctype == "CANDIDATE_GENE":
        gene = str(claim.get("gene") or "").strip()
        if gene and value_in_list(gene, genes):
            verdict = "SUPPORTED"
            reason = "gene이 ±500 kb candidate gene 목록에 존재합니다."
        else:
            reason = "gene이 candidate gene 목록에 없습니다."

    elif ctype == "OT_GENE_DISEASE":
        gene = str(claim.get("gene") or "").strip()
        diseases = unique_values(split_pipe_values(claim.get("disease")))
        matched_gene = next((g for g in genes if values_equal(g, gene)), None)
        if not matched_gene:
            reason = "gene이 candidate gene 목록에 없습니다."
        elif not diseases:
            reason = "검증할 disease 값이 없습니다."
        else:
            available = gene_diseases.get(matched_gene, [])
            exact = [value_in_list(d, available) for d in diseases]
            partial = [
                any(normalize_text(d) in normalize_text(x) or normalize_text(x) in normalize_text(d) for x in available)
                for d in diseases
            ]
            if all(exact):
                verdict = "SUPPORTED"
                reason = "모든 gene-disease 조합이 해당 gene 행에 정확히 존재합니다."
            elif all(partial):
                verdict = "PARTIALLY_SUPPORTED"
                reason = "모든 gene-disease 표현이 부분적으로 일치합니다."
            elif any(exact) or any(partial):
                verdict = "PARTIALLY_SUPPORTED"
                reason = "일부 gene-disease 조합만 해당 gene 행과 일치합니다."
            else:
                reason = "해당 gene의 Open Targets disease에 존재하지 않습니다."

    elif ctype == "OT_GENE_DISEASE_SCORE":
        gene = str(claim.get("gene") or "").strip()
        diseases = split_pipe_values(claim.get("disease"))
        scores = split_pipe_values(claim.get("score"))
        matched_gene = next((g for g in genes if values_equal(g, gene)), None)
        if not matched_gene:
            reason = "gene이 candidate gene 목록에 없습니다."
        elif not diseases or not scores:
            reason = "검증할 disease 또는 score 값이 없습니다."
        elif len(diseases) != len(scores):
            verdict = "PARTIALLY_SUPPORTED"
            reason = f"disease와 score 개수가 다릅니다(disease={len(diseases)}, score={len(scores)})."
        else:
            score_map = gene_scores.get(matched_gene, {})
            pair_results: list[str] = []
            for disease, score in zip(diseases, scores):
                expected = score_map.get(normalize_text(disease))
                if expected is None:
                    pair_results.append("missing")
                    continue
                try:
                    same_score = abs(float(expected) - float(score)) < 1e-9
                except (TypeError, ValueError):
                    same_score = values_equal(expected, score)
                pair_results.append("exact" if same_score else "score_mismatch")

            if pair_results and all(x == "exact" for x in pair_results):
                verdict = "SUPPORTED"
                reason = "모든 gene-disease-score 쌍이 제공 근거에 정확히 일치합니다."
            elif any(x == "exact" for x in pair_results):
                verdict = "PARTIALLY_SUPPORTED"
                reason = "일부 gene-disease-score 쌍만 제공 근거와 정확히 일치합니다."
            elif any(x == "score_mismatch" for x in pair_results):
                verdict = "PARTIALLY_SUPPORTED"
                reason = "gene-disease는 존재하지만 하나 이상의 score가 다릅니다."
            else:
                reason = "해당 gene-disease 조합의 score가 없습니다."

    elif ctype == "LIMITATION":
        limitation_type = claim.get("limitation_type")
        if limitation_type == "NO_DIRECT_GWAS_FOR_PHENOTYPE":
            phenotype_present = any(
                phenotype_matches_trait(phenotype, trait)
                for trait in traits
            )
            if not phenotype_present:
                verdict = "SUPPORTED"
                reason = "제공된 GWAS trait에 분석 대상 phenotype이 없습니다."
            else:
                reason = "제공된 GWAS trait에 분석 대상 phenotype이 존재합니다."
        elif limitation_type == "OT_IS_NOT_SNP_DISEASE_EVIDENCE":
            verdict = "SUPPORTED"
            reason = "Open Targets 근거는 gene-disease association이라는 방법론적 제한입니다."
        elif limitation_type == "NO_CAUSALITY_ESTABLISHED":
            verdict = "SUPPORTED"
            reason = "현재 입력은 위치 매핑 및 DB association이며 인과성을 확립하지 않습니다."
        else:
            reason = "허용되지 않은 limitation_type입니다."

    return {
        **claim,
        "verdict": verdict,
        "verification_reason": reason,
        "verifier": "python_rule_v4_english",
    }


def verify_claims(
    structured_claims: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    phenotype: str,
) -> list[dict[str, Any]]:
    evidence_index = build_evidence_index(evidence_rows)
    return [
        verify_structured_claim(claim, evidence_index, phenotype)
        for claim in structured_claims
    ]


# ============================================================
# Step 5-B: 최종 교정
# ============================================================

CORRECTION_PROMPT = r"""
You are a genomics researcher producing a final evidence-verified GWAS interpretation.
Write entirely in English.

Rules:
1. Retain SUPPORTED claims.
2. Rewrite PARTIALLY_SUPPORTED claims only within the scope supported by verification_reason and the database evidence.
3. Remove UNSUPPORTED claims.
4. Do not describe a positional candidate gene as causal.
5. Do not convert Open Targets gene–disease associations into direct SNP–disease associations.
6. Do not interpret Open Targets scores as SNP effect sizes, GWAS P-values, or SNP–phenotype association strengths.
7. Do not infer LD, fine-mapping, mechanisms, pathways, or increased risk.
8. Do not use “statistically significant” or “nearest gene” unless explicitly present in the evidence.
9. Describe missing evidence only as “not reported in the provided evidence.”
10. Add no new facts.
11. Preserve every SNP ID, gene symbol, trait name, phenotype name, disease name, and numeric score exactly as supplied.
12. Keep the phenotype name “insomnia” exactly as written. Never translate, transliterate, or replace it.

Output only the following format:
[Final verified interpretation]
A conservative interpretation in 3–5 English sentences.

[Final claims]
1. Retained English claim
2. Retained English claim
3. Retained English claim

SNP: {snp_id}
Target phenotype: {phenotype}
Initial interpretation: {initial_interpretation}
Verified structured claims: {verified_claims_json}
Database evidence: {evidence_json}
"""


def generate_corrected_interpretation(
    snp_id: str,
    initial_interpretation: str,
    verified_claims: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    phenotype: str,
) -> str:
    prompt = CORRECTION_PROMPT.format(
        snp_id=snp_id,
        phenotype=phenotype,
        initial_interpretation=initial_interpretation,
        verified_claims_json=json.dumps(
            verified_claims,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        evidence_json=json.dumps(
            evidence_rows,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    )

    return call_llm(
        prompt,
        label=f"{snp_id} correction",
        max_tokens=700,
    )


# ============================================================
# 메인 실행
# ============================================================

ev = pd.read_csv(RESULTS / "evidence_results.csv").fillna("")

snp_groups: dict[str, list[dict[str, Any]]] = {}
for _, row in ev.iterrows():
    sid = str(row["SNP_ID"])
    snp_groups.setdefault(sid, []).append(
        {
            "gene": row["gene"],
            "gwas_catalog_traits": row["gwas_catalog_traits"],
            "open_targets_diseases": row["open_targets_diseases"],
            "open_targets_scores": row["open_targets_scores"],
        }
    )

snp_list = list(snp_groups.keys())
print(f"[Step 4~5 v4.3 English] {len(snp_list)}개 SNP 처리 시작 (표현형: {PHENOTYPE})")
print("=" * 70)

results: list[dict[str, Any]] = []

for i, snp_id in enumerate(snp_list, 1):
    evidence_rows = snp_groups[snp_id]
    genes = list(dict.fromkeys(r["gene"] for r in evidence_rows if r["gene"]))

    print(f"\n[{i:2d}/{len(snp_list)}] {snp_id} | genes: {', '.join(genes)}")

    print("  [Step 4] 구조화 초기 해석 생성")
    interp = generate_interpretation(snp_id, evidence_rows, PHENOTYPE)
    structured_claims = interp["structured_claims"]
    print(
        f"  → 구조화 클레임: {len(structured_claims)}개 | "
        f"JSON parse={'OK' if interp['generation_parse_ok'] else 'FAIL'}"
    )

    print("  [Step 5-A] Python 규칙 기반 검증")
    verified_claims = verify_claims(structured_claims, evidence_rows, PHENOTYPE)
    verdicts = [x["verdict"] for x in verified_claims]
    s = verdicts.count("SUPPORTED")
    p = verdicts.count("PARTIALLY_SUPPORTED")
    u = verdicts.count("UNSUPPORTED")
    print(f"  → S:{s} P:{p} U:{u}")
    for claim in verified_claims:
        print(
            f"    - {claim['verdict']}: {claim['statement']} "
            f"[{claim['verification_reason']}]"
        )

    print("  [Step 5-B] 검증 결과 기반 최종 해석 생성")
    corrected = generate_corrected_interpretation(
        snp_id,
        interp["initial_interpretation"],
        verified_claims,
        evidence_rows,
        PHENOTYPE,
    )

    total_claims = len(verified_claims)
    support_rate = (s + p) / total_claims if total_claims else 0.0
    strict_support_rate = s / total_claims if total_claims else 0.0
    unsupported_rate = u / total_claims if total_claims else 0.0
    confidence_score = (s + 0.5 * p) / total_claims if total_claims else 0.0

    results.append(
        {
            "snp_id": snp_id,
            "genes": genes,
            "evidence": evidence_rows,
            "initial_interpretation": interp["initial_interpretation"],
            "structured_claims": structured_claims,
            "verified_claims": verified_claims,
            "verified_interpretation": corrected,
            "generation_parse_ok": interp["generation_parse_ok"],
            "statistics": {
                "n_claims": total_claims,
                "supported": s,
                "partially_supported": p,
                "unsupported": u,
                "strict_support_rate": round(strict_support_rate, 3),
                "evidence_support_rate": round(support_rate, 3),
                "unsupported_rate": round(unsupported_rate, 3),
                "confidence_score": round(confidence_score, 3),
            },
        }
    )


# ============================================================
# 저장 및 요약
# ============================================================

out_path = RESULTS / "interpretation_results_verified.json"
with out_path.open("w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

all_verdicts = [
    claim["verdict"]
    for result in results
    for claim in result["verified_claims"]
]
total = len(all_verdicts)
s_total = all_verdicts.count("SUPPORTED")
p_total = all_verdicts.count("PARTIALLY_SUPPORTED")
u_total = all_verdicts.count("UNSUPPORTED")
parse_ok_total = sum(bool(x["generation_parse_ok"]) for x in results)

print("\n" + "=" * 70)
print(f"완료 SNP: {len(results)}")
print(f"구조화 JSON 정상: {parse_ok_total}/{len(results)}")
print(f"전체 초기 클레임: {total}")
if total:
    print(f"SUPPORTED: {s_total} ({s_total / total * 100:.1f}%)")
    print(f"PARTIALLY_SUPPORTED: {p_total} ({p_total / total * 100:.1f}%)")
    print(f"UNSUPPORTED: {u_total} ({u_total / total * 100:.1f}%)")
    print(f"초기 claim DB 근거 지지율 (S+P): {(s_total + p_total) / total * 100:.1f}%")
    print(f"초기 claim unsupported rate: {u_total / total * 100:.1f}%")
print(f"\n저장 완료: {out_path}")

run_metadata = {
    "provider": "Groq",
    "generation_model": GENERATION_MODEL,
    "verification_model": "python_rule_v4_english",
    "phenotype": PHENOTYPE,
    "temperature": 0.0,
    "pipeline_version": PIPELINE_VERSION,
    "generation_reasoning_effort": "low",
    "generation_max_completion_tokens": {
        "structured_interpretation": 900,
        "correction": 700,
    },
    "api_statistics": API_STATS,
    "deterministic_verification": True,
    "output_language": "English",
    "structured_json_ok": parse_ok_total,
    "n_snps": len(results),
}

metadata_path = RESULTS / "groq_run_metadata.json"
with metadata_path.open("w", encoding="utf-8") as f:
    json.dump(run_metadata, f, ensure_ascii=False, indent=2)

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
