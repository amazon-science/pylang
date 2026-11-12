# Syntax Without Semantics: PyLang Evaluation

Evaluation code and benchmark for the paper
**[Syntax Without Semantics: Teaching LLMs to Code in an Unseen Language](https://arxiv.org/abs/2605.15607)** (COLM 2026).

PyLang is a minimal imperative programming language that does not appear in any
pretraining corpus. It lets us test whether LLMs can carry their coding ability
into a language they have never seen. This repository contains:

- `interpreter.py`: the reference PyLang interpreter.
- `evaluate.py`: the evaluator used in the paper.
- `data/pylang_benchmark.json`: the 352-problem PyLang evaluation benchmark.
- `data/pylangQuestion_test.jsonl`: the 251 Codeforces problems from the benchmark in chat format (system, user, and assistant turns, where the assistant turn is a PyLang solution).

> Only the evaluation benchmark and tooling are released. The training data is not part of this release.

## Note

This code is being released solely for academic and scientific reproducibility purposes, in support of the methods and findings described in the associated publication. Pull requests are not being accepted in order to maintain the code exactly as it was used in the paper.

The data in this repository should not be used for training AI models.

## The PyLang language

PyLang programs are made of functions with C-style braces. They use dynamically
typed variables, `if`/`else`, `while` loops, and integer-indexed arrays. `print` and
`len` are the only built-ins. For example:

```
function first_repeated_char(s) {
    i = 0;
    while (i < len(s)) {
        j = 0;
        while (j < i) {
            if (s[i] == s[j]) {
                return s[i];
            }
            j = j + 1;
        }
        i = i + 1;
    }
}

print(first_repeated_char("abcabc"));
```

Run any PyLang file with the interpreter:

```bash
python3 interpreter.py program.pl
```

## Benchmark

`data/pylang_benchmark.json` is a list of 352 problems:

| Source       | Problems | Test cases | Calling convention |
|--------------|---------:|-----------:|--------------------|
| Codeforces   | 251      | 468        | `solve(input)`, where `input` is the full stdin as a string and the answer is printed to stdout |
| MBPP         | 101      | 303        | Direct function call, e.g. `first_repeated_char("abcabc")` |
| **Total**    | **352**  | **771**    | |

Each entry has these fields:

| Field               | Description |
|---------------------|-------------|
| `id`                | Index in the benchmark (0-based) |
| `source`            | `"codeforces"` or `"mbpp"` |
| `problem_statement` | Natural-language problem description |
| `messages`          | Chat-formatted prompt (system + user) used for generation |
| `test_cases`        | List of `[original_id, problem, test_input, expected_output, is_math]` |
| `solution`          | Reference PyLang solution |
| `original_id`       | ID of the problem in its source dataset |

All 352 reference solutions pass 771/771 test cases under the evaluator.

## Evaluating a model

Requirements: Python 3.8+ and `tqdm` (`pip install tqdm`).

### 1. Generate solutions

Prompt your model with the `messages` field of each benchmark entry. Save the
outputs in either of these formats:

- **A directory of `.pl` files** named by 1-based problem index: `1.pl`, `2.pl`, …, `352.pl`.
- **A JSON file** holding a list of 352 solution strings, in benchmark order.

Solutions may be wrapped in a ```` ```pylang ```` code fence. The evaluator strips it.

### 2. Run the evaluator

```bash
# From a directory of .pl files
python3 evaluate.py \
    --solutions-dir path/to/eval_solutions \
    --eval-file data/pylang_benchmark.json

# From a JSON list of solutions
python3 evaluate.py \
    --json-file path/to/solutions.json \
    --eval-file data/pylang_benchmark.json
```

| Flag              | Description |
|-------------------|-------------|
| `--solutions-dir` | Directory of `N.pl` solution files |
| `--json-file`     | JSON list of solution strings (alternative to `--solutions-dir`) |
| `--eval-file`     | Benchmark file (default: `data/pylang_benchmark.json`) |
| `--workers`       | Number of parallel worker processes (default: 8) |

To sanity-check your setup, run the evaluator on the reference solutions. It should report 352/352 problems passed:

```bash
python3 -c "import json; d=json.load(open('data/pylang_benchmark.json')); json.dump([x['solution'] for x in d], open('ref.json','w'))"
python3 evaluate.py --json-file ref.json --eval-file data/pylang_benchmark.json
```

### How solutions are scored

Each test runs in a fresh PyLang interpreter process with a 30-second timeout.

- **Codeforces:** The evaluator extracts the first function in the solution and renames it to `solve`, then calls it on the test's stdin string. Output must match exactly after trimming whitespace. Equivalent boolean spellings such as `YES`/`Yes`/`true` are accepted.
- **MBPP:** The evaluator keeps every function in the solution so that helpers are preserved. It first tries to call the entry point the way the test does, with typed arguments. If that fails, it converts the arguments into stdin form and calls `solve("...")`. Matching is flexible: numeric equality, boolean equivalence, case-insensitive strings, and quotes and parentheses are ignored.

Tests marked `is_math` compare numbers with a relative tolerance of `1e-6`.

A problem counts as solved only if all of its test cases pass.

### Output

The evaluator prints the problem pass rate, the test pass rate, and a per-source
(Codeforces/MBPP) breakdown. It also writes detailed per-problem results to:

- `<solutions-dir>/evaluation_results.json` when `--solutions-dir` is used.
- `<json-file-stem>_evaluation_results.json` when `--json-file` is used.

## Citation

```bibtex
@inproceedings{
kumar2026syntax,
title={Syntax Without Semantics: Teaching {LLM}s to Code in an Unseen Language},
author={Vinayshekhar Bannihatti Kumar and Disha Makhija and Manoj Ghuhan Arivazhagan and Rashmi Gangadharaiah},
booktitle={Third Conference on Language Modeling},
year={2026}
}
```

## Security

If you discover a potential security issue in this project we ask that you notify AWS/Amazon Security via our [vulnerability reporting page](http://aws.amazon.com/security/vulnerability-reporting/). Please do **not** create a public github issue.

## License

This project is licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0) License. See [LICENSE](LICENSE).

This repository includes third-party data from MBPP (via [Muennighoff/mbpp](https://huggingface.co/datasets/Muennighoff/mbpp)) and Codeforces (via [open-r1/codeforces](https://huggingface.co/datasets/open-r1/codeforces)), both licensed under CC BY 4.0. See [THIRD-PARTY-NOTICES](THIRD-PARTY-NOTICES) for attribution details.
