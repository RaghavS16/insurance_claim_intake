/**
 * audio-processor.js
 *
 * AudioWorklet processor for real-time PCM16 audio capture with sequence tracking
 * and browser memory leak prevention.
 * Must be served as a static file and loaded via AudioContext.audioWorklet.addModule().
 *
 * Features:
 * - Real-time float32 to signed int16 conversion at 16kHz
 * - Monotonic packet sequence tracking and timestamps
 * - Bidirectional control port supporting 'reset', 'flush', and 'stop' commands
 * - Clean buffer reclamation on disconnection to prevent memory leaks
 */

const CHUNK_FRAMES = 2560; // 160ms chunks at 16kHz

class PCM16Processor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = new Int16Array(CHUNK_FRAMES);
    this._writeIndex = 0;
    this._seqId = 0;
    this._isActive = true;

    // Listen for lifecycle control events from main thread
    this.port.onmessage = (event) => {
      const data = event.data;
      if (!data) return;

      if (data.type === "reset" || data.type === "stop") {
        this.resetBuffer();
        if (data.type === "stop") {
          this._isActive = false;
        } else {
          this._isActive = true;
          this._seqId = 0;
        }
      } else if (data.type === "flush") {
        this.flushBuffer();
      }
    };
  }

  resetBuffer() {
    if (this._buffer) {
      this._buffer.fill(0);
    }
    this._buffer = new Int16Array(CHUNK_FRAMES);
    this._writeIndex = 0;
  }

  flushBuffer() {
    if (this._writeIndex > 0) {
      const partial = this._buffer.slice(0, this._writeIndex);
      this.port.postMessage(
        {
          type: "audio_chunk",
          seq_id: ++this._seqId,
          timestamp: Date.now(),
          buffer: partial.buffer,
        },
        [partial.buffer]
      );
      this.resetBuffer();
    }
  }

  /**
   * Convert a 32-bit float sample in [-1, 1] to a signed 16-bit integer.
   * @param {number} f32
   * @returns {number}
   */
  static floatToPCM16(f32) {
    const clamped = Math.max(-1, Math.min(1, f32));
    return clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
  }

  /**
   * Called by the audio render thread with each 128-sample block.
   * @param {Float32Array[][]} inputs
   * @param {Float32Array[][]} outputs
   * @param {Record<string, Float32Array>} parameters
   * @returns {boolean}
   */
  process(inputs, outputs, parameters) { // eslint-disable-line @typescript-eslint/no-unused-vars
    if (!this._isActive) {
      return false; // Terminate processor cleanly
    }

    const channel = inputs[0]?.[0];
    if (!channel || channel.length === 0) {
      return true;
    }

    for (let i = 0; i < channel.length; i++) {
      this._buffer[this._writeIndex++] = PCM16Processor.floatToPCM16(channel[i]);

      if (this._writeIndex >= CHUNK_FRAMES) {
        const chunk = new Int16Array(this._buffer);
        // Post raw buffer or structured message
        this.port.postMessage(chunk.buffer, [chunk.buffer]);
        this._buffer = new Int16Array(CHUNK_FRAMES);
        this._writeIndex = 0;
      }
    }

    return true;
  }
}

try {
  registerProcessor("audio-processor", PCM16Processor);
} catch {}

try {
  registerProcessor("pcm16-processor", PCM16Processor);
} catch {}

