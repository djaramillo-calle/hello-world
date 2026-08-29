#!/usr/bin/env node
/* English Signal Check — test suite.
   Drives the SHIPPED page (diagnostic.html) in jsdom; every check is an
   assertion and any failure makes the process exit non-zero.
   Run: node scripts/test.js */

const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const HTML = fs.readFileSync(path.join(__dirname, "..", "diagnostic.html"), "utf8");

let failures = 0, passes = 0;
function assert(cond, label) {
  if (cond) { passes++; console.log("  ok    " + label); }
  else { failures++; process.exitCode = 1; console.log("  FAIL  " + label); }
}
function assertEq(got, want, label) {
  assert(Object.is(got, want) || got === want, label + ` (got ${JSON.stringify(got)}, want ${JSON.stringify(want)})`);
}

function makePage(opts = {}) {
  const dom = new JSDOM(HTML, {
    runScripts: "dangerously",
    url: "https://signalcheck.test/",
    pretendToBeVisual: true,
    beforeParse(w) {
      w.__alerts = []; w.__confirms = []; w.__clip = null;
      w.alert = m => w.__alerts.push(String(m));
      w.confirm = m => { w.__confirms.push(String(m)); return opts.confirmAnswer !== undefined ? opts.confirmAnswer : true; };
      if (!opts.noTTS) {
        w.__spoken = [];
        w.SpeechSynthesisUtterance = function (t) { this.text = t; };
        w.speechSynthesis = {
          cancel() {}, speak(u) { w.__spoken.push(u.text); },
          getVoices: () => [{ name: "TestVoice", lang: "en-US" }]
        };
      }
      if (opts.seedStorage !== undefined) {
        const store = { "engsig.v1": opts.seedStorage };
        Object.defineProperty(w, "localStorage", { value: {
          getItem: k => (k in store ? store[k] : null),
          setItem: (k, v) => { store[k] = String(v); },
          removeItem: k => { delete store[k]; }
        }});
      }
      try {
        Object.defineProperty(w.navigator, "clipboard", {
          value: { writeText: t => { w.__clip = t; return Promise.resolve(); } }
        });
      } catch (e) {}
    }
  });
  return dom.window;
}

const ev = (w, code) => w.eval(code);

/* fill every C-test gap with its key (via the shipped CT structure) */
function fillCtest(w, passages) {
  ev(w, `
    CT.forEach((g, pi) => {
      if (${JSON.stringify(passages || null)} && !${JSON.stringify(passages || null)}.includes(pi)) return;
      g.answers.forEach((ans, gi) => {
        const inp = document.querySelector('#ct-holder input[data-p="'+pi+'"][data-g="'+gi+'"]');
        inp.value = ans;
      });
    });
  `);
}

console.log("== T1: C-test construction ==");
{
  const w = makePage();
  for (let i = 0; i < 4; i++)
    assertEq(ev(w, `gapText(BANK.ctest[${i}].text, 20).answers.length`), 20, `passage ${i + 1} has 20 gaps`);
  assert(ev(w, `BANK.ctest.every(p => { const g = gapText(p.text, 20); const firstSentEnd = p.text.search(/[.!?]/); return g.parts.filter(x => x.t === "gap").length === 20; })`), "gap structure intact");
}

console.log("== T2: item-bank integrity (locks FIX-15) ==");
{
  const w = makePage();
  // U19/FIX-15 scope: the 1000-band probes legitimately live inside the
  // ~1,500-word core list; the confirmed defect was overlap at >= 2000.
  assertEq(ev(w, `Object.entries(BANK.vocab.bands).filter(e => +e[0] >= 2000).flatMap(e => e[1]).filter(x => BANK.k1set.has(x)).length`), 0,
    "no band-2000+ word appears in the core list");
  assertEq(ev(w, `BANK.vocab.pseudo.filter(x => BANK.k1set.has(x)).length`), 0, "no pseudoword in core list");
  assertEq(ev(w, `Object.values(BANK.vocab.bands).flat().filter(x => BANK.vocab.pseudo.includes(x)).length`), 0,
    "bands and pseudowords disjoint");
  assertEq(ev(w, `Object.values(BANK.vocab.bands).every(b => b.length === 8)`), true, "8 words per band");
  assertEq(ev(w, `BANK.vocab.pseudo.length`), 32, "32 pseudowords");
  assert(!ev(w, `BANK.vocab.pseudo.includes("zolvent") || BANK.vocab.pseudo.includes("prantic")`),
    "risky pseudowords zolvent/prantic replaced");
}

console.log("== T3: deterministic shuffle ==");
{
  const w1 = makePage(), w2 = makePage();
  const o1 = ev(w1, `VT.map(x => x.w).join(",")`), o2 = ev(w2, `VT.map(x => x.w).join(",")`);
  assertEq(o1, o2, "item order identical across loads");
  const longestPseudoRun = ev(w1, `
    (() => { let run = 0, best = 0;
      VT.forEach(x => { if (!x.real) { run++; best = Math.max(best, run); } else run = 0; });
      return best; })()`);
  assert(longestPseudoRun <= 6, `pseudowords interleaved (longest run ${longestPseudoRun} <= 6)`);
}

