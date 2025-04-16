import argparse
import glob
import json
import os
from enum import Enum
from collections import Counter
from typing import Dict, List, Tuple
from statistics import mean
from log_parsers import MAP_REPO_TO_PARSER

FAIL_TO_PASS = "FAIL_TO_PASS"
FAIL_TO_FAIL = "FAIL_TO_FAIL"
PASS_TO_PASS = "PASS_TO_PASS"
PASS_TO_FAIL = "PASS_TO_FAIL"

# Evaluation Log Constants
APPLY_PATCH_FAIL = ">>>>> Patch Apply Failed"
APPLY_PATCH_PASS = ">>>>> Applied Patch"
INSTALL_FAIL = ">>>>> Init Failed"
INSTALL_PASS = ">>>>> Init Succeeded"
RESET_FAILED = ">>>>> Reset Failed"
TESTS_TIMEOUT = ">>>>> Tests Timed Out"
TESTS_ERROR = ">>>>> Tests Errored"

get_file_name_from_lp = lambda x: x.rsplit("/", 1)[-1]
get_id_from_lp = lambda x: get_file_name_from_lp(x).split(".")[0]
get_repo_from_lp = lambda x: get_id_from_lp(x).rsplit("-", 1)[0].replace("__", "/")

test_passed = lambda case, sm: case in sm and sm[case] == TestStatus.PASSED.value

test_failed = lambda case, sm: case not in sm or any(
    [sm[case] == status for status in [TestStatus.FAILED.value, TestStatus.ERROR.value]]
)


class TestStatus(Enum):
    FAILED = "FAILED"
    PASSED = "PASSED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


# FROM metrics
class ResolvedStatus(Enum):
    NO = "RESOLVED_NO"
    PARTIAL = "RESOLVED_PARTIAL"
    FULL = "RESOLVED_FULL"

def compute_fail_to_pass(report: dict) -> float:
    """
    Compute fail-to-pass metric. Accepts single report as argument.
    """
    total = len(report[FAIL_TO_PASS]["success"]) + len(report[FAIL_TO_PASS]["failure"])
    if total == 0:
        return 1
    return len(report[FAIL_TO_PASS]["success"]) / total

def compute_pass_to_pass(report: dict) -> float:
    """
    Compute pass-to-pass metric. Accepts single report as argument.
    """
    total = len(report[PASS_TO_PASS]["success"]) + len(report[PASS_TO_PASS]["failure"])
    if total == 0:
        # TODO: Don't factor in p2p metrics
        return 1
    return len(report[PASS_TO_PASS]["success"]) / total

def compute_fail_to_pass_unweighted(reports: list[dict]) -> float:
    """
    Compute unweighted fail-to-pass metric. Accepts list of reports as argument.
    """
    if len(reports) == 0:
        return 0
    return mean([compute_fail_to_pass(r) for r in reports])

def compute_fail_to_pass_weighted(reports: list[dict]) -> float:
    """
    Compute weighted fail-to-pass metric. Accepts list of reports as argument.
    """
    report_all = {
        FAIL_TO_PASS: {
            "success": [x for r in reports for x in r[FAIL_TO_PASS]["success"]],
            "failure": [x for r in reports for x in r[FAIL_TO_PASS]["failure"]],
        },
    }
    return compute_fail_to_pass(report_all)


def compute_pass_to_pass_unweighted(reports: list[dict]) -> float:
    """
    Compute unweighted pass-to-pass metric. Accepts list of reports as argument.
    """
    if len(reports) == 0:
        return 0
    return mean([compute_pass_to_pass(r) for r in reports])

def compute_pass_to_pass_weighted(reports: list[dict]) -> float:
    """
    Compute weighted pass-to-pass metric. Accepts list of reports as argument.
    """
    report_all = {
        PASS_TO_PASS: {
            "success": [x for r in reports for x in r[PASS_TO_PASS]["success"]],
            "failure": [x for r in reports for x in r[PASS_TO_PASS]["failure"]],
        },
    }
    return compute_pass_to_pass(report_all)

