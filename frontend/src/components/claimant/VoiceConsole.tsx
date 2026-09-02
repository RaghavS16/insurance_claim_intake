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
  confirmed,
}) => {
  return (
    <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-white via-white/95 to-transparent pt-6 pb-4 px-4 md:px-8 flex flex-col items-center justify-end z-20">
      {/* Waveform Visualizer */}
      <div className="flex items-center gap-1.5 mb-2 h-7 opacity-85">
        <div className={`w-1.5 bg-[#0891B2] rounded-full ${isRecording ? "h-3 waveform-bar" : "h-2"}`}></div>
        <div className={`w-1.5 bg-[#0891B2] rounded-full ${isRecording ? "h-6 waveform-bar delay-1" : "h-2"}`}></div>
        <div className={`w-1.5 bg-[#0891B2] rounded-full ${isRecording ? "h-4 waveform-bar delay-2" : "h-2"}`}></div>
        <div className={`w-1.5 bg-[#0891B2] rounded-full ${isRecording ? "h-8 waveform-bar delay-3" : "h-3"}`}></div>
        <div className={`w-1.5 bg-[#0891B2] rounded-full ${isRecording ? "h-5 waveform-bar delay-4" : "h-2"}`}></div>
        <div className={`w-1.5 bg-[#0891B2] rounded-full ${isRecording ? "h-7 waveform-bar delay-5" : "h-2"}`}></div>
        <div className={`w-1.5 bg-[#0891B2] rounded-full ${isRecording ? "h-3 waveform-bar" : "h-2"}`}></div>
      </div>

      {/* Active Speech Preview Quote */}
      <div className="text-center mb-3 min-h-[18px]">
        <p className="font-body text-xs text-[#505f76] truncate max-w-md">
          {isRecording
            ? "Listening... Speak naturally to describe your claim"
            : textMode
            ? "Type your message below and press Enter"
            : "Tap the microphone to speak with your claims assistant"}
        </p>
      </div>

      {/* Text Input Drawer when in Text Mode */}
      {textMode && (
        <form onSubmit={onSendText} className="w-full max-w-lg flex items-center gap-2 mb-3">
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

      {/* Voice Controls Row */}
      <div className="flex items-center justify-center gap-4">
        <button
          type="button"
          onClick={() => setTextMode(!textMode)}
          title={textMode ? "Switch to Voice Only" : "Switch to Keyboard Input"}
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
          disabled={confirmed}
          title={isRecording ? "Mute Microphone" : "Start Speaking"}
          className={`w-16 h-16 rounded-full text-white flex items-center justify-center relative z-10 transition-all cursor-pointer shadow-md ${
            isRecording
              ? "bg-[#0891B2] pulse-ring scale-105"
              : "bg-[#0891B2] hover:bg-[#007f9d]"
          } disabled:opacity-50`}
        >
          <span className="material-symbols-outlined fill text-2xl" style={{ fontVariationSettings: "'FILL' 1" }}>
            {isRecording ? "mic" : "mic_none"}
          </span>
        </button>

        <button
          type="button"
          onClick={onStopAudio}
          title="Stop Audio / Reset"
          className="w-10 h-10 rounded-full bg-[#f7f9fb] border border-[#bdc8ce] flex items-center justify-center text-[#505f76] hover:bg-[#eceef0] transition-colors cursor-pointer"
        >
          <span className="material-symbols-outlined text-sm">stop</span>
        </button>
      </div>
    </div>
  );
};
