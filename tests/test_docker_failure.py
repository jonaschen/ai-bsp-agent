
import pytest
import docker
from unittest.mock import patch
from studio.utils.sandbox import DockerSandbox

def test_docker_connection_failure_robustness():
    """
    Simulates the FileNotFoundError and verifies that DockerSandbox handles it gracefully
    with a descriptive RuntimeError.
    """
    error_msg = "Error while fetching server API version: ('Connection aborted.', FileNotFoundError(2, 'No such file or directory'))"

    with patch("docker.from_env", side_effect=Exception(error_msg)):
        with pytest.raises(RuntimeError) as excinfo:
            sandbox = DockerSandbox()

        assert "Docker Sandbox failure: Connection to Docker daemon failed" in str(excinfo.value)
        print(f"\nCaught improved error: {excinfo.value}")

if __name__ == "__main__":
    test_docker_connection_failure_robustness()
