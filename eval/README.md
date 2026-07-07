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
