/* Visual editor for the "Campos adicionales" JSON setting (backend only).
   Builds the UI with DOM APIs (never innerHTML with user values) and keeps the hidden
   textarea in sync. If the stored JSON is invalid, the raw textarea stays visible instead
   of being overwritten. */
(function () {
    "use strict";

    function el(tag, attrs, children) {
        var node = document.createElement(tag);
        Object.keys(attrs || {}).forEach(function (k) {
            if (k === "text") {
                node.textContent = attrs[k];
            } else if (k === "className") {
                node.className = attrs[k];
            } else {
                node.setAttribute(k, attrs[k]);
            }
        });
        (children || []).forEach(function (c) { node.appendChild(c); });
        return node;
    }

    function init() {
        var ta = document.querySelector("textarea.extra-fields-json");
        if (!ta) {
            return;
        }
        var fields;
        try {
            fields = JSON.parse(ta.value || "[]");
            if (!Array.isArray(fields)) {
                throw new Error("not a list");
            }
        } catch (e) {
            var warn = el("p", {className: "text-danger", text: "El JSON guardado no es válido; corrígelo a mano o bórralo para usar el editor."});
            ta.parentNode.insertBefore(warn, ta);
            return;
        }

        var container = el("div", {className: "extra-fields-ui"});
        ta.parentNode.insertBefore(container, ta);
        ta.style.display = "none";

        function sync() {
            ta.value = JSON.stringify(fields.filter(function (f) { return f.label; }), null, 2);
        }

        function row(f, i) {
            var label = el("input", {type: "text", className: "form-control", placeholder: "Etiqueta"});
            label.value = f.label || "";
            var type = el("select", {className: "form-control"}, [
                el("option", {value: "text", text: "Texto"}),
                el("option", {value: "choice", text: "Lista de opciones"})
            ]);
            type.value = f.type === "choice" ? "choice" : "text";
            var required = el("input", {type: "checkbox"});
            required.checked = !!f.required;
            var options = el("textarea", {className: "form-control", rows: "3", placeholder: "Una opción por línea"});
            options.value = (f.options || []).join("\n");
            var optionsBox = el("div", {className: "form-group"}, [el("label", {text: "Opciones"}), options]);
            optionsBox.style.display = type.value === "choice" ? "" : "none";
            var remove = el("button", {type: "button", className: "btn btn-default btn-sm", text: "Quitar"});

            function update() {
                f.label = label.value.trim();
                f.type = type.value;
                f.required = required.checked;
                f.options = f.type === "choice"
                    ? options.value.split(/\r?\n/).map(function (s) { return s.trim(); }).filter(Boolean)
                    : [];
                optionsBox.style.display = f.type === "choice" ? "" : "none";
                sync();
            }
            [label, type, required, options].forEach(function (input) {
                input.addEventListener("input", update);
                input.addEventListener("change", update);
            });
            remove.addEventListener("click", function () {
                fields.splice(i, 1);
                sync();
                render();
            });

            return el("div", {className: "panel panel-default"}, [
                el("div", {className: "panel-body"}, [
                    el("div", {className: "form-group"}, [el("label", {text: "Etiqueta"}), label]),
                    el("div", {className: "form-group"}, [el("label", {text: "Tipo"}), type]),
                    el("div", {className: "checkbox"}, [el("label", {}, [required, document.createTextNode(" Obligatorio")])]),
                    optionsBox,
                    remove
                ])
            ]);
        }

        function render() {
            container.textContent = "";
            fields.forEach(function (f, i) { container.appendChild(row(f, i)); });
            var add = el("button", {type: "button", className: "btn btn-default", text: "Agregar campo"});
            add.addEventListener("click", function () {
                fields.push({label: "", type: "text", required: false, options: []});
                render();
            });
            container.appendChild(add);
        }

        render();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
