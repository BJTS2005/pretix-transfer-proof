/* pretix renders its payment forms without enctype="multipart/form-data", so a file input
   would only send the file name. Switch every form that contains a file input to multipart. */
(function () {
    "use strict";

    function arm(form) {
        if (form && form.querySelector && form.querySelector('input[type="file"]')) {
            form.setAttribute("enctype", "multipart/form-data");
            form.encoding = "multipart/form-data";
        }
    }

    function armAll() {
        document.querySelectorAll("form").forEach(arm);
    }

    document.addEventListener("submit", function (event) {
        arm(event.target);
    }, true);

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", armAll);
    } else {
        armAll();
    }
})();
