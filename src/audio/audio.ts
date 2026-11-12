import * as THREE from "three/webgpu";

/**
 * Every sound is synthesized: no samples. A small mixer (music / ambience / effects buses into a
 * glue compressor and a limiter), a generative festival band that gets louder near the stalls,
 * and one-shot voices placed in space by simple distance + stereo pan from the camera.
 */
const YO = [0, 2, 5, 7, 9]; // Yo pentatonic (D E G A B over D)
const midi = (n: number) => 440 * Math.pow(2, (n - 69) / 12);

export class Audio {
  ctx: AudioContext | null = null;
  private master!: GainNode;
  private music!: GainNode;
  private amb!: GainNode;
  private fx!: GainNode;
  private noiseBuf!: AudioBuffer;
  private windG!: GainNode;
  private windF!: BiquadFilterNode;
  private crowdG!: GainNode;
  private seaG!: GainNode;
  private sizzleG!: GainNode;
  private purrG!: GainNode;
  private nextBeat = 0;
  private beat = 0;
  private bar = 0;
  private phrase: number[] = [];
  private readonly listener = new THREE.Vector3();
  private readonly right = new THREE.Vector3();
  musicNear = 0;
  muted = false;
  /** Music duck while a fireworks show is on (the band pauses for the hanabi). */
  private bandOn = 1;

  start(): void {
    if (this.ctx) { void this.ctx.resume(); return; }
    const ctx = new AudioContext({ latencyHint: "interactive" });
    this.ctx = ctx;
    const comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -18; comp.ratio.value = 3; comp.attack.value = 0.01; comp.release.value = 0.25;
    const lim = ctx.createDynamicsCompressor();
    lim.threshold.value = -3; lim.ratio.value = 20; lim.attack.value = 0.002; lim.release.value = 0.1;
    this.master = ctx.createGain();
    this.master.gain.value = 0;
    this.master.gain.linearRampToValueAtTime(0.9, ctx.currentTime + 3);
    comp.connect(lim).connect(this.master).connect(ctx.destination);
    this.music = ctx.createGain(); this.music.gain.value = 0.3; this.music.connect(comp);
    this.amb = ctx.createGain(); this.amb.gain.value = 0.8; this.amb.connect(comp);
    this.fx = ctx.createGain(); this.fx.gain.value = 0.9; this.fx.connect(comp);
    // Shared noise.
    const len = ctx.sampleRate * 2;
    this.noiseBuf = ctx.createBuffer(1, len, ctx.sampleRate);
    const d = this.noiseBuf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
    // A little room for the music and the chimes.
    const verb = this.makeVerb(1.8);
    const verbG = ctx.createGain(); verbG.gain.value = 0.22;
    this.music.connect(verbG).connect(verb).connect(comp);
    this.fxVerb = ctx.createGain(); this.fxVerb.gain.value = 0.3; this.fxVerb.connect(verb);

    // Beds: wind, crowd murmur, sea, grill sizzle, purr.
    ({ g: this.windG, f: this.windF } = this.bed("lowpass", 500, 0.7, 0));
    this.crowdG = this.crowdBed();
    this.seaG = this.bed("lowpass", 700, 0.5, 0).g;
    this.sizzleG = this.bed("highpass", 4000, 0.4, 0).g;
    this.purrG = this.purrBed();
    this.nextBeat = ctx.currentTime + 0.5;
    this.newPhrase();
  }

  private fxVerb!: GainNode;

  private makeVerb(secs: number): ConvolverNode {
    const ctx = this.ctx!;
    const n = Math.floor(ctx.sampleRate * secs);
    const b = ctx.createBuffer(2, n, ctx.sampleRate);
    for (let c = 0; c < 2; c++) {
      const ch = b.getChannelData(c);
      for (let i = 0; i < n; i++) ch[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / n, 3);
    }
    const v = ctx.createConvolver();
    v.buffer = b;
    return v;
  }

