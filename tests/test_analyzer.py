import ast

import pytest

import analyzer as an


def descriptions(findings):
    return [item["description"] for item in findings]


# --- security -----------------------------------------------------------

def test_hardcoded_secret_detected():
    result = an.find_hardcoded_secrets(['api_key = "abcd1234"'], "python")
    assert len(result) == 1 and result[0]["severity"] == "high" and result[0]["line"] == 1


def test_env_reference_is_not_flagged_as_secret():
    assert an.find_hardcoded_secrets(['password = "from_env_var"'], "python") == []


def test_non_secret_name_not_flagged():
    assert an.find_hardcoded_secrets(['username = "alice"'], "python") == []


def test_sql_injection_detected_for_concatenation():
    lines = ['query = "SELECT * FROM users WHERE id = " + user_id']
    assert an.find_sql_injection(lines, "python")


def test_parameterized_query_not_flagged():
    assert an.find_sql_injection(['cur.execute("SELECT * FROM users WHERE id = ?", (uid,))'], "python") == []


@pytest.mark.parametrize("snippet", ["eval(x)", "os.system(cmd)", "pickle.loads(data)", "yaml.load(f)"])
def test_dangerous_calls_detected(snippet):
    assert an.find_dangerous_calls([snippet])


# --- bugs ---------------------------------------------------------------

def test_bare_except_and_mutable_default_detected():
    lines = ["def f(a=[]):", "    try:", "        pass", "    except:", "        pass"]
    found = descriptions(an.find_bugs(lines, "python"))
    assert any("Mutable default" in d for d in found)
    assert any("Bare 'except:'" in d for d in found)


def test_division_by_length_flagged():
    assert an.find_bugs(["avg = total / len(items)"], "python")


def test_division_guard_ignores_words_that_merely_contain_if():
    # Regression: the substring "if" in "verify" used to suppress the finding.
    assert an.find_bugs(["avg = total / len(items)  # verify later"], "python")


def test_guarded_division_not_flagged():
    assert an.find_bugs(["avg = total / len(items) if items else 0"], "python") == []


def test_off_by_one_loop_bound_detected():
    assert an.find_bugs(["for (int i = 0; i <= arr.length; i++) {"], "java")


def test_go_unchecked_error_detected():
    lines = ["f, err := os.Open(name)", "use(f)"]
    assert an.find_bugs(lines, "go")


def test_empty_catch_block_detected():
    assert an.find_empty_catch_blocks("try { x() } catch (e) {}")


# --- syntax -------------------------------------------------------------

def test_python_syntax_error_reports_line():
    result = an.find_syntax_errors("x = 1\ndef f(:\n", "python")
    assert result and result[0]["line"] == 2


def test_valid_python_has_no_syntax_errors():
    assert an.find_syntax_errors("x = 1\n", "python") == []


def test_unbalanced_braces_detected():
    assert an.find_syntax_errors("int main() {\n  return 0;\n", "cpp")


def test_braces_inside_strings_are_ignored():
    assert an.find_syntax_errors('int main() {\n  char *s = "{";\n  return 0;\n}\n', "cpp") == []


# --- function spans / complexity ---------------------------------------

def test_else_if_is_not_treated_as_a_function():
    code = "void f(int n) {\n  if (n) {\n  } else if (n > 0) {\n  }\n}\n"
    spans = an.estimate_function_spans(code.splitlines(), "java")
    assert [s[0] for s in spans] == [1]


def test_long_function_flagged():
    body = "\n".join(f"    x{i} = {i}" for i in range(45))
    code = f"def big():\n{body}\n"
    lines = code.splitlines()
    quality = an.find_quality_issues(lines, "python", an.estimate_function_spans(lines, "python"))
    assert any("spans" in d for d in descriptions(quality))


