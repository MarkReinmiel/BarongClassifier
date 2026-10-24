(function () {
  var fileInput = document.getElementById("fileGal");
  var camInput = document.getElementById("fileCam");
  var camBtn = document.getElementById("camBtn");
  var prev = document.getElementById("prev");
  var prompt = document.getElementById("prompt");
  var analyze = document.getElementById("analyze");
  var form = document.getElementById("classifyForm");
  var url = null;
  var mobileCameraQuery = window.matchMedia("(max-width: 899px)");

  function isMobileCameraView() {
    return mobileCameraQuery.matches;
  }

  function setFile(file) {
    if (!file) return;
    if (url) URL.revokeObjectURL(url);
    url = URL.createObjectURL(file);
    prev.src = url;
    prev.hidden = false;
    if (prompt) prompt.style.display = "none";
    analyze.disabled = false;
    var transfer = new DataTransfer();
    transfer.items.add(file);
    fileInput.files = transfer.files;
  }

  document.getElementById("galBtn").onclick = function () { fileInput.click(); };
  if (camBtn) {
    camBtn.onclick = function () {
      if (!isMobileCameraView()) return;
      camInput.click();
    };
  }
  fileInput.onchange = function (event) { setFile(event.target.files[0]); };
  camInput.onchange = function (event) { setFile(event.target.files[0]); };

  form.addEventListener("submit", function () {
    analyze.disabled = true;
    analyze.innerHTML = '<span class="spin"></span> Analyzing…';
  });
})();
