import React from "react";

interface VoiceOrbProps {
  agentState: string; // idle, listening, thinking, speaking
  isRecording: boolean;
  onToggleRecording: () => void;
  disabled?: boolean;
}

export const VoiceOrb: React.FC<VoiceOrbProps> = ({
  agentState,
  isRecording,
  onToggleRecording,
  disabled = false,
}) => {
  const getStateGlow = () => {
    switch (agentState) {
      case "listening":
        return "shadow-[0_0_50px_rgba(34,197,94,0.4)] border-emerald-500 scale-105";
      case "thinking":
        return "shadow-[0_0_50px_rgba(234,179,8,0.4)] border-amber-500 animate-pulse";
      case "speaking":
        return "shadow-[0_0_60px_rgba(59,130,246,0.5)] border-blue-500 animate-bounce";
      default:
        return isRecording
          ? "shadow-[0_0_30px_rgba(99,102,241,0.3)] border-indigo-500"
          : "border-outline-variant hover:border-primary shadow-sm";
    }
  };

  const getStateLabel = () => {
    switch (agentState) {
      case "listening":
        return "Listening to you...";
      case "thinking":
        return "Analyzing claim details...";
      case "speaking":
        return "Agent is speaking...";
      default:
        return isRecording ? "Microphone active" : "Tap microphone to speak";
    }
  };

  return (
    <div className="flex flex-col items-center justify-center p-6 gap-3">
      <button
        onClick={onToggleRecording}
        disabled={disabled}
        aria-label={isRecording ? "Stop voice intake" : "Start voice intake"}
        className={`w-28 h-28 rounded-full bg-surface-container-high border-2 flex items-center justify-center transition-all duration-300 relative group ${getStateGlow()} ${
          disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer active:scale-95"
        }`}
      >
        {isRecording && (
          <span className="absolute inset-0 rounded-full bg-primary/10 animate-ping" />
        )}
        <span className="material-symbols-outlined text-4xl text-primary group-hover:scale-110 transition-transform">
          {isRecording ? "mic" : "mic_off"}
        </span>
      </button>

      <span className="text-xs font-semibold text-secondary font-label tracking-wide uppercase">
        {getStateLabel()}
      </span>
    </div>
  );
};
