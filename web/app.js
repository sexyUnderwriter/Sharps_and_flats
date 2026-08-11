// Chord Pattern Phrase Builder
// Loads tokenized bar assets (data/bars.json) and lets the user assemble a
// chord progression from real notated bars, then play it back.

const STEP_SEMITONES = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };

let DATA = null;
let barsByMeasure = new Map();
let midiRange = { min: 48, max: 84 };

// pattern = ordered list of { chord, measure } slots the user has built
const pattern = [];
let selectedSlotIndex = null;
let playToken = 0; // increments to invalidate in-flight playback highlighting
let viewMode = "roll"; // "roll" (piano-roll graph) or "notation" (sheet music)

async function init() {
  const res = await fetch("../data/bars.json");
  DATA = await res.json();
  document.getElementById("tempo").value = Math.round(DATA.tempo);

  for (const bar of DATA.bars) {
    barsByMeasure.set(bar.measure, bar);
  }
  computeMidiRange();
  renderChordPalette();
  renderPattern();
  renderVariantGrid(null);
  wireControls();
}

function midiOf(note) {
  return (note.octave + 1) * 12 + STEP_SEMITONES[note.step] + (note.alter || 0);
}

function computeMidiRange() {
  let min = Infinity, max = -Infinity;
  for (const bar of DATA.bars) {
    for (const note of [...bar.treble, ...bar.bass]) {
      if (note.type !== "note") continue;
      const m = midiOf(note);
      if (m < min) min = m;
      if (m > max) max = m;
    }
  }
  if (isFinite(min) && isFinite(max)) {
    midiRange = { min: min - 2, max: max + 2 };
  }
}

// Ordered, de-duplicated chord list as it first appears in the score.
function chordList() {
  const seen = new Set();
  const order = [];
  for (const c of DATA.chordOrder) {
    if (!seen.has(c)) { seen.add(c); order.push(c); }
  }
  return order;
}

function renderChordPalette() {
  const el = document.getElementById("chord-palette");
  el.innerHTML = "";
  for (const chord of chordList()) {
    const count = (DATA.chordGroups[chord] || []).length;
    const chip = document.createElement("button");
    chip.className = "chord-chip";
    chip.innerHTML = `${chord} <span class="count">${count} options</span>`;
    chip.addEventListener("click", () => addSlot(chord));
    el.appendChild(chip);
  }
}

function addSlot(chord) {
  const defaultMeasure = DATA.chordGroups[chord][0];
  pattern.push({ chord, measure: defaultMeasure });
  selectedSlotIndex = pattern.length - 1;
  renderPattern();
  renderVariantGrid(selectedSlotIndex);
  renderPhrase();
}

function removeSlot(index) {
  pattern.splice(index, 1);
  if (selectedSlotIndex === index) selectedSlotIndex = null;
  else if (selectedSlotIndex !== null && selectedSlotIndex > index) selectedSlotIndex--;
  renderPattern();
  renderVariantGrid(selectedSlotIndex);
  renderPhrase();
}

function renderPattern() {
  const el = document.getElementById("pattern-strip");
  el.innerHTML = "";
  pattern.forEach((slot, i) => {
    const div = document.createElement("div");
    div.className = "slot" + (i === selectedSlotIndex ? " selected" : "");
    div.dataset.index = String(i);
    div.innerHTML = `
      <button class="remove-btn" title="Remove">×</button>
      <div class="chord-name">${slot.chord}</div>
      <div class="variant-label">bar ${slot.measure}</div>
    `;
    div.addEventListener("click", (e) => {
      if (e.target.closest(".remove-btn")) return;
      selectedSlotIndex = i;
      renderPattern();
      renderVariantGrid(i);
    });
    div.querySelector(".remove-btn").addEventListener("click", () => removeSlot(i));
    el.appendChild(div);
  });
  document.getElementById("play-phrase").disabled = pattern.length === 0;
  document.getElementById("stop-phrase").disabled = true;
  document.getElementById("randomize-bars").disabled = pattern.length === 0;
}

function randomizeBars() {
  pattern.forEach((slot) => {
    const measures = DATA.chordGroups[slot.chord] || [];
    if (measures.length === 0) return;
    slot.measure = measures[Math.floor(Math.random() * measures.length)];
  });
  renderPattern();
  renderVariantGrid(selectedSlotIndex);
  renderPhrase();
}

