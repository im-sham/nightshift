from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import json
import subprocess
import re

from .models import Finding, FindingSeverity
from .config import ProjectConfig


@dataclass
class DependencyInfo:
    name: str
    current_version: str
    latest_version: Optional[str] = None
    source_file: Optional[str] = None
    project: Optional[str] = None


@dataclass
class CrossProjectAnalyzer:
    projects: list[ProjectConfig]

    def analyze_shared_dependencies(self) -> list[Finding]:
        findings = []
        all_deps = {}
        
        for project in self.projects:
            deps = self._extract_dependencies(project)
            for dep in deps:
                key = dep.name.lower()
                if key not in all_deps:
                    all_deps[key] = []
                all_deps[key].append(dep)
        
        for dep_name, instances in all_deps.items():
            if len(instances) > 1:
                versions = set(d.current_version for d in instances)
                if len(versions) > 1:
                    projects_str = ", ".join(d.project for d in instances)
                    versions_str = ", ".join(f"{d.project}: {d.current_version}" for d in instances)
                    
                    findings.append(Finding(
                        id=f"dep_conflict_{dep_name}",
                        severity=FindingSeverity.MEDIUM,
                        title=f"Version mismatch: {dep_name}",
                        description=f"Dependency '{dep_name}' has different versions across projects: {versions_str}",
                        location=projects_str,
                        recommendation=f"Align {dep_name} versions across projects to avoid compatibility issues",
                    ))
        
        return findings

    def _extract_dependencies(self, project: ProjectConfig) -> list[DependencyInfo]:
        deps = []
        
        pyproject = project.path / "pyproject.toml"
        if pyproject.exists():
            deps.extend(self._parse_pyproject(pyproject, project.name))
        
        requirements = project.path / "requirements.txt"
        if requirements.exists():
            deps.extend(self._parse_requirements(requirements, project.name))
        
        package_json = project.path / "package.json"
        if package_json.exists():
            deps.extend(self._parse_package_json(package_json, project.name))
        
        return deps

    def _parse_pyproject(self, path: Path, project_name: str) -> list[DependencyInfo]:
        deps = []
        content = path.read_text()
        
        pattern = r'"([a-zA-Z0-9_-]+)([><=!]+[^"]+)?"'
        in_deps = False
        
        for line in content.split("\n"):
            if "dependencies" in line.lower():
                in_deps = True
            elif in_deps and line.strip().startswith("]"):
                in_deps = False
            elif in_deps:
                match = re.search(pattern, line)
                if match:
                    name = match.group(1)
                    version = match.group(2) or "any"
                    deps.append(DependencyInfo(
                        name=name,
                        current_version=version.strip(),
                        source_file=str(path),
                        project=project_name
                    ))
        
        return deps

    def _parse_requirements(self, path: Path, project_name: str) -> list[DependencyInfo]:
        deps = []
        content = path.read_text()
        
        for line in content.split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                match = re.match(r"([a-zA-Z0-9_-]+)([><=!]+.+)?", line)
                if match:
                    deps.append(DependencyInfo(
                        name=match.group(1),
                        current_version=match.group(2) or "any",
                        source_file=str(path),
                        project=project_name
                    ))
        
        return deps

    def _parse_package_json(self, path: Path, project_name: str) -> list[DependencyInfo]:
        deps = []
        content = json.loads(path.read_text())
        
        for dep_type in ("dependencies", "devDependencies"):
            if dep_type in content:
                for name, version in content[dep_type].items():
                    deps.append(DependencyInfo(
                        name=name,
                        current_version=version,
                        source_file=str(path),
                        project=project_name
                    ))
        
        return deps

    def find_shared_code_opportunities(self) -> list[Finding]:
        findings = []
        
        common_patterns = {}
        for project in self.projects:
            for pattern in ["utils", "helpers", "common", "shared", "lib"]:
                matches = list(project.path.rglob(f"*{pattern}*"))
                for match in matches:
                    if match.is_dir() and "__pycache__" not in str(match):
                        key = match.name.lower()
                        if key not in common_patterns:
                            common_patterns[key] = []
                        common_patterns[key].append((project.name, str(match)))
        
        for pattern, locations in common_patterns.items():
            if len(locations) > 1:
                projects_str = ", ".join(loc[0] for loc in locations)
                findings.append(Finding(
                    id=f"shared_code_{pattern}",
                    severity=FindingSeverity.LOW,
                    title=f"Potential shared code: {pattern}",
                    description=f"Both projects have '{pattern}' directories. Consider extracting shared utilities to a common package.",
                    location=projects_str,
                    recommendation=f"Evaluate if code in '{pattern}' directories can be shared between projects",
                ))
        
        return findings
