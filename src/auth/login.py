import logging
from studio.utils.sandbox import SecureSandbox

logger = logging.getLogger(__name__)

def process_login_logs(log_data: str) -> str:
    """
    Processes login logs in a secure sandbox.
    """
    sandbox = SecureSandbox()
    try:
        # Inject the log data into the sandbox
        files = {
            "login.log": log_data,
            "analyzer.py": "import sys\nwith open('login.log', 'r') as f:\n    logs = f.read()\nfailed_count = logs.count('FAILED LOGIN')\nprint(f'Analysis Complete: {failed_count} failures detected.')"
        }
        sandbox.setup_workspace(files)

        # Run the analyzer
        result = sandbox.run_command("python3 analyzer.py")
        if result.exit_code == 0:
            return result.stdout.strip()
        else:
            return f"Error processing logs: {result.stderr}"
    finally:
        sandbox.teardown()
