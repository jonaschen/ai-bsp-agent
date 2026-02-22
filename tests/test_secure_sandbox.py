import sys
import pytest
from unittest.mock import MagicMock, patch

# --- Pre-import Mocking ---
# We must mock 'docker' before importing studio.utils.sandbox because
# the module imports docker at the top level.
if "docker" not in sys.modules:
    mock_docker = MagicMock()
    mock_docker.errors.DockerException = Exception
    mock_docker.errors.ContainerError = Exception
    sys.modules["docker"] = mock_docker
    sys.modules["docker.errors"] = mock_docker.errors
    sys.modules["docker.models.containers"] = MagicMock()

from studio.utils.sandbox import SecureSandbox

class TestSecureSandbox:
    @pytest.fixture
    def mock_client(self):
        with patch("studio.utils.sandbox.docker") as patched_docker:
            client = MagicMock()
            patched_docker.from_env.return_value = client
            yield client

    def test_secure_sandbox_init_starts_container_with_restrictions(self, mock_client):
        # Arrange
        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container

        # Act
        sandbox = SecureSandbox(image="secure-image")

        # Assert
        mock_client.containers.run.assert_called_once()
        args, kwargs = mock_client.containers.run.call_args

        assert args[0] == "secure-image"
        assert kwargs["detach"] is True
        assert kwargs["auto_remove"] is True
        assert kwargs["mem_limit"] == "256m"
        assert kwargs["network_disabled"] is True
        assert kwargs["read_only"] is True

        assert sandbox.container == mock_container

    def test_secure_sandbox_teardown(self, mock_client):
        # Arrange
        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container
        sandbox = SecureSandbox()

        # Act
        sandbox.teardown()

        # Assert
        mock_container.stop.assert_called_once()
        assert sandbox.container is None
