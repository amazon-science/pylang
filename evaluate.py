"""
Unified PyLang evaluator for both codeforces and MBPP problems.

Loads from data/pylang_benchmark.json and branches evaluation strategy per-entry
based on the `source` field:

  codeforces: extract first function → rename to solve() → strict output matching
  mbpp:       extract ALL functions → no rename → flexible output matching

A per-source (codeforces/mbpp) breakdown is printed automatically.

Usage:
    python evaluate.py --solutions-dir MODEL/eval_solutions
    python evaluate.py --json-file solutions.json
"""

import os
import json
import subprocess
import time
import math
import re
import tempfile
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

MODEL_NAME = "pylang_generation_time_full_train_test15_algn_wt0dot01/"
SOLUTIONS_DIR = f"{MODEL_NAME}/eval_solutions"
JSON_FILE = None
UNIFIED_EVAL_FILE = "data/pylang_benchmark.json"
INTERPRETER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "interpreter.py")
TIMEOUT = 30
NUM_WORKERS = 8
MATH_REL_TOL = 1e-6  # relative tolerance for floating-point (is_math) comparisons


TRUE_VALS = {"True", "true", "YES", "Yes", "yes", "1"}
FALSE_VALS = {"False", "false", "NO", "No", "no", "0"}


def _boolean_equivalent(a, b):
    """Check if two values are boolean-equivalent (yes/no, true/false, 1/0)."""
    return (a in TRUE_VALS and b in TRUE_VALS) or (a in FALSE_VALS and b in FALSE_VALS)


def assert_equal_values(a, b):
    try:
        if type(b) == list:
            expected_output_type = type(b[0])
            a = [expected_output_type(x) for x in a]
        return float(a) == float(b)
    except:
        return a == b


def _split_top_level_args(args_str):
    """Split arguments at top-level commas, respecting brackets/parens/quotes."""
    args = []
    depth = 0
    current = ""
    in_str = False
    str_char = None
    for ch in args_str:
        if in_str:
            current += ch
            if ch == str_char:
                in_str = False
        elif ch in ('"', "'"):
            in_str = True
            str_char = ch
            current += ch
        elif ch in ('(', '[', '{'):
            depth += 1
            current += ch
        elif ch in (')', ']', '}'):
            depth -= 1
            current += ch
        elif ch == ',' and depth == 0:
            args.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        args.append(current.strip())
    return args


def _format_arg_for_stdin(arg):
    """Convert a single MBPP argument to codeforces stdin format.

    - Strings: strip quotes
    - Lists/tuples: strip brackets, space-separate elements, strip inner quotes
    - Nested lists: each sub-list on its own line
    - Scalars: as-is
    """
    stripped = arg.strip()
    if (stripped.startswith('"') and stripped.endswith('"')) or \
       (stripped.startswith("'") and stripped.endswith("'")):
        return stripped[1:-1]
    if (stripped.startswith('[') and stripped.endswith(']')) or \
       (stripped.startswith('(') and stripped.endswith(')')):
        inner = stripped[1:-1].strip()
        if not inner:
            return ''
        # Check for nested lists: [[1,2],[3,4]]
        elements = _split_top_level_args(inner)
        formatted = []
        for elem in elements:
            elem = elem.strip()
            # Strip quotes from string elements
            if (elem.startswith('"') and elem.endswith('"')) or \
               (elem.startswith("'") and elem.endswith("'")):
                elem = elem[1:-1]
            # Recursively handle nested lists
            elif (elem.startswith('[') and elem.endswith(']')) or \
                 (elem.startswith('(') and elem.endswith(')')):
                elem = _format_arg_for_stdin(elem)
            formatted.append(elem)
        # If elements contain spaces (nested lists were flattened), join with newlines
        if any(' ' in f for f in formatted):
            return '\\n'.join(formatted)
        return ' '.join(formatted)
    return stripped