function renderVariantGrid(slotIndex) {
  const grid = document.getElementById("variant-grid");
  const hint = document.getElementById("picker-hint");
  grid.innerHTML = "";

  if (slotIndex === null || slotIndex === undefined || !pattern[slotIndex]) {
    hint.style.display = "block";
    return;
  }
  hint.style.display = "none";
  const slot = pattern[slotIndex];
  const measures = DATA.chordGroups[slot.chord] || [];

  for (const measure of measures) {
    const bar = barsByMeasure.get(measure);
    const card = document.createElement("div");
    card.className = "variant-card" + (measure === slot.measure ? " chosen" : "");
    card.innerHTML = `<div class="measure-label">bar ${measure}</div>`;
    card.appendChild(makeVisual(bar));
    if (viewMode === "roll") {
      const legend = document.createElement("div");
      legend.className = "roll-legend";
      legend.innerHTML = `<span class="t">■</span> treble &nbsp; <span class="b">■</span> bass`;
      card.appendChild(legend);
    }
    card.addEventListener("click", () => {
      slot.measure = measure;
      renderPattern();
      renderVariantGrid(slotIndex);
      renderPhrase();
    });
    grid.appendChild(card);
  }
}

// Draws a simple piano-roll (time on x, pitch on y) for one bar's two staves.
function makeRollCanvas(bar) {
  const canvas = document.createElement("canvas");
  canvas.className = "roll";
  canvas.width = 260;
  canvas.height = 120;
  drawRoll(canvas, bar);
  return canvas;
}

// Returns the visual for a bar according to the current view mode (graph or notation).
function makeVisual(bar) {
  return viewMode === "notation" ? makeNotationEl(bar) : makeRollCanvas(bar);
}

function makeNotationEl(bar) {
  const div = document.createElement("div");
  div.className = "notation";
  if (window.Vex && window.Vex.Flow) {
    try {
      drawNotation(div, bar);
    } catch (err) {
      div.textContent = "Notation unavailable";
      console.error("VexFlow render failed", err);
    }
  } else {
    div.textContent = "Notation unavailable (VexFlow failed to load)";
  }
  return div;
}

function pitchToVexKey(ev) {
  const acc = ev.alter === 1 ? "#" : ev.alter === -1 ? "b" : "";
  return `${ev.step.toLowerCase()}${acc}/${ev.octave}`;
}

// Builds VexFlow StaveNotes for one staff's raw (unmerged) notation events,
// along with the tuplet groups and tie pairs found among them.
function buildVexVoice(VF, events, clef) {
  const notes = [];
  const tupletGroups = [];
  const ties = [];
  let currentGroup = null;
  let pendingTieFrom = null;

  events.forEach((ev, idx) => {
    const keys = ev.type === "rest" ? ["b/4"] : [pitchToVexKey(ev)];
    const note = new VF.StaveNote({ keys, duration: ev.vexDuration, clef });
    for (let d = 0; d < (ev.dots || 0); d++) VF.Dot.buildAndAttach([note], { all: true });
    if (ev.type === "note" && ev.alter) {
      note.addModifier(new VF.Accidental(ev.alter === 1 ? "#" : "b"), 0);
    }
    notes.push(note);

    if (ev.tupletStart) {
      currentGroup = { actual: ev.tupletActual, normal: ev.tupletNormal, notes: [note] };
    } else if (currentGroup) {
      currentGroup.notes.push(note);
    }
    if (ev.tupletStop && currentGroup) {
      tupletGroups.push(currentGroup);
      currentGroup = null;
    }

    if (ev.tieStart) pendingTieFrom = idx;
    if (ev.tieStop && pendingTieFrom !== null) {
      ties.push({ first: pendingTieFrom, last: idx });
      pendingTieFrom = null;
    }
  });

  return { notes, tupletGroups, ties };
}

