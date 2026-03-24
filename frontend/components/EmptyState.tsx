import { type LucideIcon } from "lucide-react";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: string;
}

export default function EmptyState({ icon: Icon, title, description }: EmptyStateProps) {
  return (
    <div className="rounded-xl border border-border bg-white p-12 text-center">
      <Icon className="mx-auto mb-4 h-12 w-12 text-muted/30" />
      <p className="text-lg font-medium text-dark">{title}</p>
      {description && (
        <p className="mt-2 text-sm text-muted">{description}</p>
      )}
    </div>
  );
}
