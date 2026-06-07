// app.js — sharing the "message for family" and saving a family phone number.
// Used by both the result page and the history-detail page.

function getMessage() {
  var el = document.getElementById("child-message");
  return el ? el.value : "";
}

// Copy the family message to the clipboard.
function copyMessage() {
  var el = document.getElementById("child-message");
  if (!el) return;
  el.select();
  document.execCommand("copy");
  alert(el.dataset.copied || "Copied");
}

// One-tap forward: use the phone's native share sheet (WhatsApp, WeChat, SMS…).
// Falls back to copying on browsers without the Web Share API (most desktops).
function shareMessage() {
  var text = getMessage();
  if (navigator.share) {
    navigator.share({ text: text }).catch(function () {});
  } else {
    copyMessage();
  }
}

// Open WhatsApp directly with the message pre-filled (very common in the UK).
function whatsappShare() {
  var text = encodeURIComponent(getMessage());
  window.open("https://wa.me/?text=" + text, "_blank");
}

// --- family phone number, stored only in this browser (no server) ---

function saveFamily() {
  var inp = document.getElementById("family-number");
  if (!inp) return;
  var n = inp.value.trim();
  if (n) {
    localStorage.setItem("familyPhone", n);
    renderFamily();
  }
}

function changeFamily() {
  localStorage.removeItem("familyPhone");
  renderFamily();
}

function renderFamily() {
  var n = localStorage.getItem("familyPhone");
  var setBox = document.getElementById("family-set");
  var saveBox = document.getElementById("family-save");
  var link = document.getElementById("family-call");
  if (!setBox || !saveBox) return; // not on a page with the call section
  if (n) {
    saveBox.style.display = "none";
    setBox.style.display = "flex";
    if (link) {
      link.href = "tel:" + n;
      var num = link.querySelector(".num");
      if (num) num.textContent = n;
    }
  } else {
    saveBox.style.display = "block";
    setBox.style.display = "none";
  }
}

document.addEventListener("DOMContentLoaded", renderFamily);