function drawNotation(container, bar) {
  const VF = window.Vex.Flow;
  const width = 340;
  const height = 150;
  container.innerHTML = "";
  const renderer = new VF.Renderer(container, VF.Renderer.Backends.SVG);
  renderer.resize(width, height);
  const context = renderer.getContext();

  const staveWidth = width - 20;
  const trebleStave = new VF.Stave(5, 0, staveWidth).addClef("treble");
  const bassStave = new VF.Stave(5, 75, staveWidth).addClef("bass");
  trebleStave.setContext(context).draw();
  bassStave.setContext(context).draw();
  new VF.StaveConnector(trebleStave, bassStave)
    .setType(VF.StaveConnector.type.BRACE)
    .setContext(context)
    .draw();
  new VF.StaveConnector(trebleStave, bassStave)
    .setType(VF.StaveConnector.type.SINGLE_LEFT)
    .setContext(context)
    .draw();

  const treble = buildVexVoice(VF, bar.trebleNotation, "treble");
  const bass = buildVexVoice(VF, bar.bassNotation, "bass");

  // Tuplets must be constructed before beaming: creating a Tuplet rescales its
  // notes' tick values to the actual (sounding) duration, which the default
  // per-quarter-note beam grouping depends on. Beaming before this point uses
  // each note's nominal (unscaled) duration and produces wrong beam groups.
  [treble, bass].forEach(({ tupletGroups }) => {
    tupletGroups.forEach((g) => {
      if (!g.actual || !g.normal) return;
      g.tuplet = new VF.Tuplet(g.notes, { numNotes: g.actual, notesOccupied: g.normal });
    });
  });

  const trebleVoice = new VF.Voice({ numBeats: DATA.beats, beatValue: DATA.beatType }).setStrict(false);
  trebleVoice.addTickables(treble.notes);
  const bassVoice = new VF.Voice({ numBeats: DATA.beats, beatValue: DATA.beatType }).setStrict(false);
  bassVoice.addTickables(bass.notes);

  new VF.Formatter()
    .joinVoices([trebleVoice])
    .joinVoices([bassVoice])
    .format([trebleVoice, bassVoice], staveWidth - 50);

  trebleVoice.draw(context, trebleStave);
  bassVoice.draw(context, bassStave);

  const trebleBeams = VF.Beam.generateBeams(treble.notes, { groups: [new VF.Fraction(1, 4)] });
  const bassBeams = VF.Beam.generateBeams(bass.notes, { groups: [new VF.Fraction(1, 4)] });
  [...trebleBeams, ...bassBeams].forEach((b) => b.setContext(context).draw());

  [treble, bass].forEach(({ tupletGroups }) => {
    tupletGroups.forEach((g) => g.tuplet && g.tuplet.setContext(context).draw());
  });

  [treble, bass].forEach(({ notes, ties }) => {
    ties.forEach(({ first, last }) => {
      new VF.StaveTie({
        first_note: notes[first],
        last_note: notes[last],
        first_indices: [0],
        last_indices: [0],
      })
        .setContext(context)
        .draw();
    });
  });

  const svg = container.querySelector("svg");
  if (svg) {
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.removeAttribute("width");
    svg.removeAttribute("height");
  }
}

function drawRoll(canvas, bar) {
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height;
  ctx.clearRect(0, 0, W, H);
  const ticksPerBar = bar.ticksPerBar;
  const span = midiRange.max - midiRange.min || 1;

  const drawStaff = (events, color) => {
    let t = 0;
    ctx.fillStyle = color;
    for (const ev of events) {
      const x = (t / ticksPerBar) * W;
      const w = Math.max(1, (ev.duration / ticksPerBar) * W - 1);
      if (ev.type === "note") {
        const m = midiOf(ev);
        const y = H - ((m - midiRange.min) / span) * H;
        ctx.fillRect(x, y - 3, w, 6);
      }
      t += ev.duration;
    }
  };
  drawStaff(bar.bass, "#2f9e6b");
  drawStaff(bar.treble, "#3468c0");
}

function renderPhrase() {
  const el = document.getElementById("phrase-view");
  el.innerHTML = "";
  pattern.forEach((slot, i) => {
    const bar = barsByMeasure.get(slot.measure);
    const wrap = document.createElement("div");
    wrap.className = "phrase-bar";
    wrap.dataset.index = String(i);
    wrap.appendChild(makeVisual(bar));
    const label = document.createElement("div");
    label.className = "label";
    label.textContent = `${slot.chord} · bar ${slot.measure}`;
    wrap.appendChild(label);
    el.appendChild(wrap);
  });
}

// --- Playback (Web Audio API) ---------------------------------------------

let audioCtx = null;
const activeNodes = [];
const activeTimers = [];

function ensureAudioCtx() {
  if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  return audioCtx;
}

function midiToFreq(m) {
  return 440 * Math.pow(2, (m - 69) / 12);
}

