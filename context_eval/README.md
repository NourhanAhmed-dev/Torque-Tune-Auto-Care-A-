# Context Evaluation

This folder contains the implementation and evaluation of four context window management strategies used to compare different approaches for handling long conversations.

The benchmark follows the project requirements by evaluating each strategy on the same fixed long-context test suite and comparing their accuracy, token usage, and latency.

---

## Implemented Strategies

- **Sliding Window**
  - Keeps only the most recent conversation turns.

- **Observation Masking**
  - Replaces old tool outputs with a placeholder while preserving the dialogue.

- **Recursive Summarization**
  - Compresses older conversation chunks into summary messages.

- **Zone-Based Pruning**
  - Divides the transcript into pinned, head, middle, and recent zones, applying a different pruning policy to each.

---

## Folder Structure

```
context_eval/
├── schema.py                 
├── utils.py                  
├── sliding_window.py         
├── observation_masking.py    
├── recursive_summary.py      
├── zone_pruning.py           
├── test_cases.py             
├── evaluate.py               
└── comparison_table.md       
```

---

## Running the Evaluation

Create a `.env` file in the project root.

```env
GEMINI_API_KEY=YOUR_API_KEY
GEMINI_MODEL=gemini-3.5-flash-lite
```
Sanity Check (No API calls):

```bash
python -c "from context_eval.test_cases import BURIAL_CASES as C; from context_eval.utils import transcript_tokens as T; print([(len(c), T(c)) for c in C[:3]])"
```
Run a quick validation:

```bash
python -m context_eval.evaluate --smoke
```

Run the complete benchmark:

```bash
python -m context_eval.evaluate
```

The evaluation script automatically:

- executes all four strategies,
- measures accuracy, token usage, and latency,
- retries transient Gemini API rate-limit (429) errors,
- generates `comparison_table.md`.

---

## Test Suite

The benchmark uses synthetic long-context transcripts where an important early fact is buried beneath many tool outputs.

Each transcript contains:

1. System message
2. Early critical fact
3. Multiple tool calls with large JSON outputs
4. Final user query requiring recall of the early fact

Ten benchmark cases are included with different transcript lengths and fact locations.

---

## Evaluation Metrics

Each strategy is compared using:

- Detail recalled (accuracy)
- Average input tokens
- Average output tokens
- Average latency

The generated results are written to:

```
context_eval/comparison_table.md
```

---

## Notes

- Token counting is centralized in `utils.py` using `tiktoken`.
- `test_cases.py` is intentionally fixed so every strategy is evaluated on the same benchmark.
- Rate-limit handling is implemented inside `evaluate.py` to improve evaluation reliability.