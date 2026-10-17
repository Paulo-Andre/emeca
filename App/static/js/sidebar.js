(() => {
  function initSidebar() {
    const sidebar = document.querySelector(".sidebar");
    const button = sidebar?.querySelector(".sidebar-toggle");
    if (!sidebar || !button) return;

    const key = "emeca-sidebar-collapsed";

    const apply = (collapsed) => {
      sidebar.classList.toggle("is-collapsed", collapsed);
      button.setAttribute("aria-expanded", collapsed ? "false" : "true");
      button.setAttribute("aria-label", collapsed ? "Expandir menu" : "Recolher menu");
      button.title = collapsed ? "Expandir menu" : "Recolher menu";

      const current = button.querySelector("[data-lucide], svg");
      if (current) {
        const name = collapsed ? "panel-left-open" : "panel-left-close";
        if (current.tagName.toLowerCase() === "svg") {
          current.replaceWith(document.createElement("i"));
          const next = button.querySelector("i");
          next.setAttribute("data-lucide", name);
        } else {
          current.setAttribute("data-lucide", name);
        }
      }
      if (window.lucide) window.lucide.createIcons();
    };

    let collapsed = false;
    try {
      collapsed = localStorage.getItem(key) === "1";
    } catch (_) {}
    apply(collapsed);

    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const next = !sidebar.classList.contains("is-collapsed");
      try {
        localStorage.setItem(key, next ? "1" : "0");
      } catch (_) {}
      apply(next);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initSidebar, { once: true });
  } else {
    initSidebar();
  }
})();
