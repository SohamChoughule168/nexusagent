import React from "react";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./DropdownMenu";
import type { AgentDetail } from "../types";
import { Edit, Copy, Trash2, Eye, MoreVertical, Bot, Settings } from "lucide-react";

interface AgentCardProps {
  agent: AgentDetail;
  onEdit: () => void;
  onView: () => void;
  onDelete: () => void;
  onDuplicate: () => void;
}

export function AgentCard({ agent, onEdit, onView, onDelete, onDuplicate }: AgentCardProps) {
  const isActive = agent.status === "active";

  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <Bot className="h-5 w-5 text-muted-foreground" />
            <CardTitle className="text-lg font-semibold">{agent.name}</CardTitle>
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                aria-label="Open agent menu"
              >
                <MoreVertical className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={onView}>
                <Eye className="mr-2 h-4 w-4" />
                View Details
              </DropdownMenuItem>
              <DropdownMenuItem onClick={onEdit}>
                <Edit className="mr-2 h-4 w-4" />
                Edit Agent
              </DropdownMenuItem>
              <DropdownMenuItem onClick={onDuplicate}>
                <Copy className="mr-2 h-4 w-4" />
                Duplicate
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={onDelete} className="text-destructive">
                <Trash2 className="mr-2 h-4 w-4" />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </CardHeader>

      <CardContent className="pb-3">
        {agent.description ? (
          <p className="text-sm text-muted-foreground line-clamp-3">
            {agent.description}
          </p>
        ) : (
          <p className="text-sm text-muted-foreground italic">No description</p>
        )}

        <div className="mt-3 space-y-2">
          <div className="flex items-center gap-2 text-xs">
            <span className="text-muted-foreground">Model:</span>
            <span className="font-medium">
              {agent.model_name || "Not configured"}
            </span>
          </div>

          <div className="flex items-center gap-2 text-xs">
            <span className="text-muted-foreground">Knowledge Bases:</span>
            <span className="font-medium">
              {agent.knowledge_base_ids?.length ?? 0}
            </span>
          </div>

          <div className="flex items-center gap-2 text-xs">
            <span className="text-muted-foreground">Tools:</span>
            <span className="font-medium">
              {agent.enabled_tool_ids?.length ?? 0}
            </span>
          </div>
        </div>
      </CardContent>

      <CardFooter className="flex justify-between items-center pt-3">
        <Badge variant={isActive ? "default" : "secondary"}>
          {isActive ? "Active" : "Inactive"}
        </Badge>
        <Button variant="ghost" size="sm" onClick={onEdit}>
          <Settings className="mr-1 h-3 w-3" />
          Configure
        </Button>
      </CardFooter>
    </Card>
  );
}

export default AgentCard;