  private noise(): AudioBufferSourceNode {
    const s = this.ctx!.createBufferSource();
    s.buffer = this.noiseBuf;
    s.loop = true;
    s.loopStart = Math.random();
    return s;
  }

  private bed(type: BiquadFilterType, freq: number, q: number, gain: number) {
    const ctx = this.ctx!;
    const s = this.noise();
    const f = ctx.createBiquadFilter(); f.type = type; f.frequency.value = freq; f.Q.value = q;
    const g = ctx.createGain(); g.gain.value = gain;
    s.connect(f).connect(g).connect(this.amb);
    s.start();
    return { g, f };
  }

  private crowdBed(): GainNode {
    const ctx = this.ctx!;
    const out = ctx.createGain(); out.gain.value = 0;
    out.connect(this.amb);
    // Murmur: noise through moving vowel formants, amplitude-modulated like many distant voices.
    for (const [f0, q] of [[420, 4], [900, 5], [1700, 6]]) {
      const s = this.noise();
      const bp = ctx.createBiquadFilter(); bp.type = "bandpass"; bp.frequency.value = f0; bp.Q.value = q;
      const lfo = ctx.createOscillator(); lfo.frequency.value = 0.3 + Math.random() * 0.4;
      const lg = ctx.createGain(); lg.gain.value = f0 * 0.25;
      lfo.connect(lg).connect(bp.frequency);
      const am = ctx.createGain(); am.gain.value = 0.5;
      const amo = ctx.createOscillator(); amo.frequency.value = 3 + Math.random() * 2;
      const amg = ctx.createGain(); amg.gain.value = 0.35;
      amo.connect(amg).connect(am.gain);
      s.connect(bp).connect(am).connect(out);
      s.start(); lfo.start(); amo.start();
    }
    return out;
  }

  private purrBed(): GainNode {
    const ctx = this.ctx!;
    const s = this.noise();
    const lp = ctx.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 220;
    const am = ctx.createGain(); am.gain.value = 0.4;
    const o = ctx.createOscillator(); o.frequency.value = 24;
    const og = ctx.createGain(); og.gain.value = 0.4;
    o.connect(og).connect(am.gain);
    const g = ctx.createGain(); g.gain.value = 0;
    s.connect(lp).connect(am).connect(g).connect(this.fx);
    s.start(); o.start();
    return g;
  }

  setMuted(m: boolean): void {
    this.muted = m;
    if (this.ctx) this.master.gain.setTargetAtTime(m ? 0 : 0.9, this.ctx.currentTime, 0.2);
  }

  /** Per-frame: listener pose and the levels of every bed. */
  update(cam: THREE.Camera, levels: { wind: number; crowd: number; sea: number; music: number; sizzle: number; purr: number }): void {
    const ctx = this.ctx;
    if (!ctx) return;
    this.listener.copy(cam.position);
    this.right.set(1, 0, 0).applyQuaternion(cam.quaternion);
    const t = ctx.currentTime;
    this.windG.gain.setTargetAtTime(0.05 + levels.wind * 0.18, t, 0.3);
    this.windF.frequency.setTargetAtTime(300 + levels.wind * 900, t, 0.3);
    this.crowdG.gain.setTargetAtTime(levels.crowd * 0.12, t, 0.5);
    this.seaG.gain.setTargetAtTime(levels.sea * (0.25 + 0.2 * Math.sin(t * 0.55) ** 2), t, 0.2);
    this.sizzleG.gain.setTargetAtTime(levels.sizzle * 0.05, t, 0.3);
    this.purrG.gain.setTargetAtTime(levels.purr * 0.5, t, 0.2);
    this.musicNear = levels.music;
    this.music.gain.setTargetAtTime((0.05 + levels.music * 0.32) * this.bandOn, t, 0.6);
    this.scheduleBand();
  }

  setBand(on: boolean): void { this.bandOn = on ? 1 : 0.15; }

