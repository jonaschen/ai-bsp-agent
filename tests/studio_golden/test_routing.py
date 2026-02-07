import pytest
from studio.manager import StudioManager

def test_routing_logic():
    mgr = StudioManager()

    # Test PM routing
    assert mgr.route_task("Feature request: add log parsing") == "PM"
    assert mgr.route_task("We need a new blueprint for the Screener") == "PM"
    assert mgr.route_task("Plan the next evolution step") == "PM"
    assert mgr.route_task("Update product strategy") == "PM"

    # Test Architect routing
    assert mgr.route_task("Fix the bug in dmesg parser") == "Architect"
    assert mgr.route_task("Implement the Librarian agent") == "Architect"
    assert mgr.route_task("Update the logic for stack unwinding") == "Architect"
    assert mgr.route_task("Add code for register lookup") == "Architect"

    # Test Optimizer routing
    assert mgr.route_task("Optimize the SYSTEM_PROMPT for Pathologist") == "Optimizer"
    assert mgr.route_task("Tune the meta-prompting loop") == "Optimizer"

    # Test QA routing
    assert mgr.route_task("Run pytest for all agents") == "QA"
    assert mgr.route_task("Verify the Librarian's output") == "QA"

    # Default
    assert mgr.route_task("Something unknown") == "Architect"
