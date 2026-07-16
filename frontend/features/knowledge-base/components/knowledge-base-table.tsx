"use client";

import * as React from "react";
import Link from "next/link";
import { Pencil, Trash2 } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatTimestamp } from "@/lib/datetime";
import type { KnowledgeBase } from "@/types/knowledge-base";

export interface KnowledgeBaseTableProps {
  knowledgeBases: KnowledgeBase[];
  onEdit: (kb: KnowledgeBase) => void;
  onDelete: (kb: KnowledgeBase) => void;
}

/**
 * Table of the tenant's knowledge bases. The name links to the KB's document
 * view; Edit / Delete act on the row. Empty state is owned by the parent
 * (dashboard) so it can render a richer placeholder.
 */
export function KnowledgeBaseTable({
  knowledgeBases,
  onEdit,
  onDelete,
}: KnowledgeBaseTableProps) {
  return (
    <div className="rounded-lg border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead className="hidden md:table-cell">Description</TableHead>
            <TableHead className="hidden lg:table-cell">Embedding</TableHead>
            <TableHead className="hidden lg:table-cell">Strategy</TableHead>
            <TableHead className="hidden sm:table-cell">Updated</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {knowledgeBases.map((kb) => (
            <TableRow key={kb.id}>
              <TableCell>
                <Link
                  href={`/knowledge-bases/${kb.id}`}
                  className="font-medium text-foreground hover:text-primary hover:underline"
                >
                  {kb.name}
                </Link>
              </TableCell>
              <TableCell className="hidden max-w-xs truncate md:table-cell text-muted-foreground">
                {kb.description || "—"}
              </TableCell>
              <TableCell className="hidden lg:table-cell">
                <Badge variant="outline" className="capitalize">
                  {kb.embedding_model}
                </Badge>
              </TableCell>
              <TableCell className="hidden capitalize lg:table-cell text-muted-foreground">
                {kb.chunk_strategy}
              </TableCell>
              <TableCell className="hidden sm:table-cell text-muted-foreground">
                {formatTimestamp(kb.updated_at ?? kb.created_at)}
              </TableCell>
              <TableCell className="text-right">
                <div className="flex justify-end gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onEdit(kb)}
                    aria-label={`Edit ${kb.name}`}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onDelete(kb)}
                    aria-label={`Delete ${kb.name}`}
                    className="text-destructive hover:text-destructive"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export default KnowledgeBaseTable;
