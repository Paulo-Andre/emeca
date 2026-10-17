(() => {
  "use strict";

  const menuButton = document.querySelector(".mobile-menu-button");
  const nav = document.getElementById("menu-principal");
  const more = document.querySelector(".site-nav-more");

  const closeMenu = () => {
    nav?.classList.remove("is-open");
    menuButton?.setAttribute("aria-expanded", "false");
  };

  menuButton?.addEventListener("click", () => {
    const aberto = menuButton.getAttribute("aria-expanded") === "true";
    menuButton.setAttribute("aria-expanded", String(!aberto));
    nav?.classList.toggle("is-open", !aberto);
  });

  nav?.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", closeMenu);
  });

  document.addEventListener("click", (event) => {
    if (more?.open && !more.contains(event.target)) {
      more.removeAttribute("open");
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      more?.removeAttribute("open");
      closeMenu();
    }
  });

  const carousel = document.querySelector("[data-carousel]");
  if (carousel) {
    const slides = [...carousel.querySelectorAll("[data-slide]")];
    const dots = [...carousel.querySelectorAll("[data-carousel-dot]")];
    const prev = carousel.querySelector("[data-carousel-prev]");
    const next = carousel.querySelector("[data-carousel-next]");
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let index = 0;
    let timer = null;
    let touchStartX = 0;

    function show(target) {
      if (!slides.length) return;
      index = (target + slides.length) % slides.length;
      slides.forEach((slide, i) => {
        const active = i === index;
        slide.classList.toggle("is-active", active);
        slide.setAttribute("aria-hidden", active ? "false" : "true");
      });
      dots.forEach((dot, i) => {
        dot.classList.toggle("active", i === index);
        dot.setAttribute("aria-current", i === index ? "true" : "false");
      });
    }

    function stop() {
      if (timer) window.clearInterval(timer);
      timer = null;
    }

    function start() {
      stop();
      if (!reduceMotion && slides.length > 1) {
        timer = window.setInterval(() => show(index + 1), 6500);
      }
    }

    prev?.addEventListener("click", () => { show(index - 1); start(); });
    next?.addEventListener("click", () => { show(index + 1); start(); });
    dots.forEach((dot, i) => dot.addEventListener("click", () => { show(i); start(); }));

    carousel.addEventListener("mouseenter", stop);
    carousel.addEventListener("mouseleave", start);
    carousel.addEventListener("focusin", stop);
    carousel.addEventListener("focusout", start);

    carousel.addEventListener("touchstart", (event) => {
      touchStartX = event.changedTouches[0]?.clientX || 0;
      stop();
    }, { passive: true });

    carousel.addEventListener("touchend", (event) => {
      const endX = event.changedTouches[0]?.clientX || 0;
      const delta = endX - touchStartX;
      if (Math.abs(delta) > 45) {
        show(delta > 0 ? index - 1 : index + 1);
      }
      start();
    }, { passive: true });

    show(0);
    start();
  }


  const cpfInputs = document.querySelectorAll("[data-cpf-mask='true']");

  const formatCpf = (value) => {
    const digits = String(value || "").replace(/\D/g, "").slice(0, 11);
    if (digits.length <= 3) return digits;
    if (digits.length <= 6) return `${digits.slice(0, 3)}.${digits.slice(3)}`;
    if (digits.length <= 9) {
      return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6)}`;
    }
    return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6, 9)}-${digits.slice(9)}`;
  };

  cpfInputs.forEach((input) => {
    const applyMask = () => {
      input.value = formatCpf(input.value);
    };

    input.addEventListener("input", applyMask);
    input.addEventListener("blur", applyMask);
    applyMask();
  });

  if (window.lucide) window.lucide.createIcons();
})();
