(function () {
  var button = document.getElementById("add-workplace");
  var container = document.getElementById("workplace-forms");
  var template = document.getElementById("workplace-empty-form");
  var totalInput = document.querySelector('input[name="wp-TOTAL_FORMS"]');
  if (!button || !container || !template || !totalInput) {
    return;
  }

  button.addEventListener("click", function () {
    var index = parseInt(totalInput.value, 10);
    if (Number.isNaN(index)) {
      index = container.querySelectorAll(".workplace-row").length;
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
