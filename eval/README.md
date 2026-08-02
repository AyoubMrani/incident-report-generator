# eval — retrieval evaluation & analysis

Quantitative evaluation of the chatbot's retrieval component, for the thesis
"experiments" chapter. Everything here is reproducible from the reports in
`../reports/`.

## Run it

```bash
cd eval
python make_eval_set.py        # -> eval_set.json (labeled queries)
python benchmark_retrieval.py  # Recall@k / MRR / nDCG: vector vs bm25 vs hybrid
python ablations.py            # chunk_size and top_k sensitivity
python error_analysis.py       # where hybrid fails and why
python corpus_eda.py           # corpus stats + figures/*.png

# or the whole thing as a notebook:
python build_notebook.py       # generates evaluation.ipynb
jupyter nbconvert --to notebook --execute --inplace evaluation.ipynb
```

## Files

| File | Produces |
|---|---|
| `make_eval_set.py` | `eval_set.json` — 119 labeled queries (4 styles) over 30 reports |
| `benchmark_retrieval.py` | retrieval metrics table (the headline result) |
| `ablations.py` | hyperparameter sensitivity tables |
| `error_analysis.py` | failure breakdown by style/cause |
| `corpus_eda.py` | descriptive stats + `figures/*.png` |
| `ask.py` | one question -> the parsed answer, for manual testing |
| `live_check.py` | end-to-end checks against the **real** model |
| `model_bench.py` | compare generation models on quality and latency |

## Choosing the generation model

`model_bench.py` drives the whole pipeline — same retrieval, same prompt, same
grounding rules — and varies only which model generates, so the comparison is
about the model rather than the plumbing. It scores properties an answer needs
to be useful (grounded steps, right report cited, a runnable artifact, no
cross-incident contamination, a real root cause), never wording.

```bash
python eval/model_bench.py                     # 3b vs 8b
python eval/model_bench.py --models llama3:8b  # one model
python eval/model_bench.py --repeat 3          # stability
```

Latest run (5 incident questions, M4 / 17 GB), in `model_bench_results.json`:

| model | quality | mean confidence | median latency |
|---|---|---|---|
| `llama3.2:3b` | 21/25 | 87.0% | **28.6s** |
| `llama3:8b` | 22/25 | 92.0% | 75.7s |

8b buys one extra check out of 25 for 2.6x the latency, and is not uniformly
better — it scored *lower* on "database connection pool exhausted" (80% vs
90%). Both produced the same number of steps on four of five questions, which
says retrieval and grounding are doing the work, not model size. `3b` stays the
default; `OLLAMA_MODEL=llama3:8b docker compose up -d` switches it with no
rebuild.

## Two kinds of testing, and why both exist

`backend/tests/` (pytest, 207 tests) swaps in a **fake** LLM provider. That is
the right call for plumbing — parsing, gates, caching, grounding rules — and it
keeps the suite fast and deterministic. But it means the suite structurally
cannot see how `llama3.2:3b` actually behaves.

Every bug that has actually hurt this project was a *model-behaviour* bug that
only showed up when a human ran a query by hand:

* a command documented in one incident bleeding into an unrelated answer
* `SELECT ...` rendered as if it were a runnable query
* 40% confidence on a question the corpus answers in full
* "thanks, that helped" triggering a corpus search

`live_check.py` closes that gap. It drives the running server over HTTP with the
real model and asserts on properties that hold regardless of how the model
samples — never on exact wording, which would flake every run.

```bash
python eval/live_check.py                # all cases (~2-3 min)
python eval/live_check.py -k rollback    # just one
python eval/live_check.py --json out.json
```

Exit status is 0 only if every case passes. Add a case whenever you find a bad
answer by hand — that is how a manual finding becomes a permanent check.
| `build_notebook.py` | `evaluation.ipynb` presenting all of the above |

## Headline result (reproduced)

| config | Recall@5 | MRR | nDCG@5 |
|---|---|---|---|
| vector | 0.706 | 0.598 | 0.625 |
| bm25 | 0.916 | 0.791 | 0.822 |
| **hybrid (shipped)** | **0.941** | **0.916** | **0.923** |

Hybrid wins because it covers both regimes: dense retrieval handles paraphrased
symptom/title queries, BM25 handles exact identifiers (where dense recall drops
to 0.30). See the notebook for the full breakdown, ablations, and error analysis.

## Caveat (state in the report)

Queries are **auto-generated** from the reports (paraphrase → source report), a
reproducible proxy since no real query logs exist. Real queries are noisier;
these numbers are an optimistic bound. `eval_set.json` is editable by hand if you
want to add real queries.
