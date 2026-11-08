(function () {
  var fileInput = document.getElementById("fileGal");
  var camInput = document.getElementById("fileCam");
  var clearBtn = document.getElementById("clearBtn");
  var prev = document.getElementById("prev");
  var prompt = document.getElementById("prompt");
  var analyze = document.getElementById("analyze");
  var classifyHelp = document.getElementById("classifyHelp");
  var form = document.getElementById("classifyForm");
  var loading = document.getElementById("classifyLoading");
  var previewActions = document.getElementById("previewActions");
  var saveImageBtn = document.getElementById("saveImage");
  var viewPreviewBtn = document.getElementById("viewPreviewBtn");
  var downloadPreviewBtn = document.getElementById("downloadPreviewBtn");
  var previewImageModal = document.getElementById("previewImageModal");
  var fullPreviewImage = document.getElementById("fullPreviewImage");
  var closePreviewImageModal = document.getElementById("closePreviewImageModal");
  var url = null;
  var currentFile = null;
  var submitting = false;

  if (!fileInput || !prev || !analyze || !form) return;

  function setAnalyzeVisible(visible) {
    analyze.hidden = !visible;
    analyze.disabled = !visible;
    if (classifyHelp) classifyHelp.hidden = !visible;
  }

  function showLoading(on) {
    if (!loading) return;
    loading.hidden = !on;
    loading.setAttribute("aria-busy", on ? "true" : "false");
  }

  function clearFile() {
    if (url) URL.revokeObjectURL(url);
    url = null;
    currentFile = null;
    prev.removeAttribute("src");
    prev.alt = "";
    prev.hidden = true;
    prev.style.display = "none";
    if (prompt) prompt.style.display = "";
    setAnalyzeVisible(false);
    if (clearBtn) clearBtn.hidden = true;
    if (previewActions) previewActions.hidden = true;
    fileInput.value = "";
    if (camInput) camInput.value = "";
  }

  function setFile(file) {
    if (!file) return;
    if (url) URL.revokeObjectURL(url);
    currentFile = file;
    url = URL.createObjectURL(file);
    prev.src = url;
    prev.alt = "Selected textile preview";
    prev.hidden = false;
    prev.style.display = "block";
    if (prompt) prompt.style.display = "none";
    setAnalyzeVisible(true);
    if (clearBtn) clearBtn.hidden = false;
    if (previewActions) previewActions.hidden = false;

    try {
      var transfer = new DataTransfer();
      transfer.items.add(file);
      fileInput.files = transfer.files;
    } catch (err) {
      // Some older mobile browsers block DataTransfer assignment.
    }
  }

  function blobToWebp(blob) {
    if (blob && blob.type === "image/webp") {
      return Promise.resolve(blob);
    }
    return new Promise(function (resolve, reject) {
      var img = new Image();
      var objectUrl = URL.createObjectURL(blob);
      img.onload = function () {
        var canvas = document.createElement("canvas");
        canvas.width = img.naturalWidth || img.width || 1;
        canvas.height = img.naturalHeight || img.height || 1;
        canvas.getContext("2d").drawImage(img, 0, 0);
        URL.revokeObjectURL(objectUrl);
        canvas.toBlob(
          function (out) {
            if (out) resolve(out);
            else reject(new Error("Could not encode WebP."));
          },
          "image/webp",
          0.9
        );
      };
      img.onerror = function () {
        URL.revokeObjectURL(objectUrl);
        reject(new Error("Could not read the photo."));
      };
      img.src = objectUrl;
    });
  }

  function downloadBlob(blob, filename) {
    var href = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = href;
    a.download = filename;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () {
      URL.revokeObjectURL(href);
    }, 1500);
  }

  async function getPreviewWebp() {
    var source = currentFile || (fileInput.files && fileInput.files[0]);
    if (!source) throw new Error("Capture or choose a photo first.");
    return blobToWebp(source);
  }

  async function savePreviewAsWebp() {
    var webp = await getPreviewWebp();
    var filename = "barong-capture-" + Date.now() + ".webp";
    try {
      if (window.showSaveFilePicker) {
        var handle = await window.showSaveFilePicker({
          suggestedName: filename,
          types: [
            {
              description: "WebP image",
              accept: { "image/webp": [".webp"] },
            },
          ],
        });
        var writable = await handle.createWritable();
        await writable.write(webp);
        await writable.close();
        return;
      }
    } catch (err) {
      if (err && err.name === "AbortError") return;
    }
    try {
      var shareFile = new File([webp], filename, { type: "image/webp" });
      if (navigator.canShare && navigator.canShare({ files: [shareFile] })) {
        await navigator.share({ files: [shareFile], title: "BarongClassifier photo" });
        return;
      }
    } catch (err2) {
      if (err2 && err2.name === "AbortError") return;
    }
    downloadBlob(webp, filename);
  }

  async function downloadPreviewAsWebp() {
    var webp = await getPreviewWebp();
    downloadBlob(webp, "barong-capture-" + Date.now() + ".webp");
  }

  function openPreviewModal() {
    if (!previewImageModal || !fullPreviewImage) return;
    var src = (prev && prev.src) || url;
    if (!src) return;
    fullPreviewImage.src = src;
    previewImageModal.hidden = false;
  }

  function closePreviewModal() {
    if (!previewImageModal) return;
    previewImageModal.hidden = true;
  }

  clearFile();

  if (clearBtn) clearBtn.onclick = clearFile;
  if (viewPreviewBtn) {
    viewPreviewBtn.addEventListener("click", openPreviewModal);
  }
  if (closePreviewImageModal) {
    closePreviewImageModal.addEventListener("click", closePreviewModal);
  }
  if (previewImageModal) {
    previewImageModal.addEventListener("click", function (event) {
      if (event.target === previewImageModal) closePreviewModal();
    });
  }
  if (saveImageBtn) {
    saveImageBtn.addEventListener("click", function () {
      saveImageBtn.disabled = true;
      Promise.resolve(savePreviewAsWebp())
        .catch(function (err) {
          console.error(err);
          window.alert((err && err.message) || "Could not save the photo.");
        })
        .finally(function () {
          saveImageBtn.disabled = false;
        });
    });
  }
  if (downloadPreviewBtn) {
    downloadPreviewBtn.addEventListener("click", function () {
      downloadPreviewBtn.disabled = true;
      Promise.resolve(downloadPreviewAsWebp())
        .catch(function (err) {
          console.error(err);
          window.alert((err && err.message) || "Could not download the photo.");
        })
        .finally(function () {
          downloadPreviewBtn.disabled = false;
        });
    });
  }
  fileInput.addEventListener("change", function (event) {
    setFile(event.target.files && event.target.files[0]);
  });
  if (camInput) {
    camInput.addEventListener("change", function (event) {
      setFile(event.target.files && event.target.files[0]);
    });
  }

  form.addEventListener("submit", function (event) {
    if (submitting) {
      event.preventDefault();
      return;
    }
    if (!fileInput.files || !fileInput.files.length) {
      if (camInput && camInput.files && camInput.files.length) {
        try {
          var transfer = new DataTransfer();
          transfer.items.add(camInput.files[0]);
          fileInput.files = transfer.files;
        } catch (err) {
          // fall through
        }
      }
    }
    if (!fileInput.files || !fileInput.files.length) {
      event.preventDefault();
      setAnalyzeVisible(false);
      showLoading(false);
      return;
    }
    submitting = true;
    analyze.disabled = true;
    analyze.innerHTML = '<span class="spin"></span> Analyzing…';
    showLoading(true);
  });

  window.addEventListener("pageshow", function () {
    submitting = false;
    showLoading(false);
    if (analyze && fileInput.files && fileInput.files.length) {
      setAnalyzeVisible(true);
      analyze.innerHTML =
        '<span class="classify-analyze-icon" aria-hidden="true">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>' +
        "</span><span>Analyze Textile</span>";
    } else {
      setAnalyzeVisible(false);
    }
  });
})();