console.log("== T4: vocabulary validity gate on SHIPPED scoreVocab ==");
{
  const w = makePage();
  // mark all 8 real 1000-band words + exactly 9 pseudowords -> f = 9/32 = 0.281 -> valid
  ev(w, `
    let pseudoMarked = 0;
    [...document.querySelectorAll("#vt-holder button")].forEach(b => {
      const it = VT[+b.dataset.i];
      if (it.real && it.band === 1000) b.click();
      else if (!it.real && pseudoMarked < 9) { b.click(); pseudoMarked++; }
    });
    scoreVocab();
  `);
  assertEq(ev(w, `S.current.vocab.valid`), true, "f = 9/32 -> valid");
  ev(w, `resetVocab();`);
  ev(w, `
    let pseudoMarked = 0;
    [...document.querySelectorAll("#vt-holder button")].forEach(b => {
      const it = VT[+b.dataset.i];
      if (it.real && it.band === 1000) b.click();
      else if (!it.real && pseudoMarked < 10) { b.click(); pseudoMarked++; }
    });
    scoreVocab();
  `);
  assertEq(ev(w, `S.current.vocab.valid`), false, "f = 10/32 -> void");
  assert(!ev(w, `document.getElementById("vt-result").innerHTML`).includes("Knowledge starts thinning"),
    "VOID card leaks no band diagnosis (FIX-7)");
  assert(ev(w, `sessionRow(S.current).vocab`) === null, "void size never exported to a row");
}

console.log("== T5: dictation scoring ==");
{
  const w = makePage();
  assertEq(ev(w, `tokenOverlap("The meeting was moved.", "the meeting was moved").hit`), 4, "exact match, case/punct-insensitive");
  assertEq(ev(w, `tokenOverlap("I don't know", "I don\\u2019t know").hit`), 3, "curly apostrophe == straight (FIX-10)");
  assertEq(ev(w, `tokenOverlap("a b c d", "a x c").hit`), 2, "partial credit counts");
  assertEq(ev(w, `norm("don\\u2019t")`), "don't", "norm() normalizes curly apostrophes");
}

console.log("== T6: MTLD vs independent implementation ==");
{
  const w = makePage();
  function refMtld(toks, thresh = 0.72) {
    function run(t) {
      let factors = 0, types = new Set(), n = 0;
      for (const x of t) { types.add(x); n++; if (types.size / n <= thresh) { factors++; types = new Set(); n = 0; } }
      if (n > 0) factors += (1 - types.size / n) / (1 - thresh);
      return factors > 0 ? t.length / factors : null;
    }
    const a = run(toks), b = run([...toks].reverse());
    return a === null || b === null ? null : (a + b) / 2;
  }
  const f1 = "the cat sat on the mat and the dog ran to the cat while a bird flew over the mat and the sun set slowly behind the old hill".split(" ");
  const f2 = "i think that i think that i think it is good and i think it is good and i think so too really".split(" ");
  for (const [i, f] of [f1, f2].entries()) {
    const got = ev(w, `mtld(${JSON.stringify(f)})`), want = refMtld(f);
    assert(Math.abs(got - want) < 0.1, `fixture ${i + 1}: shipped ${got && got.toFixed(2)} vs reference ${want && want.toFixed(2)}`);
  }
  assertEq(ev(w, `mtld(Array.from({length: 300}, (_, i) => "w" + i))`), null,
    "zero-factor text reports null, not token count (FIX-28)");
}

console.log("== T7: C-test alternates + monotone ceiling ==");
{
  const w = makePage();
  ev(w, `document.querySelector('#ct-holder input[data-p="1"][data-g="10"]').value = "ribute";
         document.querySelector('#ct-holder input[data-p="2"][data-g="11"]').value = "e";
         document.querySelector('#ct-holder input[data-p="2"][data-g="0"]').value = "erate";`);
  ev(w, `scoreCtest();`);
  assertEq(ev(w, `S.current.ctest.correct`), 3, "attribute / lie / moderate accepted (FIX-14)");
  ev(w, `resetCtest();`);
  const w2 = makePage();
  fillCtest(w2, [3]); // only the hardest passage correct
  ev(w2, `scoreCtest();`);
  assertEq(ev(w2, `S.current.ctest.ceiling`), "below A2–B1", "only-P4-correct does not report a C1 ceiling (FIX-13)");
  const w3 = makePage();
  fillCtest(w3); ev(w3, `scoreCtest();`);
  assertEq(ev(w3, `S.current.ctest.pct`), 1, "all keys accepted");
  assertEq(ev(w3, `S.current.ctest.ceiling`), "C1–C2", "full marks -> top ceiling");
}