  // ------------------------------------------------------------------ the band
  private newPhrase() {
    // A gentle shinobue melody over 4 bars, stepwise in the Yo scale.
    let deg = 2;
    this.phrase = [];
    for (let i = 0; i < 16; i++) {
      if (Math.random() < 0.28) { this.phrase.push(-1); continue; }
      deg = Math.max(0, Math.min(9, deg + [-2, -1, -1, 1, 1, 2, 0][Math.floor(Math.random() * 7)]));
      this.phrase.push(deg);
    }
    this.phrase[15] = 0;
  }

  private scheduleBand() {
    const ctx = this.ctx!;
    const spb = 60 / 104 / 2; // eighth notes at 104 bpm
    while (this.nextBeat < ctx.currentTime + 0.2) {
      const t = this.nextBeat, b = this.beat % 8;
      // Taiko on 1 and the "and" of 3; shime-daiko pattern; chappa on the off-beats.
      if (b === 0 || (b === 5 && this.bar % 2 === 1)) this.taiko(t, b === 0 ? 1 : 0.6);
      if ([0, 2, 3, 4, 6].includes(b)) this.shime(t, b === 0 ? 0.6 : 0.35);
      if (b % 2 === 1) this.chappa(t, 0.22);
      // Flute: quarter notes from the phrase.
      if (b % 2 === 0) {
        const idx = (this.bar % 4) * 4 + b / 2;
        const deg = this.phrase[idx];
        if (deg >= 0) this.flute(t, midi(74 + YO[deg % 5] + 12 * Math.floor(deg / 5)), spb * 2 * (Math.random() < 0.3 ? 2 : 1.6));
      }
      // Shamisen: plucked drone and fifths.
      if (b === 0 || b === 3 || b === 6) this.pluck(t, midi(50 + [0, 7, 12][b / 3 | 0]), 0.25);
      this.nextBeat += spb;
      this.beat++;
      if (this.beat % 8 === 0) {
        this.bar++;
        if (this.bar % 4 === 0) this.newPhrase();
      }
    }
  }

  private env(t: number, a: number, peak: number, dec: number, dest: AudioNode = this.music): GainNode {
    const g = this.ctx!.createGain();
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(peak, t + a);
    g.gain.exponentialRampToValueAtTime(0.0001, t + a + dec);
    g.connect(dest);
    return g;
  }

  private taiko(t: number, v: number) {
    const ctx = this.ctx!;
    const o = ctx.createOscillator(); o.type = "sine";
    o.frequency.setValueAtTime(110, t); o.frequency.exponentialRampToValueAtTime(52, t + 0.25);
    o.connect(this.env(t, 0.004, 0.9 * v, 0.55));
    o.start(t); o.stop(t + 0.7);
    const n = this.noise(); const f = ctx.createBiquadFilter(); f.type = "lowpass"; f.frequency.value = 400;
    n.connect(f).connect(this.env(t, 0.002, 0.3 * v, 0.12)); n.start(t); n.stop(t + 0.2);
  }
  private shime(t: number, v: number) {
    const ctx = this.ctx!;
    const n = this.noise(); const f = ctx.createBiquadFilter(); f.type = "bandpass"; f.frequency.value = 900; f.Q.value = 3;
    n.connect(f).connect(this.env(t, 0.001, 0.5 * v, 0.07)); n.start(t); n.stop(t + 0.12);
    const o = ctx.createOscillator(); o.frequency.value = 330; o.connect(this.env(t, 0.001, 0.15 * v, 0.06)); o.start(t); o.stop(t + 0.1);
  }
  private chappa(t: number, v: number) {
    const ctx = this.ctx!;
    const n = this.noise(); const f = ctx.createBiquadFilter(); f.type = "highpass"; f.frequency.value = 6000;
    n.connect(f).connect(this.env(t, 0.001, v, 0.09)); n.start(t); n.stop(t + 0.14);
  }
  private flute(t: number, hz: number, dur: number) {
    const ctx = this.ctx!;
    const o = ctx.createOscillator(); o.type = "sine"; o.frequency.setValueAtTime(hz * 0.985, t); o.frequency.linearRampToValueAtTime(hz, t + 0.06);
    const vib = ctx.createOscillator(); vib.frequency.value = 5.2; const vg = ctx.createGain(); vg.gain.setValueAtTime(0, t); vg.gain.linearRampToValueAtTime(hz * 0.012, t + dur * 0.6);
    vib.connect(vg).connect(o.frequency);
    const g = ctx.createGain(); g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(0.16, t + 0.05); g.gain.setValueAtTime(0.14, t + dur * 0.8); g.gain.linearRampToValueAtTime(0, t + dur);
    g.connect(this.music);
    o.connect(g);
    const o2 = ctx.createOscillator(); o2.frequency.value = hz * 2; const g2 = ctx.createGain(); g2.gain.value = 0.15; o2.connect(g2).connect(g);
    // Breath.
    const n = this.noise(); const bf = ctx.createBiquadFilter(); bf.type = "bandpass"; bf.frequency.value = hz * 2; bf.Q.value = 2;
    const ng = ctx.createGain(); ng.gain.value = 0.05; n.connect(bf).connect(ng).connect(g);
    for (const s of [o, vib, o2, n]) { s.start(t); s.stop(t + dur + 0.05); }
  }
  private pluck(t: number, hz: number, v: number) {
    const ctx = this.ctx!;
    const o = ctx.createOscillator(); o.type = "sawtooth"; o.frequency.value = hz;
    const f = ctx.createBiquadFilter(); f.type = "lowpass"; f.frequency.setValueAtTime(hz * 8, t); f.frequency.exponentialRampToValueAtTime(hz * 1.5, t + 0.25);
    o.connect(f).connect(this.env(t, 0.002, v * 0.35, 0.45));
    o.start(t); o.stop(t + 0.5);
  }

