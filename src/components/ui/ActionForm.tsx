"use client";

import { useTransition } from "react";

/**
 * <form> для Server Actions, що НЕ скидає введені дані після відправки
 * (React 19 автоматично очищує форми з action). Без JS працює як звичайна форма.
 */
export function ActionForm({
  action,
  onSubmit,
  ...props
}: Omit<React.FormHTMLAttributes<HTMLFormElement>, "action"> & { action: (fd: FormData) => void }) {
  const [, start] = useTransition();
  return (
    <form
      {...props}
      action={action}
      onSubmit={(e) => {
        onSubmit?.(e);
        if (e.defaultPrevented) return;
        e.preventDefault();
        const fd = new FormData(e.currentTarget, (e.nativeEvent as SubmitEvent).submitter);
        start(() => action(fd));
      }}
    />
  );
}
