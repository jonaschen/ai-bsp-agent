import pytest
import tempfile
from studio.manager import StudioManager

class TestStudioManagerRouting:
    @pytest.fixture
    def manager(self):
        # minimal setup for StudioManager, just for testing route_task
        # it requires root_dir and creates state file
        with tempfile.TemporaryDirectory() as temp_dir:
            yield StudioManager(root_dir=temp_dir)

    def test_route_architect_keywords(self, manager):
        keywords = ["fix", "bug", "feature", "implement", "logic", "code"]
        for kw in keywords:
            # Simple case
            assert manager.route_task(f"Please {kw} this") == "Architect"
            # Embedded case
            assert manager.route_task(f"I found a {kw} in the system") == "Architect"

    def test_route_optimizer_keywords(self, manager):
        keywords = ["prompt", "optimize", "tune", "meta"]
        for kw in keywords:
            assert manager.route_task(f"Please {kw} the model") == "Optimizer"

    def test_route_qa_keywords(self, manager):
        keywords = ["test", "verify", "qa", "pytest"]
        for kw in keywords:
            assert manager.route_task(f"Run {kw} suite") == "QA"

    def test_route_pm_keywords(self, manager):
        keywords = ["plan", "blueprint", "strategy"]
        for kw in keywords:
            assert manager.route_task(f"Create a {kw}") == "PM"

    def test_default_routing(self, manager):
        # No keywords match
        assert manager.route_task("This is a general task") == "Architect"
        assert manager.route_task("Make coffee") == "Architect"

    def test_case_insensitivity(self, manager):
        assert manager.route_task("FIX this BUG") == "Architect"
        assert manager.route_task("OPTIMIZE performance") == "Optimizer"
        assert manager.route_task("run TEST suite") == "QA"
        assert manager.route_task("create BLUEPRINT") == "PM"

    def test_priority_precedence(self, manager):
        # "fix" (Architect) vs "optimize" (Optimizer) -> Architect should win
        assert manager.route_task("fix and optimize the code") == "Architect"

        # "optimize" (Optimizer) vs "test" (QA) -> Optimizer should win
        assert manager.route_task("optimize the test suite") == "Optimizer"

        # "test" (QA) vs "plan" (PM) -> QA should win
        assert manager.route_task("test the plan") == "QA"
