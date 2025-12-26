/**
* EnTrus  products_data.js (Layer 9)
* Provides a simple loader for data/products.json.
*/

window.EnTrusProducts = window.EnTrusProducts || {};

(function () {
  let cache = null;

  async function loadProducts() {
    if (cache) return cache;

    try {
      const res = await fetch("data/products.json", { cache: "no-store" });
      if (!res.ok) {
        console.error("[EnTrusProducts] Failed to load products.json", res.status);
        cache = [];
        return cache;
      }
      const data = await res.json();
      if (!Array.isArray(data)) {
        console.error("[EnTrusProducts] products.json is not an array");
        cache = [];
        return cache;
      }

      cache = data;
      return cache;
    } catch (err) {
      console.error("[EnTrusProducts] Error loading products.json", err);
      cache = [];
      return cache;
    }
  }

  function getCachedProducts() {
    return cache || [];
  }

  window.EnTrusProducts.load = loadProducts;
  window.EnTrusProducts.getCached = getCachedProducts;
})();
