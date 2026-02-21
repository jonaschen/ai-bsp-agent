import pytest
from unittest.mock import MagicMock, patch

class TestSecureSandbox:
    @pytest.fixture
    def mock_docker(self):
        # Patch the entire docker module where it is used in studio.utils.sandbox
        with patch("studio.utils.sandbox.docker") as patched_docker:
            # Setup necessary exceptions and classes
            patched_docker.errors.DockerException = Exception
            patched_docker.errors.ContainerError = Exception

            client = MagicMock()
            patched_docker.from_env.return_value = client
            yield patched_docker, client

    def test_secure_sandbox_initialization(self, mock_docker):
        # Arrange
        patched_docker, mock_client = mock_docker
        from studio.utils.sandbox import SecureSandbox

        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container

        # Act
        sandbox = SecureSandbox()

        # Assert
        mock_client.containers.run.assert_called_once()
        _, kwargs = mock_client.containers.run.call_args

        # Check security constraints
        assert kwargs.get("read_only") is True
        assert kwargs.get("network_disabled") is True
        assert kwargs.get("auto_remove") is True
        # Check no shell access to host (no mounts by default)
        assert "volumes" not in kwargs or not kwargs["volumes"]

    def test_secure_sandbox_tmpfs(self, mock_docker):
        # Arrange
        patched_docker, mock_client = mock_docker
        from studio.utils.sandbox import SecureSandbox

        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container

        # Act
        sandbox = SecureSandbox()

        # Assert
        _, kwargs = mock_client.containers.run.call_args
        assert "/tmp" in kwargs.get("tmpfs", {})
        assert "/workspace" in kwargs.get("tmpfs", {})
