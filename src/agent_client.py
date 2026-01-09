import subprocess
import json
import os
from pathlib import Path
from typing import Optional
import asyncio


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
        request = {
            "subagent_type": agent_type,
            "prompt": prompt,
            "run_in_background": False,
        }

        env = os.environ.copy()
        if project_path:
            env["OPENCODE_PROJECT_PATH"] = str(project_path)

        cmd = [self.opencode_path]
        if model:
            cmd.extend(["--model", model])
        cmd.extend(["--api", "call_agent", json.dumps(request)])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(project_path) if project_path else None,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

            if proc.returncode == 0:
                return {
                    "success": True,
                    "output": stdout.decode(),
                    "error": None,
                }

            return {
                "success": False,
                "output": stdout.decode(),
                "error": stderr.decode(),
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
