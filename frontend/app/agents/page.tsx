import { AgentBuilderDashboard } from "@/features/agent-builder/components/AgentBuilderDashboard";

export const metadata = {
  title: "Agent Builder",
};

/** Agent Builder module entry route. */
export default function AgentsPage() {
  return <AgentBuilderDashboard />;
}
