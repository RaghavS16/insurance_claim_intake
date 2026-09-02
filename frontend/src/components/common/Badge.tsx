import React from "react";

interface BadgeProps {
  status: string;
  variant?: "success" | "warning" | "error" | "info" | "neutral";
  size?: "sm" | "md";
}

export const Badge: React.FC<BadgeProps> = ({ status, variant = "neutral", size = "sm" }) => {
  const getColors = () => {
    switch (variant) {
      case "success":
        return "bg-emerald-500/10 text-emerald-600 border-emerald-500/20";
      case "warning":
        return "bg-amber-500/10 text-amber-600 border-amber-500/20";
      case "error":
        return "bg-rose-500/10 text-rose-600 border-rose-500/20";
      case "info":
        return "bg-sky-500/10 text-sky-600 border-sky-500/20";
      default:
        return "bg-surface-container-high text-secondary border-outline-variant";
    }
  };

  const sizeClasses = size === "sm" ? "px-2 py-0.5 text-[10px]" : "px-2.5 py-1 text-xs";

  return (
    <span
      className={`inline-flex items-center font-semibold rounded-full border ${getColors()} ${sizeClasses} uppercase tracking-wider`}
    >
      {status}
    </span>
  );
};
