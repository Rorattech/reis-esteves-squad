interface LoadingStateProps {
  label?: string;
}

export function LoadingState({ label = "Carregando..." }: LoadingStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-slate-500">
      <div
        className="h-6 w-6 animate-spin rounded-full border-2 border-slate-300 border-t-slate-600"
        role="status"
        aria-label={label}
      />
      <p className="text-sm">{label}</p>
    </div>
  );
}
