"""Local, rule-based static analysis engine.

Produces the same result shape the Claude-backed reviewer will eventually
return (bugs / quality / security / complexity / refactored_code / score /
verdict), but computes everything from the submitted code using regex and
brace/indentation heuristics instead of an LLM call.
"""

import ast
import os
import re
import subprocess
import tempfile

COMMENT_PREFIX = {
    "python": "#",
    "javascript": "//",
    "cpp": "//",
    "java": "//",
    "go": "//",
}

SECRET_KEYWORDS = ("api_key", "apikey", "secret", "password", "passwd", "pwd", "token", "auth_key")

SQL_KEYWORDS = ("select ", "insert ", "update ", "delete ", "drop ")

DANGEROUS_CALLS = {
    "eval(": "Use of eval() can execute arbitrary code; avoid evaluating untrusted input.",
    "exec(": "Use of exec() can execute arbitrary code; avoid evaluating untrusted input.",
    "os.system(": "os.system() with untrusted input enables command injection; use subprocess with an argument list instead.",
    "shell=True": "A subprocess call with shell=True enables command injection if any part of the command is untrusted.",
    "pickle.loads(": "Unpickling untrusted data can execute arbitrary code; prefer a safe format like JSON.",
    "yaml.load(": "yaml.load() without a safe Loader can execute arbitrary code; use yaml.safe_load() instead.",
}

DEBUG_PRINT_PATTERNS = {
    "python": [r"\bprint\("],
    "javascript": [r"console\.log\("],
    "java": [r"System\.out\.println\("],
    "cpp": [r"std::cout", r"\bcout\s*<<"],
    "go": [r"fmt\.Println\(", r"fmt\.Printf\("],
}

LOOP_KEYWORD_PATTERNS = {
    "python": [r"\bfor\b", r"\bwhile\b"],
    "javascript": [r"\bfor\b", r"\bwhile\b"],
    "java": [r"\bfor\b", r"\bwhile\b"],
    "cpp": [r"\bfor\b", r"\bwhile\b"],
    "go": [r"\bfor\b"],
}

SORT_HINTS = [r"\.sort\(", r"\bsorted\(", r"Arrays\.sort\(", r"sort\.Slice\(", r"sort\.Ints\(", r"std::sort\("]

GROWTH_HINTS = [r"\.append\(", r"\.push\(", r"\.add\(", r":=\s*append\("]

FUNCTION_DEF_PATTERNS = {
    "python": r"def\s+(\w+)\s*\(",
    "javascript": r"function\s+(\w+)\s*\(",
    "java": r"\b\w+\s+(\w+)\s*\([^)]*\)\s*\{",
    "cpp": r"\b\w[\w:<>]*\s+(\w+)\s*\([^)]*\)\s*\{",
    "go": r"func\s+(\w+)\s*\(",
}

SEVERITY_WEIGHTS = {"high": 3.0, "medium": 1.5, "low": 0.5}

SAFE_SUBSTITUTIONS = {
    "python": [
        (re.compile(r"^(\s*)except\s*:\s*$", re.MULTILINE), r"\1except Exception:"),
        (re.compile(r"==\s*None\b"), "is None"),
        (re.compile(r"!=\s*None\b"), "is not None"),
    ],
    "javascript": [
        (re.compile(r"\bvar\b"), "let"),
        (re.compile(r"(?<![=!<>])==(?!=)"), "==="),
        (re.compile(r"(?<!!)!=(?!=)"), "!=="),
    ],
}

GENERIC_SAFE_SUBSTITUTIONS = [
    (re.compile(r"\byaml\.load\("), "yaml.safe_load("),
]

# Languages where a bare debug-print line can be dropped outright without
# risking a compile error. Go is excluded: removing a line can leave a
# declared variable unused, which Go treats as a hard compile error.
DEBUG_LINE_PATTERNS = {
    "python": re.compile(r"^print\(.*\)$"),
    "javascript": re.compile(r"^console\.log\(.*\);?$"),
    "java": re.compile(r"^System\.out\.println\(.*\);$"),
    "cpp": re.compile(r"^(?:std::)?cout\s*<<.*;$"),
}

