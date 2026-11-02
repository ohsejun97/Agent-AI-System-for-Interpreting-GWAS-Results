# final/ — CURT 최종 단계 코드와 결과 (2026-07-24 백업)

Step 4~5(LLM 해석 생성 + 검증)를 Ollama 자기검증에서 **Groq 생성 + Python 규칙 검증**으로 바꾼 최종 단계의 코드와 결과다.
2026-07-24 16:54에 만든 작업 폴더 백업에서 옮겼다. 백업은 이 저장소의 `a94db82` 위에 커밋하지 않은 변경이었다.

## 구성

| 경로 | 내용 |
|---|---|
| `insomnia/run_step45.py` | 백업 시점의 최신 스크립트 (`PIPELINE_VERSION = groq_v4_4_english_robust`) |
| `insomnia/versions/` | 중간 버전 스크립트: `groq_v3`(LLM 검증, 보정), `groq_v4_1`(규칙 검증), `groq_v4_2` |
| `insomnia/results/interpretation_results_verified*.json` | 버전별 검증 결과 (클레임과 판정) |
| `insomnia/results/groq_run_metadata*.json` | 버전별 실행 정보 (모델, 검증 방식, API 요청·토큰 수) |
| `sleepdur/results/evidence_results.csv` | 수면 시간 Step 3 근거 재수집 결과 (최종 단계에서 갱신) |
| `logs/` | Step 1~3 재확인 로그와 Step 4~5 버전별 실행 로그 |

## 불면증 버전별 판정 (클레임 33개, 중간보고는 26개)

| 버전 | 생성 | 검증 | SUPPORTED | 결과 파일 |
|---|---|---|---|---|
| 중간보고 (6/26) | Ollama qwen2.5:3b | 같은 LLM 자기검증 | 1/26 (3.8%) | `../insomnia/results/interpretation_results.json` |
| groq v2 | Groq `openai/gpt-oss-20b` | LLM `llama-3.1-8b-instant`, 보정 없음 | 1/33 (3.0%), PARTIAL 32 | `…_groq_v2_uncalibrated.json` |
| groq v3 | 같음 | LLM `llama-3.1-8b-instant`, 보정 | 12/33 (36.4%) | `…_groq_v3.json` |
| groq v4.1 | 같음 | Python 규칙 `python_rule_v4` | 28/33 (84.8%) | `…_groq_v4_1.json` |
| **최종 v4.3** | 같음 | Python 규칙 `python_rule_v4_english` | **32/33 (97.0%)** | `interpretation_results_verified.json`, `groq_run_metadata.json` |

## 주의
- **97.0%는 정확도가 아니다.** DB 필드와 생성 클레임이 맞는지 규칙으로 대조한 내부 근거 일치율이다. 생물학적으로 맞는지는 재지 않았다.
- 최종 결과(v4.3, 15:40 실행)를 만든 스크립트 원본은 남아 있지 않다. `insomnia/run_step45.py`는 그 5분 뒤 수정한 v4.4이고, v4.4 실행은 Groq 429(요청 한도)로 SNP 11개 중 7번째에서 멈췄다(`logs/insomnia_step45_groq_v4_4_english.log`).
- 수면 시간(49 SNP, 147 클레임, 98.0%)의 Step 4~5 결과 파일은 이 백업에 없다. 최종보고서에만 수치가 있다.
- 실행하려면 `GROQ_API_KEY` 환경변수가 필요하다. 키는 저장소에 없다.
- 로그에 실행 서버의 작업 경로(`/data/ohsejun/...`)가 남아 있다.
