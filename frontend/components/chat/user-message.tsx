import { cn } from "@/lib/utils";
import { formatTimestamp } from "@/lib/datetime";
import type { Message } from "@/types/conversation";

export interface UserMessageProps {
  message: Message;
  className?: string;
}

/** Right-aligned user message bubble. */
export function UserMessage({ message, className }: UserMessageProps) {
  return (
    <div className={cn("flex justify-end", className)}>
      <div className="flex max-w-[85%] flex-col items-end gap-1 sm:max-w-[75%]">
        <div className="rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm leading-relaxed text-primary-foreground shadow-sm">
          <p className="whitespace-pre-wrap break-words">{message.content}</p>
        </div>
        <span className="px-1 text-[11px] text-muted-foreground">
          {formatTimestamp(message.created_at)}
        </span>
      </div>
    </div>
  );
}

export default UserMessage;