  // ------------------------------------------------------------------ placed one-shots
  /** Gain and pan for a world point (simple distance falloff). */
  private place(p: THREE.Vector3 | null, ref = 4): { g: number; pan: number } {
    if (!p) return { g: 1, pan: 0 };
    const d = p.distanceTo(this.listener);
    const dir = p.clone().sub(this.listener).normalize();
    return { g: ref / Math.max(ref, d), pan: THREE.MathUtils.clamp(dir.dot(this.right), -1, 1) * 0.8 };
  }
  private out(p: THREE.Vector3 | null, ref = 4, verb = 0.3): AudioNode {
    const ctx = this.ctx!;
    const { g, pan } = this.place(p, ref);
    const gn = ctx.createGain(); gn.gain.value = g;
    const pn = ctx.createStereoPanner(); pn.pan.value = pan;
    gn.connect(pn).connect(this.fx);
    if (verb > 0) { const vg = ctx.createGain(); vg.gain.value = verb * g; pn.connect(vg).connect(this.fxVerb); }
    return gn;
  }

  /** Geta on stone (karan-koron), soft on sand. */
  step(p: THREE.Vector3, surface: "stone" | "wood" | "sand", left: boolean, run: boolean): void {
    const ctx = this.ctx; if (!ctx) return;
    const t = ctx.currentTime;
    const o = this.out(p, 3, surface === "sand" ? 0 : 0.15);
    if (surface === "sand") {
      const n = this.noise(); const f = ctx.createBiquadFilter(); f.type = "lowpass"; f.frequency.value = 900;
      n.connect(f).connect(this.env(t, 0.01, run ? 0.28 : 0.18, 0.12, o)); n.start(t); n.stop(t + 0.2);
      return;
    }
    // Wooden clack: two resonances, slightly different per foot.
    const base = (left ? 1 : 1.07) * (surface === "wood" ? 0.8 : 1);
    for (const [hz, a] of [[1150 * base, 0.5], [2650 * base, 0.3], [480 * base, 0.25]]) {
      const n = this.noise(); const f = ctx.createBiquadFilter(); f.type = "bandpass"; f.frequency.value = hz; f.Q.value = 14;
      n.connect(f).connect(this.env(t, 0.001, a * (run ? 1.2 : 0.9), 0.07, o)); n.start(t); n.stop(t + 0.12);
    }
  }

