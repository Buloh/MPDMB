(function () {
  var button = document.getElementById("add-document");
  var container = document.getElementById("document-forms");
  var template = document.getElementById("document-empty-form");
  var totalInput = document.querySelector('input[name="doc-TOTAL_FORMS"]');
  if (!button || !container || !template || !totalInput) {
    return;
  }

  button.addEventListener("click", function () {
    var index = parseInt(totalInput.value, 10);
    if (Number.isNaN(index)) {
      index = container.querySelectorAll(".document-row").length;
    }
    var html = template.innerHTML.replace(/__prefix__/g, String(index));
    var wrapper = document.createElement("div");
    wrapper.innerHTML = html.trim();
    var row = wrapper.firstElementChild;
    if (row) {
      container.appendChild(row);
      totalInput.value = String(index + 1);
    }
  });
})();
