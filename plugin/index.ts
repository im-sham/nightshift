import type { Plugin, Hooks } from "@opencode-ai/plugin";
import { z } from "zod";

const NIGHTSHIFT_API = "http://127.0.0.1:7890";

async function apiCall(endpoint: string, options: RequestInit = {}): Promise<any> {
  const response = await fetch(`${NIGHTSHIFT_API}${endpoint}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API error: ${response.status} - ${text}`);
  }
  
  return response.json();
}

const nightshiftPlugin: Plugin = async (): Promise<Hooks> => {
  return {
    tool: {
      nightshift_start: {
        description: "Start a nightshift research run on selected projects. Runs analysis overnight and generates HTML report.",
        args: ({
          projects: z.array(z.string()).describe("Project names: opsorchestra, ghost-sentry, or paths"),
          duration: z.number().optional().default(8).describe("Max duration in hours"),
          create_github_issues: z.boolean().optional().default(false).describe("Auto-create GitHub issues for critical findings"),
          priority_mode: z.enum(["balanced", "security_first", "research_heavy", "quick_scan"]).optional().default("balanced"),
          slack_webhook: z.string().optional().describe("Slack webhook URL for notifications"),
          webhook_url: z.string().optional().describe("Generic webhook URL for notifications"),
        } as any),
        async execute(args) {
          const {
            projects,
            duration,
            create_github_issues,
            priority_mode,
            slack_webhook,
            webhook_url,
          } = args as {
            projects: string[];
            duration?: number;
            create_github_issues?: boolean;
            priority_mode?: "balanced" | "security_first" | "research_heavy" | "quick_scan";
            slack_webhook?: string;
            webhook_url?: string;
          };

          const effectiveDuration = duration ?? 8;
          const effectiveCreateGithubIssues = create_github_issues ?? false;
          const effectivePriorityMode = priority_mode ?? "balanced";

          try {
            await apiCall("/start", {
              method: "POST",
              body: JSON.stringify({
                projects,
                duration_hours: effectiveDuration,
                create_github_issues: effectiveCreateGithubIssues,
                priority_mode: effectivePriorityMode,
                slack_webhook,
                webhook_url,
              }),
            });

            return `Nightshift started for: ${projects.join(", ")}
Duration: ${effectiveDuration}h
GitHub Issues: ${effectiveCreateGithubIssues}
Mode: ${effectivePriorityMode}
Slack: ${slack_webhook ? "enabled" : "disabled"}`;
          } catch (e: any) {
            return `Nightshift start failed: ${e.message}

Make sure the nightshift server is running:
  nightshift serve`;
          }
        },
      },

      nightshift_stop: {
        description: "Stop a running nightshift research run",
        args: {},
        async execute() {
          const result = await apiCall("/stop", { method: "POST" });
          return result.message || "Stop requested";
        },
      },

      nightshift_status: {
        description: "Get current nightshift run status and statistics",
        args: {},
        async execute() {
          try {
            const result = await apiCall("/status");
            const lines = [
              `Status: ${result.status}`,
              `Run ID: ${result.run_id || "none"}`,
              `Elapsed: ${result.elapsed_minutes} minutes`,
              `Tasks: ${result.completed_tasks} completed, ${result.pending_tasks} pending`,
              `Findings: ${result.total_findings}`,
            ];
            return lines.join("\n");
          } catch (e: any) {
            return `Server not running. Start with:
  nightshift serve`;
          }
        },
      },

      nightshift_report: {
        description: "Get the latest nightshift report or diff report",
        args: ({
          type: z.enum(["latest", "diff"]).optional().default("latest").describe("Report type"),
        } as any),
        async execute(args) {
          const { type } = args as { type?: "latest" | "diff" };
          const reportType = type ?? "latest";

          const endpoint = reportType === "diff" ? "/report/diff" : "/report/latest";
          await apiCall(endpoint);
          return `Nightshift ${reportType === "diff" ? "diff" : "latest"} report:
${NIGHTSHIFT_API}${endpoint}

Open in browser:
open "${NIGHTSHIFT_API}${endpoint}"`;
        },
      },

      nightshift_reports: {
        description: "List all available nightshift reports",
        args: {},
        async execute() {
          const result = await apiCall("/reports");
          const lines = result.reports.map((r: any) => `${r.name} - ${r.created}`);
          return lines.join("\n") || "No reports found";
        },
      },

      nightshift_models: {
        description: "Get model availability and performance stats",
        args: {},
        async execute() {
          const result = await apiCall("/models");
          const lines = Object.entries(result).map(([model, info]: [string, any]) => 
            `${model}: ${info.available ? "Available" : `Rate limited (${info.retry_after_seconds}s)`}`
          );
          return lines.join("\n");
        },
      },
    },
  };
};

export default nightshiftPlugin;
