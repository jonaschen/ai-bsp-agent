import sys
import pytest
from unittest.mock import MagicMock, patch

# --- Pre-import Mocking ---
mock_docker = MagicMock()
mock_docker.errors.DockerException = Exception
mock_docker.errors.ContainerError = Exception
sys.modules["docker"] = mock_docker
sys.modules["docker.errors"] = mock_docker.errors
sys.modules["docker.models.containers"] = MagicMock()

# Import the classes from studio.utils.sandbox
# Note: SecureSandbox might not exist yet, so we might need to handle that or just let it fail.
# Since the goal is a failing test (Red), let's assume it should exist.
try:
    from studio.utils.sandbox import SecureSandbox, CommandResult
except ImportError:
    SecureSandbox = None

class TestSecureSandbox:
    @pytest.fixture
    def mock_client(self):
        with patch("studio.utils.sandbox.docker") as patched_docker:
            client = MagicMock()
            patched_docker.from_env.return_value = client
            yield client

    def test_secure_sandbox_constraints(self, mock_client):
        if SecureSandbox is None:
            pytest.fail("SecureSandbox class not found in studio.utils.sandbox")

        # Arrange
        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container

        # Act
        sandbox = SecureSandbox(image="secure-image")

        # Assert
        mock_client.containers.run.assert_called_once()
        _, kwargs = mock_client.containers.run.call_args

        # Check security constraints
        assert kwargs.get("image") == "secure-image" or mock_client.containers.run.call_args[0][0] == "secure-image"
        assert kwargs.get("read_only") is True
        assert kwargs.get("network_disabled") is True
        assert kwargs.get("mem_limit") == "256m"
        assert kwargs.get("auto_remove") is True

        # Check tmpfs for /workspace
        tmpfs = kwargs.get("tmpfs")
        assert tmpfs is not None
        assert "/workspace" in tmpfs

    def test_secure_sandbox_inherits_functionality(self, mock_client):
        if SecureSandbox is None:
            pytest.fail("SecureSandbox class not found in studio.utils.sandbox")

        # Arrange
        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container
        sandbox = SecureSandbox()

        mock_container.exec_run.return_value = (0, (b"log output", b""))

        # Act
        result = sandbox.run_command("cat /logs/kernel.log")

        # Assert
        assert result.exit_code == 0
        assert result.stdout == "log output"