OFF_BY_ONE_LENGTH_RE = re.compile(r"<=(\s*)(\w+\.(?:length|size\(\)))")
OFF_BY_ONE_LEN_CALL_RE = re.compile(r"<=(\s*)len\((\w+)\)")

SECRET_ASSIGNMENT_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)(\s*[:=]\s*)[\"']([^\"']{4,})[\"']")

SECRET_ENV_EXPR = {
    "python": 'os.getenv("{name}")',
    "javascript": "process.env.{name}",
    "java": 'System.getenv("{name}")',
    "go": 'os.Getenv("{name}")',
    "cpp": 'std::getenv("{name}")',
}


def remove_debug_statements(code, language):
    """Drop lines that are nothing but a debug print call; they carry no
    logic besides side-effect output, so deleting the line is always safe."""
    pattern = DEBUG_LINE_PATTERNS.get(language)
    if not pattern:
        return code
    kept = [line for line in code.splitlines() if not pattern.match(line.strip())]
    return "\n".join(kept)


def fix_off_by_one(code):
    fixed = OFF_BY_ONE_LENGTH_RE.sub(r"<\1\2", code)
    fixed = OFF_BY_ONE_LEN_CALL_RE.sub(r"<\1len(\2)", fixed)
    return fixed


def _to_env_var_name(identifier):
    with_underscores = re.sub(r"(?<!^)(?=[A-Z])", "_", identifier)
    return with_underscores.upper().lstrip("_")


def fix_hardcoded_secrets(code, language):
    """Replace hardcoded credential literals with an environment-variable
    read, mirroring the fix find_hardcoded_secrets recommends in its message."""
    expr_template = SECRET_ENV_EXPR.get(language)
    if not expr_template:
        return code

    def replace(match):
        name, sep, value = match.group(1), match.group(2), match.group(3)
        if "env" in value.lower() or not any(keyword in name.lower() for keyword in SECRET_KEYWORDS):
            return match.group(0)
        return f"{name}{sep}{expr_template.format(name=_to_env_var_name(name))}"

    fixed = SECRET_ASSIGNMENT_RE.sub(replace, code)
    if language == "python" and fixed != code and not re.search(r"^import os\b", fixed, re.MULTILINE):
        fixed = "import os\n" + fixed
    return fixed


def find_hardcoded_secrets(lines, language):
    findings = []
    assignment_re = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*[\"']([^\"']{4,})[\"']")
    for idx, line in enumerate(lines, start=1):
        match = assignment_re.search(line)
        if not match:
            continue
        name, value = match.group(1), match.group(2)
        lowered_value = value.lower()
        if any(keyword in name.lower() for keyword in SECRET_KEYWORDS) and "env" not in lowered_value:
            findings.append(
                {
                    "line": idx,
                    "description": f"'{name}' holds a hardcoded credential. Load it from an environment variable instead.",
                    "severity": "high",
                }
            )
    return findings


def find_sql_injection(lines, language):
    findings = []
    for idx, line in enumerate(lines, start=1):
        lowered = line.lower()
        if any(keyword in lowered for keyword in SQL_KEYWORDS) and ('"' in line or "'" in line):
            if "+" in line or "%" in line or "format(" in lowered or "f'" in lowered or 'f"' in lowered or "${" in line:
                findings.append(
                    {
                        "line": idx,
                        "description": "SQL string appears to be built via concatenation/interpolation. Use parameterized queries to prevent SQL injection.",
                        "severity": "high",
                    }
                )
    return findings


def find_dangerous_calls(lines):
    findings = []
    for idx, line in enumerate(lines, start=1):
        for needle, message in DANGEROUS_CALLS.items():
            if needle in line:
                findings.append({"line": idx, "description": message, "severity": "high"})
    return findings


