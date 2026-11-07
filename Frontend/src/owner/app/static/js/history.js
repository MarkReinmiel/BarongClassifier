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
    return meta ? meta.getAttribute("content") || "" : "";
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
      deleteConfirm.disabled = true;
      fetch(pendingDeleteUrl, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": csrfToken(),
        },
        credentials: "same-origin",
      })
        .then(function (response) {
          return response.json().then(function (data) {
            return { ok: response.ok, data: data };
          });
        })
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
