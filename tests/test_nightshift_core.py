from pathlib import Path

from src.config import NightshiftConfig, ProjectConfig, _project_path_from_env_or_default
from src.diff_report import DiffReportGenerator
from src.model_manager import ModelConfig
from src.models import Finding, FindingSeverity, TaskType
from src.runner import NightshiftRunner
from src.task_queue import TaskQueue


def _make_config(tmp_path: Path, priority_mode: str = "balanced") -> NightshiftConfig:
    return NightshiftConfig(
        projects=[],
        data_dir=tmp_path / "data",
        reports_dir=tmp_path / "reports",
        priority_mode=priority_mode,
        open_report_in_browser=False,
    )


def test_task_queue_scopes_to_current_run(tmp_path):
    config = _make_config(tmp_path)
    queue = TaskQueue(config)
    project = ProjectConfig(name="demo", path=tmp_path)

    run1 = queue.create_run()
    queue.generate_tasks_for_project(project)
    first_run1_task = queue.get_next_pending_task(run_id=run1)
    assert first_run1_task is not None
    queue.mark_in_progress(first_run1_task.id, "openai/test")
    queue.mark_completed(first_run1_task.id, tokens_used=10, raw_output="[]")

    run2 = queue.create_run()
    queue.generate_tasks_for_project(project)

    # Current run context is run2, so counters and pending queue should not leak from run1.
    assert queue.get_pending_count() == 11
    assert queue.get_statistics()["completed"] == 0
    assert queue.get_statistics(run_id=run1)["completed"] == 1

    next_task = queue.get_next_pending_task()
    assert next_task is not None
    assert next_task.run_id == run2

    queue.close()


def test_runner_applies_priority_mode_security_first(tmp_path):
    project_path = tmp_path / "project"
    project_path.mkdir()
    config = NightshiftConfig(
        projects=[ProjectConfig(name="project", path=project_path)],
        data_dir=tmp_path / "data",
        reports_dir=tmp_path / "reports",
        priority_mode="security_first",
        open_report_in_browser=False,
    )

    runner = NightshiftRunner(config)
    runner.setup_tasks()
    first_task = runner.task_queue.get_next_pending_task(run_id=runner.run_id)

    assert first_task is not None
    assert first_task.task_type == TaskType.SECURITY_REVIEW
    runner.task_queue.close()


def test_runner_passes_project_path_into_agent_call(tmp_path):
    project_path = tmp_path / "project"
    project_path.mkdir()
    config = NightshiftConfig(
        projects=[ProjectConfig(name="project", path=project_path)],
        data_dir=tmp_path / "data",
        reports_dir=tmp_path / "reports",
        open_report_in_browser=False,
    )

    runner = NightshiftRunner(config)
    runner.setup_tasks()
    task = runner.task_queue.get_next_pending_task(run_id=runner.run_id)
    assert task is not None

    captured = {}

    def fake_call_agent(agent_type, prompt, model, project_path=None):
        captured["project_path"] = project_path
        return "[]"

    runner._call_opencode_agent = fake_call_agent  # type: ignore[method-assign]
    runner._execute_task(task, ModelConfig(provider="openai", model_id="test-model"))

    assert captured["project_path"] == task.project_path
    stats = runner.task_queue.get_statistics(run_id=runner.run_id)
    assert stats["completed"] == 1
    runner.task_queue.close()


def _create_run_with_finding(queue: TaskQueue, project: ProjectConfig, title: str):
    run_id = queue.create_run()
    tasks = queue.generate_tasks_for_project(project)
    task = tasks[0]

    finding = Finding(
        id=f"finding_{title.lower().replace(' ', '_')}",
        severity=FindingSeverity.HIGH,
        title=title,
        description=f"{title} description",
    )

    queue.mark_in_progress(task.id, "openai/test")
    queue.mark_completed(task.id, tokens_used=100, raw_output="[]")
    queue.save_finding(task.id, finding)
    queue.finalize_run(run_id=run_id)
    return run_id, finding


def test_diff_uses_previous_run_for_default_baseline(tmp_path):
    config = _make_config(tmp_path)
    queue = TaskQueue(config)
    project = ProjectConfig(name="demo", path=tmp_path)

    run1, finding1 = _create_run_with_finding(queue, project, "First issue")
    run2, finding2 = _create_run_with_finding(queue, project, "Second issue")
    queue.close()

    diff_generator = DiffReportGenerator(config)
    diff_generator.record_run(run1, [finding1])
    diff_generator.record_run(run2, [finding2])

    diff = diff_generator.compute_diff([finding2], current_run_id=run2)

    assert [f.title for f in diff.new_findings] == ["Second issue"]
    assert [f.title for f in diff.fixed_findings] == ["First issue"]
    assert diff.persistent_findings == []


def test_project_path_helper_honors_env_override(monkeypatch):
    monkeypatch.setenv("NIGHTSHIFT_PROJECT_OPSORCHESTRA", "~/custom/ops")
    resolved = _project_path_from_env_or_default(
        "NIGHTSHIFT_PROJECT_OPSORCHESTRA",
        Path("/default/path"),
    )
    assert str(resolved).endswith("custom/ops")
