import sys
import pytest
from unittest.mock import MagicMock, patch

# --- Pre-import Mocking ---
# We must mock 'docker' before importing studio.utils.sandbox because
# the module imports docker at the top level (in a try/except block).
mock_docker = MagicMock()
# Essential: Mock the exceptions imported via 'from docker.errors import ...'
mock_docker.errors.DockerException = Exception
mock_docker.errors.ContainerError = Exception
sys.modules["docker"] = mock_docker
sys.modules["docker.errors"] = mock_docker.errors
sys.modules["docker.models.containers"] = MagicMock()

# Now it is safe to import
from studio.utils.sandbox import DockerSandbox, CommandResult, TestRunResult, SecureSandbox

class TestDockerSandbox:
    @pytest.fixture
    def mock_client(self):
        # Since we mocked the 'docker' module in sys.modules,
        # the 'docker' name in studio.utils.sandbox refers to our mock_docker.
        # We can configure it directly or use patch on the imported module.

        # We want docker.from_env() to return a mock client.
        with patch("studio.utils.sandbox.docker") as patched_docker:
            client = MagicMock()
            patched_docker.from_env.return_value = client
            yield client

    def test_init_starts_container(self, mock_client):
        # Arrange
        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container

        # Act
        sandbox = DockerSandbox(image="test-image")

        # Assert
        mock_client.containers.run.assert_called_once()
        # Verify arguments
        args, kwargs = mock_client.containers.run.call_args
        assert args[0] == "test-image"
        assert kwargs["detach"] is True

        assert sandbox.container == mock_container
        mock_container.exec_run.assert_called_with("mkdir -p /workspace")

    def test_setup_workspace(self, mock_client):
        # Arrange
        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container
        sandbox = DockerSandbox()

        files = {"test.py": "print('hello')"}

        # Act
        result = sandbox.setup_workspace(files)

        # Assert
        assert result is True
        mock_container.put_archive.assert_called_once()
        args, _ = mock_container.put_archive.call_args
        assert args[0] == "/workspace"

    def test_install_dependencies(self, mock_client):
        # Arrange
        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container
        sandbox = DockerSandbox()

        # Mock exec_run for pip install
        # Return (exit_code, (stdout_bytes, stderr_bytes))
        mock_container.exec_run.return_value = (0, (b"Successfully installed", b""))

        # Act
        result = sandbox.install_dependencies(["numpy", "pandas"])

        # Assert
        assert result.exit_code == 0
        mock_container.exec_run.assert_called_with(
            "bash -c 'cd /workspace && pip install numpy pandas'",
            demux=True
        )

    def test_run_command_success(self, mock_client):
        # Arrange
        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container
        sandbox = DockerSandbox()

        mock_container.exec_run.return_value = (0, (b"hello world\n", b""))

        # Act
        result = sandbox.run_command("echo hello")

        # Assert
        assert result.exit_code == 0
        assert result.stdout == "hello world\n"
        assert result.stderr == ""

    def test_run_pytest_parsing(self, mock_client):
        # Arrange
        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container
        sandbox = DockerSandbox()

        # Simulate pytest -v output
        stdout_output = """
test_foo.py::test_1 PASSED
test_foo.py::test_2 PASSED
test_foo.py::test_3 FAILED
"""
        # exec_run returns (exit_code, (stdout, stderr))
        mock_container.exec_run.return_value = (1, (stdout_output.encode(), b""))

        # Act
        result = sandbox.run_pytest("tests/")

        # Assert
        assert result.passed is False
        assert result.total_tests == 3
        assert result.failed_tests == 1
        assert result.test_id == "tests/"

    def test_teardown(self, mock_client):
        # Arrange
        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container
        sandbox = DockerSandbox()

        # Act
        sandbox.teardown()

        # Assert
        mock_container.stop.assert_called_once()
        assert sandbox.container is None

class TestSecureSandbox:
    @pytest.fixture
    def mock_client(self):
        with patch("studio.utils.sandbox.docker") as patched_docker:
            client = MagicMock()
            patched_docker.from_env.return_value = client
            yield client

    def test_secure_init_constraints(self, mock_client):
        # Arrange
        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container

        # Act
        sandbox = SecureSandbox(image="secure-image")

        # Assert
        mock_client.containers.run.assert_called_once()
        args, kwargs = mock_client.containers.run.call_args

        assert args[0] == "secure-image"
        assert kwargs["read_only"] is True
        assert kwargs["network_disabled"] is True
        assert kwargs["mem_limit"] == "256m"
        assert kwargs["auto_remove"] is True

        # Verify tmpfs mounts
        assert "tmpfs" in kwargs
        tmpfs = kwargs["tmpfs"]
        assert tmpfs["/tmp"] == "size=64m"
        assert tmpfs["/workspace"] == "size=128m"
