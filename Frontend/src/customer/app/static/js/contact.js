(function () {
  var form = document.getElementById("contactForm");
  if (!form) return;

  var topicInput = document.getElementById("contactTopic");
  var topics = form.querySelectorAll(".contact-topic");
  var message = document.getElementById("contactMessage");
  var count = document.getElementById("contactCount");
  var fileInput = document.getElementById("contactFile");
  var fileName = document.getElementById("contactFileName");
  var SUPPORT = "barongclassifier@gmail.com";

  topics.forEach(function (btn) {
    btn.addEventListener("click", function () {
      topics.forEach(function (b) {
        b.classList.remove("is-active");
      });
      btn.classList.add("is-active");
      if (topicInput) topicInput.value = btn.getAttribute("data-topic") || "Other";
    });
  });

  function updateCount() {
    if (!message || !count) return;
    count.textContent = String(message.value.length) + " / 600";
  }

  if (message) {
    message.addEventListener("input", updateCount);
    updateCount();
  }

  if (fileInput && fileName) {
    fileInput.addEventListener("change", function () {
      var file = fileInput.files && fileInput.files[0];
      if (!file) {
        fileName.hidden = true;
        fileName.textContent = "";
        return;
      }
      if (file.size > 3 * 1024 * 1024) {
        fileInput.value = "";
        fileName.hidden = false;
        fileName.textContent = "File is larger than 3 MB. Please choose a smaller image.";
        return;
      }
      fileName.hidden = false;
      fileName.textContent = "Selected: " + file.name + " (attach manually in Gmail if needed)";
    });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var first = (document.getElementById("contactFirst") || {}).value || "";
    var last = (document.getElementById("contactLast") || {}).value || "";
    var email = (document.getElementById("contactEmail") || {}).value || "";
    var bodyMsg = (message && message.value) || "";
    var topic = (topicInput && topicInput.value) || "Other";

    if (!email.trim() || !bodyMsg.trim()) {
      if (!email.trim() && document.getElementById("contactEmail")) {
        document.getElementById("contactEmail").focus();
      } else if (message) {
        message.focus();
      }
      return;
    }

    var lines = [
      "Topic: " + topic,
      "Name: " + (first + " " + last).trim(),
      "Reply-to: " + email.trim(),
      "",
      bodyMsg.trim(),
    ];
    var su = encodeURIComponent("Barongcognition — " + topic);
    var body = encodeURIComponent(lines.join("\n"));
    var url =
      "https://mail.google.com/mail/?view=cm&fs=1&to=" +
      encodeURIComponent(SUPPORT) +
      "&su=" +
      su +
      "&body=" +
      body;
    window.open(url, "_blank", "noopener,noreferrer");
  });
})();
