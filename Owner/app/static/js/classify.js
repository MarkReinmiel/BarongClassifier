(function () {
  var fileInput = document.getElementById("fileGal");
  var camInput = document.getElementById("fileCam");
  var clearBtn = document.getElementById("clearBtn");
  var prev = document.getElementById("prev");
  var prompt = document.getElementById("prompt");
  var analyze = document.getElementById("analyze");
  var form = document.getElementById("classifyForm");
  var url = null;

  if (!fileInput || !prev || !analyze || !form) return;

  function clearFile() {
    if (url) URL.revokeObjectURL(url);
    url = null;
    prev.removeAttribute("src");
    prev.alt = "";
    prev.hidden = true;
    prev.style.display = "none";
    if (prompt) prompt.style.display = "";
    analyze.disabled = true;
    if (clearBtn) clearBtn.hidden = true;
    fileInput.value = "";
    if (camInput) camInput.value = "";
  }

  function setFile(file) {
    if (!file) return;
    if (url) URL.revokeObjectURL(url);
    url = URL.createObjectURL(file);
    prev.src = url;
    prev.alt = "Selected textile preview";
    prev.hidden = false;
    prev.style.display = "block";
    if (prompt) prompt.style.display = "none";
    analyze.disabled = false;
    if (clearBtn) clearBtn.hidden = false;

    // Keep the named form field populated for submit (gallery or camera).
    try {
      var transfer = new DataTransfer();
      transfer.items.add(file);
      fileInput.files = transfer.files;
    } catch (err) {
      // Some older mobile browsers block DataTransfer assignment.
    }
  }

  clearFile();

  if (clearBtn) clearBtn.onclick = clearFile;
  fileInput.addEventListener("change", function (event) {
    setFile(event.target.files && event.target.files[0]);
  });
  if (camInput) {
    camInput.addEventListener("change", function (event) {
      setFile(event.target.files && event.target.files[0]);
    });
  }

  form.addEventListener("submit", function (event) {
    if (!fileInput.files || !fileInput.files.length) {
      if (camInput && camInput.files && camInput.files.length) {
        try {
          var transfer = new DataTransfer();
          transfer.items.add(camInput.files[0]);
          fileInput.files = transfer.files;
        } catch (err) {
          // fall through; server may still receive nothing
        }
      }
    }
    if (!fileInput.files || !fileInput.files.length) {
      event.preventDefault();
      analyze.disabled = false;
      return;
    }
    analyze.disabled = true;
    analyze.innerHTML = '<span class="spin"></span> Analyzing…';
  });
})();
