// Mock Product Database matching your 5 sketch categories
const mockProducts = [
    { id: 1, category: "Health Supplements", name: "Premium Whey Protein", price: 2999, image: "https://picsum.photos/300/300?random=1", desc: "High quality isolate whey protein powder to support muscle growth and fast recovery structural cycles." },
    { id: 2, category: "Health Supplements", name: "Multivitamin Tablets", price: 599, image: "https://picsum.photos/300/300?random=2", desc: "Essential daily minerals and vitamin mixtures optimized for standard high performance cellular nutrition." },
    { id: 3, category: "Skin Care", name: "Vitamin C Face Serum", price: 450, image: "https://picsum.photos/300/300?random=3", desc: "Brightens skin composition layout configurations while eliminating blemishes and processing fine lines." },
    { id: 4, category: "Skin Care", name: "Hydrating Moisturizer", price: 350, image: "https://picsum.photos/300/300?random=4", desc: "Deep continuous 24-hour hydration barrier logic designed to keep complex skins completely smooth." },
    { id: 5, category: "Groceries", name: "Organic Basmati Rice", price: 180, image: "https://picsum.photos/300/300?random=5", desc: "Premium long grain deeply aromatic authentic rice cultivated using strict natural field arrays." },
    { id: 6, category: "Home Appliance", name: "Digital Air Fryer", price: 5499, image: "https://picsum.photos/300/300?random=6", desc: "Rapid 360 convective heating system elements ensuring delicious crisp results using minimal lipid profiles." },
    { id: 7, category: "Agri Products", name: "Bio-Organic Fertilizer", price: 250, image: "https://picsum.photos/300/300?random=7", desc: "High efficacy nitrogen/potassium biological enricher formula designed to skyrocket standard crop yield metrics." }
];

// App State Engine 
let cart = [];

// Navigation Engine Controller Hooks
function showPage(pageId) {
    document.querySelectorAll('.page').forEach(page => page.classList.remove('active'));
    document.getElementById(pageId).classList.add('active');
    window.scrollTo(0, 0);
}

// Global Header Event Attachments
document.getElementById('logo-home').addEventListener('click', () => showPage('home-page'));

// ADD THIS NEW LINE FOR THE BACK BUTTON:
document.getElementById('back-btn').addEventListener('click', () => showPage('home-page'));

document.getElementById('cart-btn').addEventListener('click', () => {
    renderCart();
    showPage('cart-page');
});

// Category Hook Instantiation
document.querySelectorAll('.category-card').forEach(card => {
    card.addEventListener('click', () => {
        const selectedCat = card.getAttribute('data-category');
        renderCategoryPage(selectedCat);
    });
});

// 2nd Page Generator: Populate products matching target categories
function renderCategoryPage(categoryName) {
    document.getElementById('category-title').innerText = categoryName;
    const container = document.getElementById('products-container');
    container.innerHTML = '';

    const filtered = mockProducts.filter(p => p.category === categoryName);

    if (filtered.length === 0) {
        container.innerHTML = `<p style="padding:20px;">No items found in this section yet.</p>`;
    } else {
        filtered.forEach(product => {
            const card = document.createElement('div');
            card.className = 'product-card';
            card.innerHTML = `
                <img src="${product.image}" alt="${product.name}" class="goto-detail" data-id="${product.id}">
                <div class="product-info">
                    <div class="prod-name goto-detail" data-id="${product.id}">${product.name}</div>
                    <div class="prod-price">₹${product.price}</div>
                    <button class="add-to-cart-btn" data-id="${product.id}">Add to Cart</button>
                </div>
            `;
            container.appendChild(card);
        });
    }

    // Attach programmatic click listeners for item detailing views or rapid insertions
    container.querySelectorAll('.goto-detail').forEach(el => {
        el.addEventListener('click', () => renderProductDetail(el.getAttribute('data-id')));
    });

    container.querySelectorAll('.add-to-cart-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            addToCart(btn.getAttribute('data-id'), 1);
        });
    });

    showPage('category-page');
}

