/**
 * script.js
 *
 * Cart state lives entirely in the browser via localStorage — there is no
 * server-side cart/session (see app.py notes: no logged-in users yet, so
 * nothing meaningful to persist server-side). The cart is a plain object:
 *   { "<productId>": <quantity>, ... }
 *
 * This file is organized in three layers:
 *   1. Cart data layer  (read/write localStorage, no DOM access)
 *   2. Cart UI layer    (badge count, toast — shared across every page)
 *   3. Page-specific rendering (category load-more, product detail, cart page)
 *
 * Keeping (1) free of DOM code means the cart logic can be tested or reused
 * without a page to render into, and a future change in storage strategy
 * (e.g. moving to a server cart) only touches this one layer.
 */

(() => {
    "use strict";

    const CART_STORAGE_KEY = "viper_cart_v1";

    // ------------------------------------------------------------------
    // 1. Cart data layer
    // ------------------------------------------------------------------

    function readCart() {
        try {
            const raw = localStorage.getItem(CART_STORAGE_KEY);
            if (!raw) return {};
            const parsed = JSON.parse(raw);
            return typeof parsed === "object" && parsed !== null ? parsed : {};
        } catch (err) {
            // Corrupted localStorage value (manual edit, old format, etc.)
            // Fail safe to an empty cart rather than throwing on every page load.
            console.error("Could not read cart from localStorage:", err);
            return {};
        }
    }

    function writeCart(cart) {
        try {
            localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(cart));
            return true;
        } catch (err) {
            // Can fail in private browsing on some browsers, or if storage
            // is full/disabled. Surface this rather than pretending it worked.
            console.error("Could not save cart to localStorage:", err);
            return false;
        }
    }

    function addToCart(productId, quantity) {
        const cart = readCart();
        const key = String(productId);
        cart[key] = (cart[key] || 0) + quantity;
        writeCart(cart);
        updateCartBadge();
        return cart[key];
    }

    function setQuantity(productId, quantity) {
        const cart = readCart();
        const key = String(productId);
        if (quantity <= 0) {
            delete cart[key];
        } else {
            cart[key] = quantity;
        }
        writeCart(cart);
        updateCartBadge();
    }

    function removeFromCart(productId) {
        const cart = readCart();
        delete cart[String(productId)];
        writeCart(cart);
        updateCartBadge();
    }

    function clearCart() {
        writeCart({});
        updateCartBadge();
    }

    function cartItemCount() {
        const cart = readCart();
        return Object.values(cart).reduce((sum, qty) => sum + qty, 0);
    }

    // ------------------------------------------------------------------
    // 2. Cart UI layer (shared across every page via base.html)
    // ------------------------------------------------------------------

    function updateCartBadge() {
        const badge = document.getElementById("cart-count");
        if (badge) badge.textContent = String(cartItemCount());
    }

    let toastTimeout = null;

    function showToast(message) {
        let toast = document.getElementById("toast");
        if (!toast) {
            toast = document.createElement("div");
            toast.id = "toast";
            toast.className = "toast";
            toast.innerHTML = `
                <svg class="toast-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polyline points="20 6 9 17 4 12"/></svg>
                <span id="toast-message"></span>
            `;
            document.body.appendChild(toast);
        }
        toast.querySelector("#toast-message").textContent = message;
        toast.classList.add("visible");

        clearTimeout(toastTimeout);
        toastTimeout = setTimeout(() => toast.classList.remove("visible"), 2200);
    }

    function formatPrice(amount) {
        return "\u20B9" + amount.toLocaleString("en-IN");
    }

    // ------------------------------------------------------------------
    // 3a. "Add to cart" buttons — category grid + product detail page
    // ------------------------------------------------------------------

    function wireAddToCartButtons(root = document) {
        root.querySelectorAll(".add-to-cart-btn[data-product-id]").forEach((btn) => {
            if (btn.dataset.wired) return; // avoid double-binding on re-render
            btn.dataset.wired = "true";
            btn.addEventListener("click", (e) => {
                e.preventDefault();
                const productId = btn.dataset.productId;
                addToCart(productId, 1);
                showToast("Added to cart");
            });
        });
    }

    function initProductDetailPage() {
        const addBtn = document.getElementById("detail-add-btn");
        if (!addBtn) return; // not on the product detail page

        const qtyValueEl = document.getElementById("qty-value");
        const minusBtn = document.getElementById("qty-minus");
        const plusBtn = document.getElementById("qty-plus");
        let quantity = 1;

        minusBtn.addEventListener("click", () => {
            if (quantity > 1) {
                quantity -= 1;
                qtyValueEl.textContent = String(quantity);
            }
        });

        plusBtn.addEventListener("click", () => {
            quantity += 1;
            qtyValueEl.textContent = String(quantity);
        });

        addBtn.addEventListener("click", () => {
            addToCart(addBtn.dataset.productId, quantity);
            showToast(`Added ${quantity} item${quantity > 1 ? "s" : ""} to cart`);
        });
    }

    // ------------------------------------------------------------------
    // 3b. Category page — "load more" pagination
    // ------------------------------------------------------------------

    function renderProductCard(product) {
        const article = document.createElement("article");
        article.className = "product-card";
        article.innerHTML = `
            <a href="/product/${product.id}" class="product-card-image-link">
                <img src="${product.image_url}" alt="${product.image_path ? escapeHtml(product.name) : "No image available for " + escapeHtml(product.name)}" loading="lazy">
            </a>
            <div class="product-card-body">
                <a href="/product/${product.id}" class="product-card-name">${escapeHtml(product.name)}</a>
                <div class="product-card-price">${formatPrice(product.price)}</div>
                <div class="product-card-actions">
                    <button class="btn btn-primary product-card-add-btn add-to-cart-btn" data-product-id="${product.id}">Add to cart</button>
                </div>
            </div>
        `;
        return article;
    }

    function escapeHtml(str) {
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    function initCategoryLoadMore() {
        const grid = document.getElementById("product-grid");
        const loadMoreWrap = document.getElementById("load-more-wrap");
        const loadMoreBtn = document.getElementById("load-more-btn");
        if (!grid || !loadMoreBtn) return; // not on a category page, or no products

        const category = grid.dataset.category;
        const pageSize = parseInt(grid.dataset.pageSize, 10) || 20;
        let loaded = parseInt(grid.dataset.loaded, 10) || 0;
        const total = parseInt(grid.dataset.total, 10) || 0;
        let nextPage = 2; // page 1 was already server-rendered

        function updateLoadMoreVisibility() {
            loadMoreWrap.classList.toggle("hidden", loaded >= total);
        }

        updateLoadMoreVisibility();

        loadMoreBtn.addEventListener("click", async () => {
            loadMoreBtn.disabled = true;
            loadMoreBtn.textContent = "Loading…";

            try {
                const url = `/api/products?category=${encodeURIComponent(category)}&page=${nextPage}&per_page=${pageSize}`;
                const res = await fetch(url);
                if (!res.ok) throw new Error(`Request failed: ${res.status}`);
                const data = await res.json();

                data.products.forEach((product) => {
                    grid.appendChild(renderProductCard(product));
                });
                wireAddToCartButtons(grid);

                loaded += data.products.length;
                grid.dataset.loaded = String(loaded);
                nextPage += 1;
                updateLoadMoreVisibility();
            } catch (err) {
                console.error("Failed to load more products:", err);
                showToast("Could not load more products. Please try again.");
            } finally {
                loadMoreBtn.disabled = false;
                loadMoreBtn.textContent = "Load more products";
            }
        });
    }

    // ------------------------------------------------------------------
    // 3c. Cart page — render from localStorage + /api/products/<id>
    // ------------------------------------------------------------------

    async function fetchProductDetails(productIds) {
        // Cart only stores {productId: quantity}, not name/price/image, so
        // current product data is fetched fresh from the API every time the
        // cart page loads. This also means if a product's price changes,
        // the cart always reflects the current price, not a stale cached one.
        const results = await Promise.all(
            productIds.map(async (id) => {
                try {
                    const res = await fetch(`/api/products/${id}`);
                    if (!res.ok) return null; // product may have been removed
                    return await res.json();
                } catch (err) {
                    console.error(`Failed to fetch product ${id}:`, err);
                    return null;
                }
            })
        );
        return results;
    }

    function renderCartRow(template, product, quantity) {
        const row = template.content.firstElementChild.cloneNode(true);
        row.dataset.productId = String(product.id);

        const imageLink = row.querySelector(".cart-item-image");
        imageLink.href = `/product/${product.id}`;
        const img = imageLink.querySelector("img");
        img.src = product.image_url;
        img.alt = product.name;

        const nameLink = row.querySelector(".cart-item-name");
        nameLink.href = `/product/${product.id}`;
        nameLink.textContent = product.name;

        row.querySelector(".cart-item-unit-price").textContent = `${formatPrice(product.price)} each`;
        row.querySelector(".qty-value").textContent = String(quantity);
        row.querySelector(".cart-item-line-total").textContent = formatPrice(product.price * quantity);

        return row;
    }

    function initCartPage() {
        const loadingEl = document.getElementById("cart-loading");
        const contentEl = document.getElementById("cart-content");
        const emptyEl = document.getElementById("cart-empty");
        const listEl = document.getElementById("cart-items-list");
        const template = document.getElementById("cart-row-template");
        if (!loadingEl || !template) return; // not on the cart page

        async function render() {
            const cart = readCart();
            const productIds = Object.keys(cart);

            loadingEl.hidden = false;
            contentEl.hidden = true;
            emptyEl.hidden = true;

            if (productIds.length === 0) {
                loadingEl.hidden = true;
                emptyEl.hidden = false;
                return;
            }

            const products = await fetchProductDetails(productIds);

            // A product might have been deleted from the catalog since it
            // was added to the cart — drop those rather than rendering a
            // broken row, and silently reconcile localStorage to match.
            const validPairs = products
                .map((product, i) => ({ product, quantity: cart[productIds[i]] }))
                .filter((pair) => pair.product !== null);

            if (validPairs.length !== productIds.length) {
                const reconciled = {};
                validPairs.forEach(({ product, quantity }) => {
                    reconciled[String(product.id)] = quantity;
                });
                writeCart(reconciled);
            }

            if (validPairs.length === 0) {
                loadingEl.hidden = true;
                emptyEl.hidden = false;
                updateCartBadge();
                return;
            }

            listEl.innerHTML = "";
            let totalItems = 0;
            let totalAmount = 0;

            validPairs.forEach(({ product, quantity }) => {
                listEl.appendChild(renderCartRow(template, product, quantity));
                totalItems += quantity;
                totalAmount += product.price * quantity;
            });

            document.getElementById("cart-summary-count").textContent = String(totalItems);
            document.getElementById("cart-summary-total").textContent = formatPrice(totalAmount);

            loadingEl.hidden = true;
            contentEl.hidden = false;
            updateCartBadge();
        }

        listEl.addEventListener("click", (e) => {
            const row = e.target.closest(".cart-item-row");
            if (!row) return;
            const productId = row.dataset.productId;

            if (e.target.closest(".cart-qty-plus")) {
                const current = readCart()[productId] || 0;
                setQuantity(productId, current + 1);
                render();
            } else if (e.target.closest(".cart-qty-minus")) {
                const current = readCart()[productId] || 0;
                setQuantity(productId, current - 1);
                render();
            } else if (e.target.closest(".cart-item-remove")) {
                removeFromCart(productId);
                render();
            }
        });

        document.getElementById("checkout-btn").addEventListener("click", () => {
            clearCart();
            showToast("Order placed! Thank you for shopping with us.");
            setTimeout(() => {
                window.location.href = "/";
            }, 1200);
        });

        render();
    }

    // ------------------------------------------------------------------
    // Init — runs on every page via base.html
    // ------------------------------------------------------------------

    document.addEventListener("DOMContentLoaded", () => {
        updateCartBadge();
        wireAddToCartButtons();
        initProductDetailPage();
        initCategoryLoadMore();
        initCartPage();
    });
})();