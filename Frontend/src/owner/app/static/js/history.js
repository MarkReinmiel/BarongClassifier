(function () {
  var previewModal = document.getElementById("historyPreviewModal");
  var previewImage = document.getElementById("historyPreviewImage");
  var previewTitle = document.getElementById("historyPreviewTitle");
  var deleteModal = document.getElementById("historyDeleteModal");
  var deleteLabel = document.getElementById("historyDeleteLabel");
  var deleteConfirm = document.getElementById("historyDeleteConfirm");
  var pendingDeleteUrl = "";
  var pendingRow = null;

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) {
      var fromMeta = meta.getAttribute("content") || "";
      if (fromMeta) return fromMeta;
    }
    var input = document.querySelector('input[name="csrf_token"]');
    return input ? input.value || "" : "";
  }

  function openDialog(dialog) {
    if (!dialog) return;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  function closeDialog(dialog) {
    if (!dialog) return;
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
  }

  function openPreview(src, label) {
    if (!previewModal || !previewImage) return;
    previewImage.src = src || "";
    previewImage.alt = label ? label + " preview" : "Classification preview";
    if (previewTitle) previewTitle.textContent = label || "Classification preview";
    openDialog(previewModal);
  }

  function parseJsonResponse(response) {
    return response.text().then(function (text) {
      var data = null;
      if (text) {
        try {
          data = JSON.parse(text);
        } catch (_error) {
          var hint =
            response.status === 400
              ? "Security check failed. Refresh the page and try again."
              : "Server returned an unexpected response (" + response.status + ").";
          throw new Error(hint);
        }
      }
      return { ok: response.ok, status: response.status, data: data || {} };
    });
  }

  document.addEventListener("click", function (event) {
    var previewBtn = event.target.closest("[data-history-preview]");
    if (previewBtn) {
      openPreview(
        previewBtn.getAttribute("data-preview-src"),
        previewBtn.getAttribute("data-preview-label")
      );
      return;
    }

    if (event.target.closest("[data-preview-close]")) {
      closeDialog(previewModal);
      return;
    }

    var deleteBtn = event.target.closest("[data-history-delete]");
    if (deleteBtn) {
      pendingDeleteUrl = deleteBtn.getAttribute("data-delete-url") || "";
      pendingRow = deleteBtn.closest("[data-history-row]");
      if (deleteLabel) {
        deleteLabel.textContent =
          deleteBtn.getAttribute("data-delete-label") || "this classification";
      }
      openDialog(deleteModal);
      return;
    }

    if (event.target.closest("[data-delete-cancel]")) {
      pendingDeleteUrl = "";
      pendingRow = null;
      closeDialog(deleteModal);
    }
  });

  if (previewModal) {
    previewModal.addEventListener("click", function (event) {
      if (event.target === previewModal) closeDialog(previewModal);
    });
  }
  if (deleteModal) {
    deleteModal.addEventListener("click", function (event) {
      if (event.target === deleteModal) {
        pendingDeleteUrl = "";
        pendingRow = null;
        closeDialog(deleteModal);
      }
    });
  }

  if (deleteConfirm) {
    deleteConfirm.addEventListener("click", function () {
      if (!pendingDeleteUrl) return;
      var token = csrfToken();
      if (!token) {
        window.alert("Security token missing. Refresh the page and try again.");
        return;
      }
      deleteConfirm.disabled = true;
      var body = new URLSearchParams();
      body.set("csrf_token", token);
      fetch(pendingDeleteUrl, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": token,
          "X-CSRF-Token": token,
        },
        body: body.toString(),
        credentials: "same-origin",
      })
        .then(parseJsonResponse)
        .then(function (result) {
          if (!result.ok || !result.data || !result.data.ok) {
            throw new Error(
              (result.data && result.data.error) || "Could not delete classification."
            );
          }
          if (pendingRow) pendingRow.remove();
          closeDialog(deleteModal);
          if (!document.querySelector("[data-history-row]")) {
            window.location.reload();
          }
        })
        .catch(function (error) {
          window.alert(error.message || "Could not delete classification.");
        })
        .finally(function () {
          deleteConfirm.disabled = false;
          pendingDeleteUrl = "";
          pendingRow = null;
        });
    });
  }
})();
