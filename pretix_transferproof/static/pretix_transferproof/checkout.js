function arm(form) {
    if (!form || !form.querySelector) {
        return;
    }
    if (form.querySelector('input[type="file"]')) {
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
