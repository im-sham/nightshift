import subprocess
import json
import os
from pathlib import Path
from typing import Optional
import asyncio
import tempfile


class OpencodeAgentClient:
    def __init__(self, opencode_path: Optional[str] = None):
        self.opencode_path = opencode_path or self._find_opencode()
        self.server_url = "http://localhost:2345"

    def _find_opencode(self) -> str:
        result = subprocess.run(["which", "opencode"], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
        return "opencode"

    async def call_agent(
        self,
        agent_type: str,
        prompt: str,
        project_path: Optional[Path] = None,
        model: Optional[str] = None,
    ) -> dict:
        env = os.environ.copy()
        if project_path:
            env["OPENCODE_PROJECT_PATH"] = str(project_path)

        async def run_once(run_env: dict, run_model: Optional[str]) -> tuple[int, str, str, str]:
            cmd = self._build_run_command(agent_type=agent_type, prompt=prompt, model=run_model)
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(project_path) if project_path else None,
                env=run_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
            stdout_text = stdout.decode()
            stderr_text = stderr.decode()
            parsed_output = self._parse_run_output(stdout_text)
            return proc.returncode, parsed_output, stdout_text, stderr_text

        try:
            returncode, parsed_output, raw_stdout, stderr_text = await run_once(env, model)
            if returncode == 0 and parsed_output.strip():
                return {
                    "success": True,
                    "output": parsed_output,
                    "error": stderr_text.strip() or None,
                }

            if model and self._is_model_not_found(stderr_text):
                returncode, parsed_output, raw_stdout, stderr_text = await run_once(env, None)
                if returncode == 0 and parsed_output.strip():
                    return {
                        "success": True,
                        "output": parsed_output,
                        "error": stderr_text.strip() or None,
                    }

            # If local/global opencode plugins crash schema resolution, retry with isolated HOME.
            if "schema._zod.def" in stderr_text or "to-json-schema" in stderr_text:
                retry_env = env.copy()
                retry_env["HOME"] = tempfile.mkdtemp(prefix="nightshift-opencode-home-")

                returncode, parsed_output, raw_stdout, stderr_text = await run_once(retry_env, model)
                if model and self._is_model_not_found(stderr_text):
                    returncode, parsed_output, raw_stdout, stderr_text = await run_once(retry_env, None)

                if returncode == 0 and parsed_output.strip():
                    return {
                        "success": True,
                        "output": parsed_output,
                        "error": stderr_text.strip() or None,
                    }

            # Fallback for older OpenCode builds that supported the old API shape.
            legacy_request = {
                "subagent_type": agent_type,
                "prompt": prompt,
                "run_in_background": False,
            }
            legacy_cmd = [self.opencode_path]
            if model:
                legacy_cmd.extend(["--model", model])
            legacy_cmd.extend(["--api", "call_agent", json.dumps(legacy_request)])
            proc = await asyncio.create_subprocess_exec(
                *legacy_cmd,
                cwd=str(project_path) if project_path else None,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
            legacy_stdout = stdout.decode().strip()
            legacy_stderr = stderr.decode().strip()

            if proc.returncode == 0:
                return {
                    "success": True,
                    "output": legacy_stdout,
                    "error": None,
                }

            return {
                "success": False,
                "output": parsed_output or raw_stdout.strip() or legacy_stdout,
                "error": legacy_stderr or stderr_text.strip() or "Agent call failed",
            }

        except asyncio.TimeoutError:
            return {
                "success": False,
                "output": "",
                "error": "Agent call timed out after 5 minutes",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
            }

    def _parse_run_output(self, stdout_text: str) -> str:
        text_chunks: list[str] = []

        for line in stdout_text.splitlines():
            line = line.strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if event.get("type") != "text":
                continue

            part = event.get("part", {})
            text = part.get("text")
            if isinstance(text, str):
                text_chunks.append(text)

        if text_chunks:
            return "".join(text_chunks).strip()

        return stdout_text.strip()

    def _build_run_command(
        self,
        agent_type: str,
        prompt: str,
        model: Optional[str],
    ) -> list[str]:
        cmd = [self.opencode_path, "run", "--format", "json"]

        # Subagents are not valid --agent values in modern OpenCode CLI.
        primary_agent = None if agent_type in {"explore", "librarian", "oracle"} else agent_type
        if primary_agent:
            cmd.extend(["--agent", primary_agent])

        if model:
            cmd.extend(["--model", model])

        cmd.append(prompt)
        return cmd

    def _is_model_not_found(self, stderr_text: str) -> bool:
        return (
            "ProviderModelNotFoundError" in stderr_text
            or "ModelNotFoundError" in stderr_text
            or "model not found" in stderr_text.lower()
        )


    async def explore(self, prompt: str, project_path: Path) -> dict:
        return await self.call_agent("explore", prompt, project_path)

    async def librarian(self, prompt: str) -> dict:
        return await self.call_agent("librarian", prompt)

    async def oracle(self, prompt: str, project_path: Optional[Path] = None) -> dict:
        return await self.call_agent("oracle", prompt, project_path)


class MockAgentClient:
    async def call_agent(
        self,
        agent_type: str,
        prompt: str,
        project_path: Optional[Path] = None,
        model: Optional[str] = None,
    ) -> dict:
        return {
            "success": True,
            "output": json.dumps([{
                "severity": "info",
                "title": f"Analysis from {agent_type}",
                "description": f"Mock response for: {prompt[:100]}...",
                "recommendation": "This is a mock response. Configure opencode integration for real results.",
            }]),
            "error": None,
        }

    async def explore(self, prompt: str, project_path: Path) -> dict:
        return await self.call_agent("explore", prompt, project_path)

    async def librarian(self, prompt: str) -> dict:
        return await self.call_agent("librarian", prompt)

    async def oracle(self, prompt: str, project_path: Optional[Path] = None) -> dict:
        return await self.call_agent("oracle", prompt, project_path)


def get_agent_client(use_mock: bool = False):
    if use_mock:
        return MockAgentClient()
    return OpencodeAgentClient()
