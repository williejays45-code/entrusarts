(function () {
    var products = (window.EnTrusBracelets || []).filter(function (p) {
        return p && p.status !== "archived";
    });

    var grid = document.getElementById("bracelet-grid");
    if (!grid) {
        return;
    }

    if (!products.length) {
        var empty = document.createElement("p");
        empty.className = "bracelet-empty";
        empty.textContent = "Bracelet data found, but no items are active yet.";
        grid.appendChild(empty);
        return;
    }

    products.forEach(function (p) {
        var card = document.createElement("article");
        card.className = "bracelet-card";

        var statusLabel = "";
        if (p.status === "planned") statusLabel = "Planned Drop";
        if (p.status === "active")  statusLabel = "Available Soon";

        card.innerHTML =
            '<div class="bracelet-tagline">' + (p.frequency || "") + "</div>" +
            '<h2 class="bracelet-name">' + (p.name || "") + "</h2>" +
            '<p class="bracelet-subline">' + (p.tagline || "") + "</p>" +
            '<p class="bracelet-desc">' + (p.description || "") + "</p>" +
            '<div class="bracelet-meta">' +
                '<span class="bracelet-code">' + (p.code || "") + "</span>" +
                (p.price ? '<span class="bracelet-price">$' + p.price + "</span>" : "") +
            "</div>" +
            (statusLabel
                ? '<div class="bracelet-status bracelet-status-' + p.status + '">' + statusLabel + "</div>"
                : "");

        var btnRow = document.createElement("div");
        btnRow.className = "bracelet-actions";

        var addBtn = document.createElement("button");
        addBtn.className = "bracelet-add";
        addBtn.textContent = "Add to Cart";
        addBtn.addEventListener("click", function () {
            if (window.EnTrusCart) {
                window.EnTrusCart.add(p);
            }
        });
        btnRow.appendChild(addBtn);

        if (p.viewerSlug) {
            var viewBtn = document.createElement("button");
            viewBtn.className = "bracelet-view";
            viewBtn.textContent = "View Model";
            viewBtn.addEventListener("click", function () {
                var url = "bracelet_viewer.html?id=" + encodeURIComponent(p.viewerSlug);
                window.location.href = url;
            });
            btnRow.appendChild(viewBtn);
        }

        if (p.id) {
            var detailLink = document.createElement("a");
            detailLink.className = "bracelet-detail";
            detailLink.textContent = "Details";
            detailLink.href = "../products/bracelets/" + encodeURIComponent(p.id) + ".html";
            btnRow.appendChild(detailLink);
        }

        card.appendChild(btnRow);
        grid.appendChild(card);
    });
})();
