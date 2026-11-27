/**
 * The Inbox's sound (spec 082, R3.1 a R3.5): two short tones made in the
 * browser with Web Audio — no file to ship or license.
 *
 * Browsers only let a page sound after the person touched it (autoplay
 * policy). So the `AudioContext` is born on the first `pointerdown` or
 * `keydown` (R3.5); before that nothing sounds and nothing is said. The
 * preference is per browser (`localStorage`), on by default (R3.4).
 */
export const SOUND_KEY = "nexus.inbox.sound";
export const SOUND_EVENT = "nexus:inbox-sound";
/** A burst sounds once every 3 s at most (R3.3). */
export const RING_GAP_MS = 3000;

type AudioCtor = typeof AudioContext;
let audio: AudioContext | null = null;
let memory: boolean | null = null;

export function soundOn(): boolean {
  try {
    const v = window.localStorage.getItem(SOUND_KEY);
    return v === null ? (memory ?? true) : v !== "off";
  } catch {
    return memory ?? true;
  }
}

export function setSoundOn(on: boolean): void {
  memory = on;
  try {
    window.localStorage.setItem(SOUND_KEY, on ? "on" : "off");
  } catch {
    /* blocked storage: the choice lives in memory for this tab */
  }
  window.dispatchEvent(new CustomEvent(SOUND_EVENT, { detail: on }));
}

function ctor(): AudioCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { AudioContext?: AudioCtor; webkitAudioContext?: AudioCtor };
  return w.AudioContext ?? w.webkitAudioContext ?? null;
}

/** Wait for the person's first gesture to create (or wake) the audio. Returns the cleanup. */
export function armChime(): () => void {
  if (typeof window === "undefined") return () => undefined;
  const wake = () => {
    try {
      const Ctor = ctor();
      if (!Ctor) return;
      audio ??= new Ctor();
      if (audio.state === "suspended") void audio.resume().catch(() => undefined);
    } catch {
      /* no audio on this browser: the counter and the title still say it */
    }
  };
  window.addEventListener("pointerdown", wake, { passive: true });
  window.addEventListener("keydown", wake);
  return () => {
    window.removeEventListener("pointerdown", wake);
    window.removeEventListener("keydown", wake);
  };
}

/** Two tones (880 Hz then 1320 Hz, 90 ms each). `false` when the browser does not let it sound yet. */
export function playChime(): boolean {
  if (!audio || audio.state !== "running") return false;
  try {
    const at = audio.currentTime;
    [880, 1320].forEach((hz, i) => {
      const start = at + i * 0.11;
      const osc = audio!.createOscillator();
      const gain = audio!.createGain();
      osc.type = "sine";
      osc.frequency.value = hz;
      gain.gain.setValueAtTime(0, start);
      gain.gain.linearRampToValueAtTime(0.15, start + 0.01);
      gain.gain.linearRampToValueAtTime(0, start + 0.09);
      osc.connect(gain).connect(audio!.destination);
      osc.start(start);
      osc.stop(start + 0.1);
    });
    return true;
  } catch {
    return false;
  }
}

/** Test seam: forget the audio context, as a fresh page would. */
export function resetChimeForTests(): void {
  audio = null;
  memory = null;
}
