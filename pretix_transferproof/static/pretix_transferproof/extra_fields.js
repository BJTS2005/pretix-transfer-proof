document.addEventListener("DOMContentLoaded", function () {
    const ta = document.querySelector("textarea.extra-fields-json");
    if (!ta) return;
    const container = document.createElement("div");
    container.className = "extra-fields-ui";
    ta.parentNode.insertBefore(container, ta);
    ta.style.display = "none";

    function parse() {
        try { return JSON.parse(ta.value || "[]"); } catch (e) { return []; }
    }
    function render() {
        const fields = parse();
        container.innerHTML = "";
        fields.forEach((f, i) => {
            const div = document.createElement("div");
            div.style.border = "1px solid #ddd";
            div.style.padding = "8px";
            div.style.marginBottom = "8px";
            div.innerHTML = `
                <label>Etiqueta <input class="lbl" value="${f.label || ""}"></label>
                <label>Tipo
                    <select class="typ">
                        <option value="text" ${f.type !== "choice" ? "selected" : ""}>Texto</option>
                        <option value="choice" ${f.type === "choice" ? "selected" : ""}>Opción múltiple</option>
                    </select>
                </label>
                <label><input type="checkbox" class="req" ${f.required ? "checked" : ""}> Obligatorio</label>
                <label class="opts" style="${f.type === "choice" ? "" : "display:none"}">Opciones (una por línea)<br>
                    <textarea class="opt">${(f.options || []).join("\\n")}</textarea>
                </label>
                <button type="button" class="rm">Quitar</button>
            `;
            container.appendChild(div);
            div.querySelector(".typ").addEventListener("change", () => {
                div.querySelector(".opts").style.display = div.querySelector(".typ").value === "choice" ? "" : "none";
                save();
            });
            div.querySelector(".rm").addEventListener("click", () => {
                fields.splice(i, 1);
                ta.value = JSON.stringify(fields, null, 2);
                render();
            });
            ["lbl", "typ", "req", "opt"].forEach(cls => {
                const el = div.querySelector("." + cls);
                if (el) el.addEventListener("input", save);
                if (el) el.addEventListener("change", save);
            });
        });
        const add = document.createElement("button");
        add.type = "button";
        add.textContent = "Agregar campo";
        add.addEventListener("click", () => {
            fields.push({label: "", type: "text", required: false, options: []});
            ta.value = JSON.stringify(fields, null, 2);
            render();
        });
        container.appendChild(add);
    }
    function save() {
        const fields = [];
        container.querySelectorAll("div").forEach(div => {
            const label = div.querySelector(".lbl")?.value || "";
            if (!label) return;
            const type = div.querySelector(".typ")?.value || "text";
            const required = !!div.querySelector(".req")?.checked;
            const options = (div.querySelector(".opt")?.value || "").split("\\n").map(s => s.trim()).filter(Boolean);
            fields.push({label, type, required, options: type === "choice" ? options : []});
        });
        ta.value = JSON.stringify(fields, null, 2);
    }
    render();
});
