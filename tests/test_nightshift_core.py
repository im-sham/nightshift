from pathlib import Path
import subprocess

from src.config import (
    NightshiftConfig,
    ProjectConfig,
    _project_path_from_env_or_default,
    get_config_defaults,
    get_default_project_aliases,
    get_preferred_models,
    get_config,
    load_user_config,
    render_default_config_toml,
)
from src.diff_report import DiffReportGenerator
from src.agent_client import OpencodeAgentClient
from src.model_manager import ModelConfig
from src.models import Finding, FindingSeverity, TaskType
from src.runner import NightshiftRunner
from src.task_queue import TaskQueue
import src.model_manager as model_manager


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


def test_opencode_run_output_parser_and_subagent_mapping():
    client = OpencodeAgentClient(opencode_path="opencode")

    stream = (
        '{"type":"step_start","part":{"type":"step-start"}}\n'
        '{"type":"text","part":{"text":"["}}\n'
        '{"type":"text","part":{"text":"]"}}\n'
        '{"type":"step_finish","part":{"type":"step-finish"}}\n'
    )
    assert client._parse_run_output(stream) == "[]"

    cmd = client._build_run_command(
        agent_type="explore",
        prompt="Analyze this",
        model="openai/gpt-5",
    )
    assert "--agent" not in cmd
    assert "--model" in cmd


def test_config_file_defaults_and_aliases(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[defaults]
duration_hours = 4.5
priority_mode = "security_first"
open_report_in_browser = false

[projects]
sample_repo = "/tmp/sample-repo"

[models]
preferred = ["openai/gpt-5.2", "google/gemini-3-pro-high"]
"""
    )

    monkeypatch.setenv("NIGHTSHIFT_CONFIG_FILE", str(config_file))
    loaded = load_user_config()
    defaults = get_config_defaults(loaded)
    aliases = get_default_project_aliases(user_config=loaded)
    preferred_models = get_preferred_models(user_config=loaded)

    assert defaults["duration_hours"] == 4.5
    assert defaults["priority_mode"] == "security_first"
    assert defaults["open_report_in_browser"] is False
    assert aliases["sample_repo"] == Path("/tmp/sample-repo")
    assert [f"{m.provider}/{m.model_id}" for m in preferred_models] == [
        "openai/gpt-5.2",
        "google/gemini-3-pro-high",
    ]

    cfg = get_config(["sample_repo"])
    assert cfg.max_duration_hours == 4.5
    assert cfg.priority_mode == "security_first"
    assert cfg.open_report_in_browser is False
    assert cfg.projects[0].name == "sample_repo"


def test_render_default_config_toml_includes_sanitized_current_project(tmp_path):
    content = render_default_config_toml(tmp_path / "my cool project")
    assert "[defaults]" in content
    assert "my_cool_project" in content


def test_model_discovery_and_auto_chain(monkeypatch):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="openai/gpt-5.2\nopenai/gpt-5-nano\ngoogle/gemini-3-pro-high\n",
            stderr="",
        )

    monkeypatch.setattr(model_manager.subprocess, "run", fake_run)
    model_manager._MODEL_DISCOVERY_CACHE["timestamp"] = 0
    model_manager._MODEL_DISCOVERY_CACHE["models"] = []

    discovered = model_manager.discover_available_model_ids(refresh=True)
    assert "openai/gpt-5.2" in discovered

    manager = model_manager.create_default_manager(
        preferred_models=[ModelConfig("google", "nonexistent-model", priority=1)],
        use_discovery=True,
    )
    keys = [f"{m.provider}/{m.model_id}" for m in manager.models]
    assert keys
    assert keys[0] == "openai/gpt-5.2"
