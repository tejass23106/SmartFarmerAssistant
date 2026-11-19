/* Voice assistant helpers: speech-to-text (Web Speech API, when the browser supports it) and read-aloud.
   Speech is processed by the browser/OS, not by this server. The recognised text is shown to the farmer, who
   presses Send; nothing is submitted automatically. */
(function () {
  "use strict";
  var LANG = { en: "en-IN", kn: "kn-IN", hi: "hi-IN" };
  var S = document.getElementById("voiceStrings");
  var ui = S ? S.dataset : {};
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  var TTS = "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
  var langSel = document.getElementById("chatLang"), input = document.getElementById("chatInput");
  var micBtn = document.getElementById("micBtn"), ttsWrap = document.getElementById("ttsWrap"), ttsToggle = document.getElementById("ttsToggle");

  function note(text, cls) {
    var el = document.getElementById("voiceMsg");
    if (!el) return;
    el.textContent = text || "";
    el.className = "alert py-2 small mt-2 " + (text ? (cls || "alert-warning") : "d-none");
  }
  function currentLang() { return langSel ? langSel.value : "en"; }

  function pickVoice(lang) {
    if (!TTS) return null;
    var want = (LANG[lang] || "en-IN").toLowerCase(), base = want.split("-")[0];
    var all = window.speechSynthesis.getVoices() || [];
    return all.find(function (v) { return v.lang.toLowerCase() === want; }) ||
           all.find(function (v) { return v.lang.toLowerCase().indexOf(base) === 0; }) || null;
  }

  function speakReply(text, lang) {
    if (!TTS || !ttsToggle || !ttsToggle.checked || !text) return;
    var u = new SpeechSynthesisUtterance(text.replace(/[*#`]/g, ""));
    u.lang = LANG[lang] || "en-IN";
    var v = pickVoice(lang);
    if (v) { u.voice = v; note(""); }
    else if (lang !== "en") { note(ui.novoice, "alert-info"); }
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
  }

  function setupTts() {
    if (!TTS) { return; }
    if (ttsWrap) ttsWrap.classList.remove("d-none");
    if (window.speechSynthesis.onvoiceschanged !== undefined) window.speechSynthesis.onvoiceschanged = function () {};
  }

  function setupMic() {
    if (!micBtn) return;
    if (!SR) { micBtn.classList.add("d-none"); note(ui.unsupported); return; }
    micBtn.classList.remove("d-none");
    var rec = null, listening = false;
    micBtn.addEventListener("click", function () {
      if (listening) { rec && rec.stop(); return; }
      rec = new SR();
      rec.lang = LANG[currentLang()] || "en-IN";
      rec.interimResults = false;
      rec.maxAlternatives = 1;
      rec.onstart = function () { listening = true; micBtn.classList.add("listening"); note(ui.listening, "alert-info"); };
      rec.onresult = function (e) {
        var text = (e.results[0] && e.results[0][0] && e.results[0][0].transcript) || "";
        input.value = text.trim();
        var heard = document.getElementById("voiceHeard");
        if (heard) { heard.textContent = ui.heard + " " + text; heard.classList.remove("d-none"); }
        note("");
        input.focus();
      };
      rec.onerror = function (e) {
        var msg = e.error === "not-allowed" || e.error === "service-not-allowed" ? ui.denied
                : e.error === "no-speech" ? ui.nospeech : ui.nospeech;
        note(msg);
      };
      rec.onend = function () { listening = false; micBtn.classList.remove("listening"); };
      try { rec.start(); } catch (err) { note(ui.nospeech); }
    });
  }

  if (window.speechSynthesis && window.speechSynthesis.getVoices) window.speechSynthesis.getVoices();
  setupTts();
  setupMic();
  window.FarmerVoice = { speakReply: speakReply, supported: { recognition: !!SR, speech: TTS } };
})();
