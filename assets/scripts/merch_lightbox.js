// Merch product image lightbox
(function() {
  let currentItemId = null;
  let currentSlideIndex = 0;

  // Initialize lightbox triggers on page load
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-merch-preview-image]').forEach((img) => {
      img.style.cursor = 'pointer';
      img.addEventListener('click', (e) => {
        openLightbox(e.target.closest('fieldset'));
      });
    });
  });

  function openLightbox(fieldset) {
    if (!fieldset) return;

    const productName = fieldset.querySelector('legend')?.textContent || 'Product';
    const variantMap = fieldset.querySelector('[data-merch-variant-map]');
    if (!variantMap) return;

    // Build a map of unique images keyed by URL
    const imageMap = new Map(); // url -> { url, colors: [] }
    
    variantMap.querySelectorAll('span').forEach((span) => {
      const imageUrl = span.getAttribute('data-image-url');
      const color = span.getAttribute('data-color');
      if (imageUrl) {
        if (!imageMap.has(imageUrl)) {
          imageMap.set(imageUrl, { url: imageUrl, colors: [] });
        }
        if (color && !imageMap.get(imageUrl).colors.includes(color)) {
          imageMap.get(imageUrl).colors.push(color);
        }
      }
    });

    // Convert map to array and create labels with product name and color(s)
    const images = Array.from(imageMap.values()).map(img => ({
      url: img.url,
      label: img.colors.length > 0 
        ? `${productName} - ${img.colors.join(', ')}`
        : productName
    }));

    if (images.length === 0) return;

    currentItemId = productName;
    currentSlideIndex = 0;

    showLightboxModal(images);
  }

  function showLightboxModal(images) {
    // Remove existing modal if any
    const existingModal = document.getElementById('merch-lightbox-modal');
    if (existingModal) {
      existingModal.remove();
    }

    const modal = document.createElement('div');
    modal.id = 'merch-lightbox-modal';
    modal.className = 'merch-lightbox-modal';
    modal.innerHTML = `
      <div class="merch-lightbox-content">
        <button class="merch-lightbox-close" aria-label="Close">&times;</button>
        <div class="merch-lightbox-image-container">
          ${images.map((img, idx) => `
            <div class="merch-lightbox-slide" style="display: ${idx === 0 ? 'flex' : 'none'};">
              <img src="${img.url}" alt="${img.label}">
              <p class="merch-lightbox-caption">${img.label}</p>
            </div>
          `).join('')}
        </div>
        <div class="merch-lightbox-controls">
          <button class="merch-lightbox-nav merch-lightbox-prev" aria-label="Previous image">&#10094;</button>
          <span class="merch-lightbox-counter"><span class="merch-lightbox-current">1</span> / ${images.length}</span>
          <button class="merch-lightbox-nav merch-lightbox-next" aria-label="Next image">&#10095;</button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    // Event listeners
    modal.querySelector('.merch-lightbox-close').addEventListener('click', closeLightbox);
    modal.querySelector('.merch-lightbox-prev').addEventListener('click', () => navigateSlide(-1, images.length));
    modal.querySelector('.merch-lightbox-next').addEventListener('click', () => navigateSlide(1, images.length));

    // Close on background click
    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        closeLightbox();
      }
    });

    // Keyboard navigation
    document.addEventListener('keydown', handleKeydown);

    modal.style.display = 'flex';
  }

  function navigateSlide(direction, totalImages) {
    currentSlideIndex = (currentSlideIndex + direction + totalImages) % totalImages;
    updateSlide();
  }

  function updateSlide() {
    const modal = document.getElementById('merch-lightbox-modal');
    if (!modal) return;

    const slides = modal.querySelectorAll('.merch-lightbox-slide');
    slides.forEach((slide, idx) => {
      slide.style.display = idx === currentSlideIndex ? 'flex' : 'none';
    });

    modal.querySelector('.merch-lightbox-current').textContent = currentSlideIndex + 1;
  }

  function closeLightbox() {
    const modal = document.getElementById('merch-lightbox-modal');
    if (modal) {
      modal.remove();
      document.removeEventListener('keydown', handleKeydown);
    }
  }

  function handleKeydown(e) {
    if (!document.getElementById('merch-lightbox-modal')) return;

    switch (e.key) {
      case 'Escape':
        closeLightbox();
        break;
      case 'ArrowLeft':
        e.preventDefault();
        currentSlideIndex = (currentSlideIndex - 1 + 999) % 999; // Safe modulo
        updateSlide();
        break;
      case 'ArrowRight':
        e.preventDefault();
        currentSlideIndex = (currentSlideIndex + 1) % 999;
        updateSlide();
        break;
    }
  }
})();