console.log("== T8: save / copy / report / delta (FIX-1, FIX-2) ==");
{
  const w = makePage();
  fillCtest(w); ev(w, `scoreCtest();`);
  ev(w, `saveSession();`);
  assertEq(ev(w, `S.history.length`), 1, "session saved");
  ev(w, `copyRow();`);
  assert(w.__clip && w.__clip.split("\t")[1] === "100", "copy AFTER save yields the saved data, not blanks (U01)");
  assert(ev(w, `document.getElementById("rp-holder").innerHTML`).includes("History"),
    "history table visible after save (U02)");
  ev(w, `saveSession();`);
  assertEq(ev(w, `S.history.length`), 1, "double-save refused on empty session");
  // second run in progress: delta must be visible BEFORE saving
  fillCtest(w); ev(w, `scoreCtest();`);
  ev(w, `renderReport();`);
  assert(ev(w, `document.getElementById("rp-holder").innerHTML`).includes("Change since last session (current, unsaved)"),
    "delta compares current unsaved run vs last saved (U03)");
  // FIX-2: stale EI state cleared by save
  const w4 = makePage();
  ev(w4, `BANK.ei.forEach((_, i) => { eiScore[i] = 4; }); scoreEI(); saveSession();`);
  ev(w4, `scoreEI();`);
  assert(ev(w4, `S.current.ei === undefined`), "EI cannot re-score stale answers after save (U04)");
}

console.log("== T9: speaking guards (FIX-5, FIX-6) ==");
{
  const w = makePage();
  const words = Array.from({ length: 60 }, (_, i) => "word" + (i % 30)).join(" ");
  ev(w, `document.getElementById("sp-text").value = ${JSON.stringify(words)};
         document.getElementById("sp-secs").value = "5";
         scoreSpeak();`);
  assert(ev(w, `S.current.speak === undefined`), "secs=5 refused (U13)");
  ev(w, `document.getElementById("sp-secs").value = "-30"; scoreSpeak();`);
  assert(ev(w, `S.current.speak === undefined`), "secs=-30 refused (U13)");
  ev(w, `document.getElementById("sp-text").value = ${JSON.stringify(Array(45).fill("um").join(" "))};
         document.getElementById("sp-secs").value = "120"; scoreSpeak();`);
  assert(ev(w, `S.current.speak === undefined`), "all-filler transcript refused (U14)");
  ev(w, `document.getElementById("sp-text").value = ${JSON.stringify(Array(300).fill("cat").join(" "))};
         scoreSpeak();`);
  assert(ev(w, `S.current.speak.repRatio <= 1`), "self-repair ratio capped at 1 (U14)");
  ev(w, `S.current = {}; document.getElementById("sp-text").value = ${JSON.stringify(words)}; scoreSpeak();`);
  assert(ev(w, `Number.isFinite(S.current.speak.wpm) && S.current.speak.wpm === 30`), "clean transcript scores (60 words / 120s = 30 wpm)");
}

console.log("== T10: dictation freeze (FIX-8) + beyond-core lemmatization (FIX-11) ==");
{
  const w = makePage();
  ev(w, `document.getElementById("dt-0").value = "the meeting was moved to thursday afternoon"; scoreDict();`);
  const p1 = ev(w, `S.current.dict.pct`);
  assert(ev(w, `[...document.querySelectorAll('#dc-holder input[type="text"]')].every(i => i.disabled)`),
    "inputs frozen after scoring");
  ev(w, `document.getElementById("dt-1").value = "i would have called you but my phone was dead"; scoreDict();`);
  assertEq(ev(w, `S.current.dict.pct`), p1, "re-score after reveal refused (U09)");
  const w2 = makePage();
  for (const word of ["walked", "friends", "things", "wanted", "working", "houses"])
    assert(ev(w2, `coreHas("${word}")`), `"${word}" counts as core (inflection)`);
  for (const word of ["authentication", "quagmire", "infrastructure"])
    assert(!ev(w2, `coreHas("${word}")`), `"${word}" still beyond core`);
}

console.log("== T11: corrupted storage (FIX-4) + no-TTS plays (FIX-23) ==");
{
  const w = makePage({ seedStorage: "5" });
  assertEq(ev(w, `document.querySelectorAll(".tab").length`), 8, "corrupted localStorage primitive: page still builds");
  const w2 = makePage({ noTTS: true });
  ev(w2, `playDict(0); playDict(0);`);
  assertEq(ev(w2, `document.getElementById("dp-0").textContent`), "2", "plays not burned without TTS (U24)");
  const w3 = makePage();
  ev(w3, `playDict(0);`);
  assertEq(ev(w3, `document.getElementById("dp-0").textContent`), "1", "play decremented when audio spoken");
  assertEq(ev(w3, `lastVoiceName`), "TestVoice", "voice recorded (U11)");
}

console.log("== T12: unattempted-module guards (FIX-18) ==");
{
  const w = makePage();
  ev(w, `scoreVocab();`);
  assert(ev(w, `S.current.vocab === undefined`), "empty vocab refused");
  ev(w, `scoreEI();`);
  assert(ev(w, `S.current.ei === undefined`), "empty EI refused");
  ev(w, `scoreEviz();`);
  assert(ev(w, `S.current.eviz === undefined`), "empty evidence refused");
}

console.log(`\n${passes} passed, ${failures} failed`);
if (failures === 0) console.log("SUITE PASS");
else console.log("SUITE FAIL");
