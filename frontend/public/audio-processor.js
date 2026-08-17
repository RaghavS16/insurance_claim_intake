/**
 * audio-processor.js
 *
 * AudioWorklet processor for real-time PCM16 audio capture.
 * Must be served as a static file and loaded via AudioContext.audioWorklet.addModule().
 *
 * Converts 32-bit float samples from the AudioContext to PCM16 (Int16Array),
 * then sends the raw buffer to the main thread via this.port.postMessage().
 *
 * The main thread WebSocket handler forwards the buffer directly to the server.
 * No resampling is done here — the AudioContext is created at 16000 Hz.
 *
 * Design notes:
 *  - AudioWorklet runs on the audio render thread, not the main thread.
 *  - process() is called with 128-sample blocks (128 / 16000 = 8ms per block).
 *  - We accumulate blocks until we have at least CHUNK_FRAMES (160ms worth = 2560 frames)
 *    before posting, to reduce postMessage overhead.
 *  - CHUNK_FRAMES is kept small enough that latency is < 200ms.
 */

// CHUNK_FRAMES: 160ms chunks to reduce postMessage overhead
// AudioContext is created at 16000Hz on the main thread
const CHUNK_FRAMES = 2560;

class PCM16Processor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = new Int16Array(CHUNK_FRAMES);
    this._writeIndex = 0;
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
   * @param {Float32Array[][]} inputs  - inputs[0][0] = first channel of first input
   * @param {Float32Array[][]} outputs - unused (passthrough is not needed)
   * @param {Record<string, Float32Array>} parameters - unused
   * @returns {boolean} - true to keep processor alive
   */
  process(inputs, outputs, parameters) { // eslint-disable-line @typescript-eslint/no-unused-vars
    const channel = inputs[0]?.[0];
    if (!channel || channel.length === 0) {
      return true;
    }

    for (let i = 0; i < channel.length; i++) {
      this._buffer[this._writeIndex++] = PCM16Processor.floatToPCM16(channel[i]);

      if (this._writeIndex >= CHUNK_FRAMES) {
        // Copy and post — avoid transferring the underlying buffer since we reuse it
        const chunk = new Int16Array(this._buffer);
        this.port.postMessage(chunk.buffer, [chunk.buffer]);
        this._buffer = new Int16Array(CHUNK_FRAMES);
        this._writeIndex = 0;
      }
    }

    return true; // keep processor alive
  }
}

registerProcessor("pcm16-processor", PCM16Processor);
