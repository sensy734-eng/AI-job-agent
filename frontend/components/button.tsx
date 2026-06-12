import { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
};

export function Button({ className, variant = "primary", ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex h-10 items-center justify-center gap-2 rounded-md px-4 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60",
        variant === "primary" && "bg-ink text-white hover:bg-moss",
        variant === "secondary" && "border border-ink/15 bg-white text-ink hover:border-moss hover:text-moss",
        variant === "ghost" && "text-ink hover:bg-ink/5",
        className
      )}
      {...props}
    />
  );
}
