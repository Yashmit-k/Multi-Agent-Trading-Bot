import { NotAvailableState } from "@/components/States";

export default function AgentsPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold">Agents</h1>
      <NotAvailableState feature="GET /api/v1/agents" />
    </div>
  );
}
