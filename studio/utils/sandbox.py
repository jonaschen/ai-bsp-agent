"""
studio/utils/sandbox.py
-----------------------
The "Environment" Module.
Provides a secure, isolated sandbox for the Engineer/QA Agents to compile code and run tests.

Key Features:
1. Protocol Definition: Abstract Interface for any Execution Environment (Docker, E2B, Local).
2. Concrete Implementation: Ephemeral Docker Containers.
3. Security: Network isolation (optional) and resource limits.

Dependencies:
- docker (pip install docker)
- pydantic
"""

import logging
import tarfile
import io
import time
from typing import Protocol, List, Dict, Optional, Tuple
from pydantic import BaseModel, Field

logger = logging.getLogger("studio.utils.sandbox")

# Try to import docker, handle missing dependency for scaffolding
try:
    import docker
    from docker.errors import DockerException, ContainerError
    from docker.models.containers import Container
except ImportError:
    docker = None

# --- SECTION 1: Data Models (The Result Contracts) ---

class CommandResult(BaseModel):
    """Raw output from a shell command."""
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float

class TestRunResult(BaseModel):
    """Structured result of a QA test suite."""
    test_id: str
    passed: bool
    total_tests: int
    failed_tests: int
    error_log: Optional[str] = None
    duration_ms: float

# --- SECTION 2: The Interface Protocol (Dependency Inversion) ---

class SandboxEnvironment(Protocol):
    """
    Abstract Base Class for the Execution Environment.
    The QA Agent depends on THIS, not on Docker directly.
    """

    def setup_workspace(self, files: Dict[str, str]) -> bool:
        """Initialize the environment with source code."""
        ...

    def install_dependencies(self, requirements: List[str]) -> CommandResult:
        """pip install or apt-get install."""
        ...

    def run_command(self, command: str, timeout: int = 30) -> CommandResult:
        """Execute arbitrary shell command."""
        ...

    def run_pytest(self, test_path: str) -> TestRunResult:
        """Run pytest and parse results."""
        ...

    def teardown(self):
        """Clean up resources (kill container)."""
        ...

# --- SECTION 3: Concrete Implementation (Docker) ---

class DockerSandbox:
    """
    A disposable Docker container for running untrusted AI code.
    """
    def __init__(self, image: str = "python:3.10-slim", timeout_sec: int = 60):
        if not docker:
            raise ImportError("Docker SDK not found. Run `pip install docker`.")

        self.client = docker.from_env()
        self.image = image
        self.timeout = timeout_sec
        self.container: Optional[Container] = None
        self._start_container()

    def _start_container(self):
        """Boots an ephemeral container."""
        try:
            logger.info(f"Booting Sandbox ({self.image})...")
            self.container = self.client.containers.run(
                self.image,
                command="tail -f /dev/null", # Keep alive
                detach=True,
                auto_remove=True, # Cleanup on stop
                mem_limit="512m", # Resource constraint
                network_disabled=False # Enable if pip install is needed
            )
            # Basic setup
            self.container.exec_run("mkdir -p /workspace")
        except DockerException as e:
            logger.critical(f"Failed to start Docker Sandbox: {e}")
            raise

    def setup_workspace(self, files: Dict[str, str]) -> bool:
        """
        Injects code into the container.
        """
        if not self.container:
            raise RuntimeError("Sandbox not running.")

        # Create a tarball in memory
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w') as tar:
            for filename, content in files.items():
                encoded = content.encode('utf-8')
                info = tarfile.TarInfo(name=filename)
                info.size = len(encoded)
                tar.addfile(info, io.BytesIO(encoded))

        stream.seek(0)

        # Upload tarball to /workspace
        try:
            self.container.put_archive("/workspace", stream)
            logger.info(f"Injected {len(files)} files into workspace.")
            return True
        except Exception as e:
            logger.error(f"Failed to upload workspace: {e}")
            return False

    def install_dependencies(self, requirements: List[str]) -> CommandResult:
        """
        Runs pip install.
        """
        if not requirements:
            return CommandResult(exit_code=0, stdout="", stderr="", duration_ms=0)

        packages = " ".join(requirements)
        logger.info(f"Installing: {packages}")
        return self.run_command(f"pip install {packages}")

    def run_command(self, command: str, timeout: int = 30) -> CommandResult:
        """
        Executes a shell command inside the container.
        """
        if not self.container:
            raise RuntimeError("Sandbox not running.")

        start_time = time.time()
        try:
            # Note: exec_run is distinct from running the container
            exit_code, output = self.container.exec_run(
                f"bash -c 'cd /workspace && {command}'",
                demux=True # Separate stdout/stderr
            )
            duration = (time.time() - start_time) * 1000

            stdout = output[0].decode('utf-8') if output[0] else ""
            stderr = output[1].decode('utf-8') if output[1] else ""

            return CommandResult(
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                duration_ms=duration
            )
        except Exception as e:
            return CommandResult(exit_code=-1, stdout="", stderr=str(e), duration_ms=0)

    def run_pytest(self, test_path: str) -> TestRunResult:
        """
        Specialized runner for pytest.
        """
        # Run pytest with -v (verbose) and strict error checking
        cmd = f"pytest {test_path} -v"
        result = self.run_command(cmd)

        passed = (result.exit_code == 0)

        # Simple parsing logic (could be robustified with --junitxml)
        # Assuming output like "2 passed, 1 failed"
        failed_count = result.stdout.count("FAILED")
        passed_count = result.stdout.count("PASSED")
        total = failed_count + passed_count

        return TestRunResult(
            test_id=test_path,
            passed=passed,
            total_tests=total,
            failed_tests=failed_count,
            error_log=result.stderr or result.stdout if not passed else None,
            duration_ms=result.duration_ms
        )

    def teardown(self):
        """Kills the container."""
        if self.container:
            try:
                self.container.stop()
                logger.info("Sandbox destroyed.")
            except Exception:
                pass
            self.container = None

    def __del__(self):
        self.teardown()

class SecureSandbox(DockerSandbox):
    """
    A highly restrictive version of the DockerSandbox for processing sensitive logs.
    Features:
    - Read-only root filesystem.
    - Network disabled.
    - Lower memory limit (256MB).
    - In-memory ephemeral storage (tmpfs) for /tmp and /workspace.
    """
    def _start_container(self):
        if not docker:
            raise ImportError("Docker SDK not found. Run `pip install docker`.")

        try:
            logger.info(f"Booting Secure Sandbox ({self.image})...")
            self.container = self.client.containers.run(
                self.image,
                command="tail -f /dev/null",
                detach=True,
                auto_remove=True,
                mem_limit="256m",
                network_disabled=True,
                read_only=True,
                tmpfs={
                    '/tmp': 'size=64m',
                    '/workspace': 'size=128m'
                }
            )
            # Note: /workspace is writable because it's a tmpfs mount.
        except Exception as e:
            logger.critical(f"Failed to start Secure Sandbox: {e}")
            raise