// 3rd Page Generator: Detail panel markup rendering engine
function renderProductDetail(productId) {
    const product = mockProducts.find(p => p.id == productId);
    const container = document.getElementById('product-detail-view');

    container.innerHTML = `
        <img src="${product.image}" alt="${product.name}">
        <div class="detail-content">
            <h1>${product.name}</h1>
            <div class="detail-price">₹${product.price}</div>
            <h3>About the item:</h3>
            <p class="detail-desc">${product.desc}</p>
            
            <div class="qty-selector">
                <button class="qty-btn" id="detail-minus">-</button>
                <div class="qty-val" id="detail-qty">1</div>
                <button class="qty-btn" id="detail-plus">+</button>
            </div>
            <button class="add-to-cart-btn" id="detail-add-btn" style="width:auto; padding:12px 30px;">Add to Cart</button>
        </div>
    `;

    let itemQty = 1;
    const qtyValEl = document.getElementById('detail-qty');

    document.getElementById('detail-plus').addEventListener('click', () => {
        itemQty++;
        qtyValEl.innerText = itemQty;
    });

    document.getElementById('detail-minus').addEventListener('click', () => {
        if(itemQty > 1) {
            itemQty--;
            qtyValEl.innerText = itemQty;
        }
    });

    document.getElementById('detail-add-btn').addEventListener('click', () => {
        addToCart(product.id, itemQty);
    });

    showPage('product-page');
}

// Core Cart State Mutation Core logic
function addToCart(productId, quantity) {
    const product = mockProducts.find(p => p.id == productId);
    const existing = cart.find(item => item.product.id == productId);

    if (existing) {
        existing.quantity += quantity;
    } else {
        cart.push({ product, quantity });
    }
    updateCartBadge();
    alert(`${quantity}x ${product.name} successfully appended to cart calculations.`);
}

function updateCartBadge() {
    const totalCount = cart.reduce((acc, item) => acc + item.quantity, 0);
    document.getElementById('cart-count').innerText = totalCount;
}

// 4th Page Generator: Evaluates lists, mutations, totals
function renderCart() {
    const container = document.getElementById('cart-items-container');
    const totalEl = document.getElementById('cart-total-amount');
    container.innerHTML = '';

    if (cart.length === 0) {
        container.innerHTML = `<p style="text-align:center; width:100%; padding:40px 0; font-size:18px; color:#888;">Your cart list elements are currently empty.</p>`;
        totalEl.innerText = "₹0";
        return;
    }

    let runningTotal = 0;

    cart.forEach((item, index) => {
        const rowTotal = item.product.price * item.quantity;
        runningTotal += rowTotal;

        const row = document.createElement('div');
        row.className = 'cart-item-row';
        row.innerHTML = `
            <img src="${item.product.image}" alt="${item.product.name}">
            <div class="cart-item-details">
                <h3>${item.product.name}</h3>
                <div class="cart-item-price">₹${item.product.price}</div>
            </div>
            <div class="qty-selector">
                <button class="qty-btn cart-qty-minus" data-idx="${index}">-</button>
                <div class="qty-val">${item.quantity}</div>
                <button class="qty-btn cart-qty-plus" data-idx="${index}">+</button>
            </div>
            <button class="remove-btn" data-idx="${index}">Remove</button>
        `;
        container.appendChild(row);
    });

    totalEl.innerText = `₹${runningTotal}`;

    // Cart Interactivity Hooks
    container.querySelectorAll('.cart-qty-plus').forEach(btn => {
        btn.addEventListener('click', () => {
            const idx = btn.getAttribute('data-idx');
            cart[idx].quantity++;
            updateCartBadge();
            renderCart();
        });
    });

    container.querySelectorAll('.cart-qty-minus').forEach(btn => {
        btn.addEventListener('click', () => {
            const idx = btn.getAttribute('data-idx');
            if (cart[idx].quantity > 1) {
                cart[idx].quantity--;
            } else {
                cart.splice(idx, 1);
            }
            updateCartBadge();
            renderCart();
        });
    });

    container.querySelectorAll('.remove-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const idx = btn.getAttribute('data-idx');
            cart.splice(idx, 1);
            updateCartBadge();
            renderCart();
        });
    });
}

// Checkouts Handler
document.getElementById('checkout-btn').addEventListener('click', () => {
    if(cart.length === 0) return;
    alert("Order successfully completed! Thank you for purchasing from viper.in!");
    cart = [];
    updateCartBadge();
    showPage('home-page');
});