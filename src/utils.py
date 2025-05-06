from constants import NON_TEST_EXTS
import re
import time
import subprocess
import os
import signal
import shutil

def get_test_directives(instance: dict) -> list:
    """
    Get test directives from the test_patch of a task instance

    Args:
        instance (dict): task instance
    Returns:
        directives (list): List of test directives
    """
    # For seq2seq code repos, testing command is fixed
    if instance["repo"] == "swe-bench/humaneval":
        return ["test.py"]

    # Get test directives from test patch and remove non-test files
    diff_pat = r"diff --git a/.* b/(.*)"
    test_patch = instance["test_patch"]
    directives = re.findall(diff_pat, test_patch)
    directives = [
        d for d in directives if not any(d.endswith(ext) for ext in NON_TEST_EXTS)
    ]

    # For Django tests, remove extension + "tests/" prefix and convert slashes to dots (module referencing)
    if instance["repo"] == "django/django":
        directives_transformed = []
        for d in directives:
            d = d[: -len(".py")] if d.endswith(".py") else d
            d = d[len("tests/") :] if d.startswith("tests/") else d
            d = d.replace("/", ".")
            directives_transformed.append(d)
        directives = directives_transformed

    return directives


def execute_command(command: str, timeout: int = 60, verbose = True) -> tuple:
    start_time = time.time()
    if verbose:
        print(f"Executing command: {command}")
    try:
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            executable='/bin/bash',
            preexec_fn=os.setsid
        )

        try:
            stdout, stderr = process.communicate(timeout=timeout)
            if process.returncode != 0:
                print("CMD exec failed:")
                print(stdout)
                print("STDERR:")
                print(stderr)
            return stdout, stderr

        except subprocess.TimeoutExpired:
            duration_time = time.time() - start_time
            print(f"CMD exec timed out after {duration_time} seconds, killing process group")
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                stdout, stderr = "", "Force killed after timeout"
            return stdout, stderr

    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return "", str(e)
    
    
def backup_repo(instance: dict):
    repo_path = instance['testbed_src_path']
    if not repo_path.exists():
        raise FileNotFoundError(f"Source directory does not exist: {repo_path}")
    backup_path = instance['testbed_src_path'] + '_backup'
    if backup_path.exists():
        shutil.rmtree(backup_path)
    shutil.copytree(repo_path, backup_path, symlinks=True)
    
    
def restore_repo(instance: dict):
    backup_path = instance['testbed_src_path'] + '_backup'
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup directory does not exist: {backup_path}")
    repo_path = instance['testbed_src_path']
    if repo_path.exists():
        shutil.rmtree(repo_path)
    shutil.copytree(backup_path, repo_path, symlinks=True)


def count_lines(test_path: str) -> int:
    with open(test_path, 'r', encoding='utf-8') as file:
        return sum(1 for _ in file)


def update_history(history: str, new_entry: str) -> str:
    new_history = history + new_entry + '\n' + '='*50 + '\n'
    return new_history