def convert_to_solve_call(test_input):
    """Convert MBPP test call to codeforces-style solve() call.

    Follows codeforces stdin convention:
    - Scalar args go on one line (space-separated)
    - List/tuple args each get their own line (space-separated elements)
    - Scalars come first, then lists

    first_repeated_char("abcabc")             →  solve("abcabc")
    prime_num(13)                              →  solve("13")
    pair_OR_Sum([5,9,7,6],4)                  →  solve("4\\n5 9 7 6")
    noprofit_noloss(1500,1200)                →  solve("1500 1200")
    """
    m = re.match(r'(\w+)\s*\((.+)\)$', test_input, re.DOTALL)
    if not m:
        return None

    args_str = m.group(2).strip()
    args = _split_top_level_args(args_str)

    if len(args) == 1:
        return f'solve("{_format_arg_for_stdin(args[0])}")'

    # Separate scalars from lists/tuples
    scalars = []
    lists = []
    for a in args:
        a_stripped = a.strip()
        if (a_stripped.startswith('[') and a_stripped.endswith(']')) or \
           (a_stripped.startswith('(') and a_stripped.endswith(')')):
            lists.append(_format_arg_for_stdin(a))
        else:
            scalars.append(_format_arg_for_stdin(a))

    # Build stdin: scalars on first line, then one line per list
    parts = []
    if scalars:
        parts.append(' '.join(scalars))
    parts.extend(lists)
    joined = "\\n".join(parts)
    return f'solve("{joined}")'


# ── Function extraction ──────────────────────────────────────────────────────

def _strip_code_fence(code):
    """Strip ```pylang markdown fence if present."""
    pylang_pattern = r'```pylang\s*\n(.*?)```'
    m = re.search(pylang_pattern, code, re.DOTALL)
    return m.group(1).strip() if m else code


def extract_first_function(code):
    """Extract the first complete function definition (codeforces)."""
    code = _strip_code_fence(code)
    lines = code.split('\n')
    function_lines = []
    in_function = False
    brace_count = 0

    for line in lines:
        if not in_function:
            if re.match(r'^\s*function\s+\w+\s*\(', line):
                in_function = True
                brace_count = 0
                function_lines = []

        if in_function:
            cut_pos = None
            for ci, ch in enumerate(line):
                if ch == '{':
                    brace_count += 1
                elif ch == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        cut_pos = ci + 1
                        break

            if cut_pos is not None:
                function_lines.append(line[:cut_pos])
                in_function = False
                break
            else:
                function_lines.append(line)

    return '\n'.join(function_lines) if function_lines else code


def extract_all_functions(code):
    """Extract ALL function definitions (MBPP — helpers + main)."""
    code = _strip_code_fence(code)
    lines = code.split('\n')
    all_function_lines = []
    in_function = False
    brace_count = 0
    function_lines = []

    for line in lines:
        if not in_function:
            if re.match(r'^\s*function\s+\w+\s*\(', line):
                in_function = True
                brace_count = 0
                function_lines = []

        if in_function:
            cut_pos = None
            for ci, ch in enumerate(line):
                if ch == '{':
                    brace_count += 1
                elif ch == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        cut_pos = ci + 1
                        break

            if cut_pos is not None:
                function_lines.append(line[:cut_pos])
                all_function_lines.extend(function_lines)
                all_function_lines.append('')
                in_function = False
            else:
                function_lines.append(line)

    return '\n'.join(all_function_lines).strip() if all_function_lines else code


def detect_and_normalize_function_name(code, expected_name='solve'):
    """Rename function to expected_name if different.

    Renames both the function definition AND all calls using word-boundary
    replacement. For multi-function code, renames the LAST top-level function
    (the entry point) rather than the first (which is typically a helper).
    """
    # Find all top-level function names
    func_names = re.findall(r'function\s+(\w+)\s*\(', code)
    if not func_names:
        return code, None

    # If expected_name already exists, no rename needed
    if expected_name in func_names:
        return code, expected_name

    # Rename the LAST function (entry point), not the first (helper)
    detected_name = func_names[-1]

    # Replace all occurrences (definition + calls) using word boundary
    normalized_code = re.sub(
        r'\b' + re.escape(detected_name) + r'\b',
        expected_name,
        code
    )
    return normalized_code, detected_name


# ── Validation ───────────────────────────────────────────────────────────────

def _run_pylang(test_code, interpreter_path, timeout):
    """Execute PyLang code and return CompletedProcess, or None on timeout."""
    fd, execution_file = tempfile.mkstemp(suffix='.pl', prefix='eval_')
    os.close(fd)
    try:
        with open(execution_file, 'w') as f:
            f.write(test_code)
        try:
            return subprocess.run(
                ["python3", interpreter_path, execution_file],
                capture_output=True,
                text=True,
                timeout=timeout
            )
        except subprocess.TimeoutExpired:
            return None
    finally:
        if os.path.exists(execution_file):
            os.remove(execution_file)