  /** Glass wind chime (furin): a bright bell with a little shimmer. */
  chime(p: THREE.Vector3, pitch = 1): void {
    const ctx = this.ctx; if (!ctx) return;
    const t = ctx.currentTime + Math.random() * 0.05;
    const o = this.out(p, 3, 0.6);
    for (const [r, a, d] of [[1, 0.18, 1.8], [2.76, 0.08, 1.0], [5.4, 0.04, 0.5]]) {
      const osc = ctx.createOscillator(); osc.frequency.value = 2100 * pitch * r;
      osc.connect(this.env(t, 0.002, a, d, o)); osc.start(t); osc.stop(t + d + 0.1);
    }
  }

  /** Soft task chime: a rising three-note bell. */
  taskChime(): void {
    const ctx = this.ctx; if (!ctx) return;
    const t = ctx.currentTime;
    const o = this.out(null, 1, 0.7);
    [0, 4, 7].forEach((st, i) => {
      for (const [r, a] of [[1, 0.22], [2.0, 0.06], [3.01, 0.03]]) {
        const osc = ctx.createOscillator(); osc.frequency.value = midi(79 + [0, 2, 7][i]) * r;
        osc.connect(this.env(t + i * 0.13, 0.004, a, 1.6, o)); osc.start(t + i * 0.13); osc.stop(t + i * 0.13 + 1.8);
      }
      void st;
    });
  }

  /** Checkpoint: a low temple-ish bell. */
  gateBell(p: THREE.Vector3): void {
    const ctx = this.ctx; if (!ctx) return;
    const t = ctx.currentTime;
    const o = this.out(p, 8, 0.8);
    for (const [hz, a, d] of [[196, 0.3, 3.5], [196 * 2.02, 0.12, 2.5], [196 * 3.9, 0.05, 1.5], [197.5, 0.2, 3.5]]) {
      const osc = ctx.createOscillator(); osc.frequency.value = hz; osc.connect(this.env(t, 0.005, a, d, o)); osc.start(t); osc.stop(t + d + 0.1);
    }
  }

  /** Little sounds for the mini-games. */
  blip(kind: "splash" | "clack" | "pop" | "coin" | "whoosh" | "match" | "fail", p: THREE.Vector3 | null = null): void {
    const ctx = this.ctx; if (!ctx) return;
    const t = ctx.currentTime;
    const o = this.out(p, 2, 0.2);
    if (kind === "splash") {
      const n = this.noise(); const f = ctx.createBiquadFilter(); f.type = "bandpass"; f.frequency.setValueAtTime(2500, t); f.frequency.exponentialRampToValueAtTime(700, t + 0.25); f.Q.value = 1;
      n.connect(f).connect(this.env(t, 0.005, 0.35, 0.3, o)); n.start(t); n.stop(t + 0.4);
    } else if (kind === "clack") {
      const n = this.noise(); const f = ctx.createBiquadFilter(); f.type = "bandpass"; f.frequency.value = 1800; f.Q.value = 8;
      n.connect(f).connect(this.env(t, 0.001, 0.5, 0.08, o)); n.start(t); n.stop(t + 0.12);
    } else if (kind === "pop" || kind === "coin") {
      const osc = ctx.createOscillator(); osc.frequency.setValueAtTime(kind === "coin" ? 1800 : 600, t); osc.frequency.exponentialRampToValueAtTime(kind === "coin" ? 2400 : 900, t + 0.06);
      osc.connect(this.env(t, 0.002, 0.15, kind === "coin" ? 0.4 : 0.12, o)); osc.start(t); osc.stop(t + 0.5);
    } else if (kind === "whoosh") {
      const n = this.noise(); const f = ctx.createBiquadFilter(); f.type = "bandpass"; f.frequency.setValueAtTime(400, t); f.frequency.exponentialRampToValueAtTime(1600, t + 0.3); f.Q.value = 1.5;
      n.connect(f).connect(this.env(t, 0.08, 0.2, 0.25, o)); n.start(t); n.stop(t + 0.45);
    } else if (kind === "match") {
      const n = this.noise(); const f = ctx.createBiquadFilter(); f.type = "highpass"; f.frequency.value = 2000;
      n.connect(f).connect(this.env(t, 0.005, 0.3, 0.35, o)); n.start(t); n.stop(t + 0.45);
    } else {
      const osc = ctx.createOscillator(); osc.frequency.setValueAtTime(420, t); osc.frequency.exponentialRampToValueAtTime(300, t + 0.25);
      osc.connect(this.env(t, 0.01, 0.08, 0.3, o)); osc.start(t); osc.stop(t + 0.4);
    }
  }

