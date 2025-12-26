(function () {
    function getCleanCatalog() {
        var list = window.EnTrusCatalog || [];
        return list.filter(function (p) {
            return p && p.status !== "archived";
        });
    }

    function matchesFilters(p, text, category, freq) {
        if (category && category !== "all") {
            if ((p.category || "").toLowerCase() !== category.toLowerCase()) return false;
        }
        if (freq && freq !== "all") {
            var fc = (p.frequencyCode || "").toString();
            var fStr = (p.frequency || "").toString();
            if (fc !== freq && fStr.indexOf(freq) === -1) return false;
        }
        if (text) {
            var q = text.toLowerCase();
            var blob = [
                p.name || "",
                p.code || "",
                p.category || "",
                p.frequency || "",
                p.seal || "",
                p.tagline || "",
                p.description || ""
            ].join(" ").toLowerCase();
            if (blob.indexOf(q) === -1) return false;
        }
        return true;
    }

    function renderCatalog() {
        var grid = document.getElementById("catalog-grid");
        if (!grid) return;

        var textInput = document.getElementById("filter-query");
        var catSelect = document.getElementById("filter-category");
        var freqSelect = document.getElementById("filter-frequency");

        var text = textInput ? textInput.value.trim() : "";
        var cat  = catSelect ? catSelect.value : "all";
        var freq = freqSelect ? freqSelect.value : "all";

        var list = getCleanCatalog();
        var filtered = list.filter(function (p) {
            return matchesFilters(p, text, cat, freq);
        });

        grid.innerHTML = "";

        if (!filtered.length) {
            var empty = document.createElement("p");
            empty.className = "catalog-empty";
            empty.textContent = "No items found for this filter. Adjust your search or category.";
            grid.appendChild(empty);
            return;
        }

        filtered.forEach(function (p) {
            var card = document.createElement("article");
            card.className = "catalog-card";

            var freqLabel = p.frequency || "";
            var category = (p.category || "").toUpperCase();

            card.innerHTML =
                '<div class="catalog-meta-row">' +
                    '<span class="catalog-category-pill">' + category + "</span>" +
                    (freqLabel ? '<span class="catalog-frequency">' + freqLabel + "</span>" : "") +
                "</div>" +
                '<h2 class="catalog-name">' + (p.name || "") + "</h2>" +
                '<p class="catalog-tagline">' + (p.tagline || "") + "</p>" +
                '<p class="catalog-desc">' + (p.description || "") + "</p>" +
                '<div class="catalog-bottom-row">' +
                    '<span class="catalog-code">' + (p.code || "") + "</span>" +
                    (p.price ? '<span class="catalog-price">$' + p.price + "</span>" : "") +
                "</div>";

            var actions = document.createElement("div");
            actions.className = "catalog-actions";

            if (window.EnTrusCart) {
                var addBtn = document.createElement("button");
                addBtn.className = "catalog-add";
                addBtn.textContent = "Add to Cart";
                addBtn.addEventListener("click", function () {
                    window.EnTrusCart.add({
                        id: p.id,
                        name: p.name,
                        price: p.price
                    });
                });
                actions.appendChild(addBtn);
            }

            if (p.routePath) {
                var detailLink = document.createElement("a");
                detailLink.className = "catalog-detail";
                detailLink.textContent = "Details";
                detailLink.href = p.routePath;
                actions.appendChild(detailLink);
            }

            card.appendChild(actions);
            grid.appendChild(card);
        });
    }

    function bindControls() {
        var textInput = document.getElementById("filter-query");
        var catSelect = document.getElementById("filter-category");
        var freqSelect = document.getElementById("filter-frequency");
        var clearBtn  = document.getElementById("filter-clear");

        if (textInput) textInput.addEventListener("input", renderCatalog);
        if (catSelect) catSelect.addEventListener("change", renderCatalog);
        if (freqSelect) freqSelect.addEventListener("change", renderCatalog);
        if (clearBtn) {
            clearBtn.addEventListener("click", function () {
                if (textInput) textInput.value = "";
                if (catSelect) catSelect.value = "all";
                if (freqSelect) freqSelect.value = "all";
                renderCatalog();
            });
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        bindControls();
        renderCatalog();
    });
})();