def validate_solution(code, test_cases, source, interpreter_path, timeout):
    """Validate solution against test cases using PyLang interpreter.

    Branches on `source`:
      codeforces — extract first function, rename to solve(), strict matching
      mbpp       — extract all functions, rename entry-point to match test case,
                   flexible matching
    """
    tests_passed = 0
    test_results = []
    start_time = time.time()
    per_test_timeout = min(timeout, 60)

    is_codeforces = (source == "codeforces")

    # Defaults for MBPP-specific state (unused for codeforces)
    mbpp_mode = None
    trim_args = False
    n_params = None

    if is_codeforces:
        code = extract_first_function(code)
        code, _ = detect_and_normalize_function_name(code, expected_name='solve')
    else:
        # MBPP: detect calling convention once using first test case
        code_raw = extract_all_functions(code)
        first_test = test_cases[0][2] if test_cases else ""
        func_match = re.match(r'(\w+)\s*\(', first_test)
        expected_func = func_match.group(1) if func_match else 'solve'

        # Probe: try typed-arg call on first test — check output matches expected
        # Try without print wrapper first, then with (mirrors the execution path)
        typed_code, _ = detect_and_normalize_function_name(code_raw, expected_name=expected_func)
        first_expected = test_cases[0][3] if test_cases else ""
        first_expected_clean = first_expected.replace("'", "").replace('"', "").replace('(', "").replace(')', "").strip()

        # Detect how many params the model's function takes
        sig_match = re.search(r'function\s+' + re.escape(expected_func) + r'\s*\(([^)]*)\)', typed_code)
        n_params = len([p for p in sig_match.group(1).split(',') if p.strip()]) if sig_match else None

        use_typed = False
        trim_args = False

        def _probe_pylang(call_str):
            """Try a probe call: without wrapper, then with print wrapper."""
            p = _run_pylang(f"{typed_code}\n{call_str};", interpreter_path, per_test_timeout)
            if p is not None and p.returncode == 0:
                out = p.stdout.strip()
                if not out:
                    p = _run_pylang(f"{typed_code}\nprint({call_str});", interpreter_path, per_test_timeout)
                    if p is not None and p.returncode == 0:
                        out = p.stdout.strip()
                return p, out
            return p, ""

        # First try: full args
        probe, probe_output = _probe_pylang(first_test)
        if probe is not None and probe.returncode == 0 and probe_output:
            try:
                if assert_equal_values(probe_output, first_expected_clean):
                    use_typed = True
                elif _boolean_equivalent(probe_output, first_expected_clean):
                    use_typed = True
            except Exception:
                pass

        # If full args failed and model takes fewer params, try trimmed args
        if not use_typed and n_params is not None and probe is not None and probe.returncode != 0:
            tm = re.match(r'(\w+)\s*\((.+)\)$', first_test, re.DOTALL)
            if tm:
                test_args = _split_top_level_args(tm.group(2))
                if n_params < len(test_args):
                    trimmed = f"{tm.group(1)}({', '.join(test_args[:n_params])})"
                    probe2, probe_output2 = _probe_pylang(trimmed)
                    if probe2 is not None and probe2.returncode == 0 and probe_output2:
                        try:
                            if assert_equal_values(probe_output2, first_expected_clean):
                                use_typed = True
                                trim_args = True
                            elif _boolean_equivalent(probe_output2, first_expected_clean):
                                use_typed = True
                                trim_args = True
                        except Exception:
                            pass

        if use_typed:
            code = typed_code
            mbpp_mode = "typed"
        else:
            code, _ = detect_and_normalize_function_name(code_raw, expected_name='solve')
            mbpp_mode = "solve"

    for idx, test_case in enumerate(test_cases):
        test_input = test_case[2]
        expected_output = test_case[3]
        is_math = test_case[-1] if len(test_case) > 4 else False
        tolerance = MATH_REL_TOL if is_math else None

        if not test_input:
            test_results.append({"test": idx+1, "status": "skipped", "reason": "empty input"})
            continue

        # Trim args if model takes fewer params than test provides
        effective_input = test_input
        if not is_codeforces and trim_args and n_params is not None:
            tm = re.match(r'(\w+)\s*\((.+)\)$', test_input, re.DOTALL)
            if tm:
                ta = _split_top_level_args(tm.group(2))
                if n_params < len(ta):
                    effective_input = f"{tm.group(1)}({', '.join(ta[:n_params])})"

        solve_call = None
        if is_codeforces:
            test_code = f"{code}\n{test_input};"
        elif mbpp_mode == "typed":
            # Try without print wrapper first (handles functions that print internally),
            # fall back to print wrapper (handles functions that return values)
            test_code = f"{code}\n{effective_input};"
        else:
            # mbpp_mode == "solve": convert func_name(args) → solve("args")
            solve_call = convert_to_solve_call(test_input)
            test_code = f"{code}\n{solve_call};" if solve_call else f"{code}\n{test_input};"

        result = _run_pylang(test_code, interpreter_path, per_test_timeout)

        # For MBPP: if no output, function likely returns a value
        # without printing — retry with print() wrapper to capture the return value
        if not is_codeforces and result is not None and result.returncode == 0 and not result.stdout.strip():
            if mbpp_mode == "typed":
                result = _run_pylang(f"{code}\nprint({effective_input});", interpreter_path, per_test_timeout)
            elif solve_call:
                result = _run_pylang(f"{code}\nprint({solve_call});", interpreter_path, per_test_timeout)

        if result is None:
            test_results.append({"test": idx+1, "status": "timeout"})
            continue
        if result.returncode != 0:
            test_results.append({"test": idx+1, "status": "syntax_error", "error": result.stderr[:300]})
            continue

        actual_output = result.stdout.strip()

        if is_codeforces:
            expected_clean = expected_output.replace('\\n', '\n').strip()
            if actual_output == expected_clean or _boolean_equivalent(actual_output, expected_clean):
                tests_passed += 1
                test_results.append({"test": idx+1, "status": "pass"})
            else:
                test_results.append({"test": idx+1, "status": "fail", "expected": expected_clean[:100], "actual": actual_output[:100]})
        else:
            expected_clean = expected_output.replace("'", "").replace('"', "").replace('(', "").replace(')', "").strip()
            try:
                passed = False
                if is_math:
                    if actual_output and math.isclose(float(actual_output), float(expected_clean), rel_tol=float(tolerance)):
                        passed = True
                else:
                    if assert_equal_values(actual_output, expected_clean):
                        passed = True
                    else:
                        if _boolean_equivalent(actual_output, expected_clean):
                            passed = True
                        # Case-insensitive fallback for string outputs
                        elif actual_output.lower() == expected_clean.lower():
                            passed = True

                if passed:
                    tests_passed += 1
                    test_results.append({"test": idx+1, "status": "pass"})
                else:
                    test_results.append({"test": idx+1, "status": "fail", "expected": expected_clean[:100], "actual": actual_output[:100]})
            except Exception as e:
                test_results.append({"test": idx+1, "status": "comparison_error", "error": str(e)[:100]})

    execution_time = time.time() - start_time
    success = tests_passed == len(test_cases)

    return {
        "success": success,
        "tests_passed": tests_passed,
        "total_tests": len(test_cases),
        "pass_rate": tests_passed / len(test_cases) if test_cases else 0,
        "execution_time": execution_time,
        "test_results": test_results
    }