function scheduleNote(ctx, startTime, duration, midi, gainPeak) {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = "triangle";
  osc.frequency.value = midiToFreq(midi);
  const attack = 0.01;
  const release = Math.min(0.15, duration * 0.4);
  gain.gain.setValueAtTime(0, startTime);
  gain.gain.linearRampToValueAtTime(gainPeak, startTime + attack);
  gain.gain.setValueAtTime(gainPeak, Math.max(startTime + attack, startTime + duration - release));
  gain.gain.linearRampToValueAtTime(0.0001, startTime + duration);
  osc.connect(gain).connect(ctx.destination);
  osc.start(startTime);
  osc.stop(startTime + duration + 0.02);
  activeNodes.push(osc);
}

function playPhrase() {
  if (pattern.length === 0) return;
  stopPhrase();
  const ctx = ensureAudioCtx();
  const tempo = Number(document.getElementById("tempo").value) || 110;
  const myToken = ++playToken;

  document.getElementById("play-phrase").disabled = true;
  document.getElementById("stop-phrase").disabled = false;

  let startTime = ctx.currentTime + 0.1;
  const secPerBar = [];

  pattern.forEach((slot) => {
    const bar = barsByMeasure.get(slot.measure);
    const secPerTick = 60 / tempo / bar.divisions;
    const barDuration = bar.ticksPerBar * secPerTick;
    secPerBar.push(barDuration);

    const scheduleStaff = (events, gainPeak) => {
      let t = startTime;
      for (const ev of events) {
        const dur = ev.duration * secPerTick;
        if (ev.type === "note") {
          scheduleNote(ctx, t, dur, midiOf(ev), gainPeak);
        }
        t += dur;
      }
    };
    scheduleStaff(bar.treble, 0.18);
    scheduleStaff(bar.bass, 0.15);

    startTime += barDuration;
  });

  // Highlight slots/phrase bars in sync with playback using timers.
  let acc = 0;
  pattern.forEach((_, i) => {
    const delayMs = acc * 1000;
    const durMs = secPerBar[i] * 1000;
    const timer1 = setTimeout(() => {
      if (myToken !== playToken) return;
      setPlayingHighlight(i);
    }, delayMs + 100);
    activeTimers.push(timer1);
    acc += secPerBar[i];
  });
  const endTimer = setTimeout(() => {
    if (myToken !== playToken) return;
    setPlayingHighlight(-1);
    document.getElementById("play-phrase").disabled = pattern.length === 0;
    document.getElementById("stop-phrase").disabled = true;
  }, acc * 1000 + 150);
  activeTimers.push(endTimer);
}

function setPlayingHighlight(index) {
  document.querySelectorAll(".slot").forEach((el) => el.classList.remove("playing"));
  document.querySelectorAll(".phrase-bar").forEach((el) => el.classList.remove("playing"));
  if (index >= 0) {
    document.querySelector(`.slot[data-index="${index}"]`)?.classList.add("playing");
    document.querySelector(`.phrase-bar[data-index="${index}"]`)?.classList.add("playing");
  }
}

function stopPhrase() {
  playToken++; // invalidate any pending highlight timers
  activeTimers.forEach(clearTimeout);
  activeTimers.length = 0;
  activeNodes.forEach((osc) => {
    try { osc.stop(); } catch { /* already stopped */ }
  });
  activeNodes.length = 0;
  setPlayingHighlight(-1);
  document.getElementById("play-phrase").disabled = pattern.length === 0;
  document.getElementById("stop-phrase").disabled = true;
}

function wireControls() {
  document.getElementById("play-phrase").addEventListener("click", playPhrase);
  document.getElementById("stop-phrase").addEventListener("click", stopPhrase);
  document.getElementById("randomize-bars").addEventListener("click", randomizeBars);
  document.getElementById("clear-pattern").addEventListener("click", () => {
    stopPhrase();
    pattern.length = 0;
    selectedSlotIndex = null;
    renderPattern();
    renderVariantGrid(null);
    renderPhrase();
  });
  document.getElementById("view-roll").addEventListener("click", () => setViewMode("roll"));
  document.getElementById("view-notation").addEventListener("click", () => setViewMode("notation"));
}

function setViewMode(mode) {
  if (mode === viewMode) return;
  viewMode = mode;
  document.body.classList.toggle("view-notation", mode === "notation");
  document.getElementById("view-roll").classList.toggle("active", mode === "roll");
  document.getElementById("view-notation").classList.toggle("active", mode === "notation");
  renderVariantGrid(selectedSlotIndex);
  renderPhrase();
}

init();
