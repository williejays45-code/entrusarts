/**
* EnTrus product behavior
* - Hooks View Details + Add to Cart buttons
* - Lightweight in-memory cart + modal
* - No backend calls yet (front-end only)
*/
(function () {
    "use strict";

    function getCardData(card) {
        if (!card) return null;
        var nameEl  = card.querySelector(".ea-product-name");
        var freqEl  = card.querySelector(".ea-product-frequency");
        var descEl  = card.querySelector(".ea-product-desc");
        var imgEl   = card.querySelector("img");

        return {
            id: card.getAttribute("data-product-id") || "",
            frequency: card.getAttribute("data-frequency") || (freqEl ? freqEl.textContent.trim() : ""),
            name: nameEl ? nameEl.textContent.trim() : "",
            description: descEl ? descEl.textContent.trim() : "",
            imgSrc: imgEl ? imgEl.getAttribute("src") : "",
            imgAlt: imgEl ? imgEl.getAttribute("alt") || "" : ""
        };
    }

    // Simple in-memory cart
    var cartItems = [];
    var cartCount = 0;

    function ensureCartPill() {
        var pill = document.querySelector(".ea-cart-pill");
        if (pill) return pill;

        pill = document.createElement("button");
        pill.className = "ea-cart-pill";
        pill.setAttribute("type", "button");

        var label = document.createElement("span");
        label.className = "ea-cart-pill-label";
        label.textContent = "Cart";

        var count = document.createElement("span");
        count.className = "ea-cart-pill-count";
        count.textContent = "0";

        pill.appendChild(label);
        pill.appendChild(count);

        pill.addEventListener("click", function () {
            openCartModal();
        });

        document.body.appendChild(pill);
        return pill;
    }

    function updateCartCount() {
        var pill = ensureCartPill();
        var countEl = pill.querySelector(".ea-cart-pill-count");
        if (countEl) {
            countEl.textContent = String(cartCount);
        }
    }

    function addToCart(product) {
        if (!product || !product.id) return;
        cartItems.push(product);
        cartCount += 1;
        updateCartCount();
        console.log("[EnTrusCart] Added:", product);
    }

    // Modal helpers
    var activeModal = null;

    function closeModal() {
        if (activeModal && activeModal.parentNode) {
            activeModal.parentNode.removeChild(activeModal);
        }
        activeModal = null;
    }

    function buildBaseModal() {
        var overlay = document.createElement("div");
        overlay.className = "ea-modal-overlay";

        var modal = document.createElement("div");
        modal.className = "ea-modal";

        var closeBtn = document.createElement("button");
        closeBtn.className = "ea-modal-close";
        closeBtn.setAttribute("type", "button");
        closeBtn.textContent = "";

        closeBtn.addEventListener("click", function () {
            closeModal();
        });

        overlay.addEventListener("click", function (e) {
            if (e.target === overlay) {
                closeModal();
            }
        });

        modal.appendChild(closeBtn);
        overlay.appendChild(modal);
        return { overlay: overlay, modal: modal };
    }

    function openDetailsModal(product) {
        closeModal();

        var base = buildBaseModal();
        var overlay = base.overlay;
        var modal   = base.modal;

        var title = document.createElement("h2");
        title.className = "ea-modal-title";
        title.textContent = product.name || "Product";

        var subtitle = document.createElement("p");
        subtitle.className = "ea-modal-subtitle";
        subtitle.textContent = product.frequency || "";

        var body = document.createElement("p");
        body.className = "ea-modal-body";
        body.textContent = product.description || "";

        if (product.imgSrc) {
            var imgWrap = document.createElement("div");
            imgWrap.className = "ea-modal-media";

            var img = document.createElement("img");
            img.src = product.imgSrc;
            img.alt = product.imgAlt || product.name || "";
            img.loading = "lazy";

            imgWrap.appendChild(img);
            modal.appendChild(imgWrap);
        }

        modal.appendChild(title);
        modal.appendChild(subtitle);
        modal.appendChild(body);

        var actions = document.createElement("div");
        actions.className = "ea-modal-actions";

        var addBtn = document.createElement("button");
        addBtn.className = "ea-btn ea-btn-primary";
        addBtn.textContent = "Add to Cart";

        addBtn.addEventListener("click", function () {
            addToCart(product);
            closeModal();
        });

        actions.appendChild(addBtn);
        modal.appendChild(actions);

        document.body.appendChild(overlay);
        activeModal = overlay;
    }

    function openCartModal() {
        closeModal();

        var base = buildBaseModal();
        var overlay = base.overlay;
        var modal   = base.modal;

        var title = document.createElement("h2");
        title.className = "ea-modal-title";
        title.textContent = "Cart Preview";

        var subtitle = document.createElement("p");
        subtitle.className = "ea-modal-subtitle";
        subtitle.textContent = cartItems.length
            ? "These items are sitting in your local cart."
            : "Cart is empty. Add something from the grid.";

        modal.appendChild(title);
        modal.appendChild(subtitle);

        var list = document.createElement("div");
        list.className = "ea-cart-list";

        if (cartItems.length) {
            cartItems.forEach(function (item) {
                var row = document.createElement("div");
                row.className = "ea-cart-row";

                var name = document.createElement("span");
                name.className = "ea-cart-row-name";
                name.textContent = item.name || "Product";

                var freq = document.createElement("span");
                freq.className = "ea-cart-row-frequency";
                freq.textContent = item.frequency || "";

                row.appendChild(name);
                row.appendChild(freq);
                list.appendChild(row);
            });
        }

        modal.appendChild(list);

        var foot = document.createElement("div");
        foot.className = "ea-modal-footer-note";
        foot.textContent = "Checkout wiring will connect here later. For now this is a live preview only.";

        modal.appendChild(foot);

        document.body.appendChild(overlay);
        activeModal = overlay;
    }

    function wireProducts() {
        var cards = document.querySelectorAll(".ea-product-card");
        if (!cards.length) {
            console.log("[EnTrusProducts] No product cards found on this page.");
            return;
        }

        ensureCartPill();

        cards.forEach(function (card) {
            var data = getCardData(card);
            if (!data) return;

            var detailsBtn = card.querySelector("[data-ea-action='view-details']");
            var cartBtn    = card.querySelector("[data-ea-action='add-to-cart']");

            if (detailsBtn) {
                detailsBtn.addEventListener("click", function () {
                    openDetailsModal(data);
                });
            }

            if (cartBtn) {
                cartBtn.addEventListener("click", function () {
                    addToCart(data);
                });
            }
        });

        console.log("[EnTrusProducts] Wired", cards.length, "product card(s).");
    }

    document.addEventListener("DOMContentLoaded", function () {
        try {
            wireProducts();
        } catch (err) {
            console.error("[EnTrusProducts] Error during wiring:", err);
        }
    });
})();
