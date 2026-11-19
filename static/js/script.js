(function () {
  "use strict";
  var MAX_BYTES = 5 * 1024 * 1024;

  // Auto-dismiss success/info alerts
  document.querySelectorAll(".alert-success, .alert-info").forEach(function (el) {
    setTimeout(function () { if (window.bootstrap && document.body.contains(el)) bootstrap.Alert.getOrCreateInstance(el).close(); }, 5000);
  });

  // Show/hide password
  document.querySelectorAll("[data-toggle-password]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var input = document.querySelector(btn.getAttribute("data-toggle-password"));
      if (!input) return;
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      var icon = btn.querySelector("i");
      if (icon) icon.className = "bi " + (show ? "bi-eye-slash" : "bi-eye");
    });
  });

  // Count-up animation for numbers
  if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    document.querySelectorAll(".stat-card h2").forEach(function (el) {
      var text = el.textContent.trim(), target = parseInt(text, 10);
      if (isNaN(target) || String(target) !== text || target === 0) return;
      var start = null; el.textContent = "0";
      (function step(ts) {
        if (start === null) start = ts;
        var p = Math.min((ts - start) / 700, 1);
        el.textContent = Math.round(target * p);
        if (p < 1) requestAnimationFrame(step);
      })(performance.now());
    });
  }

  // Prevent double submits (forms with data-ajax are handled by their own script)
  document.querySelectorAll('form[method="post"]').forEach(function (form) {
    if (form.hasAttribute("data-ajax")) return;
    form.addEventListener("submit", function (e) {
      if (e.defaultPrevented) return;
      var btn = form.querySelector("button:not([type='button'])");
      if (!btn) return;
      setTimeout(function () {
        btn.dataset.orig = btn.innerHTML; btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> ' + (document.body.dataset.loading || "...");
      }, 0);
    });
  });
  window.addEventListener("pageshow", function (e) {
    if (!e.persisted) return;
    document.querySelectorAll("button[data-orig]").forEach(function (b) { b.disabled = false; b.innerHTML = b.dataset.orig; });
  });

  // Saved farm -> fill soil type and location on the advisory / irrigation / fertilizer forms
  var farm = document.getElementById("farmSelect");
  if (farm) farm.addEventListener("change", function () {
    var o = farm.options[farm.selectedIndex]; if (!o || !o.value) return;
    var soil = document.getElementById("soilType"), loc = document.getElementById("location"), crop = document.getElementById("cropSelect");
    if (soil && o.dataset.soil) soil.value = o.dataset.soil;
    if (loc && o.dataset.location) loc.value = o.dataset.location;
    if (crop && o.dataset.crop) crop.value = o.dataset.crop;
  });

  // ---- Image upload: preview, drag & drop, camera capture, progress bar -------------------------------
  var input = document.getElementById("leafImage");
  if (!input) return;
  var preview = document.getElementById("imagePreview"), placeholder = document.getElementById("previewPlaceholder"),
      box = document.getElementById("previewBox"), form = document.getElementById("detectForm"),
      cameraBtn = document.getElementById("cameraBtn"), cameraInput = document.getElementById("cameraInput"),
      video = document.getElementById("cameraVideo"), captureBtn = document.getElementById("captureBtn"),
      msg = document.getElementById("uploadMsg"), stream = null;

  function say(text) { if (msg) { msg.textContent = text || ""; msg.classList.toggle("d-none", !text); } }
  function setFile(file) {
    if (!file) return;
    if (["image/jpeg", "image/png"].indexOf(file.type) === -1) { say(form.dataset.errType); input.value = ""; return; }
    if (file.size > MAX_BYTES) { say(form.dataset.errSize); input.value = ""; return; }
    var dt = new DataTransfer(); dt.items.add(file); input.files = dt.files; say("");
    preview.src = URL.createObjectURL(file); preview.classList.remove("d-none"); placeholder.classList.add("d-none");
    if (video) video.classList.add("d-none");
  }
  input.addEventListener("change", function () { setFile(input.files[0]); });
  if (box) {
    box.addEventListener("click", function (e) { if (e.target === box || e.target.closest("#previewPlaceholder") || e.target === preview) input.click(); });
    ["dragover", "dragenter"].forEach(function (ev) { box.addEventListener(ev, function (e) { e.preventDefault(); box.classList.add("dragover"); }); });
    ["dragleave", "drop"].forEach(function (ev) { box.addEventListener(ev, function (e) { e.preventDefault(); box.classList.remove("dragover"); }); });
    box.addEventListener("drop", function (e) { if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]); });
  }
  function stopCamera() { if (stream) { stream.getTracks().forEach(function (t) { t.stop(); }); stream = null; } if (video) video.classList.add("d-none"); if (captureBtn) captureBtn.classList.add("d-none"); }
  if (cameraInput) cameraInput.addEventListener("change", function () { setFile(cameraInput.files[0]); });
  if (cameraBtn) cameraBtn.addEventListener("click", function () {
    var mobile = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
    if (mobile && cameraInput) { cameraInput.click(); return; }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { say(form.dataset.errCamera); return; }
    navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } }).then(function (s) {
      stream = s; video.srcObject = s; video.classList.remove("d-none"); placeholder.classList.add("d-none"); preview.classList.add("d-none");
      captureBtn.classList.remove("d-none"); video.play();
    }).catch(function () { say(form.dataset.errCamera); });
  });
  if (captureBtn) captureBtn.addEventListener("click", function () {
    var c = document.createElement("canvas"); c.width = video.videoWidth; c.height = video.videoHeight;
    c.getContext("2d").drawImage(video, 0, 0);
    c.toBlob(function (blob) { if (blob) setFile(new File([blob], "camera.jpg", { type: "image/jpeg" })); stopCamera(); }, "image/jpeg", 0.92);
  });

  // Submit with a progress bar; the server's redirect target replaces the page (flash messages are kept)
  form.addEventListener("submit", function (e) {
    if (!input.files.length) { e.preventDefault(); say(form.dataset.errNone); return; }
    if (!window.XMLHttpRequest || !window.FormData) return;           // no progress support: normal submit
    e.preventDefault(); stopCamera();
    var btn = document.getElementById("detectBtn"), wrap = document.getElementById("uploadProgress"), bar = wrap.querySelector(".progress-bar"), label = document.getElementById("progressLabel");
    btn.disabled = true; wrap.classList.add("active"); label.textContent = form.dataset.uploading;
    var xhr = new XMLHttpRequest();
    xhr.open("POST", form.action || window.location.href);
    xhr.upload.onprogress = function (ev) {
      if (!ev.lengthComputable) return;
      var pct = Math.round(ev.loaded / ev.total * 100); bar.style.width = pct + "%";
      if (pct >= 100) { label.textContent = form.dataset.analysing; bar.classList.add("progress-bar-striped", "progress-bar-animated"); }
    };
    xhr.onload = function () {
      document.open(); document.write(xhr.responseText); document.close();
      if (xhr.responseURL && window.history && history.replaceState) history.replaceState(null, "", xhr.responseURL);
    };
    xhr.onerror = function () { btn.disabled = false; wrap.classList.remove("active"); say(form.dataset.errNetwork); };
    xhr.send(new FormData(form));
  });
})();