@pytest.mark.parametrize(
    "code, expected",
    [
        ("x = 1\n", "O(1)"),
        ("for i in a:\n    pass\n", "O(n)"),
        ("for i in a:\n    for j in a:\n        pass\n", "O(n^2)"),
        ("for i in a:\n    for j in a:\n        for k in a:\n            pass\n", "O(n^3)"),
        ("def f(n):\n    return f(n-1) + f(n-2)\n", "O(2^n)"),
        ("s = sorted(a)\n", "O(n log n)"),
    ],
)
def test_python_time_complexity(code, expected):
    assert an.estimate_complexity(code, "python")["time"] == expected


def test_space_complexity_grows_with_append():
    assert an.estimate_complexity("out = []\nfor i in a:\n    out.append(i)\n", "python")["space"] == "O(n)"


# --- scoring ------------------------------------------------------------

def test_score_is_clamped_between_0_and_10():
    many = [{"severity": "high"}] * 10
    assert an.calculate_score(many, [], []) == 0
    assert an.calculate_score([], [], []) == 10


def test_verdict_prioritises_high_severity_security():
    assert "security" in an.build_verdict(10, [{"severity": "high"}]).lower()


# --- auto-fixes ---------------------------------------------------------

def test_mutable_default_fix_produces_valid_python():
    fixed = an.fix_mutable_default_args("def f(a=[], b={}):\n    return a, b\n")
    ast.parse(fixed)
    assert "a=None" in fixed and "a = []" in fixed and "b = {}" in fixed


def test_none_comparison_fixed():
    assert "x is None" in an.apply_safe_fixes("if x == None:\n    pass\n", "python")


def test_js_var_and_loose_equality_fixed():
    fixed = an.apply_safe_fixes("var a = 1;\nif (a == 2) {}\n", "javascript")
    assert "let a" in fixed and "===" in fixed


def test_off_by_one_fixed():
    assert an.fix_off_by_one("i <= arr.length") == "i < arr.length"
    assert an.fix_off_by_one("i <= len(arr)") == "i < len(arr)"


def test_hardcoded_secret_replaced_with_env_lookup():
    fixed = an.fix_hardcoded_secrets('apiKey = "abcd1234"', "python")
    assert 'os.getenv("API_KEY")' in fixed and fixed.startswith("import os")


def test_debug_print_removed():
    assert an.remove_debug_statements("x = 1\nprint(x)\ny = 2", "python") == "x = 1\ny = 2"


@pytest.mark.parametrize(
    "src",
    [
        "def f(x):\n    if x:\n        print('a')\n    return 1\n",
        "def f(x):\n    if x:\n        print('a')\n        print('b')\n    return 1\n",
        "for i in range(3):\n    print(i)\n",
    ],
)
def test_debug_removal_never_leaves_empty_python_block(src):
    # Regression: removing a lone print used to leave an empty block (SyntaxError).
    ast.parse(an.remove_debug_statements(src, "python"))


def test_debug_removal_keeps_other_statements_in_block():
    out = an.remove_debug_statements("if x:\n    print(1)\n    y = 2\n", "python")
    assert out == "if x:\n    y = 2"


def test_go_debug_lines_are_kept():
    assert "fmt.Println" in an.remove_debug_statements('fmt.Println("x")', "go")


# --- end to end ---------------------------------------------------------

def test_analyze_code_result_shape():
    result = an.analyze_code("x = 1\n", "python")
    assert set(result) == {"bugs", "quality", "security", "complexity", "refactored_code", "score", "verdict"}
    assert set(result["complexity"]) == {"time", "space", "explanation"}


def test_syntax_error_forces_zero_score():
    result = an.analyze_code("def f(:\n", "python")
    assert result["score"] == 0 and "syntax error" in result["verdict"].lower()


def test_refactored_python_still_parses_after_fixes():
    code = "def f(x, items=[]):\n    if x == None:\n        print('none')\n    return items\n"
    refactored = an.analyze_code(code, "python")["refactored_code"]
    ast.parse(refactored)


@pytest.mark.parametrize("language", ["python", "javascript", "cpp", "java", "go"])
def test_every_supported_language_runs(language):
    assert "score" in an.analyze_code("int x = 1;", language)
