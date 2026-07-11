// src/components/ui/LoadingSpinner.tsx
import { memo } from "react";

interface LoadingSpinnerProps {
  size?: "sm" | "md" | "lg";
  fullscreen?: boolean;
}

export const LoadingSpinner = memo(({ size = "md", fullscreen = false }: LoadingSpinnerProps) => {
  const sizeClasses = {
    sm: "w-6 h-6 border-2",
    md: "w-10 h-10 border-3",
    lg: "w-16 h-16 border-4",
  };

  const spinner = (
    <div
      className={`${sizeClasses[size]} border-primary border-t-transparent rounded-full animate-spin`}
      role="status"
      aria-label="Loading"
    />
  );

  if (fullscreen) {
    return (
      <div className="flex items-center justify-center min-h-screen w-full bg-background">
        {spinner}
      </div>
    );
  }

  return spinner;
});

LoadingSpinner.displayName = "LoadingSpinner";