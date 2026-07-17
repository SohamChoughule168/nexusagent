import React from "react";
import type { AgentDetail } from "../types";
import { AgentCard } from "./AgentCard";

interface AgentListProps {
  agents: AgentDetail[];
  onEdit: (agent: AgentDetail) => void;
  onView: (agent: AgentDetail) => void;
  onDelete: (agent: AgentDetail) => void;
  onDuplicate: (agent: AgentDetail) => void;
}

/** Responsive grid of agent cards. Presentational — owns no server state. */
export function AgentList({
  agents,
  onEdit,
  onView,
  onDelete,
  onDuplicate,
}: AgentListProps) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
      {agents.map((agent) => (
        <AgentCard
          key={agent.id}
          agent={agent}
          onEdit={() => onEdit(agent)}
          onView={() => onView(agent)}
          onDelete={() => onDelete(agent)}
          onDuplicate={() => onDuplicate(agent)}
        />
      ))}
    </div>
  );
}

export default AgentList;