def get_resolution_status(report: dict) -> str:
    """
    Determine resolved status of an evaluation instance

    Criteria:
        - If fail-to-pass (Resolution) = 1 and pass-to-pass (Maintenance) = 1 -> FULL
        - If (fail-to-pass (Resolution) < 1 and > 0) and pass-to-pass (Maintenance) = 1 -> PARTIAL
        - Otherwise -> NO
    """
    f2p = compute_fail_to_pass(report)
    p2p = compute_pass_to_pass(report)

    if f2p == 1 and p2p == 1:
        return ResolvedStatus.FULL.value
    elif f2p < 1 and f2p > 0 and p2p == 1:
        return ResolvedStatus.PARTIAL.value
    else:
        return ResolvedStatus.NO.value


def get_eval_report(
    eval_sm: dict,
    gold_results: dict,
    calculate_to_fail: bool = False
) -> dict:
    """
    Create a report based on failure/pass change from gold results to eval results.

    Args:
        eval_sm (dict): evaluation status map
        gold_results (dict): gold results
        calculate_to_fail (bool): whether to calculate metrics for "x to fail" tests
    Returns:
        report (dict): report of metrics

    Metric Definitions (Gold Result Pair + Eval Result):
    - Fail-Pass (F2P) + P: Success (Resolution)
    - Pass-Pass (P2P) + P: Success (Maintenance)
    - Fail-Pass (F2P) + F: Failure
    - Pass-Pass (P2P) + F: Failure

    Miscellaneous Definitions
    - Fail-Fail (F2F) + F: Failure Maintenance
    - Pass-Fail (P2F) + F: Not considered
    - Fail-Fail (F2F) + P: Success (Extra Credit)
    - Pass-Fail (P2F) + P: Not considered
    """
    # Calculate resolution metrics
    f2p_success = []
    f2p_failure = []
    for test_case in gold_results[FAIL_TO_PASS]:
        if test_passed(test_case, eval_sm):
            # Assume silent success for now (test case not in eval_sm)
            f2p_success.append(test_case)
        elif test_failed(test_case, eval_sm):
            f2p_failure.append(test_case)

    # Calculate maintenance metrics
    p2p_success = []
    p2p_failure = []

    missing_p2p_testcase_bar = 5
    for test_case in gold_results[PASS_TO_PASS]:
        # print(test_case)
        if test_passed(test_case, eval_sm):
            p2p_success.append(test_case)

        elif test_case not in eval_sm and missing_p2p_testcase_bar > 0:
            missing_p2p_testcase_bar -= 1
            # print(missing_p2p_testcase_bar)
        elif test_failed(test_case, eval_sm):
            # print(test_case in eval_sm)
            # print(test_case)
            p2p_failure.append(test_case)

    results = {
        FAIL_TO_PASS: {
            "success": f2p_success,
            "failure": f2p_failure,
        },
        PASS_TO_PASS: {
            "success": p2p_success,
            "failure": p2p_failure,
        },
    }

    f2f_success = []
    f2f_failure = []
    p2f_success = []
    p2f_failure = []

    results.update(
        {
            FAIL_TO_FAIL: {
                "success": f2f_success,
                "failure": f2f_failure,
            },
            PASS_TO_FAIL: {
                "success": p2f_success,
                "failure": p2f_failure,
            },
        }
    )
    return results


def get_eval_report_for_log(
    instance: dict,
    eval_log_path: str
):
    """
    Wrapper for getting eval report for a list of evaluation log paths.

    Args:
        eval_logs (list): list of paths to evaluation logs
        swe_bench_tasks (str): path to eval task instances (swe-bench.json)
        callback (callable): callback function for evaluation logs
        verbose (bool): whether to print verbose output
    Returns:
        reports_patch_success (dict): dict of eval reports for patch apply successes
        reports_patch_failure (dict): dict of eval reports for patch apply failures
    """
    with open(eval_log_path, "r") as f:
        eval_log = f.read()

    repo = instance["repo"]    
    log_parser = MAP_REPO_TO_PARSER[repo]
    eval_sm = log_parser(eval_log)

    # Compare eval status map and gold status map
    report = get_eval_report(eval_sm, instance)

    status = get_resolution_status(report)
    report["status"] = status
    return report