def _evaluate_single(args):
    """Worker function for parallel evaluation."""
    eval_idx, code, test_cases, source, interpreter_path, timeout = args
    result = validate_solution(code, test_cases, source, interpreter_path, timeout)
    result['source'] = source
    return eval_idx, result



def main():
    print(f"Loading problems from unified eval file...")
    with open(UNIFIED_EVAL_FILE, 'r') as f:
        eval_data = json.load(f)
    print(f"Loaded {len(eval_data)} problems from {UNIFIED_EVAL_FILE}")

    sources = {}
    for d in eval_data:
        sources[d['source']] = sources.get(d['source'], 0) + 1
    for src, count in sorted(sources.items()):
        print(f"  {src}: {count}")

    # Build work items
    if JSON_FILE:
        with open(JSON_FILE, 'r') as f:
            codes = json.load(f)
        print(f"Loading {len(codes)} solutions from JSON: {JSON_FILE}")
        solutions = [(idx, str(code)) for idx, code in enumerate(codes)]
    else:
        solution_files = sorted([f for f in os.listdir(SOLUTIONS_DIR) if f.endswith('.pl')])
        solutions = []
        for solution_file in solution_files:
            idx = int(solution_file.split('.')[0]) - 1  # 1-based filenames to 0-based index
            solution_path = os.path.join(SOLUTIONS_DIR, solution_file)
            with open(solution_path, 'r') as f:
                code = f.read()
            solutions.append((idx, code))

    work_items = []
    for idx, code in solutions:
        if idx >= len(eval_data):
            continue

        entry = eval_data[idx]
        test_cases = entry['test_cases']
        source = entry['source']

        if not test_cases:
            continue

        work_items.append((idx, code, test_cases, source, INTERPRETER_PATH, TIMEOUT))

    matched = len(work_items)
    print(f"\nEvaluating {matched} solutions using {NUM_WORKERS} workers...")

    results = {}
    total_passed = 0
    total_tests = 0
    syntax_errors = 0
    eval_mismatches = 0

    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        futures = {executor.submit(_evaluate_single, item): item[0] for item in work_items}

        for future in tqdm(as_completed(futures), total=len(futures)):
            idx, result = future.result()
            results[idx] = result

            total_passed += result['tests_passed']
            total_tests += result['total_tests']

            for test_result in result['test_results']:
                if test_result['status'] == 'syntax_error':
                    syntax_errors += 1
                elif test_result['status'] == 'fail':
                    eval_mismatches += 1

    print(f"\nMatched {matched} out of {len(solutions)} solutions")

    overall_pass_rate = total_passed / total_tests if total_tests > 0 else 0
    all_passed = sum(1 for r in results.values() if r['success'])
    problem_pass_rate = all_passed / matched if matched > 0 else 0

    # Per-source breakdown
    per_source = {}
    for r in results.values():
        src = r['source']
        if src not in per_source:
            per_source[src] = {'tests_passed': 0, 'tests_total': 0, 'problems_passed': 0, 'problems_total': 0}
        per_source[src]['problems_total'] += 1
        per_source[src]['tests_passed'] += r['tests_passed']
        per_source[src]['tests_total'] += r['total_tests']
        if r['success']:
            per_source[src]['problems_passed'] += 1

    print(f"\n{'='*60}")
    print(f"EVALUATION RESULTS (ALL)")
    print(f"{'='*60}")
    print(f"Total solutions evaluated: {len(results)}")
    print(f"Problem pass rate: {all_passed}/{matched} ({problem_pass_rate:.2%})")
    print(f"Test pass rate:    {total_passed}/{total_tests} ({overall_pass_rate:.2%})")
    print(f"Syntax errors: {syntax_errors}")
    print(f"Evaluation mismatches: {eval_mismatches}")
    if len(per_source) > 1:
        print(f"\nPer-source breakdown:")
        for src, stats in sorted(per_source.items()):
            p_rate = stats['problems_passed'] / stats['problems_total'] if stats['problems_total'] > 0 else 0
            t_rate = stats['tests_passed'] / stats['tests_total'] if stats['tests_total'] > 0 else 0
            print(f"  {src}:")
            print(f"    Problem pass rate: {stats['problems_passed']}/{stats['problems_total']} ({p_rate:.2%})")
            print(f"    Test pass rate:    {stats['tests_passed']}/{stats['tests_total']} ({t_rate:.2%})")
    print(f"{'='*60}\n")

    if JSON_FILE:
        output_file = os.path.splitext(JSON_FILE)[0] + "_evaluation_results.json"
    else:
        output_file = f"{SOLUTIONS_DIR}/evaluation_results.json"
    with open(output_file, 'w') as f:
        json.dump({
            'overall': {
                'total_solutions': len(results),
                'matched': matched,
                'problems_fully_passed': all_passed,
                'problem_pass_rate': problem_pass_rate,
                'total_tests': total_tests,
                'total_passed': total_passed,
                'pass_rate': overall_pass_rate,
                'syntax_errors': syntax_errors,
                'eval_mismatches': eval_mismatches,
                'per_source': per_source,
            },
            'per_solution': results
        }, f, indent=2)

    print(f"Detailed results saved to {output_file}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Evaluate PyLang solutions (codeforces + MBPP)")
    parser.add_argument("--solutions-dir", type=str, default=None, help="Directory containing .pl solution files")
    parser.add_argument("--json-file", type=str, default=None, help="JSON file containing solutions array")
    parser.add_argument("--eval-file", type=str, default=None, help="Path to unified eval JSON containing all problems and test cases")
    parser.add_argument("--workers", type=int, default=None, help=f"Number of parallel workers (default: {NUM_WORKERS})")
    args = parser.parse_args()

    if args.solutions_dir is not None:
        SOLUTIONS_DIR = args.solutions_dir
    if args.json_file is not None:
        JSON_FILE = args.json_file
    if args.eval_file is not None:
        UNIFIED_EVAL_FILE = args.eval_file
    if args.workers is not None:
        NUM_WORKERS = args.workers

    main()
