import { fetchApi } from "@/lib/api";
import { ErrorState } from "@/components/States";

type AgentRow = {
  agent_name: string;
  enabled: boolean;
  mode: string;
  feature_version: string;
  last_signal_at: string | null;
  sink: string;
  service_status?: string;
  reason?: string;
};

export default async function AgentsPage() {
  try {
    const agents = await fetchApi<AgentRow[]>("/api/v1/agents");
    return (
      <div>
        <h1 className="text-2xl font-bold">Agents</h1>
        <ul className="mt-4 space-y-2">
          {agents.map((agent) => (
            <li key={agent.agent_name}>
              {agent.agent_name}: {agent.enabled ? "enabled" : "disabled"} · {agent.mode} · features {agent.feature_version}
              {agent.last_signal_at ? ` · last signal ${agent.last_signal_at}` : ""}
              {agent.reason ? ` · ${agent.reason}` : ""}
            </li>
          ))}
        </ul>
      </div>
    );
  } catch (error) {
    return (
      <div>
        <h1 className="text-2xl font-bold">Agents</h1>
        <ErrorState message={error instanceof Error ? error.message : "agents_unavailable"} />
      </div>
    );
  }
}