def _check_python_syntax(code):
    try:
        ast.parse(code)
    except SyntaxError as exc:
        return [
            {
                "line": exc.lineno or 1,
                "description": f"SyntaxError: {exc.msg}. This code will not run.",
                "severity": "high",
            }
        ]
    return []


def _check_javascript_syntax(code):
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False, encoding="utf-8") as tmp_file:
            tmp_file.write(code)
            tmp_path = tmp_file.name
        completed = subprocess.run(
            ["node", "--check", tmp_path],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return []
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    if completed.returncode == 0:
        return []

    stderr = completed.stderr
    line_match = re.search(re.escape(tmp_path) + r":(\d+)", stderr) if tmp_path else None
    line_no = int(line_match.group(1)) if line_match else 1
    message_match = re.search(r"(SyntaxError: .+)", stderr)
    message = message_match.group(1).strip() if message_match else "Syntax error detected."

    return [{"line": line_no, "description": f"{message} This code will not run.", "severity": "high"}]


def _strip_literals_and_comments(code):
    cleaned = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
    cleaned = re.sub(r"//.*", "", cleaned)
    cleaned = re.sub(r'"(?:[^"\\]|\\.)*"', '""', cleaned)
    cleaned = re.sub(r"'(?:[^'\\]|\\.)*'", "''", cleaned)
    return cleaned


def _check_brace_balance(code):
    cleaned = _strip_literals_and_comments(code)
    findings = []
    for open_ch, close_ch in (("{", "}"), ("(", ")"), ("[", "]")):
        balance = 0
        first_bad_line = None
        for line_no, line in enumerate(cleaned.splitlines(), start=1):
            balance += line.count(open_ch) - line.count(close_ch)
            if balance < 0 and first_bad_line is None:
                first_bad_line = line_no
        if balance != 0:
            findings.append(
                {
                    "line": first_bad_line or 1,
                    "description": f"Unbalanced '{open_ch}{close_ch}' pairs detected; this code will not compile.",
                    "severity": "high",
                }
            )
    return findings


def find_syntax_errors(code, language):
    if language == "python":
        return _check_python_syntax(code)
    if language == "javascript":
        return _check_javascript_syntax(code)
    if language in ("java", "cpp", "go"):
        return _check_brace_balance(code)
    return []


def find_bugs(lines, language):
    findings = []
    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()

        if language == "python" and stripped == "except:":
            findings.append(
                {
                    "line": idx,
                    "description": "Bare 'except:' catches every exception, including KeyboardInterrupt/SystemExit. Catch specific exceptions instead.",
                    "severity": "medium",
                }
            )

        if language == "python" and re.search(r"def\s+\w+\([^)]*=\s*(\[\]|\{\})", line):
            findings.append(
                {
                    "line": idx,
                    "description": "Mutable default argument is shared across every call and can leak state between invocations.",
                    "severity": "high",
                }
            )

        if re.search(r"/\s*len\(|/\s*\w+\.length\b|/\s*\w+\.size\(\)", line) and "if" not in stripped.lower():
            findings.append(
                {
                    "line": idx,
                    "description": "Dividing by a collection's length without guarding for the empty case risks a division-by-zero error.",
                    "severity": "medium",
                }
            )

        if language == "go" and re.search(r",\s*err\s*:?=", line):
            lookahead = " ".join(lines[idx : idx + 2])
            if "err != nil" not in lookahead:
                findings.append(
                    {
                        "line": idx,
                        "description": "Error returned by this call doesn't appear to be checked with 'if err != nil'.",
                        "severity": "medium",
                    }
                )

        if re.search(r"<=\s*\w+\.(length|size\(\))", line) or re.search(r"<=\s*len\(\w+\)", line):
            findings.append(
                {
                    "line": idx,
                    "description": "Loop bound uses '<=' against a length/size; this commonly causes an off-by-one, out-of-bounds access.",
                    "severity": "medium",
                }
            )

    return findings


def find_empty_catch_blocks(code):
    findings = []
    pattern = re.compile(r"catch\s*\([^)]*\)\s*\{\s*\}")
    for match in pattern.finditer(code):
        line_no = code.count("\n", 0, match.start()) + 1
        findings.append(
            {"line": line_no, "description": "Empty catch block silently swallows the error.", "severity": "medium"}
        )
    return findings


def estimate_function_spans(lines, language):
    spans = []

    if language == "python":
        def_indices = [i for i, line in enumerate(lines) if re.match(r"\s*def\s+\w+\s*\(", line)]
        for start in def_indices:
            start_indent = len(lines[start]) - len(lines[start].lstrip(" "))
            end = len(lines) - 1
            for j in range(start + 1, len(lines)):
                if lines[j].strip() == "":
                    continue
                indent = len(lines[j]) - len(lines[j].lstrip(" "))
                if indent <= start_indent:
                    end = j - 1
                    break
            spans.append((start + 1, end + 1, end - start + 1))
        return spans

    func_regex = FUNCTION_DEF_PATTERNS.get(language)
    if not func_regex:
        return spans

    for i, line in enumerate(lines):
        if not re.search(func_regex, line):
            continue
        depth = line.count("{") - line.count("}")
        end = i
        for j in range(i + 1, len(lines)):
            depth += lines[j].count("{") - lines[j].count("}")
            end = j
            if depth <= 0:
                break
        spans.append((i + 1, end + 1, end - i + 1))

    return spans


def find_quality_issues(lines, language, function_spans):
    findings = []
    debug_patterns = DEBUG_PRINT_PATTERNS.get(language, [])

    for idx, line in enumerate(lines, start=1):
        if re.search(r"#\s*(TODO|FIXME)", line, re.IGNORECASE) or re.search(r"//\s*(TODO|FIXME)", line, re.IGNORECASE):
            findings.append({"line": idx, "description": "Unresolved TODO/FIXME left in code.", "severity": "low"})

        for pattern in debug_patterns:
            if re.search(pattern, line):
                findings.append(
                    {"line": idx, "description": "Debug print statement left in code; remove before shipping.", "severity": "low"}
                )

        if language == "python" and re.search(r"for\s+\w+\s+in\s+range\(\s*len\(", line):
            findings.append(
                {
                    "line": idx,
                    "description": "Indexing via range(len(...)) is un-Pythonic; iterate directly over the collection or use enumerate().",
                    "severity": "low",
                }
            )

        if language == "javascript" and re.search(r"\bvar\s+\w+", line):
            findings.append(
                {"line": idx, "description": "'var' has function scope and can cause hoisting bugs; use 'let' or 'const'.", "severity": "low"}
            )

        if language == "javascript" and re.search(r"[^=!<>]==[^=]|[^!]!=[^=]", line):
            findings.append(
                {
                    "line": idx,
                    "description": "Loose equality (==/!=) triggers type coercion; prefer strict equality (===/!==).",
                    "severity": "low",
                }
            )

    for start, _end, length in function_spans:
        if length > 40:
            findings.append(
                {
                    "line": start,
                    "description": f"Function spans {length} lines; consider splitting it into smaller functions.",
                    "severity": "medium",
                }
            )

    return findings


def _max_loop_depth_indentation(lines):
    stack = []
    max_depth = 0
    for line in lines:
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        while stack and indent <= stack[-1]:
            stack.pop()
        if re.match(r"\s*(for|while)\b.*:\s*$", line):
            stack.append(indent)
            max_depth = max(max_depth, len(stack))
    return max_depth


def _max_loop_depth_braces(lines, language):
    patterns = LOOP_KEYWORD_PATTERNS.get(language, [r"\bfor\b", r"\bwhile\b"])
    loop_regex = re.compile("|".join(patterns))
    depth = 0
    loop_open_depths = []
    max_depth = 0

    for line in lines:
        is_loop_line = bool(loop_regex.search(line)) and "{" in line
        opens = line.count("{")
        closes = line.count("}")

        if is_loop_line:
            depth += 1
            loop_open_depths.append(depth)
            max_depth = max(max_depth, len(loop_open_depths))
            for _ in range(max(opens - 1, 0)):
                depth += 1
        else:
            depth += opens

        for _ in range(closes):
            if loop_open_depths and depth == loop_open_depths[-1]:
                loop_open_depths.pop()
            depth = max(depth - 1, 0)

    return max_depth


def _detect_recursion(code, language):
    pattern = FUNCTION_DEF_PATTERNS.get(language)
    if not pattern:
        return False, 0

    is_recursive = False
    max_calls = 0
    for match in re.finditer(pattern, code):
        name = match.group(1)
        if not name:
            continue
        window = code[match.end() : match.end() + 2000]
        call_count = len(re.findall(rf"\b{re.escape(name)}\s*\(", window))
        if call_count > 0:
            is_recursive = True
            max_calls = max(max_calls, call_count)

    return is_recursive, max_calls


def estimate_complexity(code, language):
    lines = code.splitlines()
    max_depth = _max_loop_depth_indentation(lines) if language == "python" else _max_loop_depth_braces(lines, language)

    has_sort = any(re.search(pattern, code) for pattern in SORT_HINTS)
    is_recursive, recursion_calls = _detect_recursion(code, language)

    explanation_bits = []

    if is_recursive and recursion_calls >= 2:
        time_complexity = "O(2^n)"
        explanation_bits.append("The function calls itself more than once per invocation, suggesting exponential branching recursion.")
    elif max_depth >= 3:
        time_complexity = "O(n^3)"
        explanation_bits.append("Detected 3 or more nested loops over the input.")
    elif max_depth == 2:
        time_complexity = "O(n^2)"
        explanation_bits.append("Detected 2 nested loops over the input.")
    elif has_sort and max_depth <= 1:
        time_complexity = "O(n log n)"
        explanation_bits.append("A sort call dominates the runtime.")
    elif max_depth == 1 or is_recursive:
        time_complexity = "O(n)"
        explanation_bits.append("A single pass (loop or linear recursion) over the input.")
    else:
        time_complexity = "O(1)"
        explanation_bits.append("No loops or recursion over the input were detected.")

    grows_with_input = any(re.search(pattern, code) for pattern in GROWTH_HINTS)
    space_complexity = "O(n)" if grows_with_input else "O(1)"
    explanation_bits.append(
        "A collection grows inside the function, so extra memory scales with input size."
        if grows_with_input
        else "No data structure proportional to the input size is being built."
    )

    return {"time": time_complexity, "space": space_complexity, "explanation": " ".join(explanation_bits)}


def calculate_score(bugs, quality, security):
    penalty = sum(SEVERITY_WEIGHTS.get(item.get("severity", "low"), 0.5) for item in bugs + quality + security)
    return max(0, min(10, round(10 - penalty)))


def build_verdict(score, security):
    if any(item["severity"] == "high" for item in security):
        return "Critical security issues must be fixed before this code is safe to ship."
    if score >= 9:
        return "Clean code with no significant issues found."
    if score >= 7:
        return "Solid code with a few minor issues worth addressing."
    if score >= 4:
        return "Functional but has notable bugs or quality issues that should be fixed."
    return "Multiple serious issues found; this code needs rework before use."


MUTABLE_DEFAULT_DEF_RE = re.compile(r"^(\s*)def\s+\w+\s*\(([^)]*)\)\s*:\s*$")
MUTABLE_DEFAULT_PARAM_RE = re.compile(r"(\w+)\s*=\s*(\[\]|\{\})")


def fix_mutable_default_args(code):
    """Rewrite `def f(x=[])` to `def f(x=None)` plus a body guard that assigns the
    original default, since the shared-mutable-default bug can be fixed mechanically."""
    new_lines = []
    for line in code.splitlines():
        match = MUTABLE_DEFAULT_DEF_RE.match(line)
        defaults = MUTABLE_DEFAULT_PARAM_RE.findall(match.group(2)) if match else []
        if not match or not defaults:
            new_lines.append(line)
            continue

        indent, params = match.group(1), match.group(2)
        new_params = MUTABLE_DEFAULT_PARAM_RE.sub(r"\1=None", params)
        new_lines.append(line.replace(params, new_params, 1))

        body_indent = indent + "    "
        for name, default in defaults:
            new_lines.append(f"{body_indent}if {name} is None:")
            new_lines.append(f"{body_indent}    {name} = {default}")

    return "\n".join(new_lines)


def apply_safe_fixes(code, language):
    fixed = code
    if language == "python":
        fixed = fix_mutable_default_args(fixed)
    for pattern, replacement in SAFE_SUBSTITUTIONS.get(language, []):
        fixed = pattern.sub(replacement, fixed)
    for pattern, replacement in GENERIC_SAFE_SUBSTITUTIONS:
        fixed = pattern.sub(replacement, fixed)
    fixed = remove_debug_statements(fixed, language)
    fixed = fix_off_by_one(fixed)
    fixed = fix_hardcoded_secrets(fixed, language)
    return fixed


def annotate_findings(code, language, findings):
    prefix = COMMENT_PREFIX.get(language, "//")
    lines = code.splitlines()
    by_line = {}
    for item in findings:
        line_no = item.get("line")
        if not line_no or line_no < 1 or line_no > len(lines):
            continue
        by_line.setdefault(line_no, []).append(item["description"])

    annotated = []
    for idx, line in enumerate(lines, start=1):
        for description in by_line.get(idx, []):
            indent = re.match(r"^(\s*)", line).group(1)
            annotated.append(f"{indent}{prefix} REVIEW: {description}")
        annotated.append(line)

    return "\n".join(annotated)


def build_refactored_code(original_code, language):
    fixed = apply_safe_fixes(original_code, language)
    fixed_lines = fixed.splitlines()
    function_spans = estimate_function_spans(fixed_lines, language)

    # Re-run detection on the fixed code so comments only describe issues that
    # still remain, instead of restating problems apply_safe_fixes already resolved.
    remaining_bugs = find_syntax_errors(fixed, language) + find_bugs(fixed_lines, language) + find_empty_catch_blocks(fixed)
    remaining_quality = find_quality_issues(fixed_lines, language, function_spans)
    remaining_security = (
        find_hardcoded_secrets(fixed_lines, language) + find_sql_injection(fixed_lines, language) + find_dangerous_calls(fixed_lines)
    )

    return annotate_findings(fixed, language, remaining_bugs + remaining_quality + remaining_security)


def analyze_code(code, language):
    lines = code.splitlines()
    function_spans = estimate_function_spans(lines, language)

    syntax_errors = find_syntax_errors(code, language)
    bugs = syntax_errors + find_bugs(lines, language) + find_empty_catch_blocks(code)
    security = find_hardcoded_secrets(lines, language) + find_sql_injection(lines, language) + find_dangerous_calls(lines)
    quality = find_quality_issues(lines, language, function_spans)
    complexity = estimate_complexity(code, language)

    if syntax_errors:
        score = 0
        verdict = "This code contains a syntax error and will not run or compile."
    else:
        score = calculate_score(bugs, quality, security)
        verdict = build_verdict(score, security)

    refactored_code = build_refactored_code(code, language)

    return {
        "bugs": bugs,
        "quality": quality,
        "security": security,
        "complexity": complexity,
        "refactored_code": refactored_code,
        "score": score,
        "verdict": verdict,
    }
