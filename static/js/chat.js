(function () {
  "use strict";
  var root = document.getElementById("chatApp");
  if (!root) return;
  var box = document.getElementById("chatBox"), form = document.getElementById("chatForm"), input = document.getElementById("chatInput"),
    sendBtn = document.getElementById("chatSend"), langSel = document.getElementById("chatLang"),
    csrf = document.body.dataset.csrf, convId = root.dataset.conv ? parseInt(root.dataset.conv, 10) : null;
  var T = { thinking: root.dataset.thinking, network: root.dataset.network };

  function scrollDown() { box.scrollTop = box.scrollHeight; }
  function bubble(text, cls) {
    var d = document.createElement("div"); d.className = "bubble " + cls; d.textContent = text; box.appendChild(d); scrollDown(); return d;
  }
  scrollDown();

  async function send(text) {
    text = (text || "").trim();
    if (!text) return;

    var empty = document.getElementById("chatEmpty");
    if (empty) empty.remove();

    bubble(text, "user");
    input.value = "";
    sendBtn.disabled = true;

    var typing = document.createElement("div");
    typing.className = "bubble bot typing";
    typing.innerHTML = "<span></span><span></span><span></span>";
    box.appendChild(typing);
    scrollDown();

    var assistantBubble = null;
    var fullReply = "";
    var conversationSaved = false;

    try {
      var res = await fetch(root.dataset.api, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrf,
          "Accept": "text/event-stream"
        },
        body: JSON.stringify({
          message: text,
          conversation_id: convId,
          language: langSel.value,
          stream: true
        })
      });

      if (!res.ok || !res.body) {
        throw new Error(T.network);
      }

      var reader = res.body.getReader();
      var decoder = new TextDecoder();
      var buffer = "";
      var serverError = null;

      function processFrame(frame) {
        var eventName = "";
        var dataLines = [];

        frame.split("\n").forEach(function (line) {
          if (line.indexOf("event:") === 0) {
            eventName = line.slice(6).trim();
          } else if (line.indexOf("data:") === 0) {
            dataLines.push(line.slice(5).trim());
          }
        });

        if (!eventName || !dataLines.length) return;

        var payload = JSON.parse(dataLines.join("\n"));

        if (eventName === "token") {
          if (!assistantBubble) {
            typing.remove();
            assistantBubble = bubble("", "bot");
          }

          var chunk = payload.text || "";
          fullReply += chunk;
          assistantBubble.textContent = fullReply;
          scrollDown();

        } else if (eventName === "done") {
          convId = payload.conversation_id;
          root.dataset.conv = convId;
          conversationSaved = true;

        } else if (eventName === "error") {
          serverError = payload.error || T.network;
        }
      }

      while (true) {
        var result = await reader.read();

        buffer += decoder.decode(result.value || new Uint8Array(), {
          stream: !result.done
        });

        buffer = buffer.replace(/\r\n/g, "\n");

        var separator;
        while ((separator = buffer.indexOf("\n\n")) !== -1) {
          var frame = buffer.slice(0, separator);
          buffer = buffer.slice(separator + 2);
          processFrame(frame);
        }

        if (result.done) break;
      }

      if (buffer.trim()) {
        processFrame(buffer);
      }

      typing.remove();

      if (serverError) {
        throw new Error(serverError);
      }

      if (!conversationSaved || !fullReply.trim()) {
        throw new Error(T.network);
      }

      if (window.FarmerVoice) {
        window.FarmerVoice.speakReply(fullReply, langSel.value);
      }

      if (history.replaceState) {
        history.replaceState(
          null,
          "",
          root.dataset.page + "?c=" + convId
        );
      }

    } catch (e) {
      typing.remove();

      if (assistantBubble) {
        assistantBubble.remove();
      }

      bubble(e.message || T.network, "bot err");

    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  }
  form.addEventListener("submit", function (e) { e.preventDefault(); send(input.value); });
  input.addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input.value); } });
  document.querySelectorAll("[data-suggest]").forEach(function (b) { b.addEventListener("click", function () { input.value = b.dataset.suggest; input.focus(); }); });
  window.FarmerChat = { send: send, input: input, langSelect: langSel };
})();
