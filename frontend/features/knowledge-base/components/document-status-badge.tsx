import { Badge } from "@/components/ui/badge";
import {
  documentStatusLabel,
  documentStatusVariant,
  type Document,
} from "@/types/knowledge-base";
import { cn } from "@/lib/utils";

export interface DocumentStatusBadgeProps {
  status: Document["status"];
  className?: string;
}

/**
 * Colored badge for a document's processing status (uploaded / processed /
 * indexed / failed). The variant comes from the shared type helper so the
 * dashboard and detail views stay consistent.
 */
export function DocumentStatusBadge({
  status,
  className,
}: DocumentStatusBadgeProps) {
  return (
    <Badge variant={documentStatusVariant(status)} className={cn("capitalize", className)}>
      {documentStatusLabel(status)}
    </Badge>
  );
}

export default DocumentStatusBadge;
