import { AgentTrace } from "@/components/trace/AgentTrace";
import { PageFrame } from "@/components/shell/PageFrame";

export default function TracePage() {
  return (
    <PageFrame
      title="Agent trace"
      description="Every message the agents put on the Redis event buses, as recorded by the trace recorder. Quant agents are deterministic rules, intelligence agents use an LLM, and the core stages are code. Agents give opinions; code makes the decision."
    >
      <AgentTrace />
    </PageFrame>
  );
}
