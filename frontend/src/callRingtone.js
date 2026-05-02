/**
 * North-American-style "outgoing call" ringback (what you hear while the callee's phone rings):
 * 440 Hz + 480 Hz steady for ~2 s, then ~4 s silence — not short "incoming ring" bursts.
 * Must start from a user gesture so autoplay policies allow sound.
 */

const PEAK_GAIN = 0.24;
/** One full ring + silence (common US-style cadence). */
const RING_ON_S = 2.0;
const RING_OFF_S = 4.0;
const CYCLE_MS = (RING_ON_S + RING_OFF_S) * 1000;

function scheduleRingbackTone(ctx, tStart) {
  const o1 = ctx.createOscillator();
  const o2 = ctx.createOscillator();
  const g = ctx.createGain();
  o1.type = "sine";
  o2.type = "sine";
  o1.frequency.value = 440;
  o2.frequency.value = 480;

  const fadeIn = 0.03;
  const fadeOut = 0.06;
  const dur = RING_ON_S;

  g.gain.setValueAtTime(0.0001, tStart);
  g.gain.linearRampToValueAtTime(PEAK_GAIN, tStart + fadeIn);
  g.gain.setValueAtTime(PEAK_GAIN, tStart + dur - fadeOut);
  g.gain.exponentialRampToValueAtTime(0.0001, tStart + dur);

  o1.connect(g);
  o2.connect(g);
  g.connect(ctx.destination);
  o1.start(tStart);
  o2.start(tStart);
  o1.stop(tStart + dur + 0.01);
  o2.stop(tStart + dur + 0.01);
}

export function startConnectingRing() {
  let ctx = null;
  let intervalId = null;
  let stopped = false;

  const playCycle = () => {
    if (stopped || !ctx) return;
    if (ctx.state === "suspended") {
      ctx.resume().catch(() => {});
    }
    scheduleRingbackTone(ctx, ctx.currentTime);
  };

  try {
    ctx = new (window.AudioContext || window.webkitAudioContext)();
  } catch {
    return () => {};
  }

  playCycle();
  intervalId = window.setInterval(playCycle, CYCLE_MS);

  return function stop() {
    if (stopped) return;
    stopped = true;
    if (intervalId != null) {
      clearInterval(intervalId);
      intervalId = null;
    }
    try {
      if (ctx && ctx.state !== "closed") {
        ctx.close();
      }
    } catch {
      /* ignore */
    }
    ctx = null;
  };
}
