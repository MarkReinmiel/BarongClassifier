(function () {
  var fileInput = document.getElementById("fileGal");
  var camInput = document.getElementById("fileCam");
  var clearBtn = document.getElementById("clearBtn");
  var prev = document.getElementById("prev");
  var prompt = document.getElementById("prompt");
  var analyze = document.getElementById("analyze");
  var form = document.getElementById("classifyForm");
  var drop = document.getElementById("drop");
  var chooseSourceBtn = document.getElementById("chooseSourceBtn");
  var sourceSheet = document.getElementById("sourceSheet");
  var sourceGallery = document.getElementById("sourceGallery");
  var sourceCamera = document.getElementById("sourceCamera");
  var openCamera = document.getElementById("openCamera");
  var previewActions = document.getElementById("previewActions");
  var saveImageBtn = document.getElementById("saveImage");
  var url = null;
  var lastFocus = null;
  var currentFile = null;

  if (!fileInput || !prev || !analyze || !form) return;

  function isMobileView() {
    return window.matchMedia("(max-width: 899px)").matches;
  }

  function clearFile() {
    if (url) URL.revokeObjectURL(url);
    url = null;
    currentFile = null;
    prev.removeAttribute("src");
    prev.alt = "";
    prev.hidden = true;
    if (prompt) prompt.style.display = "";
    analyze.disabled = true;
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
    if (prompt) prompt.style.display = "none";
    analyze.disabled = false;
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

  async function savePreviewAsWebp() {
    var source = currentFile || (fileInput.files && fileInput.files[0]);
    if (!source) throw new Error("Capture or choose a photo first.");
    var webp = await blobToWebp(source);
    var stamp = Date.now();
    var filename = "barong-capture-" + stamp + ".webp";
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

  function openGalleryPicker() {
    closeSourceSheet();
    try {
      fileInput.click();
    } catch (err) {
      /* ignore */
    }
  }

  function openLiveCamera() {
    closeSourceSheet();
    if (openCamera) {
      try {
        openCamera.click();
        return;
      } catch (err) {
        /* fall through */
      }
    }
    // Native capture fallback when WebRTC trigger is unavailable.
    if (camInput) {
      try {
        camInput.click();
      } catch (err2) {
        /* ignore */
      }
    }
  }

  function openSourceSheet() {
    if (!sourceSheet) {
      openGalleryPicker();
      return;
    }
    lastFocus = document.activeElement;
    sourceSheet.hidden = false;
    sourceSheet.setAttribute("aria-hidden", "false");
    document.body.classList.add("source-sheet-open");
    var first = sourceGallery || sourceSheet.querySelector("button");
    if (first && typeof first.focus === "function") first.focus();
  }

  function closeSourceSheet() {
    if (!sourceSheet || sourceSheet.hidden) return;
    sourceSheet.hidden = true;
    sourceSheet.setAttribute("aria-hidden", "true");
    document.body.classList.remove("source-sheet-open");
    if (lastFocus && typeof lastFocus.focus === "function") {
      try {
        lastFocus.focus();
      } catch (err) {
        /* ignore */
      }
    }
    lastFocus = null;
  }

  function beginChooseImage(event) {
    if (event) {
      event.preventDefault();
      event.stopPropagation();
    }
    if (isMobileView()) openSourceSheet();
    else openGalleryPicker();
  }

  if (clearBtn) clearBtn.onclick = clearFile;
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
  fileInput.addEventListener("change", function (event) {
    setFile(event.target.files && event.target.files[0]);
  });
  if (camInput) {
    camInput.addEventListener("change", function (event) {
      setFile(event.target.files && event.target.files[0]);
    });
  }

  if (chooseSourceBtn) {
    chooseSourceBtn.addEventListener("click", beginChooseImage);
  }

  if (drop) {
    drop.addEventListener("click", function (event) {
      // Ignore clicks on the clear control inside the preview card.
      if (event.target && event.target.closest && event.target.closest("#clearBtn")) return;
      if (prev && !prev.hidden) return;
      beginChooseImage(event);
    });
    drop.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") beginChooseImage(event);
    });
    if (!drop.hasAttribute("tabindex")) drop.setAttribute("tabindex", "0");
    if (!drop.getAttribute("role")) drop.setAttribute("role", "button");
    drop.setAttribute("aria-label", "Choose an image to classify");
  }

  if (sourceGallery) {
    sourceGallery.addEventListener("click", function () {
      openGalleryPicker();
    });
  }
  if (sourceCamera) {
    sourceCamera.addEventListener("click", function () {
      openLiveCamera();
    });
  }
  if (sourceSheet) {
    sourceSheet.querySelectorAll("[data-source-dismiss]").forEach(function (node) {
      node.addEventListener("click", closeSourceSheet);
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && sourceSheet && !sourceSheet.hidden) {
        event.preventDefault();
        closeSourceSheet();
      }
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
          // ignore
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

  window.BarongClassify = {
    openGalleryPicker: openGalleryPicker,
    openLiveCamera: openLiveCamera,
    openSourceSheet: openSourceSheet,
    closeSourceSheet: closeSourceSheet,
    isMobileView: isMobileView,
  };
})();
