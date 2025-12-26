/**
* EnTrus  products_render.js (Layer 9)
* Renders product cards into containers that use:
*   <div data-entrus-grid="all"></div>
*   <div data-entrus-grid="hoodie"></div>  // or bracelet, shoes, set..
*/

(function () {
  function createCard(product) {
    const card = document.createElement("article");
    card.className = "ea-product-card";

    const hasImage =
      product.images &&
      Array.isArray(product.images) &&
      product.images.length > 0;

    const freqLabel =
      product.frequency_name
        ? product.frequency + " Hz  " + product.frequency_name
        : product.frequency
        ? product.frequency + " Hz"
        : "";

    const phraseLabel = product.phrase || "";
    const codeLabel = product.code ? " (" + product.code + ")" : "";

    card.innerHTML = [
      '<div class="ea-product-img-wrap">',
      hasImage
        ? '<img src="' + product.images[0] + '" alt="' + (product.name || "") + '" />'
        : '<div class="ea-product-img-placeholder">Art incoming</div>',
      "</div>",
      '<div class="ea-product-body">',
      '  <div class="ea-product-top">',
      '    <h3 class="ea-product-name">' + (product.name || "Unnamed product") + "</h3>",
      freqLabel
        ? '    <div class="ea-product-freq">' + freqLabel + "</div>"
        : "",
      "  </div>",
      phraseLabel
        ? '  <div class="ea-product-phrase">' + phraseLabel + codeLabel + "</div>"
        : "",
      product.description_short
        ? '  <p class="ea-product-desc">' + product.description_short + "</p>"
        : "",
      '  <div class="ea-product-bottom">',
      typeof product.price === "number"
        ? '    <div class="ea-product-price">$' + product.price + " USD</div>"
        : '    <div class="ea-product-price ea-product-price-na">Price TBA</div>',
      '    <div class="ea-product-tag">' + (product.category || "product") + "</div>",
      "  </div>",
      "</div>"
    ].join("");

    return card;
  }

  function applyBasicStyles() {
    // Light-weight inject to keep alignment even if main CSS is simple
    const id = "entrus-products-layer9-style";
    if (document.getElementById(id)) return;

    const style = document.createElement("style");
    style.id = id;
    style.textContent = `
      .ea-products-section {
        margin-top: 32px;
        padding: 16px 0 24px;
        border-top: 1px solid #111827;
      }
      .ea-products-title {
        font-size: 18px;
        font-weight: 600;
        margin-bottom: 4px;
      }
      .ea-products-sub {
        font-size: 12px;
        color: #9ca3af;
        margin-bottom: 12px;
      }
      .ea-products-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 14px;
      }
      .ea-product-card {
        border-radius: 14px;
        border: 1px solid #111827;
        background: radial-gradient(circle at top left, #020617, #030712 60%);
        padding: 10px;
        display: flex;
        flex-direction: column;
        gap: 6px;
        font-size: 12px;
      }
      .ea-product-img-wrap {
        width: 100%;
        aspect-ratio: 4/3;
        border-radius: 10px;
        overflow: hidden;
        background: #020617;
        display: flex;
        align-items: center;
        justify-content: center;
        margin-bottom: 6px;
      }
      .ea-product-img-wrap img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        display: block;
      }
      .ea-product-img-placeholder {
        font-size: 11px;
        color: #6b7280;
        border: 1px dashed #374151;
        padding: 6px 8px;
        border-radius: 999px;
      }
      .ea-product-body {
        display: flex;
        flex-direction: column;
        gap: 4px;
      }
      .ea-product-top {
        display: flex;
        justify-content: space-between;
        gap: 8px;
        align-items: flex-start;
      }
      .ea-product-name {
        margin: 0;
        font-size: 13px;
        font-weight: 600;
      }
      .ea-product-freq {
        font-size: 10px;
        padding: 3px 7px;
        border-radius: 999px;
        border: 1px solid #4b5563;
        color: #e5e7eb;
        background: rgba(15,23,42,0.9);
        white-space: nowrap;
      }
      .ea-product-phrase {
        font-size: 11px;
        color: #a5b4fc;
      }
      .ea-product-desc {
        font-size: 11px;
        color: #d1d5db;
        margin: 0;
      }
      .ea-product-bottom {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-top: 4px;
      }
      .ea-product-price {
        font-size: 12px;
        font-weight: 600;
        color: #bbf7d0;
      }
      .ea-product-price-na {
        color: #9ca3af;
        font-weight: 400;
      }
      .ea-product-tag {
        font-size: 10px;
        text-transform: uppercase;
        letter-spacing: 0.14em;
        color: #9ca3af;
      }
    `;
    document.head.appendChild(style);
  }

  async function renderGrids() {
    if (!window.EnTrusProducts || !window.EnTrusProducts.load) return;

    const containers = document.querySelectorAll("[data-entrus-grid]");
    if (!containers.length) return;

    const products = await window.EnTrusProducts.load();
    applyBasicStyles();

    containers.forEach(function (container) {
      const filter = (container.getAttribute("data-entrus-grid") || "all").toLowerCase();
      let subset = products;

      if (filter !== "all") {
        subset = products.filter(function (p) {
          return (p.category || "").toLowerCase() === filter;
        });
      }

      const wrapper = document.createElement("div");
      wrapper.className = "ea-products-section";

      const title = document.createElement("div");
      title.className = "ea-products-title";
      title.textContent = "EnTrus " + (filter === "all" ? "Product Grid" : (filter.charAt(0).toUpperCase() + filter.slice(1) + " Line"));

      const sub = document.createElement("div");
      sub.className = "ea-products-sub";
      sub.textContent = "Data from data/products.json  Layer 9";

      const grid = document.createElement("div");
      grid.className = "ea-products-grid";

      if (!subset.length) {
        const empty = document.createElement("div");
        empty.style.fontSize = "11px";
        empty.style.color = "#9ca3af";
        empty.textContent = "No products defined yet for this filter.";
        grid.appendChild(empty);
      } else {
        subset.forEach(function (product) {
          grid.appendChild(createCard(product));
        });
      }

      wrapper.appendChild(title);
      wrapper.appendChild(sub);
      wrapper.appendChild(grid);

      container.innerHTML = "";
      container.appendChild(wrapper);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", renderGrids);
  } else {
    renderGrids();
  }
})();
