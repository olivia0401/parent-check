// Sharing the "message for family" + saving a family contact, used on both
// the result page and history detail.

function getMessage() {
  var el = document.getElementById("child-message");
  return el ? el.value : "";
}

function copyMessage() {
  var el = document.getElementById("child-message");
  if (!el) return;
  el.select();
  document.execCommand("copy");
  alert(el.dataset.copied || "Copied");
}

// native share sheet where available, otherwise just copy
function shareMessage() {
  var text = getMessage();
  if (navigator.share) {
    navigator.share({ text: text }).catch(function () {});
  } else {
    copyMessage();
  }
}

function whatsappShare() {
  var text = encodeURIComponent(getMessage());
  window.open("https://wa.me/?text=" + text, "_blank");
}

// no web API to send directly into a WeChat chat, so copy + open the app
function openWeChat() {
  copyMessage();
  window.location.href = "weixin://";
}

// family phone number - stored in localStorage only, never sent anywhere

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

// family WeChat ID - not dialable, just a reminder you can copy into WeChat

function saveWeixin() {
  var inp = document.getElementById("weixin-id");
  if (!inp) return;
  var v = inp.value.trim();
  if (v) {
    localStorage.setItem("familyWeixin", v);
    renderWeixin();
  }
}

function changeWeixin() {
  localStorage.removeItem("familyWeixin");
  renderWeixin();
}

function copyWeixin() {
  var v = localStorage.getItem("familyWeixin");
  if (!v) return;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(v);
  }
  alert("微信号已复制：" + v + "，可在微信里搜索粘贴。");
}

function renderWeixin() {
  var v = localStorage.getItem("familyWeixin");
  var setBox = document.getElementById("weixin-set");
  var saveBox = document.getElementById("weixin-save");
  if (!setBox || !saveBox) return; // not on a page with the WeChat section
  if (v) {
    saveBox.style.display = "none";
    setBox.style.display = "flex";
    var b = setBox.querySelector(".wxid");
    if (b) b.textContent = v;
  } else {
    saveBox.style.display = "block";
    setBox.style.display = "none";
  }
}

document.addEventListener("DOMContentLoaded", function () {
  renderFamily();
  renderWeixin();
});
