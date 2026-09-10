import React from "react";

interface VoiceConsoleProps {
  isRecording: boolean;
  textMode: boolean;
  setTextMode: (v: boolean) => void;
  textInput: string;
  setTextInput: (v: string) => void;
  onSendText: (e: React.FormEvent) => void;
  onToggleMic: () => void;
  onStopAudio: () => void;
  confirmed: boolean;
  showScrollBottom?: boolean;
  onScrollToBottom?: () => void;
}

export const VoiceConsole: React.FC<VoiceConsoleProps> = ({
  isRecording,
  textMode,
  setTextMode,
  textInput,
  setTextInput,
  onSendText,
  onToggleMic,
  onStopAudio,
  showScrollBottom,
  onScrollToBottom,
}) => (
  <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-white via-white/95 to-transparent pt-3 pb-4 px-4 md:px-8 flex flex-col items-center justify-end z-20 pointer-events-none">
    {/* Floating Scroll to latest button placed directly above the waveform audio visualizer */}
    {showScrollBottom && onScrollToBottom && (
      <button
        type="button"
        onClick={onScrollToBottom}
        className="pointer-events-auto mb-2.5 flex items-center gap-1.5 bg-[#00647c] hover:bg-[#004e61] text-white shadow-md hover:shadow-xl rounded-full px-4 py-1.5 text-xs font-semibold transition-all duration-200 cursor-pointer active:scale-95 group animate-bounce ring-2 ring-white"
      >
        <span className="material-symbols-outlined text-sm transition-transform group-hover:translate-y-0.5">
          arrow_downward
        </span>
        <span>Scroll to latest</span>
      </button>
    )}

    {/* Audio Waveform Dots Visualizer */}
    <div className="flex items-center gap-1.5 mb-2 h-7 opacity-85 pointer-events-auto">
      {[3, 6, 4, 8, 5, 7, 3].map((h, i) => (
        <div
          key={i}
          className={`w-1.5 bg-[#0891B2] rounded-full ${
            isRecording ? `h-${h} waveform-bar delay-${i + 1}` : i === 3 ? "h-3" : "h-2"
          }`}
        />
      ))}
    </div>

    {/* Hint text */}
    <div className="text-center mb-3 min-h-[18px] pointer-events-auto">
      <p className="font-body text-xs text-[#505f76] truncate max-w-md">
        {isRecording
          ? "Listening… Speak naturally; pauses are okay"
          : textMode
          ? "Type your message below and press Enter"
          : "Tap the microphone to speak with your claims assistant"}
      </p>
    </div>

    {/* Text input mode form */}
    {textMode && (
      <form onSubmit={onSendText} className="w-full max-w-lg flex items-center gap-2 mb-3 pointer-events-auto">
        <input
          type="text"
          placeholder="Type incident details, dates, or estimates..."
          value={textInput}
          onChange={(e) => setTextInput(e.target.value)}
          className="input-minimal flex-1 bg-[#f7f9fb] border border-[#bdc8ce] rounded-full px-4 py-2 text-sm text-[#191c1e] placeholder:text-[#6e797e]"
        />
        <button
          type="submit"
          className="w-10 h-10 rounded-full bg-[#0891B2] hover:bg-[#007f9d] text-white flex items-center justify-center shrink-0 transition-colors cursor-pointer"
        >
          <span className="material-symbols-outlined text-base">send</span>
        </button>
      </form>
    )}

    {/* Control Action Buttons */}
    <div className="flex items-center justify-center gap-4 pointer-events-auto">
      <button
        type="button"
        onClick={() => setTextMode(!textMode)}
        title={textMode ? "Switch to Voice" : "Switch to Keyboard"}
        className={`w-10 h-10 rounded-full flex items-center justify-center transition-colors cursor-pointer border ${
          textMode
            ? "bg-[#0891B2] text-white border-[#0891B2]"
            : "bg-[#f7f9fb] text-[#505f76] hover:bg-[#eceef0] border-[#bdc8ce]"
        }`}
      >
        <span className="material-symbols-outlined text-sm">keyboard</span>
      </button>
      <button
        type="button"
        onClick={onToggleMic}
        title={isRecording ? "Stop listening" : "Start speaking"}
        className={`w-16 h-16 rounded-full text-white flex items-center justify-center relative z-10 transition-all cursor-pointer shadow-md ${
          isRecording ? "bg-[#0891B2] pulse-ring scale-105" : "bg-[#0891B2] hover:bg-[#007f9d]"
        }`}
      >
        <span
          className="material-symbols-outlined fill text-2xl"
          style={{ fontVariationSettings: "'FILL' 1" }}
        >
          {isRecording ? "mic" : "mic_none"}
        </span>
      </button>
      <button
        type="button"
        onClick={onStopAudio}
        title="Stop assistant speaking"
        aria-label="Stop assistant speaking"
        className="w-10 h-10 rounded-full bg-[#f7f9fb] border border-[#bdc8ce] flex items-center justify-center text-[#505f76] hover:bg-[#eceef0] transition-colors cursor-pointer"
      >
        <span className="material-symbols-outlined text-sm">volume_off</span>
      </button>
    </div>
  </div>
);

