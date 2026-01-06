import type { Plugin, PluginInput, Hooks } from "@opencode-ai/plugin";
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

const nightshiftPlugin: Plugin = async (input: PluginInput): Promise<Hooks> => {
  const { $ } = input;

  return {
    tool: {
      nightshift_start: {
        description: "Start a nightshift research run on selected projects. Runs analysis overnight and generates HTML report.",
        parameters: z.object({
          projects: z.array(z.string()).describe("Project names: opsorchestra, ghost-sentry, or paths"),
          duration: z.number().optional().default(8).describe("Max duration in hours"),
          create_github_issues: z.boolean().optional().default(false).describe("Auto-create GitHub issues for critical findings"),
          priority_mode: z.enum(["balanced", "security_first", "research_heavy", "quick_scan"]).optional().default("balanced"),
          slack_webhook: z.string().optional().describe("Slack webhook URL for notifications"),
          webhook_url: z.string().optional().describe("Generic webhook URL for notifications"),
        }),
        async execute({ projects, duration, create_github_issues, priority_mode, slack_webhook, webhook_url }) {
          try {
            const result = await apiCall("/start", {
              method: "POST",
              body: JSON.stringify({
                projects,
                duration_hours: duration,
                create_github_issues,
                priority_mode,
                slack_webhook,
                webhook_url,
              }),
            });
            return {
              title: "Nightshift Started",
              output: `Started nightshift for: ${projects.join(", ")}\nDuration: ${duration}h\nGitHub Issues: ${create_github_issues}\nMode: ${priority_mode}\nSlack: ${slack_webhook ? "enabled" : "disabled"}`,
              metadata: result,
            };
          } catch (e: any) {
            return {
              title: "Nightshift Start Failed",
              output: `Failed to start: ${e.message}\n\nMake sure the nightshift server is running:\n  cd ~/Projects/nightshift && python -m src.cli serve`,
              metadata: { error: true },
            };
          }
        },
      },

      nightshift_stop: {
        description: "Stop a running nightshift research run",
        parameters: z.object({}),
        async execute() {
          const result = await apiCall("/stop", { method: "POST" });
          return {
            title: "Nightshift Stopped",
            output: result.message || "Stop requested",
            metadata: result,
          };
        },
      },

      nightshift_status: {
        description: "Get current nightshift run status and statistics",
        parameters: z.object({}),
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
            return {
              title: "Nightshift Status",
              output: lines.join("\n"),
              metadata: result,
            };
          } catch (e: any) {
            return {
              title: "Nightshift Status",
              output: `Server not running. Start with:\n  cd ~/Projects/nightshift && python -m src.cli serve`,
              metadata: { error: true },
            };
          }
        },
      },

      nightshift_report: {
        description: "Get the latest nightshift report or diff report",
        parameters: z.object({
          type: z.enum(["latest", "diff"]).optional().default("latest").describe("Report type"),
        }),
        async execute({ type }) {
          const endpoint = type === "diff" ? "/report/diff" : "/report/latest";
          const result = await apiCall(endpoint);
          return {
            title: `Nightshift ${type === "diff" ? "Diff" : "Latest"} Report`,
            output: `Report available at: ${NIGHTSHIFT_API}${endpoint}\n\nOpen in browser: open "${NIGHTSHIFT_API}${endpoint}"`,
            metadata: result,
          };
        },
      },

      nightshift_reports: {
        description: "List all available nightshift reports",
        parameters: z.object({}),
        async execute() {
          const result = await apiCall("/reports");
          const lines = result.reports.map((r: any) => `${r.name} - ${r.created}`);
          return {
            title: "Nightshift Reports",
            output: lines.join("\n") || "No reports found",
            metadata: result,
          };
        },
      },

      nightshift_models: {
        description: "Get model availability and performance stats",
        parameters: z.object({}),
        async execute() {
          const result = await apiCall("/models");
          const lines = Object.entries(result).map(([model, info]: [string, any]) => 
            `${model}: ${info.available ? "Available" : `Rate limited (${info.retry_after_seconds}s)`}`
          );
          return {
            title: "Nightshift Models",
            output: lines.join("\n"),
            metadata: result,
          };
        },
      },
    },
  };
};

export default nightshiftPlugin;
