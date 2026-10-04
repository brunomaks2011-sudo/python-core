export function Field({
  label,
  name,
  error,
  ...input
}: { label: string; name: string; error?: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  const id = `f-${name}`;
  return (
    <div>
      <label className="label" htmlFor={id}>{label}</label>
      <input id={id} name={name} className="input" aria-invalid={!!error} aria-describedby={error ? `${id}-err` : undefined} {...input} />
      {error && <p id={`${id}-err`} className="field-error">{error}</p>}
    </div>
  );
}

export function FormMessage({ error, success }: { error?: string; success?: string }) {
  if (error) return <p role="alert" className="rounded-xl bg-tomato-500/10 p-3 text-sm font-bold text-tomato-600">{error}</p>;
  if (success) return <p role="status" className="rounded-xl bg-emerald-100 p-3 text-sm font-bold text-emerald-800">{success}</p>;
  return null;
}
