/**
 * Result page image actions — always save/download as WebP.
 */
(function () {
  function imageEl() {
    return (
      document.getElementById("resultImage") ||
      document.querySelector(".result-image-container img") ||
      document.querySelector(".result-hero-photo img")
    );
  }

  function suggestedName() {
    var base =
      (document.getElementById("resultFileName") || {}).textContent ||
      (document.getElementById("predictedType") || {}).textContent ||
      "textile";
    base = String(base)
      .trim()
      .replace(/[\\/:*?"<>|]+/g, "")
      .replace(/\s+/g, "_")
      .replace(/\.(jpe?g|png|webp|bmp)$/i, "")
      .slice(0, 60) || "textile";
    return base + ".webp";
  }

  async function blobAsWebp(img) {
    if (!img || !img.src) throw new Error("No image to save.");
    var src = img.src;
    var sourceBlob = null;
    if (src.indexOf("data:") === 0) {
      sourceBlob = await (await fetch(src)).blob();
    } else {
      try {
        var remote = await fetch(src, { mode: "cors" });
        if (!remote.ok) throw new Error("fetch failed");
        sourceBlob = await remote.blob();
      } catch (err) {
        sourceBlob = null;
      }
    }
    if (sourceBlob && sourceBlob.type === "image/webp") return sourceBlob;

    var canvas = document.createElement("canvas");
    canvas.width = img.naturalWidth || img.width || 1;
    canvas.height = img.naturalHeight || img.height || 1;
    canvas.getContext("2d").drawImage(img, 0, 0);
    return await new Promise(function (resolve, reject) {
      canvas.toBlob(
        function (blob) {
          if (blob) resolve(blob);
          else reject(new Error("Could not encode WebP."));
        },
        "image/webp",
        0.9
      );
    });
  }

  function triggerAnchorDownload(blob, filename) {
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 1500);
  }

  async function saveWithPicker(blob, filename) {
    if (!window.showSaveFilePicker) return false;
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
    await writable.write(blob);
    await writable.close();
    return true;
  }

  async function saveWithShare(blob, filename) {
    var file = new File([blob], filename, { type: "image/webp" });
    if (!navigator.canShare || !navigator.canShare({ files: [file] })) {
      return false;
    }
    await navigator.share({
      files: [file],
      title: "BarongClassifier textile",
    });
    return true;
  }

  async function onDownload() {
    var img = imageEl();
    var filename = suggestedName();
    var blob = await blobAsWebp(img);
    triggerAnchorDownload(blob, filename);
  }

  async function onSave() {
    var img = imageEl();
    var filename = suggestedName();
    var blob = await blobAsWebp(img);
    try {
      if (await saveWithPicker(blob, filename)) return;
    } catch (err) {
      if (err && err.name === "AbortError") return;
    }
    try {
      if (await saveWithShare(blob, filename)) return;
    } catch (err) {
      if (err && err.name === "AbortError") return;
    }
    triggerAnchorDownload(blob, filename);
  }

  function bind(id, handler) {
    var btn = document.getElementById(id);
    if (!btn) return;
    btn.addEventListener("click", function () {
      btn.disabled = true;
      Promise.resolve(handler())
        .catch(function (err) {
          console.error(err);
          window.alert(
            (err && err.message) || "Could not save the image. Try again."
          );
        })
        .finally(function () {
          btn.disabled = false;
        });
    });
  }

  bind("downloadImageBtn", onDownload);
  bind("saveImageBtn", onSave);
})();
