import subprocess
import json
import sys
import os

def safe_json_dump(data: dict) -> str:
    """
    Safely serializes a dictionary to a JSON string, converting non-serializable
    objects (like MagicMock) to their string representation.
    """
    def json_default(obj):
        try:
            return str(obj)
        except Exception:
            return "<Unserializable Object>"

    return json.dumps(data, default=json_default, indent=2)

class QAAgent:
    """
    The Gatekeeper: Deterministic testing (pytest, lint).
    Responsibility: Enforces functional correctness and code hygiene.
    Constraint: Must be deterministic. No LLM calls.
    """
    def run_suite(self, test_path: str) -> str:
        """
        Runs the test suite using pytest and returns the result as a JSON string.
        """
        try:
            # Determine cwd and the actual test target
            if os.path.isfile(test_path):
                cwd = os.path.dirname(test_path)
                target = os.path.basename(test_path)
                python_path = cwd
            else:
                cwd = test_path
                target = "."
                python_path = cwd

            # Run pytest on the specified path
            # We use sys.executable to ensure we use the same environment
            # We set PYTHONPATH to ensure 'product' and 'studio' modules are findable
            env = os.environ.copy()
            env["PYTHONPATH"] = python_path

            result = subprocess.run(
                [sys.executable, "-m", "pytest", target],
                capture_output=True,
                text=True,
                cwd=cwd,
                env=env
            )

            status = "PASS" if result.returncode == 0 else "FAIL"
            logs = result.stdout + "\n" + result.stderr

            output = {
                "status": status,
                "logs": logs
            }

            return safe_json_dump(output)
        except Exception as e:
            return safe_json_dump({
                "status": "FAIL",
                "logs": f"Internal Error in QAAgent: {str(e)}"
            })

    def verify_prompt(self, actual_output: str, expected_keypoints: list) -> str:
        """
        Runs Semantic Similarity Checks against the 'Golden Set'.
        Note: As per AGENTS.md, this should be deterministic but also use LLM-as-a-Judge.
        To maintain deterministic constraints in the current environment, we implement
        a keyword-based check as a placeholder, which will be upgraded to a
        dedicated Judge model in production.
        """
        matched = []
        missing = []
        for kp in expected_keypoints:
            if kp.lower() in actual_output.lower():
                matched.append(kp)
            else:
                missing.append(kp)

        score = len(matched) / len(expected_keypoints) if expected_keypoints else 1.0
        status = "PASS" if score >= 0.85 else "FAIL" # 85% threshold as per Blueprint

        logs = f"Semantic Keypoint Check: {len(matched)}/{len(expected_keypoints)} matched.\n"
        logs += f"Matched: {matched}\n"
        logs += f"Missing: {missing}\n"

        return safe_json_dump({
            "status": status,
            "logs": logs,
            "score": score
        })

if __name__ == "__main__":
    try:
        # If run as a script, default to running all tests if no path provided
        path = sys.argv[1] if len(sys.argv) > 1 else "tests/"
        agent = QAAgent()
        print(agent.run_suite(path))
    except Exception as e:
        # Emergency JSON response
        error_response = {
            "status": "FATAL_ERROR",
            "message": f"Internal Error in QAAgent: {str(e)}",
            "files_checked": []
        }
        print(safe_json_dump(error_response))
        sys.exit(1)