  /** A keeper calling out: two quick sung syllables, very soft. */
  call(p: THREE.Vector3): void {
    const ctx = this.ctx; if (!ctx) return;
    const t = ctx.currentTime;
    const o = this.out(p, 3, 0.3);
    [0, 0.16, 0.3].forEach((dt, i) => {
      const osc = ctx.createOscillator(); osc.type = "sawtooth"; osc.frequency.value = [220, 247, 196][i];
      const f = ctx.createBiquadFilter(); f.type = "bandpass"; f.frequency.value = [800, 1100, 700][i]; f.Q.value = 5;
      osc.connect(f).connect(this.env(t + dt, 0.02, 0.09, 0.15, o)); osc.start(t + dt); osc.stop(t + dt + 0.25);
    });
  }

  /** Firework: launch whistle, then the burst (boom arrives with the distance), then crackle. */
  firework(launch: THREE.Vector3, burst: THREE.Vector3, delay: number, crackle: boolean): void {
    const ctx = this.ctx; if (!ctx) return;
    const t = ctx.currentTime;
    const o1 = this.out(launch, 30, 0.4);
    const w = ctx.createOscillator(); w.frequency.setValueAtTime(900, t); w.frequency.exponentialRampToValueAtTime(2200, t + delay);
    w.connect(this.env(t, 0.1, 0.03, delay, o1)); w.start(t); w.stop(t + delay + 0.1);
    const d = burst.distanceTo(this.listener);
    const tb = t + delay + Math.min(0.6, d / 343);
    const o2 = this.out(burst, 80, 1.0);
    const n = this.noise(); const f = ctx.createBiquadFilter(); f.type = "lowpass"; f.frequency.setValueAtTime(900, tb); f.frequency.exponentialRampToValueAtTime(120, tb + 0.8);
    n.connect(f).connect(this.env(tb, 0.004, 1.2, 1.6, o2)); n.start(tb); n.stop(tb + 2);
    const s = ctx.createOscillator(); s.frequency.setValueAtTime(70, tb); s.frequency.exponentialRampToValueAtTime(35, tb + 0.5);
    s.connect(this.env(tb, 0.004, 0.8, 0.9, o2)); s.start(tb); s.stop(tb + 1);
    if (crackle) {
      for (let i = 0; i < 26; i++) {
        const tc = tb + 0.4 + Math.random() * 1.4;
        const c = this.noise(); const cf = ctx.createBiquadFilter(); cf.type = "highpass"; cf.frequency.value = 3000;
        c.connect(cf).connect(this.env(tc, 0.001, 0.1 + Math.random() * 0.12, 0.03, o2)); c.start(tc); c.stop(tc + 0.05);
      }
    }
  }

  /** Sparkler fizz near the kids (short). */
  fizz(p: THREE.Vector3): void {
    const ctx = this.ctx; if (!ctx) return;
    const t = ctx.currentTime;
    const o = this.out(p, 2, 0);
    for (let i = 0; i < 6; i++) {
      const tc = t + Math.random() * 0.4;
      const c = this.noise(); const cf = ctx.createBiquadFilter(); cf.type = "highpass"; cf.frequency.value = 5000;
      c.connect(cf).connect(this.env(tc, 0.001, 0.05, 0.02, o)); c.start(tc); c.stop(tc + 0.04);
    }
  }
}
